"""Reply to FEISHU_MESSAGE_ID with a text message."""

import asyncio
import os

from feishu_im import FeishuClient, FeishuConfig, ReplyMessage
from feishu_im.chat_bot import load_dotenv


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        receipt = await client.reply_message(ReplyMessage(os.environ["FEISHU_MESSAGE_ID"], "text", {"text": os.environ.get("FEISHU_TEXT", "Reply example")}))
    print(receipt.message_id)


asyncio.run(main())
