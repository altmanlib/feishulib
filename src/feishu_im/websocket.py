"""Feishu long-connection lifecycle and frame dispatch."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Protocol, Self, cast
from urllib.parse import parse_qs, urlparse

import httpx
import websockets

from feishu_im.channel import EventChannel
from feishu_im.config import FeishuConfig
from feishu_im.exceptions import FeishuEventHandlerError, FeishuProtocolError, FeishuWebSocketError
from feishu_im.http import FeishuHttpClient
from feishu_im.protocol import FrameMethod, decode_frame, encode_frame, make_data_response, make_ping


class ConnectionState(StrEnum):
    STOPPED = "stopped"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"


class WebSocketConnection(Protocol):
    async def recv(self) -> bytes: ...
    async def send(self, data: bytes) -> None: ...
    async def close(self) -> None: ...


type Connector = Callable[[str], Awaitable[WebSocketConnection]]


class FeishuWebSocket:
    """Maintain a Feishu WebSocket connection and acknowledge event frames."""

    def __init__(
        self,
        config: FeishuConfig,
        channel: EventChannel,
        *,
        session: httpx.AsyncClient | None = None,
        connector: Connector | None = None,
    ) -> None:
        self.config = config
        self._channel = channel
        self._owns_session = session is None
        self._session = session if session is not None else httpx.AsyncClient()
        self._http = FeishuHttpClient(config, self._session)
        self._connector = connector or self._connect
        self._state = ConnectionState.STOPPED
        self._connection: WebSocketConnection | None = None
        self._closed = False
        self._write_lock = asyncio.Lock()
        self._service_id = 0
        self._ping_interval = 120.0
        self._last_pong = time.monotonic()

    @property
    def state(self) -> ConnectionState:
        return self._state

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    async def start(self) -> None:
        """Start channel workers and establish the initial connection."""
        if self._closed:
            raise RuntimeError("websocket client is closed")
        if self._connection is None:
            await self._channel.start()
            await self._open_connection()

    async def run_forever(self) -> None:
        """Receive frames, reconnecting after unexpected failures."""
        await self.start()
        attempt = 0
        while not self._closed:
            try:
                await self._receive_loop()
            except (OSError, websockets.WebSocketException, FeishuWebSocketError):
                if self._closed:
                    break
                self._state = ConnectionState.RECONNECTING
                await self._close_connection()
                delay = min(self.config.ws_reconnect_max_seconds, self.config.ws_reconnect_base_seconds * 2**attempt)
                await asyncio.sleep(delay)
                attempt += 1
                await self._open_connection()
            else:
                break

    async def close(self) -> None:
        """Close the socket, workers, and any internally-owned HTTP session."""
        if self._closed:
            return
        self._closed = True
        self._state = ConnectionState.CLOSING
        await self._close_connection()
        await self._channel.close()
        if self._owns_session:
            await self._session.aclose()
        self._state = ConnectionState.STOPPED

    async def _open_connection(self) -> None:
        self._state = ConnectionState.CONNECTING
        endpoint = await self._http.request_json(
            "POST",
            "/callback/ws/endpoint",
            json_body={"AppID": self.config.app_id, "AppSecret": self.config.app_secret},
        )
        url = endpoint.data.get("URL")
        if not isinstance(url, str) or urlparse(url).scheme != "wss":
            raise FeishuProtocolError("WebSocket endpoint URL must use wss")
        service = parse_qs(urlparse(url).query).get("service_id", [""])[0]
        try:
            self._service_id = int(service)
        except ValueError as error:
            raise FeishuProtocolError("WebSocket endpoint has invalid service_id") from error
        if self._service_id <= 0:
            raise FeishuProtocolError("WebSocket endpoint has invalid service_id")
        config = endpoint.data.get("ClientConfig")
        if isinstance(config, Mapping):
            interval = config.get("PingInterval")
            if isinstance(interval, int) and interval > 0:
                self._ping_interval = float(interval)
        self._connection = await self._connector(url)
        self._last_pong = time.monotonic()
        self._state = ConnectionState.CONNECTED
        await self._send(make_ping(self._service_id))

    async def _receive_loop(self) -> None:
        connection = self._require_connection()
        while not self._closed:
            try:
                async with asyncio.timeout(self._ping_interval):
                    raw = await connection.recv()
            except TimeoutError:
                await self._send(make_ping(self._service_id))
                if time.monotonic() - self._last_pong > self.config.ws_ping_timeout_seconds:
                    raise FeishuWebSocketError("WebSocket pong timeout")
                continue
            frame = decode_frame(raw)
            if frame.method is FrameMethod.CONTROL:
                if frame.headers.get("type") == "pong":
                    self._last_pong = time.monotonic()
                continue
            await self._handle_data(frame)

    async def _handle_data(self, frame: object) -> None:
        from feishu_im.protocol import WireFrame

        if not isinstance(frame, WireFrame):
            raise FeishuProtocolError("invalid data frame")
        if frame.headers.get("type") is None:
            raise FeishuProtocolError("data frame has no type")
        started = time.monotonic()
        status = 200
        result = None
        try:
            async with asyncio.timeout(self.config.card_action_timeout_seconds):
                result = await self._channel.dispatch(frame.payload)
        except FeishuEventHandlerError:
            status = 503
        except TimeoutError:
            status = 500
        runtime = int((time.monotonic() - started) * 1000)
        response = make_data_response(frame, status_code=status, result_payload=result.to_payload() if result else None, business_runtime_ms=runtime)
        await self._send(response)

    async def _send(self, frame: object) -> None:
        from feishu_im.protocol import WireFrame

        if not isinstance(frame, WireFrame):
            raise FeishuProtocolError("invalid outbound frame")
        async with self._write_lock:
            await self._require_connection().send(encode_frame(frame))

    async def _close_connection(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    def _require_connection(self) -> WebSocketConnection:
        if self._connection is None:
            raise FeishuWebSocketError("WebSocket is not connected")
        return self._connection

    @staticmethod
    async def _connect(url: str) -> WebSocketConnection:
        return cast(WebSocketConnection, await websockets.connect(url, ping_interval=None))
