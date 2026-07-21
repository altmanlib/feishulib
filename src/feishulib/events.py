"""Schema 2.0 event parsing with an explicit trusted identity boundary."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from feishulib.exceptions import FeishuEventParseError
from feishulib.models import JsonValue


@dataclass(frozen=True, slots=True)
class SenderIdentity:
    open_id: str | None
    user_id: str | None
    union_id: str | None


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    tenant_key: str | None
    user_id: str | None
    open_id: str
    union_id: str | None


@dataclass(frozen=True, slots=True)
class MessageEvent:
    event_id: str | None
    sender: SenderIdentity
    message_id: str
    chat_id: str | None
    chat_type: str | None
    message_type: str | None
    raw_content: str | None
    content: Mapping[str, JsonValue] | None
    text: str | None
    file_key: str | None
    root_id: str | None
    parent_id: str | None


@dataclass(frozen=True, slots=True)
class CardActionEvent:
    event_id: str | None
    operator: OperatorIdentity
    action_value: Mapping[str, JsonValue]
    action_tag: str | None
    action_name: str | None
    form_value: Mapping[str, JsonValue] | None
    token: str | None
    message_id: str | None
    chat_id: str | None


def parse_event_payload(payload: bytes) -> MessageEvent | CardActionEvent:
    """Parse one trusted Feishu schema 2.0 event payload."""
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FeishuEventParseError("event payload is not valid UTF-8 JSON") from error
    if not isinstance(body, Mapping):
        raise FeishuEventParseError("event schema must be 2.0")
    envelope = cast(Mapping[str, object], body)
    if envelope.get("schema") != "2.0":
        raise FeishuEventParseError("event schema must be 2.0")
    header = _mapping(envelope.get("header"), "header")
    event_type = header.get("event_type")
    if not isinstance(event_type, str):
        raise FeishuEventParseError("header.event_type must be a string")
    event = _mapping(envelope.get("event"), "event", event_type)
    if event_type == "im.message.receive_v1":
        return _message_event(header, event)
    if event_type == "card.action.trigger":
        return _card_event(header, event)
    raise FeishuEventParseError(f"{event_type}: unsupported event type")


def _message_event(header: Mapping[str, object], event: Mapping[str, object]) -> MessageEvent:
    message = _mapping(event.get("message"), "event.message", "im.message.receive_v1")
    sender = _mapping(event.get("sender"), "event.sender", "im.message.receive_v1")
    ids = _mapping(sender.get("sender_id"), "event.sender.sender_id", "im.message.receive_v1")
    message_id = message.get("message_id")
    if not isinstance(message_id, str) or not message_id:
        raise FeishuEventParseError("im.message.receive_v1: event.message.message_id is required")
    raw_content = message.get("content")
    raw = raw_content if isinstance(raw_content, str) else None
    content = _content(raw)
    text = content.get("text") if content is not None else None
    file_key = content.get("file_key") if content is not None else None
    return MessageEvent(
        _optional_str(header.get("event_id")),
        SenderIdentity(_optional_str(ids.get("open_id")), _optional_str(ids.get("user_id")), _optional_str(ids.get("union_id"))),
        message_id,
        _optional_str(message.get("chat_id")),
        _optional_str(message.get("chat_type")),
        _optional_str(message.get("message_type")),
        raw,
        content,
        text if isinstance(text, str) else None,
        file_key if isinstance(file_key, str) else None,
        _optional_str(message.get("root_id")),
        _optional_str(message.get("parent_id")),
    )


def _card_event(header: Mapping[str, object], event: Mapping[str, object]) -> CardActionEvent:
    operator = _mapping(event.get("operator"), "event.operator", "card.action.trigger")
    open_id = operator.get("open_id")
    if not isinstance(open_id, str) or not open_id:
        raise FeishuEventParseError("card.action.trigger: event.operator.open_id is required")
    action = _mapping(event.get("action"), "event.action", "card.action.trigger")
    value = action.get("value", {})
    action_value = cast(Mapping[str, JsonValue], _mapping(value, "event.action.value", "card.action.trigger"))
    form_value = action.get("form_value")
    return CardActionEvent(
        _optional_str(header.get("event_id")),
        OperatorIdentity(_optional_str(operator.get("tenant_key")), _optional_str(operator.get("user_id")), open_id, _optional_str(operator.get("union_id"))),
        dict(action_value),
        _optional_str(action.get("tag")),
        _optional_str(action.get("name")),
        cast(Mapping[str, JsonValue], form_value) if isinstance(form_value, Mapping) else None,
        _optional_str(event.get("token")),
        _optional_str(event.get("open_message_id")),
        _optional_str(event.get("open_chat_id")),
    )


def _content(raw_content: str | None) -> Mapping[str, JsonValue] | None:
    if raw_content is None:
        return None
    try:
        value = json.loads(raw_content)
    except json.JSONDecodeError:
        return None
    return cast(Mapping[str, JsonValue], value) if isinstance(value, Mapping) else None


def _mapping(value: object, field: str, event_type: str = "event") -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FeishuEventParseError(f"{event_type}: {field} must be an object")
    return cast(Mapping[str, object], value)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
