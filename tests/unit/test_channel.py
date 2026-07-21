import asyncio
from pathlib import Path

import pytest

from feishulib.channel import EventChannel
from feishulib.config import FeishuConfig
from feishulib.events import MessageEvent
from feishulib.exceptions import FeishuEventHandlerError
from feishulib.models import CardActionResponse, Toast


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


@pytest.mark.asyncio
async def test_close_cancels_active_handler_and_unblocks_dispatch() -> None:
    started = asyncio.Event()
    channel = EventChannel(FeishuConfig(app_id="cli_test", app_secret="secret"))

    async def handler(event: MessageEvent) -> None:
        started.set()
        await asyncio.Event().wait()

    channel.on("message", handler)
    await channel.start()
    dispatch_task = asyncio.create_task(channel.dispatch(_message_payload()))
    await asyncio.wait_for(started.wait(), timeout=0.2)

    await asyncio.wait_for(channel.close(), timeout=0.2)

    with pytest.raises(FeishuEventHandlerError) as raised:
        await dispatch_task
    assert raised.value.event_type == "shutdown"


@pytest.mark.asyncio
async def test_cancelled_dispatch_does_not_break_the_worker() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    handled: list[str] = []
    channel = EventChannel(FeishuConfig(app_id="cli_test", app_secret="secret"))

    async def handler(event: MessageEvent) -> None:
        handled.append(event.message_id)
        if len(handled) == 1:
            started.set()
            await release.wait()

    channel.on("message", handler)
    await channel.start()
    first_dispatch = asyncio.create_task(channel.dispatch(_message_payload()))
    await asyncio.wait_for(started.wait(), timeout=0.2)
    first_dispatch.cancel()

    with pytest.raises(asyncio.CancelledError):
        await first_dispatch

    release.set()
    await channel.dispatch(_message_payload())
    await channel.close()

    assert handled == ["om_message", "om_message"]
