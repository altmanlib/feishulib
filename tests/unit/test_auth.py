import asyncio
import json

import httpx
import pytest

from feishulib.auth import TenantAccessTokenManager
from feishulib.config import FeishuConfig
from feishulib.exceptions import FeishuAuthError
from feishulib.http import FeishuHttpClient


@pytest.mark.asyncio
async def test_concurrent_first_use_fetches_only_one_token() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/open-apis/auth/v3/tenant_access_token/internal"
        assert json.loads(request.content) == {"app_id": "cli_test", "app_secret": "secret"}
        await asyncio.sleep(0)
        return httpx.Response(200, json={"code": 0, "tenant_access_token": "t_1", "expire": 7200}, request=request)

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = FeishuHttpClient(FeishuConfig(app_id="cli_test", app_secret="secret"), session)
    manager = TenantAccessTokenManager(http.config, http)

    tokens = await asyncio.gather(*(manager.get_token() for _ in range(20)))

    assert tokens == ["t_1"] * 20
    assert calls == 1
    await session.aclose()


@pytest.mark.asyncio
async def test_refreshes_proactively_and_force_refreshes_once() -> None:
    now = 0.0
    calls = 0

    def clock() -> float:
        return now

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 0, "tenant_access_token": f"t_{calls}", "expire": 120}, request=request)

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    http = FeishuHttpClient(FeishuConfig(app_id="id", app_secret="secret"), session)
    manager = TenantAccessTokenManager(http.config, http, clock=clock)
    assert await manager.get_token() == "t_1"
    now = 60.0
    assert await manager.get_token() == "t_2"
    assert await manager.get_token(force_refresh=True) == "t_3"
    assert calls == 3
    await session.aclose()


@pytest.mark.asyncio
async def test_rejects_bad_token_response_without_leaking_secret() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "tenant_access_token": "", "expire": 0}, request=request)

    session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = FeishuConfig(app_id="id", app_secret="secret-value")
    manager = TenantAccessTokenManager(config, FeishuHttpClient(config, session))
    with pytest.raises(FeishuAuthError) as raised:
        await manager.get_token()
    assert "secret-value" not in str(raised.value)
    await session.aclose()
