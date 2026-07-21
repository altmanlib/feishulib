"""Print the current bot's open ID."""

import asyncio
import os

from feishu_im import FeishuClient, FeishuConfig
from feishu_im.chat_bot import load_dotenv


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        print((await client.get_bot_identity()).open_id)


asyncio.run(main())
