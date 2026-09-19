"""Async Pythonic client for selected Feishu IM capabilities."""

from importlib.metadata import PackageNotFoundError, version

from feishulib.channel import EventChannel
from feishulib.client import FeishuClient
from feishulib.config import FeishuConfig
from feishulib.events import (
    CardActionEvent,
    MessageEvent,
    OperatorIdentity,
    SenderIdentity,
)
from feishulib.exceptions import (
    FeishuApiError,
    FeishuAuthError,
    FeishuError,
    FeishuEventHandlerError,
    FeishuEventParseError,
    FeishuHttpStatusError,
    FeishuProtocolError,
    FeishuTransientError,
    FeishuWebSocketError,
)
from feishulib.models import (
    BinaryResponse,
    BotIdentity,
    CardActionResponse,
    CardUpdate,
    MessageReceipt,
    OutboundMessage,
    ReplyMessage,
    Toast,
    UpdateMessage,
)
from feishulib.websocket import FeishuWebSocket

try:
    __version__ = version("feishulib")
except PackageNotFoundError:  # pragma: no cover - source tree without installed distribution metadata
    __version__ = "0.0.0"

__all__ = [
    "BinaryResponse",
    "BotIdentity",
    "CardActionEvent",
    "CardActionResponse",
    "CardUpdate",
    "EventChannel",
    "FeishuApiError",
    "FeishuAuthError",
    "FeishuClient",
    "FeishuConfig",
    "FeishuError",
    "FeishuEventHandlerError",
    "FeishuEventParseError",
    "FeishuHttpStatusError",
    "FeishuProtocolError",
    "FeishuTransientError",
    "FeishuWebSocket",
    "FeishuWebSocketError",
    "MessageEvent",
    "MessageReceipt",
    "OperatorIdentity",
    "OutboundMessage",
    "ReplyMessage",
    "SenderIdentity",
    "Toast",
    "UpdateMessage",
    "__version__",
]
