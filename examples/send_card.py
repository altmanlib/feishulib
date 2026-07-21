"""Send an interactive card to FEISHU_RECEIVE_ID."""

import asyncio
import os

from feishu_im import FeishuClient, FeishuConfig
from feishu_im.chat_bot import load_dotenv

CARD = {"config": {"wide_screen_mode": True}, "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "**Hello** from a card"}}]}


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        receipt = await client.send_card(os.environ["FEISHU_RECEIVE_ID"], CARD, receive_id_type=os.environ.get("FEISHU_RECEIVE_ID_TYPE", "open_id"))
    print(receipt.message_id)


asyncio.run(main())
