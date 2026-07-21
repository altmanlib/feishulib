"""Run a minimal long-connection Feishu echo bot."""

import asyncio

from feishu_im.chat_bot import run


if __name__ == "__main__":
    asyncio.run(run())
