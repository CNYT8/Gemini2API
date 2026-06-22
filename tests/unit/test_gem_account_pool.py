import asyncio
import types
import pytest
from unittest.mock import AsyncMock, patch
from app.core.account_pool import AccountPool


class _FakeClient:
    def __init__(self):
        self.calls = []

    async def list_gems(self):
        return [{"id": "g1", "name": "n", "description": "", "prompt": ""}]

    async def create_gem(self, name, prompt, description=""):
        return "new-id"

    async def generate(self, prompt, model, conversation_id="", attachments=None, gem_id=None):
        self.calls.append(("generate", prompt, model, gem_id))
        return {"text": "ok", "images": [], "conversation_id": "c1"}


def _pool_with_accounts():
    pool = AccountPool.__new__(AccountPool)
    a0 = types.SimpleNamespace(id="account-0", client=_FakeClient())
    a1 = types.SimpleNamespace(id="account-1", client=_FakeClient())
    pool._accounts = [a0, a1]
    return pool, a0, a1


def test_get_account_by_id():
    pool, a0, a1 = _pool_with_accounts()
    assert pool._get_account("account-1") is a1
    assert pool._get_account("nope") is None


def test_list_gems_routes_to_account():
    pool, a0, a1 = _pool_with_accounts()
    gems = asyncio.run(pool.list_gems("account-0"))
    assert gems[0]["id"] == "g1"


def test_list_gems_unknown_account_raises():
    pool, a0, a1 = _pool_with_accounts()
    with pytest.raises(ValueError):
        asyncio.run(pool.list_gems("ghost"))


def test_generate_pinned_account_passes_gem_id():
    pool, a0, a1 = _pool_with_accounts()

    # acquire/release をモック: account_id 固定のため acquire は必ず a1 を返すはず
    # AccountPool.__new__ で __init__ をスキップしているため acquire を直接差し替える
    async def _fake_acquire(exclude=None):
        # account_id="account-1" 固定時、exclude には account-0 が入るので a1 だけが候補
        # テストでは a1 を直接返す
        return a1

    async def _fake_release(account, success, cooldown=False):
        pass

    pool.acquire = _fake_acquire
    pool.release = _fake_release

    asyncio.run(pool.generate("hi", "gemini-pro", gem_id="g9", account_id="account-1"))
    # 只命中绑定账号 account-1，且带上 gem_id
    assert a1.client.calls == [("generate", "hi", "gemini-pro", "g9")]
    assert a0.client.calls == []
