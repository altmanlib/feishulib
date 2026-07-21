"""Tenant access token caching and refresh coordination."""

import asyncio
import time
from collections.abc import Callable

from feishulib.config import FeishuConfig
from feishulib.exceptions import FeishuAuthError, FeishuError
from feishulib.http import FeishuHttpClient
from feishulib.models import JsonValue


class TenantAccessTokenManager:
    """Return cached tenant tokens and collapse concurrent refreshes."""

    def __init__(
        self,
        config: FeishuConfig,
        http: FeishuHttpClient,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._http = http
        self._clock = clock
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self._expires_at = 0.0

    async def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid tenant access token, refreshing it once when needed."""
        observed_token = self._token
        if not force_refresh and self._is_fresh():
            return self._token_or_error()
        async with self._lock:
            if not force_refresh and self._is_fresh():
                return self._token_or_error()
            if force_refresh and self._token != observed_token and self._is_fresh():
                return self._token_or_error()
            return await self._refresh()

    def _is_fresh(self) -> bool:
        return self._token is not None and self._clock() < self._expires_at - self._config.token_refresh_skew_seconds

    def _token_or_error(self) -> str:
        if self._token is None:
            raise FeishuAuthError("tenant token cache was unexpectedly empty")
        return self._token

    async def _refresh(self) -> str:
        body: dict[str, JsonValue] = {"app_id": self._config.app_id, "app_secret": self._config.app_secret}
        try:
            response = await self._http.request_json(
                "POST",
                "/open-apis/auth/v3/tenant_access_token/internal",
                json_body=body,
            )
            token = response.data.get("tenant_access_token")
            expires_in = response.data.get("expire")
            if not isinstance(token, str) or not token:
                raise ValueError("tenant token is missing or invalid")
            if not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in <= 0:
                raise ValueError("token expiry is missing or invalid")
        except (FeishuError, ValueError) as error:
            raise FeishuAuthError("tenant token refresh failed") from error
        self._token = token
        self._expires_at = self._clock() + expires_in
        return token
