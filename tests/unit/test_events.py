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


def test_card_action_uses_callback_operator_not_action_value() -> None:
    event = parse_event_payload(Path("tests/fixtures/card_action.json").read_bytes())
    assert isinstance(event, CardActionEvent)
    assert event.operator.open_id == "ou_verified"
    assert event.action_value["open_id"] == "ou_forged"
    assert event.operator.open_id != event.action_value["open_id"]


def test_card_action_without_callback_operator_open_id_is_rejected() -> None:
    payload = b'{"schema":"2.0","header":{"event_type":"card.action.trigger"},"event":{"operator":{},"action":{"value":{}}}}'
    with pytest.raises(FeishuEventParseError):
        parse_event_payload(payload)
