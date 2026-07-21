import asyncio
import types
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, patch
from app.core.account_pool import Account, AccountPool, AccountStatus, RotationStrategy


class _FakeClient:
    def __init__(self):
        self.calls = []

    async def list_gems(self):
        return [{"id": "g1", "name": "n", "description": "", "prompt": ""}]

    async def create_gem(self, name, prompt, description=""):
        return "new-id"

    async def update_gem(self, gem_id, name, prompt, description=""):
        self.calls.append(("update_gem", gem_id, name, prompt, description))
        return True

    async def delete_gem(self, gem_id):
        self.calls.append(("delete_gem", gem_id))
        return True

    async def generate(self, prompt, model, conversation_id="", attachments=None, gem_id=None):
        self.calls.append(("generate", prompt, model, gem_id))
        return {"text": "ok", "images": [], "conversation_id": "c1"}

    async def generate_stream(self, prompt, model, conversation_id="", attachments=None, gem_id=None):
        self.calls.append(("generate_stream", prompt, model, gem_id))
        yield {"type": "delta", "text": "hello"}
        yield {"type": "final", "text": "hello", "images": [], "conversation_id": "c2"}


def _pool_with_accounts():
    pool = AccountPool.__new__(AccountPool)
    a0 = types.SimpleNamespace(id="account-0", client=_FakeClient())
    a1 = types.SimpleNamespace(id="account-1", client=_FakeClient())
    pool._accounts = [a0, a1]
    pool._cond = asyncio.Condition()
    pool._session_affinity = OrderedDict()
    return pool, a0, a1


def _schedulable_account(account_id: str, active_requests: int = 0, last_used=None):
    account = Account(
        id=account_id,
        status=AccountStatus.ACTIVE,
        active_requests=active_requests,
        last_used=last_used,
    )
    account.client = types.SimpleNamespace(is_healthy=True)
    return account


def test_get_account_by_id():
    pool, a0, a1 = _pool_with_accounts()
    assert pool._get_account("account-1") is a1
    assert pool._get_account("nope") is None


def test_round_robin_prefers_lowest_load_then_lru():
    pool = AccountPool()
    now = datetime.now(timezone.utc)
    busy = _schedulable_account("account-0", active_requests=6, last_used=now - timedelta(minutes=5))
    recent = _schedulable_account("account-1", active_requests=1, last_used=now)
    oldest = _schedulable_account("account-2", active_requests=1, last_used=now - timedelta(minutes=10))
    pool._accounts = [busy, recent, oldest]
    pool._strategy = RotationStrategy.ROUND_ROBIN
    pool._max_concurrent = 8

    assert pool._find_available() is oldest


def test_round_robin_keeps_completed_request_counts_even():
    async def run():
        pool = AccountPool()
        pool._max_concurrent = 4
        pool._accounts = [
            _schedulable_account("account-0"),
            _schedulable_account("account-1"),
            _schedulable_account("account-2"),
        ]
        for _ in range(30):
            selected = await pool.acquire()
            await pool.release(selected, success=True)
        return [account.request_count for account in pool._accounts]

    assert asyncio.run(run()) == [10, 10, 10]


def test_failover_strategy_keeps_original_fixed_order():
    pool = AccountPool()
    first = _schedulable_account("account-0", active_requests=7)
    second = _schedulable_account("account-1", active_requests=0)
    pool._accounts = [first, second]
    pool._strategy = RotationStrategy.FAILOVER
    pool._max_concurrent = 8

    assert pool._find_available() is first


def test_session_affinity_waits_for_bound_account_instead_of_switching():
    async def run():
        pool = AccountPool()
        pool._max_concurrent = 1
        pool._acquire_timeout = 1
        bound = _schedulable_account("account-0", active_requests=1)
        idle = _schedulable_account("account-1", active_requests=0)
        pool._accounts = [bound, idle]
        await pool._bind_session_affinity("conversation-1", bound.id)

        waiting = asyncio.create_task(pool.acquire(affinity_key="conversation-1"))
        await asyncio.sleep(0)
        assert not waiting.done()

        await pool.release(bound, success=None)
        selected = await asyncio.wait_for(waiting, timeout=1)
        assert selected is bound
        await pool.release(selected, success=None)

    asyncio.run(run())


def test_generated_conversation_is_bound_to_selected_account():
    class _ConversationClient:
        is_healthy = True

        async def generate(self, *args, **kwargs):
            return {"text": "ok", "images": [], "conversation_id": "conversation-new"}

    async def run():
        pool = AccountPool()
        first = _schedulable_account("account-0")
        second = _schedulable_account("account-1")
        first.client = _ConversationClient()
        second.client = _ConversationClient()
        pool._accounts = [first, second]

        await pool.generate("hi", "gemini-pro")
        bound_id = pool._session_affinity["conversation-new"][0]
        bound = await pool.acquire(affinity_key="conversation-new")
        assert bound.id == bound_id
        await pool.release(bound, success=None)

    asyncio.run(run())


def test_remove_account_clears_session_affinity(tmp_path, monkeypatch):
    class _Client:
        is_healthy = True

        async def shutdown(self):
            return None

    from app.core import account_pool as account_pool_module

    async def run():
        pool = AccountPool()
        account = _schedulable_account("account-0")
        account.client = _Client()
        pool._accounts = [account]
        monkeypatch.setattr(
            account_pool_module.settings,
            "accounts_file",
            str(tmp_path / "accounts.json"),
        )
        await pool._bind_session_affinity("conversation-1", account.id)

        assert await pool.remove_account(account.id) is True
        assert "conversation-1" not in pool._session_affinity

    asyncio.run(run())


def test_list_gems_routes_to_account():
    pool, a0, a1 = _pool_with_accounts()
    gems = asyncio.run(pool.list_gems("account-0"))
    assert gems[0]["id"] == "g1"


def test_list_gems_unknown_account_raises():
    pool, a0, a1 = _pool_with_accounts()
    with pytest.raises(ValueError):
        asyncio.run(pool.list_gems("ghost"))


def test_generate_pinned_account_passes_gem_id():
    """验证锁定逻辑：account_id 固定时，acquire 收到的 exclude 应包含其他所有账号 id。"""
    pool, a0, a1 = _pool_with_accounts()

    # 记录 acquire 被调用时的 exclude 参数
    received_excludes = []

    async def _fake_acquire(exclude=None):
        received_excludes.append(exclude)
        return a1

    async def _fake_release(account, success, cooldown=False):
        pass

    pool.acquire = _fake_acquire
    pool.release = _fake_release

    asyncio.run(pool.generate("hi", "gemini-pro", gem_id="g9", account_id="account-1"))

    # 1. 只命中绑定账号 account-1，且带上 gem_id
    assert a1.client.calls == [("generate", "hi", "gemini-pro", "g9")]
    assert a0.client.calls == []

    # 2. 验证锁定逻辑：acquire 收到的 exclude 应包含除 account-1 之外的所有账号（即 account-0）
    assert len(received_excludes) == 1
    assert received_excludes[0] == {"account-0"}


def test_generate_unknown_account_raises():
    """account_id 不存在时应立即抛出 ValueError，不调用 acquire。"""
    pool, a0, a1 = _pool_with_accounts()

    acquire_called = []

    async def _fake_acquire(exclude=None):
        acquire_called.append(True)
        return a0

    pool.acquire = _fake_acquire

    with pytest.raises(ValueError):
        asyncio.run(pool.generate("hi", "gemini-pro", account_id="no-such-account"))

    # acquire 不应被调用
    assert acquire_called == []


def test_generate_stream_pinned_account_passes_gem_id():
    """流式版本：验证 gem_id 透传 + exclude 预填锁定逻辑。"""
    pool, a0, a1 = _pool_with_accounts()

    received_excludes = []

    async def _fake_acquire(exclude=None):
        received_excludes.append(exclude)
        return a1

    async def _fake_release(account, success, cooldown=False):
        pass

    pool.acquire = _fake_acquire
    pool.release = _fake_release

    async def _collect():
        events = []
        async for evt in pool.generate_stream("hi", "gemini-pro", gem_id="g7", account_id="account-1"):
            events.append(evt)
        return events

    events = asyncio.run(_collect())

    # 1. gem_id 透传到目标账号 client
    assert a1.client.calls == [("generate_stream", "hi", "gemini-pro", "g7")]
    assert a0.client.calls == []

    # 2. 收到了流式事件
    assert any(e.get("type") == "delta" for e in events)

    # 3. 锁定逻辑：exclude 包含除 account-1 外的所有账号
    assert len(received_excludes) == 1
    assert received_excludes[0] == {"account-0"}


def test_generate_stream_empty_account_fails_over_without_expiring():
    class _EmptyClient:
        async def generate_stream(self, *args, **kwargs):
            yield {"type": "final", "text": "", "images": [], "conversation_id": ""}

    class _HealthyClient:
        async def generate_stream(self, *args, **kwargs):
            yield {"type": "delta", "text": "ok"}
            yield {"type": "final", "text": "ok", "images": [], "conversation_id": ""}

    pool = AccountPool.__new__(AccountPool)
    first = types.SimpleNamespace(id="account-0", client=_EmptyClient())
    second = types.SimpleNamespace(id="account-1", client=_HealthyClient())
    pool._accounts = [first, second]
    releases = []

    async def _fake_acquire(exclude=None):
        return second if exclude and first.id in exclude else first

    async def _fake_release(account, success, cooldown=False):
        releases.append((account.id, success, cooldown))

    pool.acquire = _fake_acquire
    pool.release = _fake_release

    async def _collect():
        return [event async for event in pool.generate_stream("hi", "gemini-pro")]

    events = asyncio.run(_collect())
    assert events[0] == {"type": "delta", "text": "ok"}
    assert releases == [
        ("account-0", False, True),
        ("account-1", True, False),
    ]


def test_neutral_release_does_not_change_account_health():
    pool = AccountPool.__new__(AccountPool)
    pool._cond = asyncio.Condition()
    account = types.SimpleNamespace(
        id="account-0",
        active_requests=1,
        request_count=2,
        error_count=3,
        consecutive_failures=2,
        cooldown_until=0.0,
        status="active",
    )

    asyncio.run(pool.release(account, success=None))

    assert account.active_requests == 0
    assert account.request_count == 3
    assert account.error_count == 3
    assert account.consecutive_failures == 2
    assert account.status == "active"


def test_update_gem_routes_to_account():
    """update_gem 应路由到指定账号的 client。"""
    pool, a0, a1 = _pool_with_accounts()
    result = asyncio.run(pool.update_gem("account-1", "gem-x", "MyGem", "do stuff", "desc"))
    assert result is True
    assert a1.client.calls == [("update_gem", "gem-x", "MyGem", "do stuff", "desc")]
    assert a0.client.calls == []


def test_delete_gem_routes_to_account():
    """delete_gem 应路由到指定账号的 client。"""
    pool, a0, a1 = _pool_with_accounts()
    result = asyncio.run(pool.delete_gem("account-0", "gem-y"))
    assert result is True
    assert a0.client.calls == [("delete_gem", "gem-y")]
    assert a1.client.calls == []
