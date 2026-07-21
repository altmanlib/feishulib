from pathlib import Path


def test_every_public_business_capability_has_a_runnable_example() -> None:
    root = Path("examples")
    assert {
        "README.md",
        "bot_identity.py",
        "send_text.py",
        "send_message.py",
        "send_card.py",
        "reply_message.py",
        "reply_text.py",
        "update_message.py",
        "update_card.py",
        "delete_message.py",
        "download_resource.py",
        "chat_bot.py",
        "card_action_bot.py",
    } <= {path.name for path in root.iterdir()}
