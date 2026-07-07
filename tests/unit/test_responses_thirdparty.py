_AUTH = {"Authorization": "Bearer sk-test-key"}


class _FakeEntry:
    id = "e1"
    model = "deepseek-chat"
    provider = "openai"


class _FakePool:
    def __init__(self, entries):
        self._entries = entries
        self.marked_unhealthy = []
        self.last_used = []
    def get_entries_for_model(self, model):
        return self._entries if model == "deepseek-chat" else []
    def mark_unhealthy(self, entry_id, cooldown):
        self.marked_unhealthy.append(entry_id)
    def update_last_used(self, entry_id):
        self.last_used.append(entry_id)


def test_no_candidates_returns_none(monkeypatch):
    import app.core.responses_thirdparty as rt

    class _Req:
        app = type("A", (), {"state": type("S", (), {"api_key_pool": _FakePool([])})()})()

    import asyncio
    result = asyncio.run(rt.dispatch_thirdparty_responses(
        _Req(), "unknown-model", [{"role": "user", "content": "hi"}], [], None, False, {},
    ))
    assert result is None


def test_non_stream_dispatch_converts_chat_response_to_responses_object(monkeypatch):
    import app.core.responses_thirdparty as rt
    from fastapi.responses import JSONResponse
    import json as _json

    chat_body = {
        "id": "chatcmpl-x", "choices": [
            {"message": {"role": "assistant", "content": "Bonjour"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }

    async def fake_forward(entry, messages, req):
        return JSONResponse(content=chat_body)

    monkeypatch.setattr(rt, "forward_to_provider", fake_forward)

    class _Req:
        app = type("A", (), {"state": type("S", (), {"api_key_pool": _FakePool([_FakeEntry()])})()})()

    import asyncio
    result = asyncio.run(rt.dispatch_thirdparty_responses(
        _Req(), "deepseek-chat", [{"role": "user", "content": "say hi in french"}],
        [], None, False, {"store": True},
    ))
    assert isinstance(result, JSONResponse)
    body = _json.loads(result.body)
    assert body["object"] == "response"
    assert body["output"][0]["type"] == "message"
    assert body["output"][0]["content"][0]["text"] == "Bonjour"
    assert body["store"] is True


def test_non_stream_dispatch_fails_over_when_first_candidate_body_is_empty(monkeypatch):
    """第一家 200 但 body 为空内容（无 content/tool_calls）—— 视为失败，切到第二家，
    而不是把空结果当成功直接返回。"""
    import app.core.responses_thirdparty as rt
    from fastapi.responses import JSONResponse

    empty_chat_body = {
        "id": "chatcmpl-empty",
        "choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}],
    }
    good_chat_body = {
        "id": "chatcmpl-good",
        "choices": [{"message": {"role": "assistant", "content": "Bonjour"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }

    calls = []

    async def fake_forward(entry, messages, req):
        calls.append(entry.id)
        if entry.id == "e1":
            return JSONResponse(content=empty_chat_body)
        return JSONResponse(content=good_chat_body)

    monkeypatch.setattr(rt, "forward_to_provider", fake_forward)

    class _FakeEntry2:
        id = "e2"
        model = "deepseek-chat"
        provider = "openai"

    pool = _FakePool([_FakeEntry(), _FakeEntry2()])

    class _Req:
        app = type("A", (), {"state": type("S", (), {"api_key_pool": pool})()})()

    import asyncio
    result = asyncio.run(rt.dispatch_thirdparty_responses(
        _Req(), "deepseek-chat", [{"role": "user", "content": "say hi in french"}],
        [], None, False, {},
    ))
    assert isinstance(result, JSONResponse)
    import json as _json
    body = _json.loads(result.body)
    assert body["output"][0]["content"][0]["text"] == "Bonjour"
    assert calls == ["e1", "e2"]
    assert pool.marked_unhealthy == ["e1"]
    assert pool.last_used == ["e2"]


def test_non_stream_dispatch_forwards_temperature_and_max_tokens(monkeypatch):
    import app.core.responses_thirdparty as rt
    from fastapi.responses import JSONResponse

    chat_body = {
        "id": "chatcmpl-x",
        "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
    }

    captured = {}

    async def fake_forward(entry, messages, req):
        captured["req"] = req
        return JSONResponse(content=chat_body)

    monkeypatch.setattr(rt, "forward_to_provider", fake_forward)

    class _Req:
        app = type("A", (), {"state": type("S", (), {"api_key_pool": _FakePool([_FakeEntry()])})()})()

    import asyncio
    result = asyncio.run(rt.dispatch_thirdparty_responses(
        _Req(), "deepseek-chat", [{"role": "user", "content": "hi"}],
        [], None, False, {"temperature": 0.3, "max_output_tokens": 500},
    ))
    assert isinstance(result, JSONResponse)
    req = captured["req"]
    assert req.temperature == 0.3
    assert req.max_tokens == 500


def test_stream_dispatch_converts_provider_sse_to_responses_events(monkeypatch):
    import app.core.responses_thirdparty as rt
    from fastapi.responses import StreamingResponse
    import asyncio

    async def _fake_body():
        yield 'data: {"choices":[{"delta":{"content":"Bon"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"jour"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        yield "data: [DONE]\n\n"

    async def fake_open_stream(entry, messages, req):
        return StreamingResponse(_fake_body(), media_type="text/event-stream"), None

    class _FakeEntry:
        id = "e1"

    class _FakePool:
        def update_last_used(self, entry_id):
            pass
        def mark_unhealthy(self, entry_id, cooldown):
            pass

    # patch the module-level open_stream reference used inside responses_thirdparty
    # (setattr on the rt module, so pytest's monkeypatch auto-restores after the test)
    monkeypatch.setattr(rt, "open_stream", fake_open_stream)

    async def _collect():
        gen = rt._dispatch_stream(
            request=None, resolved_model="deepseek-chat",
            messages_raw=[{"role": "user", "content": "hi"}], tools_raw=[], tool_choice=None,
            request_params={}, entries=[_FakeEntry()], pool=_FakePool(),
        )
        out = []
        async for frame in gen:
            out.append(frame)
        return out

    frames = asyncio.run(_collect())
    body = "".join(frames)
    assert "response.output_text.delta" in body
    assert "response.output_text.done" in body
    assert "response.completed" in body
    assert "[DONE]" not in body
