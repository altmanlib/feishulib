import importlib.util
from pathlib import Path

from feishulib.events import MessageEvent, SenderIdentity


def _reply_for_message(event: MessageEvent, *, bot_open_id: str) -> str | None:
    path = Path("examples/chat_bot.py")
    specification = importlib.util.spec_from_file_location("chat_bot_example", path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.reply_for_message(event, bot_open_id=bot_open_id)


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
    assert not Path("src/feishulib/chat_bot.py").exists()
    assert _reply_for_message(_event(text="hello"), bot_open_id="ou_bot") == "你说：hello"


def test_reply_for_message_ignores_bot_and_non_text_messages() -> None:
    assert _reply_for_message(_event(text="loop", sender_open_id="ou_bot"), bot_open_id="ou_bot") is None
    assert _reply_for_message(_event(text=None), bot_open_id="ou_bot") is None
