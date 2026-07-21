import asyncio
import json
import time

import pytest

httpx = pytest.importorskip("httpx", reason="httpx not installed (runtime dependency)")

from app.core.account_pool import AccountPool, _is_cooldown_error, _is_retryable
from app.core.gemini_client import HTTPStatusError
from app.core.gemini_oauth_client import GeminiOAuthClient


def _client(handler, **kwargs):
    client = GeminiOAuthClient(
        access_token=kwargs.pop("access_token", "ya29.access"),
        project_id=kwargs.pop("project_id", "project-1"),
        **kwargs,
    )
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._healthy = True
    return client


def test_code_assist_request_is_wrapped_and_authenticated():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        seen["user_agent"] = request.headers.get("User-Agent")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "response": {
                "candidates": [{"content": {"parts": [{"text": "hello"}]}}]
            }
        })

    async def run():
        client = _client(handler, oauth_type="code_assist")
        try:
            return await client.generate("hi", "gemini-flash")
        finally:
            await client.shutdown()

    result = asyncio.run(run())
    assert seen["url"].endswith("/v1internal:generateContent")
    assert seen["authorization"] == "Bearer ya29.access"
    assert seen["user_agent"].startswith("GeminiCLI/")
    assert seen["body"]["model"] == "gemini-3-flash-preview"
    assert seen["body"]["project"] == "project-1"
    assert seen["body"]["request"]["contents"][0]["parts"][0]["text"] == "hi"
    assert result == {"text": "hello", "images": [], "conversation_id": ""}


def test_ai_studio_oauth_uses_direct_api_shape():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        })

    async def run():
        client = _client(handler, oauth_type="ai_studio", project_id="")
        try:
            return await client.generate("hello", "gemini-pro")
        finally:
            await client.shutdown()

    result = asyncio.run(run())
    assert "/v1beta/models/gemini-3-pro-preview:generateContent" in seen["url"]
    assert "request" not in seen["body"]
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "hello"
    assert result["text"] == "ok"


def test_code_assist_sse_unwraps_response_and_emits_final():
    def handler(request: httpx.Request):
        body = (
            'data: {"response":{"candidates":[{"content":{"parts":[{"text":"hel"}]}}]}}\n\n'
            'data: {"response":{"candidates":[{"content":{"parts":[{"text":"lo"}]}}]}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async def run():
        client = _client(handler, oauth_type="code_assist")
        try:
            return [event async for event in client.generate_stream("hi", "gemini-flash")]
        finally:
            await client.shutdown()

    events = asyncio.run(run())
    assert events[:2] == [
        {"type": "delta", "text": "hel"},
        {"type": "delta", "text": "lo"},
    ]
    assert events[-1]["type"] == "final"
    assert events[-1]["text"] == "hello"


def test_code_assist_sse_diffs_cumulative_frames_without_duplicate_text():
    def handler(request: httpx.Request):
        body = (
            'data: {"response":{"candidates":[{"content":{"parts":[{"text":"hel"}]}}]}}\n\n'
            'data: {"response":{"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async def run():
        client = _client(handler, oauth_type="code_assist")
        try:
            return [event async for event in client.generate_stream("hi", "gemini-flash")]
        finally:
            await client.shutdown()

    events = asyncio.run(run())
    assert events[:2] == [
        {"type": "delta", "text": "hel"},
        {"type": "delta", "text": "lo"},
    ]
    assert events[-1]["text"] == "hello"


def test_code_assist_sse_rejects_malformed_only_stream():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            text="data: not-json\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    async def run():
        client = _client(handler, oauth_type="code_assist")
        try:
            return [event async for event in client.generate_stream("hi", "gemini-flash")]
        finally:
            await client.shutdown()

    with pytest.raises(RuntimeError, match="not ready"):
        asyncio.run(run())


def test_refresh_token_is_singleflight():
    calls = 0
    updates = []

    async def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={"access_token": "new-token", "expires_in": 3600})

    async def run():
        client = GeminiOAuthClient(
            access_token="expired",
            refresh_token="refresh",
            expires_at=time.time() - 10,
            project_id="project-1",
            token_update=lambda access, refresh, expires: updates.append((access, refresh, expires)),
        )
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return await asyncio.gather(*(client._get_access_token() for _ in range(8)))
        finally:
            await client.shutdown()

    tokens = asyncio.run(run())
    assert calls == 1
    assert tokens == ["new-token"] * 8
    assert len(updates) == 1


def test_forced_refresh_after_shared_401_is_singleflight():
    calls = 0

    async def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={"access_token": "new-token", "expires_in": 3600})

    async def run():
        client = GeminiOAuthClient(
            access_token="rejected-token",
            refresh_token="refresh",
            project_id="project-1",
        )
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return await asyncio.gather(*(
                client._get_access_token(force_refresh=True) for _ in range(8)
            ))
        finally:
            await client.shutdown()

    tokens = asyncio.run(run())
    assert calls == 1
    assert tokens == ["new-token"] * 8


def test_code_assist_check_discovers_project_id():
    projects = []

    def handler(request: httpx.Request):
        return httpx.Response(200, json={"cloudaicompanionProject": "auto-project"})

    async def run():
        client = GeminiOAuthClient(
            access_token="ya29.access",
            project_update=projects.append,
        )
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await client.check_account()
            url, body = await client._build_request("hi", "gemini-flash", None, stream=False)
            return result, url, body
        finally:
            await client.shutdown()

    result, _, body = asyncio.run(run())
    assert result["valid"] is True
    assert projects == ["auto-project"]
    assert body["project"] == "auto-project"


def test_web_conversation_id_is_not_silently_sent_to_oauth():
    async def run():
        client = _client(lambda request: httpx.Response(500))
        try:
            with pytest.raises(RuntimeError, match="web conversation id"):
                await client.generate("latest only", "gemini-pro", conversation_id="web-conv")
        finally:
            await client.shutdown()

    asyncio.run(run())


def test_oauth_429_is_retryable_and_uses_account_cooldown():
    error = HTTPStatusError(429, "RESOURCE_EXHAUSTED")
    assert _is_retryable(error) is True
    assert _is_cooldown_error(error) is True


def test_legacy_cookie_json_stays_legacy_after_save(tmp_path, monkeypatch):
    accounts_file = tmp_path / "accounts.json"
    legacy = {
        "accounts": [{
            "id": "account-0",
            "psid": "cookie-value",
            "psidts": "cookie-ts",
            "label": "Legacy",
        }]
    }
    accounts_file.write_text(json.dumps(legacy), encoding="utf-8")

    from app.core import account_pool as account_pool_module

    pool = AccountPool()
    pool._load_from_file(accounts_file)
    monkeypatch.setattr(account_pool_module.settings, "accounts_file", str(accounts_file))
    pool._save_to_file()

    saved = json.loads(accounts_file.read_text(encoding="utf-8"))
    assert saved == legacy
    assert pool.accounts[0].auth_type == "cookie"


def test_mixed_pool_status_never_contains_oauth_secrets(tmp_path):
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(json.dumps({
        "accounts": [
            {"id": "account-0", "psid": "cookie", "psidts": "", "label": "web"},
            {
                "id": "account-1",
                "auth_type": "oauth",
                "oauth_type": "code_assist",
                "access_token": "secret-access",
                "refresh_token": "secret-refresh",
                "project_id": "project-1",
                "label": "cli",
            },
        ]
    }), encoding="utf-8")

    pool = AccountPool()
    pool._load_from_file(accounts_file)
    status = pool.get_status()

    assert [account.auth_type for account in pool.accounts] == ["cookie", "oauth"]
    oauth_status = status["accounts"][1]
    assert oauth_status["auth_type"] == "oauth"
    assert oauth_status["access_token_configured"] is True
    assert oauth_status["refresh_token_configured"] is True
    assert "access_token" not in oauth_status
    assert "refresh_token" not in oauth_status


def test_cli_token_alias_and_millisecond_expiry_are_accepted(tmp_path):
    accounts_file = tmp_path / "accounts.json"
    accounts_file.write_text(json.dumps({
        "accounts": [{
            "id": "account-0",
            "auth_type": "oauth",
            "token": "cli-access",
            "refresh_token": "cli-refresh",
            "expiry_date": 2_000_000_000_000,
            "project_id": "project-1",
        }]
    }), encoding="utf-8")

    pool = AccountPool()
    pool._load_from_file(accounts_file)

    assert pool.accounts[0].access_token == "cli-access"
    assert pool.accounts[0].expires_at == 2_000_000_000
