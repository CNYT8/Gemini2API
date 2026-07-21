import asyncio
import json
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any, AsyncGenerator


async def split_into_chunks(text: str, delay: float = 0.03) -> AsyncGenerator[str, None]:
    words = text.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        yield chunk
        await asyncio.sleep(delay)


def format_sse(data: dict | str) -> str:
    if isinstance(data, dict):
        return f"data: {json.dumps(data)}\n\n"
    return f"data: {data}\n\n"


def merge_gemini_stream_text(seen: str, incoming: str) -> tuple[str, str]:
    """Normalize Gemini's cumulative and incremental text stream variants.

    Different Gemini gateways emit either the entire accumulated response or
    just the newest token span. Keep the internal text append-only so OpenAI,
    Claude, and Gemini-compatible consumers never receive duplicated output.
    """
    seen = (seen or "").rstrip("\0")
    incoming = (incoming or "").rstrip("\0")
    if not incoming:
        return seen, ""
    if incoming.startswith(seen):
        return incoming, incoming[len(seen):]
    if seen.startswith(incoming):
        return seen, ""
    return seen + incoming, incoming


def is_effective_stream_event(event: Any) -> bool:
    """Return whether an account stream event contains usable model output."""
    if not isinstance(event, dict):
        return False
    if event.get("type") == "delta":
        return isinstance(event.get("text"), str) and bool(event["text"])
    if event.get("type") == "final":
        return (
            isinstance(event.get("text"), str) and bool(event["text"])
        ) or bool(event.get("images"))
    return False


async def _close_async_iterator(iterator: AsyncIterator[Any]) -> None:
    close = getattr(iterator, "aclose", None)
    if close is None:
        return
    try:
        await close()
    except BaseException:
        # Cleanup must not mask the upstream error or a client cancellation.
        pass


async def _replay_first_event(first: dict, iterator: AsyncIterator[dict]) -> AsyncGenerator[dict, None]:
    try:
        yield first
        async for event in iterator:
            yield event
    finally:
        await _close_async_iterator(iterator)


async def prefetch_first_effective_stream_event(
    events: AsyncIterable[dict], *, timeout: float = 0,
) -> AsyncIterator[dict]:
    """Wait for the first usable event and replay it with the remaining stream.

    Empty/malformed upstream frames are not a successful response. Delaying a
    protocol's assistant-start frame until this succeeds preserves the chance
    to fail over before an SSE response has observable content.
    """
    iterator = events.__aiter__()

    async def _read_first() -> dict:
        async for event in iterator:
            if is_effective_stream_event(event):
                return event
        raise RuntimeError("Gemini stream not ready: ended before first usable output")

    try:
        if timeout > 0:
            first = await asyncio.wait_for(_read_first(), timeout=timeout)
        else:
            first = await _read_first()
    except asyncio.TimeoutError as exc:
        await _close_async_iterator(iterator)
        raise RuntimeError(
            f"Gemini stream not ready: first usable output timed out after {timeout:g}s"
        ) from exc
    except BaseException:
        await _close_async_iterator(iterator)
        raise

    return _replay_first_event(first, iterator)


async def stream_with_keepalive(
    events: AsyncIterable[dict], *, interval: float = 10.0,
) -> AsyncGenerator[dict | None, None]:
    """Yield ``None`` keepalives while waiting for the first usable event.

    SSE routes translate ``None`` to a comment frame. Comments keep reverse
    proxies alive without committing an OpenAI/Claude/Responses lifecycle
    event, so account failover remains transparent to protocol consumers.
    """
    task = asyncio.create_task(prefetch_first_effective_stream_event(events))
    ready: AsyncIterator[dict] | None = None
    try:
        while ready is None:
            try:
                if interval > 0:
                    ready = await asyncio.wait_for(asyncio.shield(task), timeout=interval)
                else:
                    ready = await task
            except asyncio.TimeoutError:
                yield None
        async for event in ready:
            yield event
    finally:
        if ready is not None:
            await _close_async_iterator(ready)
        if not task.done():
            task.cancel()
        try:
            await task
        except BaseException:
            pass
