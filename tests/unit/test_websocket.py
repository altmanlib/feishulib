import asyncio
import json
from pathlib import Path

import httpx
import pytest

from feishu_im.channel import EventChannel
from feishu_im.config import FeishuConfig
from feishu_im.exceptions import FeishuWebSocketError
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


@pytest.mark.asyncio
async def test_default_connector_uses_configured_open_and_close_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}
    connection = _Connection()

    async def connect(url: str, **kwargs: object) -> _Connection:
        observed["url"] = url
        observed.update(kwargs)
        return connection

    monkeypatch.setattr("feishu_im.websocket.websockets.connect", connect)
    config = FeishuConfig(
        app_id="id",
        app_secret="secret",
        ws_open_timeout_seconds=12.0,
        ws_close_timeout_seconds=7.0,
    )
    client = FeishuWebSocket(config, EventChannel(config))

    await client._connect("wss://example.test/ws")

    assert observed == {
        "url": "wss://example.test/ws",
        "ping_interval": None,
        "open_timeout": 12.0,
        "close_timeout": 7.0,
    }
    await client.close()


@pytest.mark.asyncio
async def test_reconnect_delay_applies_configured_jitter() -> None:
    config = FeishuConfig(
        app_id="id",
        app_secret="secret",
        ws_reconnect_base_seconds=4.0,
        ws_reconnect_max_seconds=60.0,
        ws_reconnect_jitter_ratio=0.25,
    )
    low = FeishuWebSocket(config, EventChannel(config), random_float=lambda: 0.0)
    high = FeishuWebSocket(config, EventChannel(config), random_float=lambda: 1.0)

    assert low._reconnect_delay(0) == 3.0
    assert high._reconnect_delay(0) == 5.0

    await low.close()
    await high.close()


class _BlockingConnection(_Connection):
    def __init__(self) -> None:
        super().__init__()
        self._released = asyncio.Event()

    async def recv(self) -> bytes:
        await self._released.wait()
        raise OSError("closed")

    async def close(self) -> None:
        self.closed = True
        self._released.set()


@pytest.mark.asyncio
async def test_run_forever_retries_an_initial_connector_failure() -> None:
    connection = _BlockingConnection()
    connector_calls = 0
    delays: list[float] = []
    connected = asyncio.Event()

    async def endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "data": {"URL": "wss://example.test/ws?service_id=7"}},
            request=request,
        )

    async def connector(url: str) -> _BlockingConnection:
        nonlocal connector_calls
        connector_calls += 1
        if connector_calls == 1:
            raise OSError("temporary connector failure")
        connected.set()
        return connection

    async def sleep(delay: float) -> None:
        delays.append(delay)

    config = FeishuConfig(app_id="id", app_secret="secret", ws_reconnect_jitter_ratio=0)
    channel = EventChannel(config)
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as session:
        client = FeishuWebSocket(
            config,
            channel,
            session=session,
            connector=connector,
            sleep=sleep,
            random_float=lambda: 0.0,
        )
        runner = asyncio.create_task(client.run_forever())
        await asyncio.wait_for(connected.wait(), timeout=0.2)
        await client.close()
        await asyncio.wait_for(runner, timeout=0.2)

    assert connector_calls == 2
    assert delays == [config.ws_reconnect_base_seconds]
    assert connection.closed


@pytest.mark.asyncio
async def test_context_manager_retries_an_initial_connector_failure_in_run_forever() -> None:
    connection = _BlockingConnection()
    connector_calls = 0
    delays: list[float] = []
    connected = asyncio.Event()

    async def endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "data": {"URL": "wss://example.test/ws?service_id=7"}},
            request=request,
        )

    async def connector(url: str) -> _BlockingConnection:
        nonlocal connector_calls
        connector_calls += 1
        if connector_calls == 1:
            raise OSError("temporary connector failure")
        connected.set()
        return connection

    async def sleep(delay: float) -> None:
        delays.append(delay)

    config = FeishuConfig(app_id="id", app_secret="secret", ws_reconnect_jitter_ratio=0)
    channel = EventChannel(config)
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as session:
        async with FeishuWebSocket(
            config,
            channel,
            session=session,
            connector=connector,
            sleep=sleep,
            random_float=lambda: 0.0,
        ) as client:
            assert client.state is ConnectionState.STOPPED
            runner = asyncio.create_task(client.run_forever())
            await asyncio.wait_for(connected.wait(), timeout=0.2)
            await client.close()
            await asyncio.wait_for(runner, timeout=0.2)

    assert connector_calls == 2
    assert delays == [config.ws_reconnect_base_seconds]
    assert connection.closed


@pytest.mark.asyncio
async def test_reconnect_backoff_grows_for_repeated_post_connect_disconnects() -> None:
    delays: list[float] = []
    config = FeishuConfig(app_id="id", app_secret="secret", ws_reconnect_jitter_ratio=0)
    channel = EventChannel(config)

    async def endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "data": {"URL": "wss://example.test/ws?service_id=7"}},
            request=request,
        )

    async def connector(url: str) -> _Connection:
        return _Connection()

    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as session:
        client = FeishuWebSocket(config, channel, session=session, connector=connector, sleep=lambda delay: _stop_after_three_delays(client, delays, delay))
        await client.run_forever()

    assert delays == [1.0, 2.0, 4.0]


async def _stop_after_three_delays(client: FeishuWebSocket, delays: list[float], delay: float) -> None:
    delays.append(delay)
    if len(delays) == 3:
        await client.close()


class _SlowCloseConnection(_Connection):
    async def close(self) -> None:
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_reconnect_stops_when_previous_connection_cannot_close() -> None:
    connection = _SlowCloseConnection()
    connector_calls = 0
    config = FeishuConfig(app_id="id", app_secret="secret", ws_close_timeout_seconds=0.01)
    channel = EventChannel(config)

    async def endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "data": {"URL": "wss://example.test/ws?service_id=7"}},
            request=request,
        )

    async def connector(url: str) -> _SlowCloseConnection:
        nonlocal connector_calls
        connector_calls += 1
        return connection

    async def sleep(delay: float) -> None:
        raise AssertionError("reconnect must not proceed after a close timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as session:
        client = FeishuWebSocket(config, channel, session=session, connector=connector, sleep=sleep)
        try:
            with pytest.raises(FeishuWebSocketError, match="close timed out"):
                await client.run_forever()
        finally:
            await client.close()

    assert connector_calls == 1


class _FailingCloseSession(httpx.AsyncClient):
    async def aclose(self) -> None:
        raise OSError("session close failed")


@pytest.mark.asyncio
async def test_close_sets_stopped_state_when_owned_session_close_fails() -> None:
    config = FeishuConfig(app_id="id", app_secret="secret")
    session = _FailingCloseSession()
    client = FeishuWebSocket(config, EventChannel(config), session=session)
    client._owns_session = True

    with pytest.raises(OSError, match="session close failed"):
        await client.close()

    assert client.state is ConnectionState.STOPPED


@pytest.mark.asyncio
async def test_close_timeout_still_closes_channel_and_sets_stopped_state() -> None:
    config = FeishuConfig(app_id="id", app_secret="secret", ws_close_timeout_seconds=0.01)
    channel = EventChannel(config)

    async def connector(url: str) -> _Connection:
        return _Connection()

    client = FeishuWebSocket(config, channel, connector=connector)
    client._connection = _SlowCloseConnection()
    await channel.start()

    with pytest.raises(FeishuWebSocketError, match="close timed out"):
        await asyncio.wait_for(client.close(), timeout=0.2)

    assert client.state is ConnectionState.STOPPED
    with pytest.raises(RuntimeError, match="closed"):
        channel.on("message", lambda event: asyncio.sleep(0))
