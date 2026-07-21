import pytest

from feishu_im.config import FeishuConfig


def test_config_repr_does_not_expose_app_secret() -> None:
    config = FeishuConfig(app_id="cli_test", app_secret="secret-value")

    assert "cli_test" in repr(config)
    assert "secret-value" not in repr(config)


def test_config_has_safe_operational_defaults() -> None:
    config = FeishuConfig(app_id="cli_test", app_secret="secret")

    assert config.base_url == "https://open.feishu.cn"
    assert config.request_timeout_seconds == 10.0
    assert config.token_refresh_skew_seconds == 60.0
    assert config.max_retries == 3
    assert config.ws_ping_timeout_seconds == 180.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_id", ""), ("app_secret", ""), ("base_url", "http://example.test"),
        ("request_timeout_seconds", 0), ("max_retries", -1), ("retry_backoff_base_seconds", 0),
        ("retry_max_delay_seconds", 0), ("retry_jitter_ratio", 1.1),
        ("token_refresh_skew_seconds", -1), ("ws_open_timeout_seconds", 0),
        ("ws_ping_timeout_seconds", 0), ("ws_reconnect_base_seconds", 0),
        ("ws_reconnect_jitter_ratio", 1.1), ("event_queue_size", 0),
        ("card_action_timeout_seconds", 0),
    ],
)
def test_config_rejects_invalid_operational_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        options: dict[str, object] = {"app_id": "cli_test", "app_secret": "secret"}
        options[field] = value
        FeishuConfig(**options)  # type: ignore[arg-type]
