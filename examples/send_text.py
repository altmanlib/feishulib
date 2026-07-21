"""Send a text message to FEISHU_RECEIVE_ID."""

import asyncio
import os

from feishu_im import FeishuClient, FeishuConfig
from feishu_im.chat_bot import load_dotenv


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        receipt = await client.send_text(os.environ["FEISHU_RECEIVE_ID"], os.environ.get("FEISHU_TEXT", "Hello from feishu-im-client"), receive_id_type=os.environ.get("FEISHU_RECEIVE_ID_TYPE", "open_id"))
    print(receipt.message_id)


asyncio.run(main())
