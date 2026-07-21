import json

import httpx
import pytest

from feishulib.client import FeishuClient
from feishulib.config import FeishuConfig
from feishulib.exceptions import FeishuHttpStatusError


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
            return httpx.Response(200, headers={"Content-Disposition": 'attachment; filename="x.txt"', "Content-Type": "text/plain; charset=utf-8"}, content=b"file", request=request)
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om"}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        await client.reply_text("om/a", "reply")
        await client.update_card("om/a", {"elements": []})
        await client.delete_message("om/a")
        assert await client.download_file("om/a", "key/a") == b"file"
    assert any("om%2Fa/reply" in path or "om/a/reply" in path for path in paths)


@pytest.mark.asyncio
async def test_download_file_with_metadata_preserves_response_metadata() -> None:
    resource_content_type: str | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal resource_content_type
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200}, request=request)
        resource_content_type = request.headers.get("Content-Type")
        return httpx.Response(
            200,
            headers={"Content-Disposition": 'attachment; filename="x.txt"', "Content-Type": "text/plain; charset=utf-8"},
            content=b"file",
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        response = await client.download_file_with_metadata("om/a", "key/a")

    assert response.content == b"file"
    assert resource_content_type == "application/json; charset=utf-8"
    assert response.filename == "x.txt"
    assert response.content_type == "text/plain"


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


@pytest.mark.asyncio
async def test_generic_request_sends_json_and_managed_tenant_token() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200}, request=request)
        observed["method"] = request.method
        observed["path"] = request.url.path
        observed["params"] = dict(request.url.params)
        observed["authorization"] = request.headers["Authorization"]
        observed["caller_trace"] = request.headers["X-Caller-Trace"]
        observed["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"open_id": "ou_1"}]}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        response = await client.request(
            "POST",
            "/open-apis/contact/v3/users/search",
            params={"user_id_type": "open_id"},
            json_body={"department_id": "0"},
            headers={"X-Caller-Trace": "trace-1"},
        )

    assert response.data == {"items": [{"open_id": "ou_1"}]}
    assert observed["method"] == "POST"
    assert observed["path"] == "/open-apis/contact/v3/users/search"
    assert observed["params"] == {"user_id_type": "open_id"}
    assert observed["body"] == {"department_id": "0"}
    assert observed["authorization"] == "Bearer tenant-token"
    assert observed["caller_trace"] == "trace-1"


@pytest.mark.asyncio
async def test_generic_request_uses_explicit_token_without_refreshing_it() -> None:
    paths: list[str] = []
    authorizations: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("tenant_access_token/internal"):
            raise AssertionError("explicit token requests must not obtain a tenant token")
        authorizations.append(request.headers["Authorization"])
        return httpx.Response(200, json={"code": 0, "data": {"name": "Ada"}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        response = await client.request("GET", "/open-apis/authen/v1/user_info", access_token="user-token")

    assert response.data == {"name": "Ada"}
    assert paths == ["/open-apis/authen/v1/user_info"]
    assert authorizations == ["Bearer user-token"]


@pytest.mark.asyncio
async def test_generic_request_does_not_refresh_an_explicit_token_after_401() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["Authorization"] == "Bearer user-token"
        return httpx.Response(401, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        with pytest.raises(FeishuHttpStatusError) as raised:
            await client.request("GET", "/open-apis/authen/v1/user_info", access_token="user-token")

    assert raised.value.status_code == 401
    assert calls == 1


@pytest.mark.asyncio
async def test_generic_request_retries_once_after_401_with_refreshed_managed_token() -> None:
    token_calls = 0
    authorizations: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path.endswith("tenant_access_token/internal"):
            token_calls += 1
            return httpx.Response(200, json={"code": 0, "tenant_access_token": f"t{token_calls}", "expire": 7200}, request=request)
        authorizations.append(request.headers["Authorization"])
        if request.headers["Authorization"] == "Bearer t1":
            return httpx.Response(401, request=request)
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        response = await client.request("GET", "/open-apis/any/v1/resource")

    assert response.data == {"ok": True}
    assert token_calls == 2
    assert authorizations == ["Bearer t1", "Bearer t2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "headers", "access_token", "message"),
    [
        ("https://open.feishu.cn/open-apis/contact/v3/users", None, None, "path must begin with /open-apis/"),
        ("/callback/ws/endpoint", None, None, "path must begin with /open-apis/"),
        ("/open-apis/contact/v3/users", {"authorization": "Bearer unsafe"}, None, "headers must not contain Authorization"),
        ("/open-apis/contact/v3/users", None, "", "access_token must not be empty"),
    ],
)
async def test_generic_request_rejects_ambiguous_or_non_open_api_inputs(
    path: str,
    headers: dict[str, str] | None,
    access_token: str | None,
    message: str,
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))) as session:
        client = FeishuClient(FeishuConfig(app_id="id", app_secret="secret"), session=session)
        with pytest.raises(ValueError, match=message):
            await client.request("GET", path, headers=headers, access_token=access_token)
