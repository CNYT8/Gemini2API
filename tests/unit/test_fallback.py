"""Unit tests for the Gemini→third-party fallback chain helpers.

Pure-logic coverage only (no network): empty-response detection, the
FALLBACK_MODELS parser, non-chat model filtering, and candidate selection.
End-to-end behaviour is verified against a live deployment.
"""

from app.core.fallback import (
    is_empty_result,
    openai_data_is_empty,
    parse_fallback_models,
    looks_chat_capable,
    select_fallback_candidates,
)


class _Entry:
    """Minimal stand-in for an ApiKeyEntry."""

    def __init__(self, model, status="active"):
        self.id = model
        self.model = model
        self.status = status


def test_is_empty_result_true_cases():
    assert is_empty_result(None) is True
    assert is_empty_result({}) is True
    assert is_empty_result({"text": ""}) is True
    assert is_empty_result({"text": "   \n  "}) is True
    assert is_empty_result({"text": "", "images": []}) is True


def test_is_empty_result_false_cases():
    assert is_empty_result({"text": "hello"}) is False
    assert is_empty_result({"text": "  ok  "}) is False
    # Image-only results (e.g. generated images) must NOT be treated as empty.
    assert is_empty_result({"text": "", "images": [{"id": "x"}]}) is False


def test_openai_data_is_empty():
    assert openai_data_is_empty(None) is True
    assert openai_data_is_empty({}) is True
    assert openai_data_is_empty({"choices": []}) is True
    assert openai_data_is_empty({"choices": [{"message": {"content": ""}}]}) is True
    assert openai_data_is_empty({"choices": [{"message": {"content": "hi"}}]}) is False
    assert openai_data_is_empty(
        {"choices": [{"message": {"content": None, "tool_calls": [{"id": "x"}]}}]}
    ) is False


def test_parse_fallback_models():
    assert parse_fallback_models("") == []
    assert parse_fallback_models("   ") == []
    assert parse_fallback_models(None) == []
    assert parse_fallback_models("a") == ["a"]
    assert parse_fallback_models("a, b ,c") == ["a", "b", "c"]
    # Empty segments and trailing commas are dropped.
    assert parse_fallback_models("a,,b,") == ["a", "b"]


def test_looks_chat_capable():
    assert looks_chat_capable("agnes-2.0-flash") is True
    assert looks_chat_capable("gpt-4o") is True
    assert looks_chat_capable("deepseek-chat") is True
    # Non-chat modalities are excluded.
    assert looks_chat_capable("agnes-image-2.0-flash") is False
    assert looks_chat_capable("agnes-video-v2.0") is False
    assert looks_chat_capable("text-embedding-3-large") is False
    assert looks_chat_capable("whisper-1") is False
    assert looks_chat_capable("dall-e-3") is False


def test_select_auto_excludes_nonchat():
    entries = [
        _Entry("agnes-2.0-flash"),
        _Entry("agnes-image-2.0-flash"),
        _Entry("agnes-video-v2.0"),
        _Entry("gpt-4o"),
    ]
    got = {e.model for e in select_fallback_candidates(entries, [])}
    assert got == {"agnes-2.0-flash", "gpt-4o"}


def test_select_pin_preserves_order_and_ignores_filter():
    entries = [_Entry("a"), _Entry("b"), _Entry("c")]
    got = [e.model for e in select_fallback_candidates(entries, ["c", "a"])]
    assert got == ["c", "a"]


def test_select_skips_inactive():
    entries = [_Entry("a", status="disabled"), _Entry("b")]
    got = {e.model for e in select_fallback_candidates(entries, [])}
    assert got == {"b"}


def test_select_pin_only_active():
    entries = [_Entry("a", status="disabled"), _Entry("b")]
    got = [e.model for e in select_fallback_candidates(entries, ["a", "b"])]
    assert got == ["b"]
