import httpx
import pytest

from feishulib.config import FeishuConfig
from feishulib.exceptions import FeishuApiError, FeishuHttpStatusError, FeishuProtocolError, FeishuTransientError
from feishulib.http import FeishuHttpClient, redact_headers


async def _record_sleep(target: list[float], delay: float) -> None:
    target.append(delay)


@pytest.mark.asyncio
async def test_retries_429_then_returns_data() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}}, request=request)

    sleeps: list[float] = []
    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FeishuHttpClient(
        FeishuConfig(app_id="cli_test", app_secret="secret"),
        session,
        sleep=lambda delay: _record_sleep(sleeps, delay),
        random_float=lambda: 0.0,
    )

    response = await client.request_json("POST", "/open-apis/im/v1/messages", json_body={})

    assert response.data == {"message_id": "om_1"}
    assert attempts == 2
    assert sleeps == [0.0]
    await session.aclose()


@pytest.mark.asyncio
async def test_business_error_is_not_retried() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 230001, "msg": "invalid content"}, request=request)

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FeishuHttpClient(FeishuConfig(app_id="cli_test", app_secret="secret"), session)

    with pytest.raises(FeishuApiError) as raised:
        await client.request_json("POST", "/open-apis/im/v1/messages", json_body={})

    assert raised.value.code == 230001
    await session.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_retries_server_errors(status: int) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, request=request)

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FeishuHttpClient(
        FeishuConfig(app_id="id", app_secret="secret", max_retries=1),
        session,
        sleep=lambda _: _record_sleep([], 0),
        random_float=lambda: 0,
    )
    with pytest.raises(FeishuTransientError) as raised:
        await client.request_json("GET", "/open-apis/im/v1/messages")
    assert raised.value.status_code == status
    assert raised.value.attempts == 2
    assert calls == 2
    await session.aclose()


@pytest.mark.asyncio
async def test_rejects_non_retriable_and_invalid_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("bad"):
            return httpx.Response(400, json={"msg": "bad request"}, request=request)
        return httpx.Response(200, text="not-json", request=request)

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FeishuHttpClient(FeishuConfig(app_id="id", app_secret="secret"), session)
    with pytest.raises(FeishuHttpStatusError) as status_error:
        await client.request_json("GET", "/open-apis/bad")
    assert status_error.value.status_code == 400
    with pytest.raises(FeishuProtocolError):
        await client.request_json("GET", "/open-apis/im/v1/messages")
    await session.aclose()


@pytest.mark.asyncio
async def test_binary_json_error_is_not_returned_as_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/json"}, json={"code": 123, "msg": "no"}, request=request)

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FeishuHttpClient(FeishuConfig(app_id="id", app_secret="secret"), session)
    with pytest.raises(FeishuApiError):
        await client.request_bytes("GET", "/open-apis/im/v1/messages/om/resources/key")
    await session.aclose()


def test_redact_headers_is_case_insensitive() -> None:
    assert redact_headers({"Authorization": "Bearer token", "APP_SECRET": "secret", "x-token": "x", "ok": "yes"}) == {
        "Authorization": "***",
        "APP_SECRET": "***",
        "x-token": "***",
        "ok": "yes",
    }
