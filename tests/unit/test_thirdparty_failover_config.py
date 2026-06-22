"""第三方故障切换冷却时长配置的默认值与 env 暴露。"""

from app.config import Settings


def test_cooldown_default_is_180():
    assert Settings().thirdparty_failover_cooldown == 180.0


def test_cooldown_field_exists():
    assert "thirdparty_failover_cooldown" in Settings.model_fields
