"""Delete FEISHU_MESSAGE_ID after explicit confirmation."""

import asyncio
import os

from feishulib import FeishuClient, FeishuConfig
from _common import load_dotenv


async def main() -> None:
    load_dotenv()
    if os.environ.get("FEISHU_CONFIRM_DELETE") != "yes":
        raise SystemExit("Set FEISHU_CONFIRM_DELETE=yes to delete the message.")
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        await client.delete_message(os.environ["FEISHU_MESSAGE_ID"])
    print("Message deleted.")


asyncio.run(main())
