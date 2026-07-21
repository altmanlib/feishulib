import httpx
import pytest

from feishu_im.channel import EventChannel
from feishu_im.config import FeishuConfig
from feishu_im.websocket import ConnectionState, FeishuWebSocket


@pytest.mark.asyncio
async def test_close_is_idempotent_without_starting() -> None:
    session = httpx.AsyncClient()
    client = FeishuWebSocket(FeishuConfig(app_id="id", app_secret="secret"), EventChannel(FeishuConfig(app_id="id", app_secret="secret")), session=session)
    await client.close()
    await client.close()
    assert client.state is ConnectionState.STOPPED
    await session.aclose()
