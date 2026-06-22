import json
from app.core.gemini_client import GeminiWebClient


def _c():
    return GeminiWebClient.__new__(GeminiWebClient)


def test_encode_payload_unchanged_without_gem():
    c = _c()
    out = c._encode_payload("hello", "gemini-pro", "", None)
    # 无 gem 时与历史结构逐字节一致：outer=[null, inner], inner=[[prompt],null,null,model]
    assert out == json.dumps([None, json.dumps([["hello"], None, None, "gemini-pro"])])


def test_encode_payload_injects_gem_at_index_19():
    c = _c()
    out = c._encode_payload("hello", "gemini-pro", "", None, gem_id="gem-abc")
    outer = json.loads(out)
    inner = json.loads(outer[1])
    assert len(inner) >= 20
    assert inner[19] == "gem-abc"
    # 前 4 位结构保持
    assert inner[0] == ["hello"]
    assert inner[3] == "gemini-pro"


def test_encode_payload_gem_with_attachments():
    c = _c()
    out = c._encode_payload("hi", "gemini-pro", "conv1", [("fid", "f.png")], gem_id="g1")
    inner = json.loads(json.loads(out)[1])
    assert inner[19] == "g1"
    assert inner[2] == "conv1"
