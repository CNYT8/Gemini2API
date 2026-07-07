import json

_AUTH = {"Authorization": "Bearer sk-test-key"}


def test_responses_non_stream_text_reply(gem_client, monkeypatch):
    import app.routers.responses as rr

    async def fake_generate(prompt, model, conversation_id="", attachments=None,
                            gem_id=None, account_id=None):
        assert model == "gemini-pro"
        return {"text": "Hello human", "conversation_id": "", "images": []}

    monkeypatch.setattr(rr.gemini_client, "generate", fake_generate)
    r = gem_client.post("/v1/responses", json={"model": "gemini-pro", "input": "hi"}, headers=_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["output"][0]["type"] == "message"
    assert body["output"][0]["content"][0]["text"] == "Hello human"


def test_responses_requires_auth(client):
    r = client.post("/v1/responses", json={"model": "gemini-pro", "input": "hi"})
    assert r.status_code in (401, 403)


def test_responses_previous_response_id_rejected(client, monkeypatch):
    import app.routers.responses as rr

    async def fake_generate(*a, **k):
        return {"text": "x", "conversation_id": "", "images": []}
    monkeypatch.setattr(rr.gemini_client, "generate", fake_generate)

    r = client.post("/v1/responses",
                    json={"model": "gemini-pro", "input": "hi", "previous_response_id": "resp_dead"},
                    headers=_AUTH)
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_request_error"


def test_responses_missing_input_is_400(client):
    r = client.post("/v1/responses", json={"model": "gemini-pro"}, headers=_AUTH)
    assert r.status_code == 400


def test_responses_with_tool_call_returns_function_call_item(gem_client, monkeypatch):
    import app.routers.responses as rr

    async def fake_generate(prompt, model, conversation_id="", attachments=None,
                            gem_id=None, account_id=None):
        assert "run_shell" in prompt  # tool description injected into prompt
        return {"text": '{"status":"tool_use","tool_calls":[{"name":"run_shell","arguments":{"cmd":"ls"}}]}',
               "conversation_id": "", "images": []}

    monkeypatch.setattr(rr.gemini_client, "generate", fake_generate)
    r = gem_client.post("/v1/responses", json={
        "model": "gemini-pro", "input": "list files",
        "tools": [{"type": "function", "name": "run_shell", "description": "run a shell cmd",
                  "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}}}],
    }, headers=_AUTH)
    assert r.status_code == 200
    body = r.json()
    item = body["output"][0]
    assert item["type"] == "function_call"
    assert item["name"] == "run_shell"
    assert json.loads(item["arguments"]) == {"cmd": "ls"}


def test_responses_stream_emits_output_text_done_event(gem_client, monkeypatch):
    import app.routers.responses as rr

    async def fake_generate_stream(prompt, model, conversation_id="", attachments=None,
                                   gem_id=None, account_id=None):
        yield {"type": "delta", "text": "Hel"}
        yield {"type": "delta", "text": "lo"}
        yield {"type": "final", "text": "Hello", "conversation_id": "", "images": []}

    monkeypatch.setattr(rr.gemini_client, "generate_stream", fake_generate_stream)
    with gem_client.stream("POST", "/v1/responses",
                       json={"model": "gemini-pro", "input": "hi", "stream": True},
                       headers=_AUTH) as r:
        body = "".join(r.iter_text())
    assert "response.output_text.done" in body
    assert "response.function_call_arguments.done" not in body  # no tools this turn
    assert "response.completed" in body
    assert "[DONE]" not in body


def test_responses_stream_with_tools_buffers_and_emits_function_call_done(gem_client, monkeypatch):
    import app.routers.responses as rr

    async def fake_generate(prompt, model, conversation_id="", attachments=None,
                            gem_id=None, account_id=None):
        return {"text": '{"status":"tool_use","tool_calls":[{"name":"run_shell","arguments":{"cmd":"ls"}}]}',
               "conversation_id": "", "images": []}

    monkeypatch.setattr(rr.gemini_client, "generate", fake_generate)
    with gem_client.stream("POST", "/v1/responses", json={
        "model": "gemini-pro", "input": "list files", "stream": True,
        "tools": [{"type": "function", "name": "run_shell", "description": "d", "parameters": {}}],
    }, headers=_AUTH) as r:
        body = "".join(r.iter_text())
    assert "response.function_call_arguments.done" in body
    assert "response.completed" in body
