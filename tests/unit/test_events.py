from datetime import UTC, datetime
from pathlib import Path

import pytest

from feishulib.events import CardActionEvent, MessageEvent, parse_event_payload
from feishulib.exceptions import FeishuEventParseError


def test_message_receive_parses_text_and_sender_identity() -> None:
    event = parse_event_payload(Path("tests/fixtures/message_receive.json").read_bytes())
    assert isinstance(event, MessageEvent)
    assert event.message_id == "om_message"
    assert event.sender.open_id == "ou_sender"
    assert event.text == "hello"
    assert event.create_time == datetime(2026, 7, 21, 6, 30, tzinfo=UTC)
    assert event.raw_header["tenant_key"] == "tenant_1"
    assert event.raw_event["message"] == {
        "message_id": "om_message",
        "chat_id": "oc_chat",
        "chat_type": "group",
        "message_type": "text",
        "content": '{"text":"hello"}',
    }


def test_card_action_uses_callback_operator_not_action_value() -> None:
    event = parse_event_payload(Path("tests/fixtures/card_action.json").read_bytes())
    assert isinstance(event, CardActionEvent)
    assert event.operator.open_id == "ou_verified"
    assert event.action_value["open_id"] == "ou_forged"
    assert event.operator.open_id != event.action_value["open_id"]
    assert event.create_time == datetime(2026, 7, 21, 6, 30, 0, 123000, tzinfo=UTC)
    assert event.raw_header["tenant_key"] == "tenant_card"
    assert event.raw_event["operator"] == {"open_id": "ou_verified"}


def test_event_with_invalid_create_time_preserves_existing_parse_behavior() -> None:
    payload = b'{"schema":"2.0","header":{"event_type":"im.message.receive_v1","create_time":"not-a-timestamp"},"event":{"sender":{"sender_id":{"open_id":"ou_sender"}},"message":{"message_id":"om_message","content":"{\\"text\\":\\"hello\\"}"}}}'
    event = parse_event_payload(payload)
    assert isinstance(event, MessageEvent)
    assert event.create_time is None


def test_card_action_without_callback_operator_open_id_is_rejected() -> None:
    payload = b'{"schema":"2.0","header":{"event_type":"card.action.trigger"},"event":{"operator":{},"action":{"value":{}}}}'
    with pytest.raises(FeishuEventParseError):
        parse_event_payload(payload)
