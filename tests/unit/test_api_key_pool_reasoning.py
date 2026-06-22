"""ApiKeyEntry.reasoning_effort 存储与更新(纯逻辑,无网络)。"""

from dataclasses import asdict
from app.core.api_key_store import ApiKeyPool, ApiKeyEntry


def _pool(tmp_path):
    return ApiKeyPool(file_path=str(tmp_path / "api-keys.json"))


def test_add_with_reasoning_effort(tmp_path):
    pool = _pool(tmp_path)
    e = pool.add(provider="openai", model="m", api_key="sk", base_url="https://x/v1", reasoning_effort="high")
    assert e.reasoning_effort == "high"
    assert pool.get(e.id).reasoning_effort == "high"


def test_add_default_is_none(tmp_path):
    pool = _pool(tmp_path)
    e = pool.add(provider="openai", model="m", api_key="sk", base_url="https://x/v1")
    assert e.reasoning_effort is None


def test_update_reasoning_effort(tmp_path):
    pool = _pool(tmp_path)
    e = pool.add(provider="openai", model="m", api_key="sk", base_url="https://x/v1")
    assert pool.update_reasoning_effort(e.id, "medium") is True
    assert pool.get(e.id).reasoning_effort == "medium"
    # 空串清除为 None
    assert pool.update_reasoning_effort(e.id, "") is True
    assert pool.get(e.id).reasoning_effort is None
    # 不存在的 id
    assert pool.update_reasoning_effort("ghost", "low") is False


def test_load_old_record_without_field(tmp_path):
    # 模拟旧 JSON(无 reasoning_effort 键)能正常加载
    import json
    p = tmp_path / "api-keys.json"
    p.write_text(json.dumps({"abc": {
        "id": "abc", "provider": "openai", "model": "m", "api_key": "sk",
        "base_url": "https://x/v1", "label": None, "status": "active",
        "added_at": "2026-01-01T00:00:00", "last_used_at": None
    }}))
    pool = ApiKeyPool(file_path=str(p))
    assert pool.get("abc").reasoning_effort is None
