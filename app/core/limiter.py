"""共享限流器实例。

独立模块，供 app.main 与各业务路由共同导入，避免 main ↔ routers 循环导入。
默认 settings.rate_limit_enabled=False：限流装饰器经 exempt_when 全部旁路，
行为与未挂限流前完全一致（零回归）。仅当运维显式开启后才按 rate_limit_max/window 生效。
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def _client_ip_key(request) -> str:
    """限流 key 取「真实客户端 IP」。

    本服务常部署在反向代理（Nginx/Cloudflare）之后，此时 get_remote_address
    取到的是上游代理的单一 IP，会把所有真实客户端的计数合并成全局计数
    （一个客户端就能把别人的额度耗尽）。

    仅当运维显式信任代理（环境变量 TRUST_PROXY_HEADERS=1/true/yes）时，才从
    X-Forwarded-For（取首段=最初客户端）/ X-Real-IP 头解析真实 IP；这些头可被
    客户端伪造，故默认（未设此开关）保持原行为：直接用 TCP 对端地址，零回归、
    不破坏默认部署。
    """
    if os.environ.get("TRUST_PROXY_HEADERS", "").strip().lower() in ("1", "true", "yes"):
        try:
            xff = request.headers.get("x-forwarded-for")
            if xff:
                # XFF 形如 "client, proxy1, proxy2"，第一段是最初的客户端
                first = xff.split(",")[0].strip()
                if first:
                    return first
            xri = request.headers.get("x-real-ip")
            if xri and xri.strip():
                return xri.strip()
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip_key)


def dynamic_rate_limit() -> str:
    """运行时动态限流值（每请求求值），格式 "<max>/<window> second"。

    用 callable 而非常量，使面板在线修改 rate_limit_max/window 后即时生效。
    """
    return f"{settings.rate_limit_max}/{settings.rate_limit_window} second"


def rate_limit_exempt(*args, **kwargs) -> bool:
    """限流未开启时旁路（默认 rate_limit_enabled=False → 返回 True → 不计数、不限流）。"""
    return not settings.rate_limit_enabled
