from feishu_im.events import MessageEvent, SenderIdentity

from feishu_im.chat_bot import reply_for_message


def _event(*, text: str | None, sender_open_id: str | None = "ou_user") -> MessageEvent:
    return MessageEvent(
        event_id="evt_1",
        sender=SenderIdentity(open_id=sender_open_id, user_id=None, union_id=None),
        message_id="om_1",
        chat_id="oc_1",
        chat_type="group",
        message_type="text",
        raw_content=None,
        content=None,
        text=text,
        file_key=None,
        root_id=None,
        parent_id=None,
    )


def test_reply_for_message_echoes_user_text() -> None:
    assert reply_for_message(_event(text="hello"), bot_open_id="ou_bot") == "你说：hello"


def test_reply_for_message_ignores_bot_and_non_text_messages() -> None:
    assert reply_for_message(_event(text="loop", sender_open_id="ou_bot"), bot_open_id="ou_bot") is None
    assert reply_for_message(_event(text=None), bot_open_id="ou_bot") is None
