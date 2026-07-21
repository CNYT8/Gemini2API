import asyncio
import base64
import inspect
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable

import httpx

from app.config import settings
from app.core.gemini_client import HTTPStatusError
from app.core.file_upload import _resolve_bytes
from app.core.gemini_models import PUBLIC_MODELS, normalize_model_name
from app.core.stream import merge_gemini_stream_text

logger = logging.getLogger(__name__)

AI_STUDIO_BASE_URL = "https://generativelanguage.googleapis.com"
CODE_ASSIST_BASE_URL = "https://cloudcode-pa.googleapis.com"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GEMINI_CLI_USER_AGENT = "GeminiCLI/0.1.5 (Windows; AMD64)"

# Google Gemini CLI's installed-app OAuth client. Account-specific values can
# override these when a refresh token was issued to a custom OAuth client.
GEMINI_CLI_CLIENT_ID = (
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
)
GEMINI_CLI_CLIENT_SECRET = "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"

_OAUTH_MODEL_ALIASES = {
    "gemini-pro": "gemini-3-pro-preview",
    "gemini-flash": "gemini-3-flash-preview",
    "gemini-flash-thinking": "gemini-3-flash-preview",
}


def _oauth_model_name(model: str) -> str:
    name = normalize_model_name(model)
    return _OAUTH_MODEL_ALIASES.get(name, name)


def _unwrap_response(payload: dict) -> dict:
    wrapped = payload.get("response")
    return wrapped if isinstance(wrapped, dict) else payload


def _response_content(payload: dict) -> tuple[str, list[dict]]:
    payload = _unwrap_response(payload)
    candidates = payload.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        return "", []
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts: list[str] = []
    images: list[dict] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str) and text and not part.get("thought"):
            texts.append(text)
        inline = part.get("inlineData") or part.get("inline_data")
        if not isinstance(inline, dict):
            continue
        data = inline.get("data")
        if isinstance(data, str) and data:
            images.append({
                "b64": data,
                "mime": inline.get("mimeType") or inline.get("mime_type") or "image/png",
            })
    return "".join(texts), images


class _HttpxDownloadAdapter:
    """Expose curl_cffi-style redirect arguments to the shared safe downloader."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def get(self, url: str, *, timeout: float, allow_redirects: bool):
        return await self._client.get(
            url,
            timeout=timeout,
            follow_redirects=allow_redirects,
        )


class GeminiOAuthClient:
    """Gemini API/CLI client sharing the account-pool contract with GeminiWebClient."""

    def __init__(
        self,
        *,
        access_token: str,
        refresh_token: str = "",
        expires_at: float = 0,
        project_id: str = "",
        oauth_type: str = "code_assist",
        client_id: str = "",
        client_secret: str = "",
        token_update: Callable[[str, str, float], object] | None = None,
        project_update: Callable[[str], object] | None = None,
    ):
        self._access_token = access_token.strip()
        self._refresh_token = refresh_token.strip()
        self._expires_at = float(expires_at or 0)
        self._project_id = project_id.strip()
        self._oauth_type = oauth_type if oauth_type in ("code_assist", "ai_studio") else "code_assist"
        configured_client_id = client_id.strip()
        configured_client_secret = client_secret.strip()
        if configured_client_id or configured_client_secret:
            self._client_id = configured_client_id
            self._client_secret = configured_client_secret
        else:
            self._client_id = GEMINI_CLI_CLIENT_ID
            self._client_secret = GEMINI_CLI_CLIENT_SECRET
        self._token_update = token_update
        self._project_update = project_update
        self._http: httpx.AsyncClient | None = None
        self._refresh_lock = asyncio.Lock()
        self._healthy = False
        self._last_check_result: dict | None = None
        self._check_history: deque = deque(maxlen=50)

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    @property
    def models(self) -> list[str]:
        return list(PUBLIC_MODELS)

    @property
    def last_check_result(self) -> dict | None:
        return self._last_check_result

    @property
    def check_history(self) -> list[dict]:
        return list(self._check_history)

    async def initialize(self):
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(180.0, connect=20.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        result = await self.check_account()
        self._healthy = bool(result.get("valid"))

    async def _get_access_token(self, *, force_refresh: bool = False) -> str:
        observed_token = self._access_token
        now = time.time()
        if (
            not force_refresh
            and self._access_token
            and (self._expires_at <= 0 or now < self._expires_at - 60)
        ):
            return self._access_token

        async with self._refresh_lock:
            now = time.time()
            # A concurrent request may already have refreshed the token while
            # this request was waiting for the lock. Reuse that result instead
            # of creating a refresh burst after a shared 401.
            if force_refresh and self._access_token and self._access_token != observed_token:
                return self._access_token
            if (
                not force_refresh
                and self._access_token
                and (self._expires_at <= 0 or now < self._expires_at - 60)
            ):
                return self._access_token
            if not self._refresh_token:
                if self._access_token and not force_refresh:
                    return self._access_token
                raise RuntimeError("OAuth access token expired and no refresh token is configured")
            if not self._client_id or not self._client_secret:
                raise RuntimeError("OAuth token refresh requires both client_id and client_secret")
            if self._http is None:
                raise RuntimeError("OAuth client not ready")

            resp = await self._http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            if resp.status_code >= 400:
                raise HTTPStatusError(resp.status_code, resp.text)
            data = resp.json()
            access_token = str(data.get("access_token") or "").strip()
            if not access_token:
                raise RuntimeError("OAuth token refresh returned no access_token")
            self._access_token = access_token
            new_refresh = str(data.get("refresh_token") or "").strip()
            if new_refresh:
                self._refresh_token = new_refresh
            expires_in = float(data.get("expires_in") or 3600)
            self._expires_at = time.time() + max(0, expires_in)
            if self._token_update:
                updated = self._token_update(
                    self._access_token, self._refresh_token, self._expires_at
                )
                if inspect.isawaitable(updated):
                    await updated
            return self._access_token

    def _headers(self, token: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if self._oauth_type == "code_assist":
            headers["User-Agent"] = GEMINI_CLI_USER_AGENT
        return headers

    def _request_target(self, model: str, *, stream: bool) -> tuple[str, dict]:
        action = "streamGenerateContent" if stream else "generateContent"
        request = {"contents": []}
        if self._oauth_type == "code_assist":
            if not self._project_id:
                raise ValueError("Code Assist OAuth account requires project_id")
            url = f"{CODE_ASSIST_BASE_URL}/v1internal:{action}"
            if stream:
                url += "?alt=sse"
            return url, {
                "model": _oauth_model_name(model),
                "project": self._project_id,
                "request": request,
            }
        mapped = _oauth_model_name(model)
        url = f"{AI_STUDIO_BASE_URL}/v1beta/models/{mapped}:{action}"
        if stream:
            url += "?alt=sse"
        return url, request

    async def _contents(self, prompt: str, attachments: list | None) -> list[dict]:
        parts: list[dict] = [{"text": prompt}]
        if self._http is None:
            raise RuntimeError("OAuth client not ready")
        download_http = _HttpxDownloadAdapter(self._http)
        valid_attachments = [item for item in attachments or [] if isinstance(item, dict)]
        resolved_attachments = await asyncio.gather(*(
            _resolve_bytes(download_http, attachment) for attachment in valid_attachments
        ))
        for resolved in resolved_attachments:
            if not resolved:
                continue
            raw, _, mime = resolved
            parts.append({
                "inlineData": {
                    "mimeType": mime,
                    "data": base64.b64encode(raw).decode("ascii"),
                }
            })
        return [{"role": "user", "parts": parts}]

    async def _build_request(self, prompt: str, model: str, attachments: list | None, *, stream: bool):
        url, body = self._request_target(model, stream=stream)
        contents = await self._contents(prompt, attachments)
        if self._oauth_type == "code_assist":
            body["request"]["contents"] = contents
        else:
            body["contents"] = contents
        return url, body

    async def _post_json(self, url: str, body: dict) -> dict:
        if self._http is None:
            raise RuntimeError("OAuth client not ready")
        for attempt in range(2):
            token = await self._get_access_token(force_refresh=attempt == 1)
            resp = await self._http.post(url, headers=self._headers(token), json=body)
            if resp.status_code == 401 and attempt == 0 and self._refresh_token:
                continue
            if resp.status_code >= 400:
                raise HTTPStatusError(resp.status_code, resp.text)
            try:
                return resp.json()
            except json.JSONDecodeError as exc:
                raise RuntimeError("Gemini OAuth upstream returned invalid JSON") from exc
        raise RuntimeError("Gemini OAuth request failed after token refresh")

    async def check_account(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        try:
            token = await self._get_access_token()
            if self._http is None:
                raise RuntimeError("OAuth client not ready")
            if self._oauth_type == "code_assist":
                resp = await self._http.post(
                    f"{CODE_ASSIST_BASE_URL}/v1internal:loadCodeAssist",
                    headers=self._headers(token),
                    json={
                        "metadata": {
                            "ideType": "ANTIGRAVITY",
                            "platform": "PLATFORM_UNSPECIFIED",
                            "pluginType": "GEMINI",
                        }
                    },
                )
            else:
                resp = await self._http.get(
                    f"{AI_STUDIO_BASE_URL}/v1beta/models",
                    headers=self._headers(token),
                )
            if resp.status_code == 401 and self._refresh_token:
                token = await self._get_access_token(force_refresh=True)
                if self._oauth_type == "code_assist":
                    resp = await self._http.post(
                        f"{CODE_ASSIST_BASE_URL}/v1internal:loadCodeAssist",
                        headers=self._headers(token),
                        json={
                            "metadata": {
                                "ideType": "ANTIGRAVITY",
                                "platform": "PLATFORM_UNSPECIFIED",
                                "pluginType": "GEMINI",
                            }
                        },
                    )
                else:
                    resp = await self._http.get(
                        f"{AI_STUDIO_BASE_URL}/v1beta/models",
                        headers=self._headers(token),
                    )
            if resp.status_code >= 400:
                raise HTTPStatusError(resp.status_code, resp.text)
            if self._oauth_type == "code_assist" and not self._project_id:
                data = resp.json()
                discovered = data.get("cloudaicompanionProject")
                if isinstance(discovered, dict):
                    discovered = discovered.get("id")
                if isinstance(discovered, str) and discovered.strip():
                    self._project_id = discovered.strip()
                    if self._project_update:
                        updated = self._project_update(self._project_id)
                        if inspect.isawaitable(updated):
                            await updated
                else:
                    raise RuntimeError("Code Assist account has no project_id; configure one manually")
            self._healthy = True
            result = {
                "valid": True,
                "has_token": True,
                "models_count": len(PUBLIC_MODELS),
                "checked_at": now,
                "auth_type": "oauth",
                "oauth_type": self._oauth_type,
            }
        except Exception as exc:
            self._healthy = False
            result = {
                "valid": False,
                "has_token": bool(self._access_token),
                "models_count": 0,
                "checked_at": now,
                "auth_type": "oauth",
                "oauth_type": self._oauth_type,
                "error": str(exc),
            }
        self._last_check_result = result
        self._check_history.append(result)
        return result

    async def generate(
        self,
        prompt: str,
        model: str,
        conversation_id: str = "",
        attachments: list | None = None,
        gem_id: str | None = None,
    ) -> dict:
        if gem_id:
            raise ValueError("Custom Gems are only supported by Cookie accounts")
        if conversation_id:
            # Web conversation IDs are account-bound and cannot be resumed by the
            # stateless API/CLI endpoint. Let the pool fail over; the router then
            # retries with its full locally stored prompt when no web account exists.
            raise RuntimeError("OAuth client not ready for a web conversation id")
        if not self._healthy:
            result = await self.check_account()
            if not result.get("valid"):
                raise RuntimeError(f"OAuth client not ready: {result.get('error', 'account invalid')}")
        url, body = await self._build_request(prompt, model, attachments, stream=False)
        last_error: Exception | None = None
        for attempt in range(max(1, settings.same_account_5xx_retries + 1)):
            try:
                payload = await self._post_json(url, body)
                text, images = _response_content(payload)
                return {"text": text, "images": images, "conversation_id": ""}
            except HTTPStatusError as exc:
                last_error = exc
                if exc.status_code != 429 and not 500 <= exc.status_code < 600:
                    raise
                if attempt >= settings.same_account_5xx_retries:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
        raise last_error or RuntimeError("Gemini OAuth request failed")

    async def _stream_once(self, url: str, body: dict, token: str):
        if self._http is None:
            raise RuntimeError("OAuth client not ready")
        async with self._http.stream(
            "POST", url, headers=self._headers(token), json=body,
        ) as resp:
            if resp.status_code >= 400:
                raw = await resp.aread()
                raise HTTPStatusError(resp.status_code, raw.decode("utf-8", "replace"))
            data_lines: list[str] = []
            async for line in resp.aiter_lines():
                if not line:
                    if data_lines:
                        yield "\n".join(data_lines)
                        data_lines.clear()
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
                elif line.lstrip().startswith(("{", "[")):
                    if data_lines:
                        yield "\n".join(data_lines)
                        data_lines.clear()
                    yield line.strip()
            if data_lines:
                yield "\n".join(data_lines)

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        conversation_id: str = "",
        attachments: list | None = None,
        gem_id: str | None = None,
    ):
        if gem_id:
            raise ValueError("Custom Gems are only supported by Cookie accounts")
        if conversation_id:
            raise RuntimeError("OAuth client not ready for a web conversation id")
        if not self._healthy:
            result = await self.check_account()
            if not result.get("valid"):
                raise RuntimeError(f"OAuth client not ready: {result.get('error', 'account invalid')}")
        url, body = await self._build_request(prompt, model, attachments, stream=True)
        full_text = ""
        images: list[dict] = []
        token_refreshed = False
        force_token_refresh = False
        transient_retries = 0
        while True:
            token = await self._get_access_token(force_refresh=force_token_refresh)
            force_token_refresh = False
            try:
                async for raw in self._stream_once(url, body, token):
                    if raw == "[DONE]":
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.debug("Skipping malformed Gemini OAuth SSE event")
                        continue
                    text, event_images = _response_content(payload)
                    if text:
                        full_text, delta = merge_gemini_stream_text(full_text, text)
                        if delta:
                            yield {"type": "delta", "text": delta}
                    if event_images:
                        images.extend(event_images)
                if not full_text and not images:
                    raise RuntimeError("Gemini OAuth stream not ready: no usable output")
                break
            except HTTPStatusError as exc:
                if (
                    exc.status_code == 401
                    and not full_text
                    and not images
                    and not token_refreshed
                    and self._refresh_token
                ):
                    token_refreshed = True
                    force_token_refresh = True
                    continue
                if (
                    not full_text
                    and not images
                    and (exc.status_code == 429 or 500 <= exc.status_code < 600)
                    and transient_retries < settings.same_account_5xx_retries
                ):
                    transient_retries += 1
                    await asyncio.sleep(0.5 * transient_retries)
                    continue
                raise
        yield {
            "type": "final",
            "text": full_text,
            "conversation_id": "",
            "images": images,
        }

    async def update_credentials(
        self,
        *,
        access_token: str,
        refresh_token: str | None = None,
        expires_at: float = 0,
        project_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> dict:
        self._access_token = access_token.strip()
        if refresh_token is not None:
            self._refresh_token = refresh_token.strip()
        self._expires_at = float(expires_at or 0)
        if project_id is not None:
            self._project_id = project_id.strip()
        next_client_id = self._client_id if client_id is None else client_id.strip()
        next_client_secret = self._client_secret if client_secret is None else client_secret.strip()
        if not next_client_id and not next_client_secret:
            next_client_id = GEMINI_CLI_CLIENT_ID
            next_client_secret = GEMINI_CLI_CLIENT_SECRET
        self._client_id = next_client_id
        self._client_secret = next_client_secret
        self._healthy = False
        return await self.check_account()

    async def shutdown(self):
        if self._http:
            await self._http.aclose()
            self._http = None
