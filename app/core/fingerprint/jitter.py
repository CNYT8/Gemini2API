"""请求时间抖动 — 模拟人类操作间隔，避免机器行为特征"""

import random
import asyncio

from app.config import settings

JITTER_PROFILES = {
    "navigation": (200, 800),
    "api_call": (50, 300),
    "cookie_rotate": (1000, 3000),
}


async def apply_jitter(profile: str = "api_call") -> None:
    """按场景应用随机延迟"""
    # 抖动开关关闭时直接返回，不再人为引入延迟（尊重 settings.jitter_enabled）
    if not settings.jitter_enabled:
        return
    min_ms, max_ms = JITTER_PROFILES.get(profile, (50, 200))
    delay = random.uniform(min_ms, max_ms) / 1000.0
    await asyncio.sleep(delay)


def random_delay_factor() -> float:
    """返回 0.8-1.2 之间的随机因子，用于调整固定间隔"""
    # 抖动关闭时返回 1.0，使固定间隔不被扰动
    if not settings.jitter_enabled:
        return 1.0
    return random.uniform(0.8, 1.2)
