import asyncio
import base64
import hashlib
import time
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

httpx = pytest.importorskip("httpx", reason="httpx not installed (runtime dependency)")

from app.core.gemini_oauth_client import GEMINI_CLI_CLIENT_ID
from app.core.gemini_oauth_flow import (
    AI_STUDIO_REDIRECT_URI,
    AI_STUDIO_SCOPES,
    CODE_ASSIST_REDIRECT_URI,
    CODE_ASSIST_SCOPES,
    GeminiOAuthFlow,
    OAuthFlowError,
    OAuthUpstreamError,
)


def test_code_assist_auth_url_uses_builtin_client_and_pkce():
    flow = GeminiOAuthFlow()
    result = flow.create_authorization(oauth_type="code_assist", project_id="project-1")

    parsed = urlparse(result["auth_url"])
    params = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert params["client_id"] == [GEMINI_CLI_CLIENT_ID]
    assert params["redirect_uri"] == [CODE_ASSIST_REDIRECT_URI]
    assert params["scope"] == [CODE_ASSIST_SCOPES]
    assert params["state"] == [result["state"]]
    assert params["project_id"] == ["project-1"]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["code_challenge_method"] == ["S256"]
    assert "client_secret" not in params

    session = flow._sessions._sessions[result["session_id"]]
    digest = hashlib.sha256(session.code_verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert params["code_challenge"] == [expected_challenge]
    assert session.client_secret not in repr(session)


def test_ai_studio_browser_auth_requires_custom_client():
    flow = GeminiOAuthFlow()
    with pytest.raises(OAuthFlowError, match="requires a custom OAuth Client"):
        flow.create_authorization(oauth_type="ai_studio")
    with pytest.raises(OAuthFlowError, match="configured together"):
        flow.create_authorization(oauth_type="ai_studio", client_id="client-only")

    result = flow.create_authorization(
        oauth_type="ai_studio",
        client_id="custom-client",
        client_secret="custom-secret",
    )
    params = parse_qs(urlparse(result["auth_url"]).query)
    assert params["client_id"] == ["custom-client"]
    assert params["redirect_uri"] == [AI_STUDIO_REDIRECT_URI]
    assert params["scope"] == [AI_STUDIO_SCOPES]
    assert "client_secret" not in params


def test_exchange_accepts_callback_url_and_consumes_session_once():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["form"] = parse_qs(request.content.decode("utf-8"))
        return httpx.Response(200, json={
            "access_token": "ya29.access",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": CODE_ASSIST_SCOPES,
        })

    flow = GeminiOAuthFlow(http_client_factory=lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ))
    authorization = flow.create_authorization(oauth_type="code_assist", project_id="project-1")
    callback = "https://codeassist.google.com/authcode?" + urlencode({
        "code": "4/authorization-code",
        "state": authorization["state"],
    })
    before = time.time()
    token = asyncio.run(flow.exchange_code(
        session_id=authorization["session_id"],
        state=authorization["state"],
        code=callback,
        oauth_type="code_assist",
    ))

    assert seen["url"] == "https://oauth2.googleapis.com/token"
    assert seen["form"]["grant_type"] == ["authorization_code"]
    assert seen["form"]["client_id"] == [GEMINI_CLI_CLIENT_ID]
    assert seen["form"]["code"] == ["4/authorization-code"]
    assert seen["form"]["redirect_uri"] == [CODE_ASSIST_REDIRECT_URI]
    assert seen["form"]["code_verifier"][0]
    assert token["access_token"] == "ya29.access"
    assert token["refresh_token"] == "refresh-token"
    assert token["project_id"] == "project-1"
    assert before + 3290 <= token["expires_at"] <= time.time() + 3310
    assert flow._sessions.pending_count == 0

    with pytest.raises(OAuthFlowError, match="not found or has expired"):
        asyncio.run(flow.exchange_code(
            session_id=authorization["session_id"],
            state=authorization["state"],
            code="another-code",
        ))


def test_callback_state_mismatch_is_rejected_before_token_request():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"access_token": "unused"})

    flow = GeminiOAuthFlow(http_client_factory=lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ))
    authorization = flow.create_authorization()
    callback = "http://localhost/callback?code=code-1&state=wrong-state"

    with pytest.raises(OAuthFlowError, match="Callback state"):
        asyncio.run(flow.exchange_code(
            session_id=authorization["session_id"],
            state=authorization["state"],
            code=callback,
        ))
    assert calls == 0
    assert flow._sessions.pending_count == 1


def test_failed_token_exchange_releases_session_for_retry():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(400, json={
                "error": "invalid_grant",
                "error_description": "Authorization code was rejected",
            })
        return httpx.Response(200, json={"access_token": "retry-access", "expires_in": 60})

    flow = GeminiOAuthFlow(http_client_factory=lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ))
    authorization = flow.create_authorization()
    kwargs = {
        "session_id": authorization["session_id"],
        "state": authorization["state"],
        "code": "authorization-code",
    }

    with pytest.raises(OAuthUpstreamError, match="invalid_grant") as error:
        asyncio.run(flow.exchange_code(**kwargs))
    assert error.value.status_code == 400
    assert flow._sessions.pending_count == 1

    token = asyncio.run(flow.exchange_code(**kwargs))
    assert token["access_token"] == "retry-access"
    assert flow._sessions.pending_count == 0


def test_google_error_callback_is_not_treated_as_an_authorization_code():
    flow = GeminiOAuthFlow()
    authorization = flow.create_authorization()
    callback = (
        "https://codeassist.google.com/authcode?error=access_denied&"
        "error_description=The+user+cancelled"
    )
    with pytest.raises(OAuthFlowError, match="access_denied"):
        asyncio.run(flow.exchange_code(
            session_id=authorization["session_id"],
            state=authorization["state"],
            code=callback,
        ))

