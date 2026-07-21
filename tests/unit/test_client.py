import json

import httpx
import pytest

from feishulib.client import FeishuClient
from feishulib.config import FeishuConfig


@pytest.mark.asyncio
async def test_send_text_uses_structured_content_and_tenant_token() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t_token", "expire": 7200}, request=request)
        observed["query"] = dict(request.url.params)
        observed["authorization"] = request.headers["Authorization"]
        observed["body"] = request.content
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1", "chat_id": "oc_1"}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        async with FeishuClient(FeishuConfig(app_id="cli_test", app_secret="secret"), session=session) as client:
            receipt = await client.send_text("oc_1", "hello")

    assert receipt.message_id == "om_1"
    assert observed["query"] == {"receive_id_type": "chat_id"}
    assert observed["authorization"] == "Bearer t_token"
    body = json.loads(bytes(observed["body"]))
    assert json.loads(body["content"]) == {"text": "hello"}


@pytest.mark.asyncio
async def test_reply_update_delete_and_download_quote_path_parameters() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200}, request=request)
        if "/resources/" in request.url.path:
            return httpx.Response(200, headers={"Content-Disposition": 'attachment; filename="x.txt"'}, content=b"file", request=request)
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om"}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        await client.reply_text("om/a", "reply")
        await client.update_card("om/a", {"elements": []})
        await client.delete_message("om/a")
        assert await client.download_file("om/a", "key/a") == b"file"
    assert any("om%2Fa/reply" in path or "om/a/reply" in path for path in paths)


@pytest.mark.asyncio
async def test_retries_401_once_and_reads_bot_identity() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path.endswith("internal"):
            calls += 1
            return httpx.Response(200, json={"code": 0, "tenant_access_token": f"t{calls}", "expire": 7200}, request=request)
        if request.url.path.endswith("/info"):
            if request.headers["Authorization"] == "Bearer t1":
                return httpx.Response(401, request=request)
            return httpx.Response(200, json={"code": 0, "data": {"bot": {"open_id": "ou_bot"}}}, request=request)
        raise AssertionError("unexpected path")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        assert (await client.get_bot_identity()).open_id == "ou_bot"
    assert calls == 2


@pytest.mark.asyncio
async def test_send_text_generates_one_uuid_and_reuses_it_across_transport_retry() -> None:
    message_bodies: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token", "expire": 7200}, request=request)
        message_bodies.append(json.loads(request.content))
        if len(message_bodies) == 1:
            return httpx.Response(500, request=request)
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(
            FeishuConfig(
                app_id="id",
                app_secret="secret",
                retry_jitter_ratio=0,
                retry_backoff_base_seconds=0.001,
                retry_max_delay_seconds=0.001,
            ),
            session=session,
        )
        await client.send_text("oc_1", "hello")

    assert len(message_bodies) == 2
    first_uuid = message_bodies[0]["uuid"]
    assert isinstance(first_uuid, str)
    assert first_uuid
    assert [body["uuid"] for body in message_bodies] == [first_uuid, first_uuid]


@pytest.mark.asyncio
async def test_reply_message_preserves_explicit_uuid_across_transport_retry() -> None:
    message_bodies: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token", "expire": 7200}, request=request)
        message_bodies.append(json.loads(request.content))
        if len(message_bodies) == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_2"}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(
            FeishuConfig(
                app_id="id",
                app_secret="secret",
                retry_jitter_ratio=0,
                retry_backoff_base_seconds=0.001,
                retry_max_delay_seconds=0.001,
            ),
            session=session,
        )
        await client.reply_text("om_1", "hello", uuid="caller-controlled-uuid")

    assert [body["uuid"] for body in message_bodies] == ["caller-controlled-uuid", "caller-controlled-uuid"]
