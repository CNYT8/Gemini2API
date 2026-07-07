"""OpenAI Responses API（POST /responses）。挂载见 app/main.py（/v1、/openai/v1 前缀）。
Gemini 路径复用 account_pool + 现有工具模拟机制；第三方模型见 responses_thirdparty.py。"""
import json
import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.account_pool import account_pool as gemini_client
from app.core.gemini_client import GEMINI_MODELS, _resolve_model
from app.core.responses_protocol import (
    parse_responses_input, build_responses_object, new_response_id, ResponsesStreamEncoder,
)
from app.utils.tools import build_tool_prompt, parse_tool_response, estimate_tokens
from app.utils.prompt import build_prompt_from_messages, extract_attachments

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Responses"])


def _error(status: int, message: str, error_type: str = "invalid_request_error",
          param: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "error": {"message": message, "type": error_type, "param": param, "code": None},
    })


def _request_params(body: dict) -> dict:
    params = {}
    for key in ("tools", "tool_choice", "temperature", "top_p", "max_output_tokens",
               "store", "truncation", "parallel_tool_calls"):
        if key in body and body[key] is not None:
            params[key] = body[key]
    return params


def _normalize_tool_choice_for_prompt(tool_choice):
    """Responses 的 tool_choice 指定工具用扁平形状 {"type":"function","name":"x"}；
    build_tool_prompt 期望嵌套形状 {"type":"function","function":{"name":"x"}}。"""
    if isinstance(tool_choice, dict) and "function" not in tool_choice and "name" in tool_choice:
        return {"type": tool_choice.get("type", "function"),
               "function": {"name": tool_choice["name"]}}
    return tool_choice


def _build_output_items(text: str, has_tools: bool) -> tuple[list[dict], str]:
    """把模型原始回复文本组装成 Responses output 数组。返回 (output_items, 剩余文本估算用)。"""
    output = []
    if has_tools:
        parsed = parse_tool_response(text)
        if parsed["type"] == "tool_calls":
            for tc in parsed["tool_calls"]:
                output.append({
                    "id": f"fc_{uuid.uuid4().hex}", "type": "function_call", "status": "completed",
                    "call_id": f"call_{uuid.uuid4().hex[:24]}", "name": tc["name"],
                    "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False),
                })
            return output, ""
        text = parsed.get("content", text)
    output.append({
        "id": f"msg_{uuid.uuid4().hex}", "type": "message", "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    })
    return output, text


@router.post("/responses")
async def create_response(request: Request):
    body = await request.json()
    model = body.get("model", "")
    input_data = body.get("input")
    instructions = body.get("instructions")
    stream = bool(body.get("stream", False))
    tools_raw = body.get("tools") or []
    tool_choice = _normalize_tool_choice_for_prompt(body.get("tool_choice"))
    previous_response_id = body.get("previous_response_id")

    if previous_response_id:
        return _error(400, "previous_response_id is not supported by this server "
                          "(no server-side conversation state); resend full history in 'input'.",
                     param="previous_response_id")

    if input_data is None or (isinstance(input_data, (list, str)) and len(input_data) == 0):
        return _error(400, "input must contain at least one message", param="input")

    messages_raw = parse_responses_input(input_data, instructions)
    if not any(m.get("role") == "user" for m in messages_raw):
        return _error(400, "input must contain at least one user message", param="input")

    model_mapping = request.app.state.model_mapping
    resolved_model = model_mapping.resolve(model)
    gem_mapping = getattr(request.app.state, "gem_mapping", None)
    gem_id = None
    gem_account_id = None
    if gem_mapping:
        gem_info = gem_mapping.resolve(resolved_model)
        if gem_info:
            gem_id = gem_info.get("gem_id")
            gem_account_id = gem_info.get("account_id") or None
            resolved_model = gem_info.get("base_model") or "gemini-pro"

    request_params = _request_params(body)

    if resolved_model not in gemini_client.models and _resolve_model(resolved_model) not in GEMINI_MODELS:
        from app.core.responses_thirdparty import dispatch_thirdparty_responses
        result = await dispatch_thirdparty_responses(
            request, resolved_model, messages_raw, tools_raw, tool_choice, stream, request_params,
        )
        if result is not None:
            return result
        return _error(400, f"Model '{model}' is not a Gemini model and has no third-party "
                          f"entry configured", param="model")

    prompt = build_prompt_from_messages(messages_raw)
    has_tools = bool(tools_raw)
    if has_tools:
        prompt = build_tool_prompt(prompt, tools_raw, tool_choice)
    attachments = extract_attachments(messages_raw)

    if stream:
        return StreamingResponse(
            _stream_gemini_response(prompt, resolved_model, has_tools, attachments,
                                    gem_id, gem_account_id, request_params),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        result = await gemini_client.generate(prompt, resolved_model, "", attachments,
                                              gem_id=gem_id, account_id=gem_account_id)
    except Exception as e:
        return _error(502, str(e), error_type="api_error")

    text = result.get("text", "")
    output, _ = _build_output_items(text, has_tools)
    usage = {"input_tokens": estimate_tokens(prompt), "output_tokens": estimate_tokens(text)}
    obj = build_responses_object(model=resolved_model, status="completed", output=output,
                                 request_params=request_params, usage=usage,
                                 instructions=instructions)
    return JSONResponse(content=obj)


async def _stream_gemini_response(prompt, model, has_tools, attachments, gem_id, gem_account_id,
                                  request_params):
    raise NotImplementedError("implemented in Task 5")
    yield  # pragma: no cover — 让函数保持 async generator 类型，Task 5 替换整个函数体
