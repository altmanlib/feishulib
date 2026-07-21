"""Feishu long-connection lifecycle and frame dispatch."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Protocol, Self, cast
from urllib.parse import parse_qs, urlparse

import httpx
import websockets

from feishulib.channel import EventChannel
from feishulib.config import FeishuConfig
from feishulib.exceptions import (
    FeishuEventHandlerError,
    FeishuEventParseError,
    FeishuProtocolError,
    FeishuTransientError,
    FeishuWebSocketError,
)
from feishulib.http import FeishuHttpClient
from feishulib.protocol import FrameMethod, decode_frame, encode_frame, make_data_response, make_ping


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
type Sleep = Callable[[float], Awaitable[None]]
type RandomFloat = Callable[[], float]

_RECONNECTABLE_ERRORS = (OSError, TimeoutError, websockets.WebSocketException, FeishuTransientError, FeishuWebSocketError)

_LOGGER = logging.getLogger(__name__)


class FeishuWebSocket:
    """Maintain a Feishu WebSocket connection and acknowledge event frames."""

    def __init__(
        self,
        config: FeishuConfig,
        channel: EventChannel,
        *,
        session: httpx.AsyncClient | None = None,
        connector: Connector | None = None,
        sleep: Sleep = asyncio.sleep,
        random_float: RandomFloat = random.random,
    ) -> None:
        self.config = config
        self._channel = channel
        self._owns_session = session is None
        self._session = session if session is not None else httpx.AsyncClient()
        self._http = FeishuHttpClient(config, self._session)
        self._connector = connector or self._connect
        self._sleep = sleep
        self._random_float = random_float
        self._state = ConnectionState.STOPPED
        self._connection: WebSocketConnection | None = None
        self._closed = False
        self._write_lock = asyncio.Lock()
        self._service_id = 0
        self._ping_interval = 120.0
        self._last_pong = time.monotonic()
        self._received_frame_since_connect = False

    @property
    def state(self) -> ConnectionState:
        return self._state

    async def __aenter__(self) -> Self:
        await self._channel.start()
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
        """Receive frames and retry transient connection failures until closed."""
        attempt = 0
        while not self._closed:
            try:
                await self.start()
                await self._receive_loop()
                if not self._closed:
                    raise FeishuWebSocketError("WebSocket receive loop stopped unexpectedly")
            except _RECONNECTABLE_ERRORS:
                if self._closed:
                    break
                if self._received_frame_since_connect:
                    attempt = 0
                self._state = ConnectionState.RECONNECTING
                await self._close_connection()
                await self._sleep(self._reconnect_delay(attempt))
                attempt += 1
            else:
                break

    async def close(self) -> None:
        """Close the socket, workers, and any internally-owned HTTP session."""
        if self._closed:
            return
        self._closed = True
        self._state = ConnectionState.CLOSING
        try:
            await self._close_connection()
        finally:
            try:
                await self._channel.close()
            finally:
                try:
                    if self._owns_session:
                        await self._session.aclose()
                finally:
                    self._state = ConnectionState.STOPPED

    async def _open_connection(self) -> None:
        self._state = ConnectionState.CONNECTING
        self._received_frame_since_connect = False
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
                    self._received_frame_since_connect = True
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
        from feishulib.protocol import WireFrame

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
        except FeishuEventParseError as error:
            _LOGGER.warning("Dropping unsupported or invalid Feishu event: %s", error)
            status = 200
        except FeishuEventHandlerError:
            status = 503
        except TimeoutError:
            status = 500
        runtime = int((time.monotonic() - started) * 1000)
        response = make_data_response(frame, status_code=status, result_payload=result.to_payload() if result else None, business_runtime_ms=runtime)
        await self._send(response)

    async def _send(self, frame: object) -> None:
        from feishulib.protocol import WireFrame

        if not isinstance(frame, WireFrame):
            raise FeishuProtocolError("invalid outbound frame")
        async with self._write_lock:
            await self._require_connection().send(encode_frame(frame))

    async def _close_connection(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            async with asyncio.timeout(self.config.ws_close_timeout_seconds):
                await connection.close()
        except TimeoutError as error:
            raise FeishuWebSocketError("WebSocket close timed out") from error

    def _require_connection(self) -> WebSocketConnection:
        if self._connection is None:
            raise FeishuWebSocketError("WebSocket is not connected")
        return self._connection

    async def _connect(self, url: str) -> WebSocketConnection:
        return cast(
            WebSocketConnection,
            await websockets.connect(
                url,
                ping_interval=None,
                open_timeout=self.config.ws_open_timeout_seconds,
                close_timeout=self.config.ws_close_timeout_seconds,
            ),
        )

    def _reconnect_delay(self, attempt: int) -> float:
        base = min(
            self.config.ws_reconnect_max_seconds,
            self.config.ws_reconnect_base_seconds * 2**attempt,
        )
        jitter = base * self.config.ws_reconnect_jitter_ratio
        random_value = min(1.0, max(0.0, self._random_float()))
        return min(self.config.ws_reconnect_max_seconds, base - jitter + 2 * jitter * random_value)