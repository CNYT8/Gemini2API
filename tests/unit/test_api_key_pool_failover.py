"""ApiKeyPool 故障切换候选选择 + 内存冷却（纯逻辑，无网络）。"""

import app.core.api_key_store as store_mod
from app.core.api_key_store import ApiKeyPool


def _fresh_pool(tmp_path):
    # 指向不存在的文件 -> 空池；add() 会写盘到该临时路径，互不污染。
    return ApiKeyPool(file_path=str(tmp_path / "api-keys.json"))


def _add(pool, model, status="active"):
    e = pool.add(provider="openai", model=model, api_key="sk-x", base_url="https://x/v1")
    if status != "active":
        pool.update_status(e.id, status)
    return e


def test_returns_all_active_same_model_in_insertion_order(tmp_path):
    pool = _fresh_pool(tmp_path)
    a = _add(pool, "deepseek")
    b = _add(pool, "deepseek")
    _add(pool, "other")
    got = pool.get_entries_for_model("deepseek")
    assert [e.id for e in got] == [a.id, b.id]


def test_excludes_non_active_and_other_models(tmp_path):
    pool = _fresh_pool(tmp_path)
    _add(pool, "deepseek", status="disabled")
    b = _add(pool, "deepseek")
    assert [e.id for e in pool.get_entries_for_model("deepseek")] == [b.id]


def test_cooled_entry_sorted_to_back(tmp_path, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(store_mod.time, "monotonic", lambda: clock["now"])
    pool = _fresh_pool(tmp_path)
    a = _add(pool, "deepseek")
    b = _add(pool, "deepseek")
    pool.mark_unhealthy(a.id, 180.0)               # a 冷却到 1180
    assert [e.id for e in pool.get_entries_for_model("deepseek")] == [b.id, a.id]
    clock["now"] = 1181.0                            # 冷却到期
    assert [e.id for e in pool.get_entries_for_model("deepseek")] == [a.id, b.id]


def test_all_cooled_still_returned_never_starve(tmp_path, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(store_mod.time, "monotonic", lambda: clock["now"])
    pool = _fresh_pool(tmp_path)
    a = _add(pool, "deepseek")
    b = _add(pool, "deepseek")
    pool.mark_unhealthy(a.id, 180.0)
    pool.mark_unhealthy(b.id, 180.0)
    assert [e.id for e in pool.get_entries_for_model("deepseek")] == [a.id, b.id]


def test_mark_unhealthy_zero_is_noop(tmp_path, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(store_mod.time, "monotonic", lambda: clock["now"])
    pool = _fresh_pool(tmp_path)
    a = _add(pool, "deepseek")
    pool.mark_unhealthy(a.id, 0)
    assert [e.id for e in pool.get_entries_for_model("deepseek")] == [a.id]
    pool.mark_unhealthy(a.id, -5.0)
    assert [e.id for e in pool.get_entries_for_model("deepseek")] == [a.id]
