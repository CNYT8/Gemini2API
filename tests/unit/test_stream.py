import asyncio

import pytest

from app.core.stream import (
    merge_gemini_stream_text,
    prefetch_first_effective_stream_event,
    stream_with_keepalive,
)


def test_merge_gemini_stream_text_accepts_cumulative_and_incremental_frames():
    seen, delta = merge_gemini_stream_text("", "hel")
    assert (seen, delta) == ("hel", "hel")

    seen, delta = merge_gemini_stream_text(seen, "hello")
    assert (seen, delta) == ("hello", "lo")

    seen, delta = merge_gemini_stream_text(seen, "hello")
    assert (seen, delta) == ("hello", "")

    seen, delta = merge_gemini_stream_text(seen, "hel")
    assert (seen, delta) == ("hello", "")

    seen, delta = merge_gemini_stream_text(seen, " world\0")
    assert (seen, delta) == ("hello world", " world")


def test_prefetch_skips_empty_events_and_replays_first_usable_event():
    async def run():
        async def source():
            yield {"type": "delta", "text": ""}
            yield {"type": "final", "text": "", "images": []}
            yield {"type": "delta", "text": "ok"}
            yield {"type": "final", "text": "ok", "images": []}

        ready = await prefetch_first_effective_stream_event(source())
        return [event async for event in ready]

    assert asyncio.run(run()) == [
        {"type": "delta", "text": "ok"},
        {"type": "final", "text": "ok", "images": []},
    ]


def test_prefetch_rejects_empty_stream():
    async def run():
        async def source():
            yield {"type": "final", "text": "", "images": []}

        await prefetch_first_effective_stream_event(source())

    with pytest.raises(RuntimeError, match="not ready"):
        asyncio.run(run())


def test_prefetch_times_out_before_first_usable_output():
    async def run():
        async def source():
            await asyncio.sleep(0.05)
            yield {"type": "delta", "text": "late"}

        await prefetch_first_effective_stream_event(source(), timeout=0.001)

    with pytest.raises(RuntimeError, match="timed out"):
        asyncio.run(run())


def test_stream_with_keepalive_emits_comment_marker_before_slow_first_output():
    async def run():
        async def source():
            await asyncio.sleep(0.02)
            yield {"type": "delta", "text": "ok"}

        return [event async for event in stream_with_keepalive(source(), interval=0.001)]

    events = asyncio.run(run())
    assert events[0] is None
    assert events[-1] == {"type": "delta", "text": "ok"}
