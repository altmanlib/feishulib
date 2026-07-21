"""Send a generic OutboundMessage to FEISHU_RECEIVE_ID."""

import asyncio
import os

from feishu_im import FeishuClient, FeishuConfig, OutboundMessage
from feishu_im.chat_bot import load_dotenv


async def main() -> None:
    load_dotenv()
    message = OutboundMessage(os.environ["FEISHU_RECEIVE_ID"], os.environ.get("FEISHU_RECEIVE_ID_TYPE", "open_id"), "text", {"text": os.environ.get("FEISHU_TEXT", "Generic message")})
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        print((await client.send_message(message)).message_id)


asyncio.run(main())
