"""Drift guard: `.env.example` must stay in sync with `app.config.Settings`.

This is the regression test for the audit finding where config defaults and the
documented env surface drifted apart (e.g. MAX_CONCURRENT_PER_ACCOUNT, and a dozen
newer vars missing from .env.example). If a new Settings field is added without a
corresponding .env.example entry (or vice versa), this test fails so docs can't
silently fall behind the code again.
"""

import re
from pathlib import Path

from app.config import Settings

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"


def _env_example_keys() -> set[str]:
    keys: set[str] = set()
    for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Z0-9_]+)=", line)
        if m:
            keys.add(m.group(1))
    return keys


def test_env_example_matches_settings_fields():
    field_keys = {name.upper() for name in Settings.model_fields}
    env_keys = _env_example_keys()

    missing_in_env = field_keys - env_keys
    stale_in_env = env_keys - field_keys

    assert not missing_in_env, (
        "Settings fields missing from .env.example: " + ", ".join(sorted(missing_in_env))
    )
    assert not stale_in_env, (
        ".env.example keys with no matching Settings field: " + ", ".join(sorted(stale_in_env))
    )
