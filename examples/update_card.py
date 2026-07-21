"""Update FEISHU_MESSAGE_ID with the update_card convenience method."""

import asyncio
import os

from feishu_im import FeishuClient, FeishuConfig
from feishu_im.chat_bot import load_dotenv

CARD = {"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "Updated by update_card"}}]}


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        print((await client.update_card(os.environ["FEISHU_MESSAGE_ID"], CARD)).message_id)


asyncio.run(main())
