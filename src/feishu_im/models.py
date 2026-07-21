"""Typed data transfer objects for the public REST API."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type ReceiveIdType = Literal["chat_id", "open_id", "union_id", "user_id", "email"]


def _content_payload(content: Mapping[str, JsonValue]) -> str:
    return json.dumps(dict(content), ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    receive_id: str
    receive_id_type: ReceiveIdType
    msg_type: str
    content: Mapping[str, JsonValue]
    uuid: str | None = None

    def to_payload(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "receive_id": self.receive_id,
            "msg_type": self.msg_type,
            "content": _content_payload(self.content),
        }
        if self.uuid is not None:
            payload["uuid"] = self.uuid
        return payload


@dataclass(frozen=True, slots=True)
class ReplyMessage:
    message_id: str
    msg_type: str
    content: Mapping[str, JsonValue]
    reply_in_thread: bool = False
    uuid: str | None = None

    def to_payload(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "msg_type": self.msg_type,
            "content": _content_payload(self.content),
            "reply_in_thread": self.reply_in_thread,
        }
        if self.uuid is not None:
            payload["uuid"] = self.uuid
        return payload


@dataclass(frozen=True, slots=True)
class UpdateMessage:
    message_id: str
    msg_type: str
    content: Mapping[str, JsonValue]

    def to_payload(self) -> dict[str, JsonValue]:
        return {"msg_type": self.msg_type, "content": _content_payload(self.content)}


@dataclass(frozen=True, slots=True)
class MessageReceipt:
    message_id: str
    root_id: str | None = None
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class BotIdentity:
    open_id: str


@dataclass(frozen=True, slots=True)
class ApiResponse:
    data: Mapping[str, JsonValue]
    headers: Mapping[str, str]
    status_code: int
    request_id: str | None


@dataclass(frozen=True, slots=True)
class BinaryResponse:
    content: bytes
    filename: str | None
    content_type: str | None
    headers: Mapping[str, str]
    request_id: str | None


@dataclass(frozen=True, slots=True)
class Toast:
    kind: str
    content: str

    def to_payload(self) -> dict[str, JsonValue]:
        return {"type": self.kind, "content": self.content}


@dataclass(frozen=True, slots=True)
class CardUpdate:
    kind: str
    data: Mapping[str, JsonValue]

    def to_payload(self) -> dict[str, JsonValue]:
        return {"type": self.kind, "data": dict(self.data)}


@dataclass(frozen=True, slots=True)
class CardActionResponse:
    toast: Toast | None = None
    card: CardUpdate | None = None

    def to_payload(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {}
        if self.toast is not None:
            payload["toast"] = self.toast.to_payload()
        if self.card is not None:
            payload["card"] = self.card.to_payload()
        return payload
