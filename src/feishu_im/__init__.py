"""Async Pythonic client for selected Feishu IM capabilities."""

__version__ = "0.1.0"

from feishu_im.config import FeishuConfig
from feishu_im.client import FeishuClient
from feishu_im.channel import EventChannel
from feishu_im.events import CardActionEvent, MessageEvent, OperatorIdentity, SenderIdentity
from feishu_im.exceptions import (
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
from feishu_im.models import (
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
from feishu_im.websocket import FeishuWebSocket

__all__ = [
    "BinaryResponse",
    "BotIdentity",
    "CardActionResponse",
    "CardUpdate",
    "CardActionEvent",
    "EventChannel",
    "FeishuApiError",
    "FeishuAuthError",
    "FeishuConfig",
    "FeishuClient",
    "FeishuError",
    "FeishuEventHandlerError",
    "FeishuEventParseError",
    "FeishuHttpStatusError",
    "FeishuProtocolError",
    "FeishuTransientError",
    "FeishuWebSocketError",
    "MessageReceipt",
    "MessageEvent",
    "OperatorIdentity",
    "OutboundMessage",
    "ReplyMessage",
    "SenderIdentity",
    "Toast",
    "UpdateMessage",
    "FeishuWebSocket",
    "__version__",
]
