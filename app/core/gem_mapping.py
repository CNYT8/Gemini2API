import copy
import json
import logging
from pathlib import Path
from typing import Dict

from app.core.gemini_models import DEFAULT_GEM_MODEL

logger = logging.getLogger(__name__)


class GemMapping:
    """持久化「模型名 -> {gem_id, base_model, account_id}」。
    存盘格式同 model-mapping.json（indent=2, ensure_ascii=False）。
    """

    def __init__(self, path: str = "data/gem-mapping.json"):
        self.path = Path(path)
        self.mappings: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.mappings = {
                    k: v for k, v in data.items()
                    if isinstance(v, dict) and v.get("gem_id")
                }
        except Exception as e:
            logger.warning(f"GemMapping load failed: {e}")
            self.mappings = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.mappings, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get_all(self) -> Dict[str, dict]:
        return copy.deepcopy(self.mappings)

    def set(self, name: str, info: dict) -> None:
        self.mappings[name] = {
            "gem_id": info.get("gem_id", ""),
            "base_model": info.get("base_model", DEFAULT_GEM_MODEL),
            "account_id": info.get("account_id", ""),
        }
        self._save()

    def delete(self, name: str) -> bool:
        if name in self.mappings:
            del self.mappings[name]
            self._save()
            return True
        return False

    def delete_by_gem(self, gem_id: str, account_id: str) -> list[str]:
        """删除所有指向同一个 (gem_id, account_id) 的模型映射，落盘，返回被删的模型名列表。
        用于删 Gem 时联动清理：避免留下指向失效 gem 的死模型。"""
        removed = [
            name for name, info in self.mappings.items()
            if info.get("gem_id") == gem_id and info.get("account_id") == account_id
        ]
        for name in removed:
            del self.mappings[name]
        if removed:
            self._save()
        return removed

    def resolve(self, name: str) -> dict | None:
        v = self.mappings.get(name)
        return copy.deepcopy(v) if v else None
