"""动态请求头构建器 — 保证 UA/TLS/Sec-Ch-Ua 版本一致"""

from collections import OrderedDict

from app.core.fingerprint.config import fingerprint_config, FingerprintConfig


class HeaderBuilder:
    """根据指纹配置动态构建请求头，按 Chrome 真实顺序排列"""

    def build(
        self,
        *,
        url: str = "",
        method: str = "GET",
        content_type: str | None = None,
    ) -> OrderedDict:
        cfg = fingerprint_config.config
        headers = OrderedDict()

        for name in cfg.header_order:
            value = self._resolve_header(name, cfg, method, content_type)
            if value is not None:
                headers[name] = value

        return headers

    def get_impersonate_target(self) -> str:
        return fingerprint_config.config.chrome.impersonate_target

    def _resolve_header(
        self,
        name: str,
        cfg: FingerprintConfig,
        method: str,
        content_type: str | None,
    ) -> str | None:
        lower = name.lower()

        if lower == "user-agent":
            return self._build_ua(cfg)
        elif lower == "sec-ch-ua":
            return self._build_sec_ch_ua(cfg)
        elif lower == "sec-ch-ua-mobile":
            return "?0"
        elif lower == "sec-ch-ua-platform":
            return f'"{cfg.platform.os}"'
        elif lower == "origin":
            return "https://gemini.google.com"
        elif lower == "referer":
            return "https://gemini.google.com/"
        elif lower == "x-same-domain":
            return "1"
        elif lower == "sec-fetch-site":
            return "same-origin"
        elif lower == "sec-fetch-mode":
            return "cors" if method == "POST" else "navigate"
        elif lower == "sec-fetch-dest":
            return "empty" if method == "POST" else "document"
        elif lower == "content-type":
            return content_type
        elif lower in ("content-length", "host", "connection"):
            return None
        else:
            return cfg.headers.get(name)

    def _build_ua(self, cfg: FingerprintConfig) -> str:
        v = cfg.chrome.full
        os_str = f"{cfg.platform.os} NT {cfg.platform.os_version}; Win64; x64"
        return (
            f"Mozilla/5.0 ({os_str}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{v} Safari/537.36"
        )

    def _build_sec_ch_ua(self, cfg: FingerprintConfig) -> str:
        major = cfg.chrome.major
        return (
            f'"Google Chrome";v="{major}", '
            f'"Chromium";v="{major}", '
            f'"Not_A Brand";v="24"'
        )


header_builder = HeaderBuilder()
