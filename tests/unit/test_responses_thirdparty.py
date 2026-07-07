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
