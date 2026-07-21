# tests/unit/test_gems.py
import json
import asyncio
import pytest
from app.core.gemini_client import GeminiWebClient


def _make_client():
    # 不触发网络/初始化：直接造实例，replace 掉 _batchexecute
    c = GeminiWebClient.__new__(GeminiWebClient)
    return c


def _wrb(rpc_id: str, body_obj) -> str:
    # 模拟 batchexecute 响应：每行一个 [[ "wrb.fr", rpc, "<json字符串>" ]]
    inner = json.dumps(body_obj)
    return json.dumps([["wrb.fr", rpc_id, inner]]) + "\n"


def test_list_gems_parses_custom_gems(monkeypatch):
    c = _make_client()
    # body[2] 是 gem 列表；每个 gem: [id, [name, desc], [prompt]]
    body = [None, None, [
        ["gem-abc", ["Python 导师", "教 Python"], ["你是资深 Python 导师"]],
        ["gem-def", ["翻译官", "中英互译"], None],
    ]]

    async def fake_batch(rpc_id, payload_str):
        assert rpc_id == "CNgdBe"
        assert payload_str == json.dumps([2, ["en"], 0])
        return _wrb("CNgdBe", body)

    monkeypatch.setattr(c, "_batchexecute", fake_batch)
    gems = asyncio.run(c.list_gems())
    assert gems == [
        {"id": "gem-abc", "name": "Python 导师", "description": "教 Python", "prompt": "你是资深 Python 导师"},
        {"id": "gem-def", "name": "翻译官", "description": "中英互译", "prompt": ""},
    ]


def test_list_gems_returns_empty_on_failure(monkeypatch):
    c = _make_client()

    async def fake_batch(rpc_id, payload_str):
        return None

    monkeypatch.setattr(c, "_batchexecute", fake_batch)
    assert asyncio.run(c.list_gems()) == []


def test_create_gem_returns_new_id(monkeypatch):
    c = _make_client()
    # 新建响应：body[0] 是新 gem id
    body = ["gem-new-123"]

    captured = {}
    async def fake_batch(rpc_id, payload_str):
        captured["rpc"] = rpc_id
        captured["payload"] = json.loads(payload_str)
        return _wrb("oMH3Zd", body)

    monkeypatch.setattr(c, "_batchexecute", fake_batch)
    gid = asyncio.run(c.create_gem("导师", "你是导师", "desc"))
    assert gid == "gem-new-123"
    assert captured["rpc"] == "oMH3Zd"
    # payload 外层是 [[name, desc, prompt, ...]]
    assert captured["payload"][0][0] == "导师"
    assert captured["payload"][0][1] == "desc"
    assert captured["payload"][0][2] == "你是导师"


def test_update_gem_true_on_200(monkeypatch):
    c = _make_client()
    captured = {}
    async def fake_batch(rpc_id, payload_str):
        captured["rpc"] = rpc_id
        captured["payload"] = json.loads(payload_str)
        return _wrb("kHv0Vd", [])
    monkeypatch.setattr(c, "_batchexecute", fake_batch)
    ok = asyncio.run(c.update_gem("gem-1", "新名", "新提示", "新描述"))
    assert ok is True
    assert captured["rpc"] == "kHv0Vd"
    assert captured["payload"][0] == "gem-1"
    assert captured["payload"][1][0] == "新名"


def test_delete_gem_true_on_200(monkeypatch):
    c = _make_client()
    async def fake_batch(rpc_id, payload_str):
        assert rpc_id == "UXcSJb"
        assert json.loads(payload_str) == ["gem-x"]
        return _wrb("UXcSJb", [])
    monkeypatch.setattr(c, "_batchexecute", fake_batch)
    assert asyncio.run(c.delete_gem("gem-x")) is True


def test_delete_gem_false_on_none(monkeypatch):
    c = _make_client()
    async def fake_batch(rpc_id, payload_str):
        return None
    monkeypatch.setattr(c, "_batchexecute", fake_batch)
    assert asyncio.run(c.delete_gem("gem-x")) is False
