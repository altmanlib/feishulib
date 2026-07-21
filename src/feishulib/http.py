"""Resilient asynchronous HTTP transport for Feishu APIs."""

import asyncio
import json
import random
from collections.abc import Awaitable, Callable, Mapping
from email.message import Message
from typing import cast

import httpx

from feishulib.config import FeishuConfig
from feishulib.exceptions import (
    FeishuApiError,
    FeishuHttpStatusError,
    FeishuProtocolError,
    FeishuTransientError,
)
from feishulib.models import ApiResponse, BinaryResponse, JsonValue

type Sleep = Callable[[float], Awaitable[None]]
type RandomFloat = Callable[[], float]

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return headers with credentials replaced by a safe marker."""
    return {
        key: "***" if any(term in key.lower() for term in ("authorization", "secret", "token")) else value
        for key, value in headers.items()
    }


class FeishuHttpClient:
    """Small transport wrapper that validates Feishu API envelopes."""

    def __init__(
        self,
        config: FeishuConfig,
        session: httpx.AsyncClient,
        *,
        sleep: Sleep = asyncio.sleep,
        random_float: RandomFloat = random.random,
    ) -> None:
        self.config = config
        self._session = session
        self._sleep = sleep
        self._random_float = random_float

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, JsonValue] | None = None,
    ) -> ApiResponse:
        response = await self._request(method, path, headers=headers, params=params, json_body=json_body)
        body = self._json_object(response)
        return self._api_response(response, body)

    async def request_bytes(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> BinaryResponse:
        response = await self._request(method, path, headers=headers, params=params, json_body=None)
        if "json" in response.headers.get("content-type", "").lower():
            self._api_response(response, self._json_object(response))
            raise FeishuProtocolError("binary endpoint returned a successful JSON envelope")
        content_type = response.headers.get("content-type", "").split(";", 1)[0] or None
        return BinaryResponse(
            content=response.content,
            filename=self._filename(response.headers.get("content-disposition")),
            content_type=content_type,
            headers=dict(response.headers),
            request_id=self._request_id(response),
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None,
        params: Mapping[str, str] | None,
        json_body: Mapping[str, JsonValue] | None,
    ) -> httpx.Response:
        if not path.startswith(("/open-apis/", "/callback/")):
            raise ValueError("path must begin with /open-apis/ or /callback/")
        url = f"{self.config.base_url.rstrip('/')}{path}"
        last_status: int | None = None
        last_request_id: str | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self._session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=self.config.request_timeout_seconds,
                )
            except httpx.RequestError as error:
                if attempt == self.config.max_retries:
                    raise FeishuTransientError(None, attempt + 1) from error
                await self._sleep(self._delay(attempt, None))
                continue
            last_status = response.status_code
            last_request_id = self._request_id(response)
            if response.status_code in _RETRYABLE_STATUSES:
                if attempt == self.config.max_retries:
                    raise FeishuTransientError(response.status_code, attempt + 1, last_request_id)
                await self._sleep(self._delay(attempt, response.headers.get("retry-after")))
                continue
            if not 200 <= response.status_code < 300:
                raise FeishuHttpStatusError(
                    response.status_code,
                    self._safe_message(response),
                    last_request_id,
                )
            return response
        raise FeishuTransientError(last_status, self.config.max_retries + 1, last_request_id)

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        try:
            retry_delay = float(retry_after) if retry_after is not None else -1.0
        except ValueError:
            retry_delay = -1.0
        if retry_delay >= 0:
            return min(self.config.retry_max_delay_seconds, retry_delay)
        delay = min(
            self.config.retry_max_delay_seconds,
            self.config.retry_backoff_base_seconds * 2**attempt,
        )
        return delay + delay * self.config.retry_jitter_ratio * self._random_float()

    def _api_response(self, response: httpx.Response, body: Mapping[str, object]) -> ApiResponse:
        code = body.get("code")
        if not isinstance(code, int) or isinstance(code, bool):
            raise FeishuProtocolError("JSON response code must be an integer")
        request_id = self._request_id(response)
        message = body.get("msg", "")
        if not isinstance(message, str):
            message = "invalid API message"
        if code != 0:
            raise FeishuApiError(code, message, request_id)
        data = body.get("data")
        if data is None and "data" not in body:
            data = {key: value for key, value in body.items() if key not in {"code", "msg"}}
        if not isinstance(data, Mapping):
            raise FeishuProtocolError("JSON response data must be an object")
        return ApiResponse(
            data=cast(Mapping[str, JsonValue], data),
            headers=dict(response.headers),
            status_code=response.status_code,
            request_id=request_id,
        )

    @staticmethod
    def _json_object(response: httpx.Response) -> Mapping[str, object]:
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise FeishuProtocolError("response body is not valid JSON") from error
        if not isinstance(body, Mapping):
            raise FeishuProtocolError("response JSON must be an object")
        return cast(Mapping[str, object], body)

    @staticmethod
    def _request_id(response: httpx.Response) -> str | None:
        return response.headers.get("x-request-id") or response.headers.get("x-tt-logid")

    @staticmethod
    def _safe_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "HTTP request failed"
        if isinstance(body, Mapping):
            mapped_body = cast(Mapping[str, object], body)
            message = mapped_body.get("msg")
            if isinstance(message, str):
                return message
        return "HTTP request failed"

    @staticmethod
    def _filename(content_disposition: str | None) -> str | None:
        if content_disposition is None:
            return None
        message = Message()
        message["content-disposition"] = content_disposition
        filename = message.get_param("filename", header="content-disposition")
        return filename if isinstance(filename, str) else None
