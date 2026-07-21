# feishulib

A lightweight, asynchronous, typed Python client for the Feishu IM API. No runtime dependency on `lark_oapi`.

## Features

- **REST API** — send, reply, update, delete messages; download resources; query bot identity
- **Long-connection events** — receive text messages and card actions over persistent WebSocket
- **Async-native** — built on `httpx` and `websockets` with `asyncio`
- **Typed** — fully annotated public API, strict Pyright validation
- **Resilient** — automatic tenant-token refresh, HTTP retry with backoff, WebSocket reconnection with exponential backoff and jitter

## Installation

```bash
uv add feishulib
```

Requires Python >= 3.12.

## Quick Start

```python
from feishulib import FeishuClient, FeishuConfig

config = FeishuConfig(app_id="cli_xxx", app_secret="your_secret")
async with FeishuClient(config) as client:
    receipt = await client.send_text("oc_xxx", "Hello from feishulib!")
    print(receipt.message_id)
```

## REST API

All methods are on `FeishuClient`, used as an async context manager.

### Generic Open API Requests

Use `request()` for a Feishu Open API endpoint that uses the standard JSON response envelope. It accepts an HTTP method, a relative `/open-apis/` path, optional string query parameters, a JSON object body, and extra non-authentication headers.

```python
response = await client.request(
    "GET",
    "/open-apis/contact/v3/users",
    params={"user_id_type": "open_id", "page_size": "50"},
)
print(response.data["items"])
```

Use `request_raw()` for every other official endpoint shape, including multipart uploads, arbitrary JSON values, form data, raw content, and binary responses. It returns the successful `httpx.Response` without interpreting Feishu's JSON business envelope.

```python
response = await client.request_raw(
    "POST",
    "/open-apis/drive/v1/medias/upload_all",
    data={"parent_type": "explorer"},
    files={"file": ("note.txt", b"hello", "text/plain")},
)
print(response.status_code, response.content)
```

By default, the client obtains, caches, and refreshes a tenant access token. For an endpoint requiring a user or app access token, provide it explicitly; explicit tokens are not refreshed by the client:

```python
response = await client.request(
    "GET",
    "/open-apis/authen/v1/user_info",
    access_token=user_access_token,
)
```

Both methods require a path beginning with `/open-apis/`; do not supply an `Authorization` header because `access_token` is the explicit credential input. `request()` returns `ApiResponse` and validates Feishu's business `code`; `request_raw()` returns the raw successful HTTP response. Generic `GET`, `HEAD`, `OPTIONS`, and `TRACE` calls retry transient failures by default. Generic unsafe methods do not retry unless `retry=True` is explicitly provided.

### Sending Messages

```python
from feishulib import FeishuClient, FeishuConfig, OutboundMessage

async with FeishuClient(FeishuConfig(app_id, secret)) as client:
    # Send text
    receipt = await client.send_text("oc_xxx", "Hello!")

    # Send card (interactive)
    card = {
        "config": {"wide_screen_mode": True},
        "elements": [{"tag": "markdown", "content": "**Hello**"}],
    }
    receipt = await client.send_card("oc_xxx", card)

    # Send with custom message type
    from feishulib import OutboundMessage
    message = OutboundMessage(
        receive_id="oc_xxx",
        receive_id_type="chat_id",
        msg_type="post",
        content={"zh_cn": {"title": "Post", "content": [...]}},
    )
    receipt = await client.send_message(message)
```

`send_message` and `send_text` accept an optional `uuid` parameter. When omitted, the client generates one automatically and retains it across transport retries for idempotency.

### Replying to Messages

```python
from feishulib import ReplyMessage

# Reply text
receipt = await client.reply_text("om_xxx", "Got it!")

# Reply with a card
await client.reply_message(ReplyMessage("om_xxx", "interactive", card))

# Reply in thread
await client.reply_text("om_xxx", "In thread", reply_in_thread=True)
```

### Updating and Deleting Messages

```python
from feishulib import UpdateMessage

# Update message content
await client.update_message(UpdateMessage("om_xxx", "text", {"text": "Edited"}))

# Update a card
await client.update_card("om_xxx", card)

# Delete a message
await client.delete_message("om_xxx")
```

### Downloading Resources

```python
content = await client.download_file("om_xxx", "file_key_xxx", resource_type="file")
# resource_type can be "file" or "image"

resource = await client.download_file_with_metadata("om_xxx", "file_key_xxx")
print(resource.filename, resource.content_type, resource.content)
```

`download_file()` remains the bytes-only convenience API. `download_file_with_metadata()` returns a `BinaryResponse`; its `filename` and `content_type` come from the resource download HTTP response and can be `None` when Feishu does not send the relevant headers.

### Bot Identity

```python
bot = await client.get_bot_identity()
print(bot.open_id)  # e.g. "ou_xxxx"
```

## Long-Connection Events

feishulib supports receiving events via Feishu's long-connection protocol, using a minimal protobuf frame schema.

### Text Message Reception

```python
from feishulib import EventChannel, FeishuClient, FeishuConfig, FeishuWebSocket
from feishulib.events import MessageEvent

config = FeishuConfig(app_id, secret)
channel = EventChannel(config)

async with FeishuClient(config) as client:
    bot = await client.get_bot_identity()

    async def on_message(event: MessageEvent) -> None:
        if event.sender.open_id == bot.open_id:
            return  # ignore messages from self
        reply = reply_for_message(event)  # your logic
        if reply and event.chat_id:
            await client.send_text(event.chat_id, reply)

    channel.on("message", on_message)

    async with FeishuWebSocket(config, channel) as ws:
        await ws.run_forever()
```

### Event Metadata

Both `MessageEvent` and `CardActionEvent` expose `create_time`, parsed from schema 2.0 `header.create_time` as a timezone-aware UTC `datetime`. Unix seconds and milliseconds are supported; missing or malformed values are represented as `None` without relaxing structural event validation.

Both events also expose `raw_header` and `raw_event` mappings for forward-compatible access to unmodeled protocol fields. These mappings are untrusted input and must not be used to authenticate identities. Use `event.sender` for message identity and `event.operator` for card-action identity.

For received file or media messages, event content provides resource keys such as `file_key` (and, for media, possibly `image_key`); it does not provide an authoritative filename or MIME type. Never derive either value from a resource key. To inspect download metadata, use `download_file_with_metadata()` and validate the returned response headers according to your application policy.

### Card Action Handling

```python
from feishulib import CardActionResponse, EventChannel, FeishuConfig, FeishuWebSocket, Toast
from feishulib.events import CardActionEvent

config = FeishuConfig(app_id, secret)
channel = EventChannel(config)

async def on_card_action(event: CardActionEvent) -> CardActionResponse:
    print(f"Action from {event.operator.open_id}: {event.action_value}")
    return CardActionResponse(toast=Toast(kind="success", content="Done"))

channel.on("card_action", on_card_action)

async with FeishuWebSocket(config, channel) as ws:
    await ws.run_forever()
```

### Event Channel

The `EventChannel` dispatches incoming events to registered handlers:

| Method | Event | Handler signature | Notes |
| --- | --- | --- | --- |
| `channel.on("message", fn)` | `im.message.receive_v1` | `async (MessageEvent) -> None` | Multiple handlers allowed; run in registration order |
| `channel.on("card_action", fn)` | `card.action.trigger` | `async (CardActionEvent) -> CardActionResponse \| None` | At most one handler |

The card action handler can return a `CardActionResponse` with a toast, a card update, or both.

### WebSocket Connection

`FeishuWebSocket` manages the long-connection lifecycle:

- Automatic endpoint discovery via `POST /callback/ws/endpoint`
- Heartbeat via ping/pong frames
- Exponential backoff reconnection with jitter on transient failures
- Configurable open/close timeouts
- Event ACK: valid events → `200`, handler failures → `503`, timeout → `500`
- Unsupported or malformed events are acknowledged with `200` and dropped gracefully

## Configuration

```python
from feishulib import FeishuConfig

config = FeishuConfig(
    app_id="cli_xxx",
    app_secret="your_secret",
    # Optional overrides (defaults shown):
    base_url="https://open.feishu.cn",
    request_timeout_seconds=10.0,
    max_retries=3,
    retry_backoff_base_seconds=0.5,
    retry_max_delay_seconds=15.0,
    retry_jitter_ratio=0.1,
    token_refresh_skew_seconds=60.0,
    ws_open_timeout_seconds=15.0,
    ws_close_timeout_seconds=10.0,
    ws_ping_timeout_seconds=180.0,
    ws_reconnect_base_seconds=1.0,
    ws_reconnect_max_seconds=60.0,
    ws_reconnect_jitter_ratio=0.1,
    event_queue_size=100,
    event_worker_count=1,
    card_action_timeout_seconds=8.0,
)
```

`app_secret` is excluded from `repr()` to prevent accidental leakage in logs.

## Error Handling

All exceptions inherit from `FeishuError`:

| Exception | When it occurs |
| --- | --- |
| `FeishuApiError` | Feishu API returned a non-zero business code |
| `FeishuHttpStatusError` | HTTP response had a non-success status |
| `FeishuTransientError` | Retryable transport failure exhausted retry budget |
| `FeishuAuthError` | Tenant access token retrieval or validation failed |
| `FeishuProtocolError` | Remote response did not match the expected protocol |
| `FeishuWebSocketError` | WebSocket connection or frame exchange failed |
| `FeishuEventParseError` | Incoming event could not be parsed |
| `FeishuEventHandlerError` | Event handler failed or event dispatch could not proceed |

## Security

- **Card action identity** — always use `event.operator` for authentication. Values in `event.action.value` are user-controlled and must never be trusted as an identity source.
- **Event payload** — malformed and unsupported events are acknowledged and dropped without dispatch. The client logs the parse error and event type, but never logs the raw event payload, credentials, or action values.
- **Credentials** — `app_secret` is omitted from `FeishuConfig.__repr__`. Authorization headers are redacted in logs.

## Development

```bash
# Clone and install
git clone <repo>
cd feishulib
uv sync

# Run quality gate
bash scripts/verify

# Individual checks
uv run ruff check .
uv run pyright
uv run pytest --cov=src/feishulib --cov-report=term-missing
```

## License

MIT