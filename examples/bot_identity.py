"""Print the current bot's open ID."""

import asyncio
import os

from _common import load_dotenv
from feishulib import FeishuClient, FeishuConfig


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        print((await client.get_bot_identity()).open_id)


asyncio.run(main())
