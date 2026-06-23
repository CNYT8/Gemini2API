# tests/unit/test_fallback_toggle.py
import pytest
from app.config import settings
import app.routers.api_keys as ak
from app.core import fallback

_AUTH = {"Authorization": "Bearer sk-test-key"}


@pytest.fixture(autouse=True)
def _restore_fallback():
    """settings 是模块级单例，测试间复位 fallback_enabled，避免串扰。"""
    old = getattr(settings, "fallback_enabled", False)
    yield
    object.__setattr__(settings, "fallback_enabled", old)


def test_get_fallback_reflects_setting(client):
    object.__setattr__(settings, "fallback_enabled", True)
    r = client.get("/admin/api-keys/fallback", headers=_AUTH)
    assert r.status_code == 200
    assert r.json() == {"enabled": True}
    object.__setattr__(settings, "fallback_enabled", False)
    assert client.get("/admin/api-keys/fallback", headers=_AUTH).json() == {"enabled": False}


def test_patch_fallback_on_updates_persists_and_gates(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(ak, "_update_env_file", lambda updates: captured.update(updates))
    object.__setattr__(settings, "fallback_enabled", False)

    r = client.patch("/admin/api-keys/fallback", json={"enabled": True}, headers=_AUTH)
    assert r.status_code == 200
    assert r.json() == {"success": True, "enabled": True}
    assert settings.fallback_enabled is True            # 内存即时生效
    assert captured == {"fallback_enabled": True}        # 持久化入参正确
    assert fallback.fallback_enabled() is True           # 运行时门控跟随


def test_patch_fallback_off(client, monkeypatch):
    monkeypatch.setattr(ak, "_update_env_file", lambda updates: None)
    object.__setattr__(settings, "fallback_enabled", True)
    r = client.patch("/admin/api-keys/fallback", json={"enabled": False}, headers=_AUTH)
    assert r.status_code == 200
    assert settings.fallback_enabled is False
    assert fallback.fallback_enabled() is False


def test_patch_fallback_invalid_body_422(client):
    r = client.patch("/admin/api-keys/fallback", json={"enabled": "notabool"}, headers=_AUTH)
    assert r.status_code == 422   # FastAPI/pydantic body 校验


def test_patch_fallback_persist_failure_rolls_back(client, monkeypatch):
    def boom(updates):
        raise OSError("disk full")
    monkeypatch.setattr(ak, "_update_env_file", boom)
    object.__setattr__(settings, "fallback_enabled", False)
    r = client.patch("/admin/api-keys/fallback", json={"enabled": True}, headers=_AUTH)
    assert r.status_code == 500
    assert settings.fallback_enabled is False   # 写盘失败 → 内存回滚，不留半更新
