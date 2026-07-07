"""第三方模型（API 管理配置的、非 Gemini）走 /v1/responses 的适配层：
把 Responses 输入转成现有 ChatRequest 格式发给 forward_to_provider/open_stream（零改动复用），
再把返回的 Chat 补全结果转换回 Responses 输出格式。"""
import json

from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.core.api_forwarder import forward_to_provider, open_stream
from app.core.fallback import openai_data_is_empty
from app.models.openai import ChatRequest, ChatMessage, ToolDef, ToolFunction
from app.core.responses_protocol import build_responses_object, new_response_id, ResponsesStreamEncoder


def _to_chat_messages(messages_raw: list[dict]) -> list[ChatMessage]:
    return [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages_raw]


def _to_tool_defs(tools_raw: list[dict]) -> list[ToolDef] | None:
    if not tools_raw:
        return None
    defs = []
    for t in tools_raw:
        func = t.get("function", t)  # 兼容扁平/嵌套两种形状
        defs.append(ToolDef(type="function", function=ToolFunction(
            name=func.get("name", ""), description=func.get("description", ""),
            parameters=func.get("parameters", func.get("input_schema", {})),
        )))
    return defs


def _chat_response_to_responses_object(chat_body: dict, model: str, request_params: dict) -> dict:
    choice = (chat_body.get("choices") or [{}])[0]
    message = choice.get("message", {})
    output = []
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        for tc in tool_calls:
            func = tc.get("function", {})
            output.append({
                "id": f"fc_{tc.get('id', '')}" or "fc_unknown", "type": "function_call",
                "status": "completed", "call_id": tc.get("id", ""), "name": func.get("name", ""),
                "arguments": func.get("arguments", "{}"),
            })
    else:
        text = message.get("content", "") or ""
        output.append({
            "id": f"msg_{chat_body.get('id', 'x')}", "type": "message", "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        })
    usage_raw = chat_body.get("usage", {})
    usage = {"input_tokens": usage_raw.get("prompt_tokens", 0),
            "output_tokens": usage_raw.get("completion_tokens", 0)}
    return build_responses_object(model=model, status="completed", output=output,
                                  request_params=request_params, usage=usage)


async def _dispatch_non_stream(request, resolved_model, messages_raw, tools_raw, tool_choice,
                               request_params, entries, pool):
    chat_req = ChatRequest(model=resolved_model, messages=_to_chat_messages(messages_raw),
                          stream=False, tools=_to_tool_defs(tools_raw), tool_choice=tool_choice,
                          temperature=request_params.get("temperature"),
                          max_tokens=request_params.get("max_output_tokens"))
    cooldown = settings.thirdparty_failover_cooldown
    last_resp = None
    for entry in entries:
        resp = await forward_to_provider(entry, messages_raw, chat_req)
        if isinstance(resp, JSONResponse) and getattr(resp, "status_code", 200) < 400:
            body = resp.body
            if isinstance(body, (bytes, bytearray)):
                body = body.decode("utf-8", "replace")
            try:
                chat_body = json.loads(body)
            except Exception:
                chat_body = None
            if chat_body is not None and not openai_data_is_empty(chat_body):
                pool.update_last_used(entry.id)
                obj = _chat_response_to_responses_object(chat_body, resolved_model, request_params)
                return JSONResponse(content=obj)
        last_resp = resp
        pool.mark_unhealthy(entry.id, cooldown)
    return last_resp  # 全部失败：把最后一个第三方错误响应原样返回


async def dispatch_thirdparty_responses(request, resolved_model, messages_raw, tools_raw,
                                        tool_choice, stream, request_params):
    pool = getattr(request.app.state, "api_key_pool", None)
    if not pool:
        return None
    entries = pool.get_entries_for_model(resolved_model)
    if not entries:
        return None
    if stream:
        return await _dispatch_stream(request, resolved_model, messages_raw, tools_raw,
                                      tool_choice, request_params, entries, pool)
    return await _dispatch_non_stream(request, resolved_model, messages_raw, tools_raw,
                                      tool_choice, request_params, entries, pool)


async def _dispatch_stream(request, resolved_model, messages_raw, tools_raw, tool_choice,
                           request_params, entries, pool):
    chat_req = ChatRequest(model=resolved_model, messages=_to_chat_messages(messages_raw),
                          stream=True, tools=_to_tool_defs(tools_raw), tool_choice=tool_choice,
                          temperature=request_params.get("temperature"),
                          max_tokens=request_params.get("max_output_tokens"))
    response_id = new_response_id()
    enc = ResponsesStreamEncoder(response_id, resolved_model, request_params)
    yield enc.created()
    yield enc.in_progress()

    cooldown = settings.thirdparty_failover_cooldown
    stream_resp = None
    used_entry = None
    for entry in entries:
        resp, err = await open_stream(entry, messages_raw, chat_req)
        if resp is not None:
            stream_resp = resp
            used_entry = entry
            break
        pool.mark_unhealthy(entry.id, cooldown)

    if stream_resp is None:
        yield enc.failed("all third-party candidates failed to open a stream")
        return
    pool.update_last_used(used_entry.id)

    msg_id = f"msg_{new_response_id()}"
    started = False
    full_text = ""
    buf = ""
    async for raw in stream_resp.body_iterator:
        buf += raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
        while "\n\n" in buf:
            frame, buf = buf.split("\n\n", 1)
            line = frame.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                continue
            try:
                chunk = json.loads(payload)
            except Exception:
                continue
            delta = ((chunk.get("choices") or [{}])[0].get("delta") or {})
            text_piece = delta.get("content") or ""
            if text_piece:
                if not started:
                    for frame_out in enc.text_message_start(msg_id, 0):
                        yield frame_out
                    started = True
                full_text += text_piece
                yield enc.text_delta(msg_id, 0, text_piece)

    if not started:
        for frame_out in enc.text_message_start(msg_id, 0):
            yield frame_out
    for frame_out in enc.text_message_end(msg_id, 0, full_text):
        yield frame_out
    output = [{"id": msg_id, "type": "message", "role": "assistant", "status": "completed",
              "content": [{"type": "output_text", "text": full_text, "annotations": []}]}]
    yield enc.completed(output, usage={"input_tokens": 0, "output_tokens": 0})
