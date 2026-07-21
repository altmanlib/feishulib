"""Download a message resource to FEISHU_OUTPUT_PATH."""

import asyncio
import os
from pathlib import Path

from feishu_im import FeishuClient, FeishuConfig
from _common import load_dotenv


async def main() -> None:
    load_dotenv()
    async with FeishuClient(FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])) as client:
        content = await client.download_file(os.environ["FEISHU_MESSAGE_ID"], os.environ["FEISHU_FILE_KEY"], resource_type=os.environ.get("FEISHU_RESOURCE_TYPE", "file"))
    Path(os.environ.get("FEISHU_OUTPUT_PATH", "downloaded-resource")).write_bytes(content)


asyncio.run(main())
