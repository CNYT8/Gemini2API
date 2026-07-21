"""指纹配置管理 — 加载、验证、热更新"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

from app.config import settings
from app.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("data/fingerprint.json")


@dataclass
class ChromeVersion:
    major: int
    full: str
    impersonate_target: str


@dataclass
class PlatformInfo:
    os: str = "Windows"
    os_version: str = "10.0"
    arch: str = "x86_64"


@dataclass
class FingerprintConfig:
    chrome: ChromeVersion
    platform: PlatformInfo
    header_order: list[str]
    headers: dict[str, str]
    version_map: dict[str, str]
    last_updated: str = ""


class FingerprintConfigManager:
    """线程安全的指纹配置管理器，支持热更新"""

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self._path = config_path
        self._config: FingerprintConfig | None = None
        self._lock = Lock()

    def load(self) -> FingerprintConfig:
        data = None
        if self._path.exists():
            # 读容错：损坏/截断的配置文件不应让客户端初始化崩溃；
            # 解析失败时回退到默认配置并原子重写（参考 cookie_jar VULN-010 读容错）
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"指纹配置损坏，回退默认配置: {e}")
                data = None
        if data is None:
            data = self._default_data()
            self._save(data)
            logger.info(f"已生成默认指纹配置: {self._path}")

        # 结构容错：即使 JSON 合法，缺字段/结构异常也不应让客户端初始化崩溃，
        # 解析失败同样回退默认配置并原子重写
        try:
            parsed = self._parse(data)
        except Exception as e:
            logger.warning(f"指纹配置结构异常，回退默认配置: {e}")
            data = self._default_data()
            self._save(data)
            parsed = self._parse(data)

        with self._lock:
            self._config = parsed
        logger.info(
            f"指纹配置已加载: Chrome {self._config.chrome.major} "
            f"({self._config.chrome.impersonate_target})"
        )
        return self._config

    @property
    def config(self) -> FingerprintConfig:
        if self._config is None:
            return self.load()
        return self._config

    def update_chrome_version(self, major: int, full: str) -> bool:
        with self._lock:
            if self._config.chrome.major == major:
                return False
            target = self._config.version_map.get(str(major))
            if not target:
                logger.warning(f"Chrome {major} 无对应 impersonate target，跳过更新")
                return False
            self._config.chrome = ChromeVersion(
                major=major, full=full, impersonate_target=target
            )
            self._config.last_updated = datetime.now(timezone.utc).isoformat()
        self._persist()
        logger.info(f"指纹配置已更新: Chrome {major} -> {target}")
        return True

    def _persist(self):
        data = self._serialize()
        self._save(data)

    def _save(self, data: dict):
        # 原子落盘（临时文件 + os.replace），避免后台版本同步写入中途崩溃/断电
        # 导致 fingerprint.json 被截断成半截 JSON（VULN-010）
        atomic_write_json(self._path, data, indent=2, ensure_ascii=False)

    def _parse(self, data: dict) -> FingerprintConfig:
        cv = data["chrome_version"]
        pf = data.get("platform", {})
        return FingerprintConfig(
            chrome=ChromeVersion(
                major=cv["major"],
                full=cv["full"],
                impersonate_target=cv["impersonate_target"],
            ),
            platform=PlatformInfo(
                os=pf.get("os", "Windows"),
                os_version=pf.get("os_version", "10.0"),
                arch=pf.get("arch", "x86_64"),
            ),
            header_order=data.get("header_order", []),
            headers=data.get("headers", {}),
            version_map=data.get("version_map", {}),
            last_updated=data.get("last_updated", ""),
        )

    def _serialize(self) -> dict:
        c = self._config
        return {
            "chrome_version": {
                "major": c.chrome.major,
                "full": c.chrome.full,
                "impersonate_target": c.chrome.impersonate_target,
            },
            "platform": {
                "os": c.platform.os,
                "os_version": c.platform.os_version,
                "arch": c.platform.arch,
            },
            "header_order": c.header_order,
            "headers": c.headers,
            "version_map": c.version_map,
            "last_updated": c.last_updated,
        }

    def _default_data(self) -> dict:
        return {
            "chrome_version": {
                "major": 124,
                "full": "124.0.6367.91",
                "impersonate_target": "chrome124",
            },
            "platform": {
                "os": "Windows",
                "os_version": "10.0",
                "arch": "x86_64",
            },
            "header_order": [
                "sec-ch-ua",
                "sec-ch-ua-mobile",
                "sec-ch-ua-platform",
                "User-Agent",
                "X-Same-Domain",
                "Origin",
                "Sec-Fetch-Site",
                "Sec-Fetch-Mode",
                "Sec-Fetch-Dest",
                "Referer",
                "Accept-Encoding",
                "Accept-Language",
            ],
            "headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br, zstd",
            },
            "version_map": {
                "119": "chrome119",
                "120": "chrome120",
                "123": "chrome123",
                "124": "chrome124",
            },
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }


# 尊重 settings.fingerprint_config_path，而非硬编码 DEFAULT_CONFIG_PATH
fingerprint_config = FingerprintConfigManager(Path(settings.fingerprint_config_path))
