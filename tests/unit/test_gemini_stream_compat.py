_AUTH = {"Authorization": "Bearer sk-test-key"}


def _gemini_body(text="hi"):
    return {"contents": [{"role": "user", "parts": [{"text": text}]}]}


def test_gemini_stream_generate_content_alt_sse(client, monkeypatch):
    import app.routers.gemini as gr

    async def fake_generate_stream(prompt, model, conversation_id="", attachments=None,
                                   gem_id=None, account_id=None):
        yield {"type": "delta", "text": "Hel"}
        yield {"type": "delta", "text": "lo"}
        yield {"type": "final", "text": "Hello", "conversation_id": "", "images": []}

    monkeypatch.setattr(gr.gemini_client, "generate_stream", fake_generate_stream)

    with client.stream(
        "POST",
        "/v1beta/models/gemini-pro:streamGenerateContent?alt=sse",
        json=_gemini_body(),
        headers=_AUTH,
    ) as resp:
        body = "".join(resp.iter_text())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"candidates"' in body
    assert '"finishReason": "STOP"' in body
    assert "\n\n" in body


def test_gemini_stream_generate_content_without_alt_keeps_json_lines(client, monkeypatch):
    import app.routers.gemini as gr

    async def fake_generate_stream(prompt, model, conversation_id="", attachments=None,
                                   gem_id=None, account_id=None):
        yield {"type": "delta", "text": "ok"}
        yield {"type": "final", "text": "ok", "conversation_id": "", "images": []}

    monkeypatch.setattr(gr.gemini_client, "generate_stream", fake_generate_stream)

    with client.stream(
        "POST",
        "/v1beta/models/gemini-pro:streamGenerateContent",
        json=_gemini_body(),
        headers=_AUTH,
    ) as resp:
        body = "".join(resp.iter_text())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert 'data: ' not in body
    assert body.endswith("\n")


def test_gemini_stream_keeps_generated_images(client, monkeypatch):
    import app.routers.gemini as gr

    async def fake_generate_stream(prompt, model, conversation_id="", attachments=None,
                                   gem_id=None, account_id=None):
        yield {"type": "delta", "text": "Here"}
        yield {"type": "final", "text": "Here", "conversation_id": "", "images": [{
            "id": "img-1", "b64": "aGVsbG8=", "mime": "image/png",
        }]}

    monkeypatch.setattr(gr.gemini_client, "generate_stream", fake_generate_stream)

    with client.stream(
        "POST",
        "/v1beta/models/gemini-pro:streamGenerateContent?alt=sse",
        json=_gemini_body("draw a cat"),
        headers=_AUTH,
    ) as resp:
        body = "".join(resp.iter_text())

    assert resp.status_code == 200
    assert "![generated image](" in body
    assert "img-1" in body
    assert "inlineData" in body
