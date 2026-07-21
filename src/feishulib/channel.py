"""Bounded worker dispatch for parsed Feishu events."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from feishulib.config import FeishuConfig
from feishulib.events import CardActionEvent, MessageEvent, parse_event_payload
from feishulib.exceptions import FeishuEventHandlerError
from feishulib.models import CardActionResponse

type EventHandler[TEvent, TResult] = Callable[[TEvent], Awaitable[TResult]]


@dataclass(slots=True)
class _DispatchItem:
    event: MessageEvent | CardActionEvent
    result: asyncio.Future[CardActionResponse | None]


class EventChannel:
    """Dispatch parsed events outside of the WebSocket receive loop."""

    def __init__(self, config: FeishuConfig) -> None:
        self._config = config
        self._message_handlers: list[EventHandler[MessageEvent, None]] = []
        self._card_handler: EventHandler[CardActionEvent, CardActionResponse | None] | None = None
        self._queue: asyncio.Queue[_DispatchItem] = asyncio.Queue(maxsize=config.event_queue_size)
        self._workers: list[asyncio.Task[None]] = []
        self._started = False
        self._closed = False

    def on(self, name: str, handler: Callable[..., Awaitable[object]]) -> None:
        """Register an asynchronous event handler."""
        if self._closed:
            raise RuntimeError("event channel is closed")
        if name == "message":
            self._message_handlers.append(handler)  # type: ignore[arg-type]
            return
        if name == "card_action":
            if self._card_handler is not None:
                raise ValueError("only one card_action handler is allowed")
            self._card_handler = handler  # type: ignore[assignment]
            return
        raise ValueError("unknown event name")

    async def start(self) -> None:
        """Start the configured worker pool."""
        if self._closed:
            raise RuntimeError("event channel is closed")
        if not self._started:
            self._started = True
            self._workers = [asyncio.create_task(self._worker()) for _ in range(self._config.event_worker_count)]

    async def dispatch(self, payload: bytes) -> CardActionResponse | None:
        """Parse, enqueue, and await one event's handler result."""
        if not self._started or self._closed:
            raise RuntimeError("event channel is not running")
        event = parse_event_payload(payload)
        result: asyncio.Future[CardActionResponse | None] = asyncio.get_running_loop().create_future()
        try:
            self._queue.put_nowait(_DispatchItem(event, result))
        except asyncio.QueueFull as error:
            raise FeishuEventHandlerError("queue", error) from error
        return await result

    async def close(self) -> None:
        """Cancel workers and reject subsequent dispatches."""
        if self._closed:
            return
        self._closed = True
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if not item.result.done():
                item.result.set_exception(FeishuEventHandlerError("shutdown", RuntimeError("channel closed")))

    async def _worker(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if isinstance(item.event, MessageEvent):
                    for handler in self._message_handlers:
                        await handler(item.event)
                    if not item.result.done():
                        item.result.set_result(None)
                elif self._card_handler is None:
                    if not item.result.done():
                        item.result.set_result(None)
                else:
                    response = await self._card_handler(item.event)
                    if response is not None and not isinstance(response, CardActionResponse):  # type: ignore[unnecessary-isinstance]
                        raise TypeError("card_action handler must return CardActionResponse or None")
                    if not item.result.done():
                        item.result.set_result(response)
            except asyncio.CancelledError as error:
                if not item.result.done():
                    item.result.set_exception(FeishuEventHandlerError("shutdown", error))
                raise
            except Exception as error:
                if not item.result.done():
                    item.result.set_exception(FeishuEventHandlerError("handler", error))
            finally:
                self._queue.task_done()
