"""Return a toast for each card action received over a long connection."""

import asyncio
import os

from feishu_im import CardActionResponse, EventChannel, FeishuConfig, FeishuWebSocket, Toast
from _common import load_dotenv
from feishu_im.events import CardActionEvent


async def main() -> None:
    load_dotenv()
    config = FeishuConfig(os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"])
    channel = EventChannel(config)

    async def on_action(event: CardActionEvent) -> CardActionResponse:
        print(f"Card action from {event.operator.open_id}")
        return CardActionResponse(toast=Toast(kind="success", content="Action received"))

    channel.on("card_action", on_action)
    async with FeishuWebSocket(config, channel) as websocket:
        print("Card action bot is online.")
        await websocket.run_forever()


asyncio.run(main())
