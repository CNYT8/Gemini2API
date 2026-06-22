from app.core.gem_mapping import GemMapping


def _new(tmp_path):
    return GemMapping(path=str(tmp_path / "gem-mapping.json"))


def test_set_then_resolve(tmp_path):
    gm = _new(tmp_path)
    gm.set("my-gem", {"gem_id": "g1", "base_model": "gemini-pro", "account_id": "account-0"})
    assert gm.resolve("my-gem") == {"gem_id": "g1", "base_model": "gemini-pro", "account_id": "account-0"}


def test_resolve_unknown_returns_none(tmp_path):
    gm = _new(tmp_path)
    assert gm.resolve("nope") is None


def test_persist_across_instances(tmp_path):
    p = str(tmp_path / "gem-mapping.json")
    GemMapping(path=p).set("g", {"gem_id": "x", "base_model": "gemini-flash", "account_id": "a"})
    assert GemMapping(path=p).resolve("g")["gem_id"] == "x"


def test_delete(tmp_path):
    gm = _new(tmp_path)
    gm.set("g", {"gem_id": "x", "base_model": "gemini-pro", "account_id": "a"})
    assert gm.delete("g") is True
    assert gm.resolve("g") is None
    assert gm.delete("g") is False


def test_delete_by_gem_only_matches_gem_id_and_account(tmp_path):
    gm = _new(tmp_path)
    # 同 gem_id 但不同账号 -> 不该误删
    gm.set("m-target", {"gem_id": "g1", "base_model": "gemini-pro", "account_id": "acc-A"})
    gm.set("m-other-account", {"gem_id": "g1", "base_model": "gemini-pro", "account_id": "acc-B"})
    # 同账号但不同 gem_id -> 不该误删
    gm.set("m-other-gem", {"gem_id": "g2", "base_model": "gemini-pro", "account_id": "acc-A"})
    # 再来一条同样匹配的 -> 也该删
    gm.set("m-target-2", {"gem_id": "g1", "base_model": "gemini-flash", "account_id": "acc-A"})

    removed = gm.delete_by_gem("g1", "acc-A")
    assert sorted(removed) == ["m-target", "m-target-2"]
    # 被删的没了
    assert gm.resolve("m-target") is None
    assert gm.resolve("m-target-2") is None
    # 没匹配的还在
    assert gm.resolve("m-other-account") is not None
    assert gm.resolve("m-other-gem") is not None


def test_delete_by_gem_no_match_returns_empty(tmp_path):
    gm = _new(tmp_path)
    gm.set("m", {"gem_id": "g1", "base_model": "gemini-pro", "account_id": "acc-A"})
    assert gm.delete_by_gem("nope", "acc-A") == []
    assert gm.resolve("m") is not None


def test_get_all_is_a_copy(tmp_path):
    gm = _new(tmp_path)
    gm.set("g", {"gem_id": "x", "base_model": "gemini-pro", "account_id": "a"})
    snap = gm.get_all()
    snap["g"]["gem_id"] = "tampered"
    assert gm.resolve("g")["gem_id"] == "x"
