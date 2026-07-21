import asyncio

from app.routers import claude as claude_router
from app.routers import openai as openai_router


def test_openai_does_not_emit_assistant_start_for_empty_upstream(monkeypatch):
    async def empty_stream(*args, **kwargs):
        yield {"type": "final", "text": "", "images": [], "conversation_id": ""}

    monkeypatch.setattr(openai_router.gemini_client, "generate_stream", empty_stream)

    async def collect():
        return [chunk async for chunk in openai_router._stream_response("hi", "gemini-pro", False)]

    body = "".join(asyncio.run(collect()))
    assert '"role": "assistant"' not in body
    assert "not ready" in body


def test_claude_emits_error_without_message_start_for_empty_upstream(monkeypatch):
    async def empty_stream(*args, **kwargs):
        yield {"type": "final", "text": "", "images": [], "conversation_id": ""}

    monkeypatch.setattr(claude_router.gemini_client, "generate_stream", empty_stream)

    async def collect():
        return [chunk async for chunk in claude_router._stream_claude("hi", "gemini-pro", False)]

    body = "".join(asyncio.run(collect()))
    assert '"type": "message_start"' not in body
    assert '"type": "error"' in body
