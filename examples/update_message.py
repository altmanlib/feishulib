"""Update FEISHU_MESSAGE_ID with an interactive card."""

import asyncio
import os

from feishu_im import FeishuClient, FeishuConfig, UpdateMessage
from feishu_im.chat_bot import load_dotenv


CARD = {"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "Updated card"}}]}


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        receipt = await client.update_message(UpdateMessage(os.environ["FEISHU_MESSAGE_ID"], "interactive", CARD))
    print(receipt.message_id)


asyncio.run(main())
