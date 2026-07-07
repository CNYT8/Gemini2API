"""OpenAI Responses API（/v1/responses）协议纯函数：input 解析、响应组装、流式事件编码。
无状态，不碰账号池/网络——生成本身仍由 account_pool.generate/generate_stream 完成。"""
import json
import time
import uuid


def _content_part_to_chat_shape(part: dict) -> dict | None:
    """Responses 内容块 -> 内部（chat 兼容）内容块。input_text/output_text -> text；
    input_image -> OpenAI 的 image_url 形状（供 extract_attachments 识别）。"""
    ptype = part.get("type")
    if ptype in ("input_text", "output_text"):
        return {"type": "text", "text": part.get("text", "")}
    if ptype == "input_image":
        url = part.get("image_url")
        if isinstance(url, dict):
            url = url.get("url", "")
        return {"type": "image_url", "image_url": {"url": url}}
    return None


def _message_item_to_internal(item: dict) -> dict:
    role = item.get("role", "user")
    content = item.get("content")
    if isinstance(content, str):
        return {"role": role, "content": content}
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            converted = _content_part_to_chat_shape(part)
            if converted:
                parts.append(converted)
        return {"role": role, "content": parts}
    return {"role": role, "content": ""}


def _input_item_to_internal(item: dict) -> dict | None:
    itype = item.get("type")
    if itype in (None, "message"):
        return _message_item_to_internal(item)
    if itype == "function_call":
        name = item.get("name", "")
        arguments = item.get("arguments", "")
        return {"role": "assistant",
                "content": f"(called tool {name} with arguments {arguments})"}
    if itype in ("function_call_output", "tool_result"):
        output = item.get("output", item.get("content", ""))
        return {"role": "tool", "content": output}
    return None


def parse_responses_input(input_data, instructions: str | None = None) -> list[dict]:
    messages: list[dict] = []
    if instructions:
        messages.append({"role": "system", "content": instructions})

    if isinstance(input_data, str):
        messages.append({"role": "user", "content": input_data})
        return messages

    items = input_data if isinstance(input_data, list) else [input_data]
    for item in items:
        if not isinstance(item, dict):
            continue
        converted = _input_item_to_internal(item)
        if converted:
            messages.append(converted)
    return messages


def new_response_id() -> str:
    return f"resp_{uuid.uuid4().hex}"


def _nested_usage(usage: dict | None) -> dict:
    usage = usage or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": usage.get("cached_tokens", 0)},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": usage.get("reasoning_tokens", 0)},
        "total_tokens": input_tokens + output_tokens,
    }


_ECHO_KEYS = ("tools", "tool_choice", "temperature", "top_p", "max_output_tokens",
              "store", "truncation", "parallel_tool_calls")


def build_responses_object(*, model: str, status: str, output: list[dict],
                           request_params: dict, usage: dict | None = None,
                           previous_response_id: str | None = None,
                           instructions: str | None = None,
                           error: dict | None = None) -> dict:
    obj = {
        "id": new_response_id(),
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "model": model,
        "output": output,
        "usage": _nested_usage(usage),
        "previous_response_id": previous_response_id,
        "instructions": instructions,
        "error": error,
    }
    for key in _ECHO_KEYS:
        if key in request_params:
            obj[key] = request_params[key]
    return obj
