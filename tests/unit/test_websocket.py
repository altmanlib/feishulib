import json
from pathlib import Path

import httpx
import pytest

from feishu_im.channel import EventChannel
from feishu_im.config import FeishuConfig
from feishu_im.protocol import FrameMethod, WireFrame, decode_frame
from feishu_im.websocket import ConnectionState, FeishuWebSocket


class _Connection:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False

    async def recv(self) -> bytes:
        raise OSError("done")

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_close_is_idempotent_without_starting() -> None:
    session = httpx.AsyncClient()
    client = FeishuWebSocket(FeishuConfig(app_id="id", app_secret="secret"), EventChannel(FeishuConfig(app_id="id", app_secret="secret")), session=session)
    await client.close()
    await client.close()
    assert client.state is ConnectionState.STOPPED
    await session.aclose()


@pytest.mark.asyncio
async def test_discovers_endpoint_sends_ping_and_acks_data_frame() -> None:
    connection = _Connection()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/callback/ws/endpoint"
        return httpx.Response(
            200,
            json={"code": 0, "data": {"URL": "wss://example.test/ws?device_id=d&service_id=7", "ClientConfig": {"PingInterval": 5}}},
            request=request,
        )

    async def connector(url: str) -> _Connection:
        assert url.startswith("wss://")
        return connection

    config = FeishuConfig(app_id="id", app_secret="secret")
    channel = EventChannel(config)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuWebSocket(config, channel, session=session, connector=connector)
        await client.start()
        assert decode_frame(connection.sent[0]).headers == {"type": "ping"}
        payload = Path("tests/fixtures/message_receive.json").read_bytes()
        frame = WireFrame(1, 2, 7, FrameMethod.DATA, {"type": "event"}, payload)
        await client._handle_data(frame)
        response = decode_frame(connection.sent[-1])
        assert response.method is FrameMethod.DATA
        assert response.headers["biz_rt"].isdigit()
        await client.close()
    assert connection.closed


def _response_code(connection: _Connection) -> int:
    frame = decode_frame(connection.sent[-1])
    body = json.loads(frame.payload)
    return body["code"]


@pytest.mark.asyncio
async def test_invalid_event_is_acknowledged_without_closing_connection(caplog: pytest.LogCaptureFixture) -> None:
    connection = _Connection()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "data": {"URL": "wss://example.test/ws?service_id=7"}},
            request=request,
        )

    async def connector(url: str) -> _Connection:
        return connection

    config = FeishuConfig(app_id="id", app_secret="secret")
    channel = EventChannel(config)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuWebSocket(config, channel, session=session, connector=connector)
        await client.start()
        invalid_payload = b'{"schema":"2.0","header":{"event_type":"p2.unknown"},"event":{"secret":"do-not-log"}}'
        await client._handle_data(WireFrame(1, 2, 7, FrameMethod.DATA, {"type": "event"}, invalid_payload))

        assert _response_code(connection) == 200
        assert client.state is ConnectionState.CONNECTED
        assert "do-not-log" not in caplog.text
        await client.close()


@pytest.mark.asyncio
async def test_invalid_card_handler_result_is_reported_as_retryable_failure() -> None:
    connection = _Connection()

    async def endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "data": {"URL": "wss://example.test/ws?service_id=7"}},
            request=request,
        )

    async def connector(url: str) -> _Connection:
        return connection

    config = FeishuConfig(app_id="id", app_secret="secret")
    channel = EventChannel(config)

    async def handler(event: object) -> object:
        return {"toast": "not-a-CardActionResponse"}

    channel.on("card_action", handler)
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as session:
        client = FeishuWebSocket(config, channel, session=session, connector=connector)
        await client.start()
        payload = Path("tests/fixtures/card_action.json").read_bytes()
        await client._handle_data(WireFrame(1, 2, 7, FrameMethod.DATA, {"type": "event"}, payload))

        assert _response_code(connection) == 503
        await client.close()
