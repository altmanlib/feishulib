import pytest

from feishu_im.config import FeishuConfig


def test_config_has_safe_operational_defaults() -> None:
    config = FeishuConfig(app_id="cli_test", app_secret="secret")

    assert config.base_url == "https://open.feishu.cn"
    assert config.request_timeout_seconds == 10.0
    assert config.token_refresh_skew_seconds == 60.0
    assert config.max_retries == 3
    assert config.ws_ping_timeout_seconds == 180.0


@pytest.mark.parametrize(
    ("field", "value"),
    [("request_timeout_seconds", 0), ("max_retries", -1), ("retry_jitter_ratio", 1.1)],
)
def test_config_rejects_invalid_operational_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        FeishuConfig(app_id="cli_test", app_secret="secret", **{field: value})  # type: ignore[arg-type]
