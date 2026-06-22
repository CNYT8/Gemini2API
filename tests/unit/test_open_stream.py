"""OpenAI 兼容流式 pre-flight：开口前据上游状态决定提交或换家（用 MockTransport，不触网）。"""

import asyncio
import httpx
from fastapi.responses import StreamingResponse, JSONResponse

import app.core.api_forwarder as fwd


class _Entry:
    def __init__(self, model="deepseek", provider="openai",
                 base_url="https://up.example/v1", api_key="sk-x"):
        self.id = model
        self.model = model
        self.provider = provider
        self.base_url = base_url
        self.api_key = api_key


class _Req:
    stream = True
    temperature = None
    max_tokens = None
    tools = None
    tool_choice = None


def _patch_transport(monkeypatch, handler):
    def _factory(timeout=300.0):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)
    monkeypatch.setattr(fwd, "_make_async_client", _factory)
    # Bypass SSRF guard so mock URLs (e.g. https://up.example/v1) pass validation
    monkeypatch.setattr(fwd, "_build_safe_target_url",
                        lambda entry, suffix: f"{entry.base_url.rstrip('/')}{suffix}")


async def _drain(stream_resp):
    chunks = []
    async for c in stream_resp.body_iterator:
        chunks.append(c if isinstance(c, str) else c.decode())
    return "".join(chunks)


def test_open_stream_commits_on_200(monkeypatch):
    def handler(request):
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n')
    _patch_transport(monkeypatch, handler)

    async def _run():
        stream_resp, err = await fwd.open_openai_stream(_Entry(), [{"role": "user", "content": "x"}], _Req())
        assert err is None
        assert isinstance(stream_resp, StreamingResponse)
        body = await _drain(stream_resp)
        assert '"content":"hi"' in body
        assert "[DONE]" in body
    asyncio.run(_run())


def test_open_stream_fails_over_on_429(monkeypatch):
    def handler(request):
        return httpx.Response(429, json={"error": {"message": "insufficient_quota"}})
    _patch_transport(monkeypatch, handler)

    async def _run():
        stream_resp, err = await fwd.open_openai_stream(_Entry(), [{"role": "user", "content": "x"}], _Req())
        assert stream_resp is None
        assert isinstance(err, JSONResponse) and err.status_code == 429
    asyncio.run(_run())


def test_open_stream_connection_error_returns_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom")
    _patch_transport(monkeypatch, handler)

    async def _run():
        stream_resp, err = await fwd.open_openai_stream(_Entry(), [{"role": "user", "content": "x"}], _Req())
        assert stream_resp is None
        assert isinstance(err, JSONResponse) and err.status_code == 502
    asyncio.run(_run())


def test_open_stream_dispatch_anthropic_commits_without_preflight(monkeypatch):
    sentinel = StreamingResponse(iter([b"x"]), media_type="text/event-stream")

    async def fake_forward(entry, messages, req):
        return sentinel
    monkeypatch.setattr(fwd, "forward_to_provider", fake_forward)

    async def _run():
        stream_resp, err = await fwd.open_stream(_Entry(provider="anthropic"), [{"role": "user", "content": "x"}], _Req())
        assert err is None
        assert stream_resp is sentinel
    asyncio.run(_run())
