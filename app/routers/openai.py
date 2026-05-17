import json
import time
import uuid
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.account_pool import account_pool as gemini_client
from app.core.api_forwarder import forward_to_provider
from app.core.conversation_store import conversation_store
from app.core.gemini_client import GEMINI_MODELS, MODEL_ALIASES, _resolve_model
from app.core.stream import split_into_chunks, format_sse
from app.models.openai import (
    ChatRequest, ChatResponse, Choice, ChoiceMessage,
    StreamChunk, StreamChoice, StreamDelta,
    ModelList, ModelInfo, UsageInfo,
)
from app.utils.tools import build_tool_prompt, parse_tool_response, estimate_tokens
from app.utils.prompt import build_prompt_from_messages

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/openai/v1", tags=["OpenAI"])


@router.get("/models")
async def list_models(request: Request):
    models = list(gemini_client.models)
    # Also include models from API key pool
    pool = getattr(request.app.state, 'api_key_pool', None)
    if pool:
        for entry in pool.entries.values():
            if entry.status == 'active' and entry.model not in models:
                models.append(entry.model)
    now = int(time.time())
    data = [ModelInfo(id=m, created=now) for m in models]
    return ModelList(data=data)


@router.post("/chat/completions")
async def chat_completions(req: ChatRequest, request: Request):
    model_mapping = request.app.state.model_mapping
    resolved_model = model_mapping.resolve(req.model)

    if resolved_model not in gemini_client.models and _resolve_model(resolved_model) not in GEMINI_MODELS:
        pool = getattr(request.app.state, 'api_key_pool', None)
        if pool:
            entry = pool.get_key_for_model(resolved_model)
            if entry:
                messages_raw = [m.model_dump() for m in req.messages]
                result = await forward_to_provider(entry, messages_raw, req)
                pool.update_last_used(entry.id)
                return result

    messages_raw = [m.model_dump() for m in req.messages]

    # 对话上下文持久化：检查是否有 conversation_id
    gemini_conv_id = ""
    conv = None
    if req.conversation_id:
        conv = await conversation_store.get(req.conversation_id)
        if conv and conv.gemini_conv_id:
            gemini_conv_id = conv.gemini_conv_id

    # 如果有有效的 gemini_conv_id，只发最新一条用户消息
    if gemini_conv_id and messages_raw:
        last_user_msg = ""
        for msg in reversed(messages_raw):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
                last_user_msg = content
                break
        prompt = last_user_msg if last_user_msg else build_prompt_from_messages(messages_raw)
    else:
        prompt = build_prompt_from_messages(messages_raw)

    has_tools = bool(req.tools)
    if has_tools:
        tools_raw = [t.model_dump() for t in req.tools]
        prompt = build_tool_prompt(prompt, tools_raw, req.tool_choice)

    if req.stream:
        return StreamingResponse(
            _stream_response(prompt, resolved_model, has_tools, gemini_conv_id, conv, messages_raw, req.model),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        result = await gemini_client.generate(prompt, resolved_model, gemini_conv_id)
    except (RuntimeError, ValueError) as e:
        # Fallback: 如果 conversation_id 过期，用完整 prompt 重试
        if gemini_conv_id:
            prompt = build_prompt_from_messages(messages_raw)
            if has_tools:
                tools_raw = [t.model_dump() for t in req.tools]
                prompt = build_tool_prompt(prompt, tools_raw, req.tool_choice)
            try:
                result = await gemini_client.generate(prompt, resolved_model)
                gemini_conv_id = ""
            except Exception:
                return JSONResponse(
                    status_code=500,
                    content={"error": {"message": str(e), "type": "api_error"}},
                )
        else:
            return JSONResponse(
                status_code=500 if "retry" in str(e).lower() else 400,
                content={"error": {"message": str(e), "type": "api_error"}},
            )

    text = result.get("text", "")
    new_conv_id = result.get("conversation_id", "")
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    # 持久化对话
    if new_conv_id:
        if not conv:
            conv_store_id = req.conversation_id or completion_id
            conv = await conversation_store.create(conv_store_id, resolved_model)
        conv.gemini_conv_id = new_conv_id
        last_user = messages_raw[-1].get("content", "") if messages_raw else ""
        if isinstance(last_user, list):
            last_user = str(last_user)
        conv.add_message("user", last_user)
        conv.add_message("assistant", text)
        await conversation_store.update(conv)

    if has_tools:
        parsed = parse_tool_response(text)
        if parsed["type"] == "tool_calls":
            tool_calls = []
            for i, tc in enumerate(parsed["tool_calls"]):
                call_id = f"call_{uuid.uuid4().hex[:8]}"
                tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments", {})),
                    },
                })
            return ChatResponse(
                id=completion_id,
                model=req.model,
                choices=[Choice(
                    message=ChoiceMessage(role="assistant", tool_calls=tool_calls),
                    finish_reason="tool_calls",
                )],
                usage=UsageInfo(
                    prompt_tokens=estimate_tokens(prompt),
                    completion_tokens=estimate_tokens(text),
                    total_tokens=estimate_tokens(prompt) + estimate_tokens(text),
                ),
                conversation_id=conv.id if conv else None,
            )
        text = parsed.get("content", text)

    return ChatResponse(
        id=completion_id,
        model=req.model,
        choices=[Choice(
            message=ChoiceMessage(role="assistant", content=text),
            finish_reason="stop",
        )],
        usage=UsageInfo(
            prompt_tokens=estimate_tokens(prompt),
            completion_tokens=estimate_tokens(text),
            total_tokens=estimate_tokens(prompt) + estimate_tokens(text),
        ),
        conversation_id=conv.id if conv else None,
    )


async def _stream_response(prompt: str, model: str, has_tools: bool, gemini_conv_id: str = "", conv=None, messages_raw=None, display_model: str = "") -> AsyncGenerator[str, None]:
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    model_name = display_model or model

    try:
        result = await gemini_client.generate(prompt, model, gemini_conv_id)
    except Exception as e:
        if gemini_conv_id and messages_raw:
            full_prompt = build_prompt_from_messages(messages_raw)
            try:
                result = await gemini_client.generate(full_prompt, model)
            except Exception as e2:
                error_chunk = StreamChunk(
                    id=completion_id,
                    model=model_name,
                    choices=[StreamChoice(delta=StreamDelta(content=f"Error: {e2}"), finish_reason="stop")],
                )
                yield format_sse(error_chunk.model_dump())
                yield "data: [DONE]\n\n"
                return
        else:
            error_chunk = StreamChunk(
                id=completion_id,
                model=model_name,
                choices=[StreamChoice(delta=StreamDelta(content=f"Error: {e}"), finish_reason="stop")],
            )
            yield format_sse(error_chunk.model_dump())
            yield "data: [DONE]\n\n"
            return

    text = result.get("text", "")
    new_conv_id = result.get("conversation_id", "")

    if new_conv_id and conv:
        conv.gemini_conv_id = new_conv_id
        conv.add_message("assistant", text)
        await conversation_store.update(conv)

    if has_tools:
        parsed = parse_tool_response(text)
        if parsed["type"] == "tool_calls":
            for tc in parsed["tool_calls"]:
                call_id = f"call_{uuid.uuid4().hex[:8]}"
                tool_call_data = {
                    "id": call_id,
                    "type": "function",
          "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments", {})),
                    },
                }
                chunk = StreamChunk(
                    id=completion_id,
                    model=model_name,
                    choices=[StreamChoice(delta=StreamDelta(tool_calls=[tool_call_data]))],
                )
                yield format_sse(chunk.model_dump())

            final = StreamChunk(
                id=completion_id,
                model=model_name,
                choices=[StreamChoice(delta=StreamDelta(), finish_reason="tool_calls")],
            )
            yield format_sse(final.model_dump())
            yield "data: [DONE]\n\n"
            return
        text = parsed.get("content", text)

    first = StreamChunk(
        id=completion_id,
        model=model_name,
        choices=[StreamChoice(delta=StreamDelta(role="assistant"))],
    )
    yield format_sse(first.model_dump())

    async for word in split_into_chunks(text):
        chunk = StreamChunk(
            id=completion_id,
            model=model_name,
            choices=[StreamChoice(delta=StreamDelta(content=word))],
        )
        yield format_sse(chunk.model_dump())

    done_chunk = StreamChunk(
        id=completion_id,
        model=model_name,
        choices=[StreamChoice(delta=StreamDelta(), finish_reason="stop")],
    )
    yield format_sse(done_chunk.model_dump())
    yield "data: [DONE]\n\n"
