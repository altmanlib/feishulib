"""Run a minimal long-connection Feishu echo bot."""

import asyncio
import os
from pathlib import Path

from feishulib import EventChannel, FeishuClient, FeishuConfig, FeishuWebSocket
from feishulib.events import MessageEvent


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE pairs without evaluating shell expressions."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def reply_for_message(event: MessageEvent, *, bot_open_id: str) -> str | None:
    """Return the reply for a user text message, excluding the bot itself."""
    if event.sender.open_id == bot_open_id or not event.text:
        return None
    return f"你说：{event.text}"


async def run() -> None:
    """Connect to Feishu and reply to incoming text messages in their chat."""
    load_dotenv()
    config = FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])
    channel = EventChannel(config)
    async with FeishuClient(config) as client:
        bot = await client.get_bot_identity()

        async def on_message(event: MessageEvent) -> None:
            reply = reply_for_message(event, bot_open_id=bot.open_id)
            if reply is not None and event.chat_id is not None:
                await client.send_text(event.chat_id, reply)

        channel.on("message", on_message)
        async with FeishuWebSocket(config, channel) as websocket:
            print("Bot is online. Send a text message to the bot.")
            await websocket.run_forever()


if __name__ == "__main__":
    asyncio.run(run())
