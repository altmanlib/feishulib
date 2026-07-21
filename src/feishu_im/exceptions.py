"""Explicit exceptions raised by the Feishu IM client."""


class FeishuError(Exception):
    """Base exception for all client failures."""


class FeishuAuthError(FeishuError):
    """Tenant access token retrieval or validation failed."""


class FeishuApiError(FeishuError):
    """The Feishu API returned a non-zero business code."""

    def __init__(self, code: int, message: str, request_id: str | None = None) -> None:
        self.code = code
        self.message = message
        self.request_id = request_id
        super().__init__(f"Feishu API error {code}: {message}")


class FeishuHttpStatusError(FeishuError):
    """An HTTP response had a non-success status."""

    def __init__(self, status_code: int, message: str, request_id: str | None = None) -> None:
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        super().__init__(f"Feishu HTTP status {status_code}: {message}")


class FeishuTransientError(FeishuError):
    """A retryable transport or HTTP failure exhausted its retry budget."""

    def __init__(self, status_code: int | None, attempts: int, request_id: str | None = None) -> None:
        self.status_code = status_code
        self.attempts = attempts
        self.request_id = request_id
        super().__init__(f"Feishu transient failure after {attempts} attempts")


class FeishuProtocolError(FeishuError):
    """A remote response did not match the expected protocol."""


class FeishuWebSocketError(FeishuError):
    """A WebSocket connection or frame exchange failed."""


class FeishuEventParseError(FeishuError):
    """An incoming event could not be parsed safely."""


class FeishuEventHandlerError(FeishuError):
    """An event handler failed or event dispatch could not proceed."""

    def __init__(self, event_type: str, cause: BaseException) -> None:
        self.event_type = event_type
        self.cause = cause
        super().__init__(f"Feishu event handler failed for {event_type}: {cause}")
