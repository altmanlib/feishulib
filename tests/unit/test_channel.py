from pathlib import Path

import pytest

from feishu_im.channel import EventChannel
from feishu_im.config import FeishuConfig
from feishu_im.models import CardActionResponse, Toast


def _message_payload() -> bytes:
    return Path("tests/fixtures/message_receive.json").read_bytes()


def _card_action_payload() -> bytes:
    return Path("tests/fixtures/card_action.json").read_bytes()


@pytest.mark.asyncio
async def test_message_handlers_run_in_registration_order() -> None:
    calls: list[str] = []
    channel = EventChannel(FeishuConfig(app_id="cli_test", app_secret="secret"))

    async def first(event: object) -> None:
        calls.append("first")

    async def second(event: object) -> None:
        calls.append("second")

    channel.on("message", first)
    channel.on("message", second)
    await channel.start()
    await channel.dispatch(_message_payload())
    await channel.close()
    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_card_action_returns_worker_response() -> None:
    channel = EventChannel(FeishuConfig(app_id="cli_test", app_secret="secret"))

    async def handler(event: object) -> CardActionResponse:
        return CardActionResponse(toast=Toast(kind="success", content="Approved"))

    channel.on("card_action", handler)
    await channel.start()
    result = await channel.dispatch(_card_action_payload())
    await channel.close()
    assert result is not None
    assert result.to_payload()["toast"]["content"] == "Approved"
