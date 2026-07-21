from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.core.gemini_oauth_client import (
    GEMINI_CLI_CLIENT_ID,
    GEMINI_CLI_CLIENT_SECRET,
    GOOGLE_TOKEN_URL,
)

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
CODE_ASSIST_REDIRECT_URI = "https://codeassist.google.com/authcode"
AI_STUDIO_REDIRECT_URI = "http://localhost:1455/auth/callback"
CODE_ASSIST_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile"
)
AI_STUDIO_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/generative-language.retriever"
)
OAUTH_SESSION_TTL_SECONDS = 30 * 60
MAX_OAUTH_SESSIONS = 512


class OAuthFlowError(ValueError):
    """The browser authorization request is invalid or no longer usable."""


class OAuthUpstreamError(RuntimeError):
    """Google rejected the authorization code or could not be reached."""

    def __init__(self, message: str, *, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


@dataclass
class _OAuthSession:
    state: str
    code_verifier: str = field(repr=False)
    oauth_type: str = "code_assist"
    redirect_uri: str = ""
    project_id: str = ""
    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)
    created_at: float = field(default_factory=time.monotonic)
    in_use: bool = False


class _OAuthSessionStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = OAUTH_SESSION_TTL_SECONDS,
        max_sessions: int = MAX_OAUTH_SESSIONS,
    ):
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._sessions: dict[str, _OAuthSession] = {}
        self._lock = threading.Lock()

    def _remove_expired_locked(self, now: float) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.created_at > self._ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def create(self, session: _OAuthSession) -> str:
        with self._lock:
            self._remove_expired_locked(time.monotonic())
            if len(self._sessions) >= self._max_sessions:
                removable = [
                    (item.created_at, session_id)
                    for session_id, item in self._sessions.items()
                    if not item.in_use
                ]
                if not removable:
                    raise OAuthFlowError("Too many OAuth authorizations are already in progress")
                _, oldest_id = min(removable)
                self._sessions.pop(oldest_id, None)

            session_id = secrets.token_urlsafe(24)
            while session_id in self._sessions:
                session_id = secrets.token_urlsafe(24)
            self._sessions[session_id] = session
            return session_id

    def claim(self, session_id: str, state: str, oauth_type: str) -> _OAuthSession:
        with self._lock:
            now = time.monotonic()
            self._remove_expired_locked(now)
            session = self._sessions.get(session_id)
            if session is None:
                raise OAuthFlowError("OAuth authorization session was not found or has expired")
            if not _constant_time_equal(state, session.state):
                raise OAuthFlowError("OAuth state verification failed")
            if oauth_type and oauth_type != session.oauth_type:
                raise OAuthFlowError("OAuth mode does not match the authorization session")
            if session.in_use:
                raise OAuthFlowError("OAuth authorization session is already being exchanged")
            session.in_use = True
            return session

    def release(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.in_use = False

    def consume(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    @property
    def pending_count(self) -> int:
        with self._lock:
            self._remove_expired_locked(time.monotonic())
            return len(self._sessions)


def _new_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0))


class GeminiOAuthFlow:
    def __init__(
        self,
        *,
        session_store: _OAuthSessionStore | None = None,
        http_client_factory: Callable[[], httpx.AsyncClient] = _new_http_client,
    ):
        self._sessions = session_store or _OAuthSessionStore()
        self._http_client_factory = http_client_factory

    @staticmethod
    def capabilities() -> dict:
        return {
            "oauth_types": ["code_assist", "ai_studio"],
            "code_assist_builtin_client": True,
            "ai_studio_oauth_enabled": True,
            "ai_studio_requires_custom_client": True,
            "required_redirect_uris": [
                CODE_ASSIST_REDIRECT_URI,
                AI_STUDIO_REDIRECT_URI,
            ],
            "session_ttl_seconds": OAUTH_SESSION_TTL_SECONDS,
        }

    @staticmethod
    def _normalize_oauth_type(value: str) -> str:
        oauth_type = str(value or "code_assist").strip().lower()
        if oauth_type not in ("code_assist", "ai_studio"):
            raise OAuthFlowError("oauth_type must be code_assist or ai_studio")
        return oauth_type

    @staticmethod
    def _bounded(value: str, name: str, max_length: int) -> str:
        normalized = str(value or "").strip()
        if len(normalized) > max_length:
            raise OAuthFlowError(f"{name} is too long")
        return normalized

    def create_authorization(
        self,
        *,
        oauth_type: str = "code_assist",
        project_id: str = "",
        client_id: str = "",
        client_secret: str = "",
    ) -> dict:
        oauth_type = self._normalize_oauth_type(oauth_type)
        project_id = self._bounded(project_id, "project_id", 256)
        client_id = self._bounded(client_id, "oauth_client_id", 2048)
        client_secret = self._bounded(client_secret, "oauth_client_secret", 2048)
        if bool(client_id) != bool(client_secret):
            raise OAuthFlowError("OAuth Client ID and Client Secret must be configured together")

        using_builtin_client = not client_id and not client_secret
        if oauth_type == "ai_studio" and using_builtin_client:
            raise OAuthFlowError("AI Studio browser authorization requires a custom OAuth Client ID and Client Secret")
        if using_builtin_client:
            client_id = GEMINI_CLI_CLIENT_ID
            client_secret = GEMINI_CLI_CLIENT_SECRET

        redirect_uri = (
            CODE_ASSIST_REDIRECT_URI
            if oauth_type == "code_assist" and using_builtin_client
            else AI_STUDIO_REDIRECT_URI
        )
        scopes = CODE_ASSIST_SCOPES if oauth_type == "code_assist" else AI_STUDIO_SCOPES
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        session_id = self._sessions.create(_OAuthSession(
            state=state,
            code_verifier=code_verifier,
            oauth_type=oauth_type,
            redirect_uri=redirect_uri,
            project_id=project_id,
            client_id=client_id,
            client_secret=client_secret,
        ))
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        if project_id:
            params["project_id"] = project_id

        return {
            "auth_url": f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}",
            "session_id": session_id,
            "state": state,
            "redirect_uri": redirect_uri,
            "expires_in": OAUTH_SESSION_TTL_SECONDS,
        }

    @staticmethod
    def _authorization_response(value: str) -> tuple[str, str]:
        raw = str(value or "").strip()
        if not raw:
            raise OAuthFlowError("Authorization code is required")
        if len(raw) > 8192:
            raise OAuthFlowError("Authorization response is too long")
        looks_like_callback = (
            "://" in raw
            or raw.startswith("?")
            or raw.startswith("code=")
            or "&code=" in raw
            or raw.startswith("error=")
            or "?error=" in raw
            or "&error=" in raw
        )
        if not looks_like_callback:
            return raw, ""

        candidate = raw
        if "://" not in candidate:
            candidate = f"http://localhost/callback?{candidate.lstrip('?')}"
        parsed = urlparse(candidate)
        params = parse_qs(parsed.query, keep_blank_values=True)
        if not params and parsed.fragment:
            params = parse_qs(parsed.fragment, keep_blank_values=True)
        error = (params.get("error") or [""])[0].strip()
        if error:
            description = (params.get("error_description") or [""])[0].strip()
            message = f"Google authorization failed: {error}"
            if description:
                message += f" ({description[:300]})"
            raise OAuthFlowError(message)
        code = (params.get("code") or [""])[0].strip()
        if not code:
            raise OAuthFlowError("Authorization callback does not contain a code")
        callback_state = (params.get("state") or [""])[0].strip()
        return code, callback_state

    async def exchange_code(
        self,
        *,
        session_id: str,
        state: str,
        code: str,
        oauth_type: str = "",
    ) -> dict:
        session_id = self._bounded(session_id, "session_id", 256)
        supplied_state = self._bounded(state, "state", 512)
        if not session_id or not supplied_state:
            raise OAuthFlowError("session_id and state are required")
        normalized_type = self._normalize_oauth_type(oauth_type) if oauth_type else ""
        authorization_code, callback_state = self._authorization_response(code)
        if callback_state and not _constant_time_equal(callback_state, supplied_state):
            raise OAuthFlowError("Callback state does not match this authorization session")

        session = self._sessions.claim(session_id, supplied_state, normalized_type)
        try:
            try:
                async with self._http_client_factory() as client:
                    response = await client.post(
                        GOOGLE_TOKEN_URL,
                        data={
                            "grant_type": "authorization_code",
                            "client_id": session.client_id,
                            "client_secret": session.client_secret,
                            "code": authorization_code,
                            "code_verifier": session.code_verifier,
                            "redirect_uri": session.redirect_uri,
                        },
                    )
            except httpx.HTTPError as exc:
                raise OAuthUpstreamError("Could not connect to the Google OAuth token endpoint") from exc
            except Exception as exc:
                raise OAuthUpstreamError("Could not complete the Google OAuth token request") from exc

            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            if response.status_code >= 400:
                error = str(payload.get("error") or f"HTTP {response.status_code}")
                description = str(payload.get("error_description") or "").strip()
                message = f"Google OAuth token exchange failed: {error}"
                if description:
                    message += f" ({description[:300]})"
                raise OAuthUpstreamError(
                    message,
                    status_code=400 if response.status_code < 500 else 502,
                )

            access_token = str(payload.get("access_token") or "").strip()
            if not access_token:
                raise OAuthUpstreamError("Google OAuth token exchange returned no access_token")
            refresh_token = str(payload.get("refresh_token") or "").strip()
            try:
                expires_in = max(0, int(payload.get("expires_in") or 3600))
            except (TypeError, ValueError):
                expires_in = 3600
            now = time.time()
            expires_at = now + max(30, expires_in - 300) if expires_in else 0

            self._sessions.consume(session_id)
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "expires_at": expires_at,
                "token_type": str(payload.get("token_type") or "Bearer"),
                "scope": str(payload.get("scope") or ""),
                "project_id": session.project_id,
                "oauth_type": session.oauth_type,
            }
        finally:
            # Successful exchanges have already consumed the session; on every
            # failure/cancellation this makes the same session available to retry.
            self._sessions.release(session_id)


gemini_oauth_flow = GeminiOAuthFlow()
