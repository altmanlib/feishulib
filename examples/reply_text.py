"""Reply to FEISHU_MESSAGE_ID using the reply_text convenience method."""

import asyncio
import os

from _common import load_dotenv
from feishulib import FeishuClient, FeishuConfig


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        print((await client.reply_text(os.environ["FEISHU_MESSAGE_ID"], os.environ.get("FEISHU_TEXT", "Text reply"))).message_id)


asyncio.run(main())
