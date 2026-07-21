"""Runtime configuration for the Feishu IM client."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    base_url: str = "https://open.feishu.cn"
    request_timeout_seconds: float = 10.0
    max_retries: int = 3
    retry_backoff_base_seconds: float = 0.5
    retry_max_delay_seconds: float = 15.0
    retry_jitter_ratio: float = 0.1
    token_refresh_skew_seconds: float = 60.0
    ws_open_timeout_seconds: float = 15.0
    ws_close_timeout_seconds: float = 10.0
    ws_ping_timeout_seconds: float = 180.0
    ws_reconnect_base_seconds: float = 1.0
    ws_reconnect_max_seconds: float = 60.0
    ws_reconnect_jitter_ratio: float = 0.1
    event_queue_size: int = 100
    event_worker_count: int = 1
    card_action_timeout_seconds: float = 8.0

    def __post_init__(self) -> None:
        if not self.app_id:
            raise ValueError("app_id must not be empty")
        if not self.app_secret:
            raise ValueError("app_secret must not be empty")
        if not self.base_url.startswith("https://"):
            raise ValueError("base_url must use https")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_backoff_base_seconds <= 0 or self.retry_max_delay_seconds <= 0:
            raise ValueError("retry delays must be positive")
        if not 0 <= self.retry_jitter_ratio <= 1:
            raise ValueError("retry_jitter_ratio must be between 0 and 1")
        if self.token_refresh_skew_seconds < 0:
            raise ValueError("token_refresh_skew_seconds must be non-negative")
        if self.ws_open_timeout_seconds <= 0 or self.ws_close_timeout_seconds <= 0:
            raise ValueError("websocket timeouts must be positive")
        if self.ws_ping_timeout_seconds <= 0:
            raise ValueError("ws_ping_timeout_seconds must be positive")
        if self.ws_reconnect_base_seconds <= 0 or self.ws_reconnect_max_seconds <= 0:
            raise ValueError("websocket reconnect delays must be positive")
        if not 0 <= self.ws_reconnect_jitter_ratio <= 1:
            raise ValueError("ws_reconnect_jitter_ratio must be between 0 and 1")
        if self.event_queue_size < 1 or self.event_worker_count < 1:
            raise ValueError("event queue size and worker count must be positive")
        if self.card_action_timeout_seconds <= 0:
            raise ValueError("card_action_timeout_seconds must be positive")
