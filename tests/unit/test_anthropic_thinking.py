"""Anthropic 思考注入与响应映射(MockTransport/伪响应,不触网)。"""

import asyncio
import json
import httpx
import app.core.api_forwarder as fwd


class _Entry:
    def __init__(self, effort=None):
        self.id = "e"; self.provider = "anthropic"; self.model = "claude"
        self.api_key = "sk"; self.base_url = "https://up.example"
        self.reasoning_effort = effort


class _Req:
    def __init__(self, stream=False):
        self.stream = stream; self.max_tokens = None; self.tools = None; self.temperature = None
        self.tool_choice = None
    messages = None


def _no_ssrf(monkeypatch):
    monkeypatch.setattr(fwd, "_build_safe_target_url", lambda entry, suffix: entry.base_url.rstrip("/") + suffix)


def test_convert_nonstream_maps_thinking():
    out = fwd._convert_anthropic_to_openai(
        {"content": [{"type": "thinking", "thinking": "想"}, {"type": "text", "text": "答"}],
         "stop_reason": "end_turn", "usage": {}}, "claude")
    msg = out["choices"][0]["message"]
    assert msg.get("reasoning_content") == "想"
    assert msg.get("content") == "答"


def test_convert_nonstream_no_thinking_unchanged():
    out = fwd._convert_anthropic_to_openai(
        {"content": [{"type": "text", "text": "答"}], "stop_reason": "end_turn", "usage": {}}, "claude")
    assert "reasoning_content" not in out["choices"][0]["message"]


def test_anthropic_request_injects_thinking(monkeypatch):
    _no_ssrf(monkeypatch)
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}],
                                         "stop_reason": "end_turn", "usage": {}})

    def factory(timeout=300.0):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)
    monkeypatch.setattr(fwd, "_make_async_client", factory)

    req = _Req(stream=False)
    req.messages = [{"role": "user", "content": "x"}]
    asyncio.run(fwd._forward_anthropic(_Entry("high"), req.messages, req))
    body = captured["body"]
    assert body["thinking"] == {"type": "enabled", "budget_tokens": 4096}
    assert body["max_tokens"] > 4096


def test_anthropic_request_numeric_effort(monkeypatch):
    _no_ssrf(monkeypatch)
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}],
                                         "stop_reason": "end_turn", "usage": {}})
    monkeypatch.setattr(fwd, "_make_async_client",
                        lambda timeout=300.0: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout))
    req = _Req(stream=False); req.messages = [{"role": "user", "content": "x"}]
    asyncio.run(fwd._forward_anthropic(_Entry("2048"), req.messages, req))
    assert captured["body"]["thinking"]["budget_tokens"] == 2048


def test_anthropic_request_no_thinking_when_unset(monkeypatch):
    _no_ssrf(monkeypatch)
    captured = {}
    monkeypatch.setattr(fwd, "_make_async_client",
                        lambda timeout=300.0: httpx.AsyncClient(
                            transport=httpx.MockTransport(
                                lambda r: (captured.__setitem__("body", json.loads(r.content)),
                                           httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}],
                                                                     "stop_reason": "end_turn", "usage": {}}))[1]),
                            timeout=timeout))
    req = _Req(stream=False); req.messages = [{"role": "user", "content": "x"}]
    asyncio.run(fwd._forward_anthropic(_Entry(None), req.messages, req))
    assert "thinking" not in captured["body"]


def test_stream_maps_thinking_delta():
    class _Resp:
        async def aiter_lines(self):
            for l in [
                'data: {"type":"message_start"}',
                'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"想"}}',
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"答"}}',
            ]:
                yield l

    async def _run():
        chunks = []
        async for c in fwd._anthropic_stream_to_openai(_Resp(), "claude"):
            chunks.append(c)
        return "".join(chunks)
    out = asyncio.run(_run())
    assert '"reasoning_content": "\\u60f3"' in out or '"reasoning_content": "想"' in out
    assert '"content": "\\u7b54"' in out or '"content": "答"' in out
