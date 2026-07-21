"""High-level asynchronous Feishu IM and bot client."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Literal, Self
from urllib.parse import quote
from uuid import uuid4

import httpx

from feishulib.auth import TenantAccessTokenManager
from feishulib.config import FeishuConfig
from feishulib.exceptions import FeishuApiError, FeishuHttpStatusError
from feishulib.http import FeishuHttpClient, RequestContent, RequestData, RequestFiles
from feishulib.models import (
    ApiResponse,
    BinaryResponse,
    BotIdentity,
    JsonValue,
    MessageReceipt,
    OutboundMessage,
    ReceiveIdType,
    ReplyMessage,
    UpdateMessage,
)


class FeishuClient:
    """Facade for the selected Feishu IM REST surface."""

    def __init__(self, config: FeishuConfig, *, session: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._owns_session = session is None
        self._session = session if session is not None else httpx.AsyncClient()
        self._http = FeishuHttpClient(config, self._session)
        self._tokens = TenantAccessTokenManager(config, self._http)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_session:
            await self._session.aclose()

    @staticmethod
    def _outbound_with_uuid(message: OutboundMessage) -> OutboundMessage:
        if message.uuid is not None:
            return message
        return replace(message, uuid=str(uuid4()))

    @staticmethod
    def _reply_with_uuid(message: ReplyMessage) -> ReplyMessage:
        if message.uuid is not None:
            return message
        return replace(message, uuid=str(uuid4()))

    async def send_message(self, message: OutboundMessage) -> MessageReceipt:
        message = self._outbound_with_uuid(message)
        response = await self._authorized_json(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": message.receive_id_type},
            json_body=message.to_payload(),
        )
        return self._receipt(response)

    async def send_text(
        self,
        receive_id: str,
        text: str,
        *,
        receive_id_type: ReceiveIdType = "chat_id",
        uuid: str | None = None,
    ) -> MessageReceipt:
        return await self.send_message(OutboundMessage(receive_id, receive_id_type, "text", {"text": text}, uuid))

    async def send_card(
        self,
        receive_id: str,
        card: Mapping[str, JsonValue],
        *,
        receive_id_type: ReceiveIdType = "chat_id",
        uuid: str | None = None,
    ) -> MessageReceipt:
        return await self.send_message(OutboundMessage(receive_id, receive_id_type, "interactive", card, uuid))

    async def reply_message(self, message: ReplyMessage) -> MessageReceipt:
        message = self._reply_with_uuid(message)
        response = await self._authorized_json(
            "POST",
            f"/open-apis/im/v1/messages/{quote(message.message_id, safe='')}/reply",
            json_body=message.to_payload(),
        )
        return self._receipt(response)

    async def reply_text(
        self,
        message_id: str,
        text: str,
        *,
        reply_in_thread: bool = False,
        uuid: str | None = None,
    ) -> MessageReceipt:
        return await self.reply_message(ReplyMessage(message_id, "text", {"text": text}, reply_in_thread, uuid))

    async def update_message(self, message: UpdateMessage) -> MessageReceipt:
        response = await self._authorized_json(
            "PUT",
            f"/open-apis/im/v1/messages/{quote(message.message_id, safe='')}",
            json_body=message.to_payload(),
        )
        return self._receipt(response)

    async def update_card(self, message_id: str, card: Mapping[str, JsonValue]) -> MessageReceipt:
        return await self.update_message(UpdateMessage(message_id, "interactive", card))

    async def delete_message(self, message_id: str) -> None:
        await self._authorized_json("DELETE", f"/open-apis/im/v1/messages/{quote(message_id, safe='')}")

    async def download_file(
        self,
        message_id: str,
        file_key: str,
        *,
        resource_type: Literal["file", "image"] = "file",
    ) -> bytes:
        response = await self.download_file_with_metadata(message_id, file_key, resource_type=resource_type)
        return response.content

    async def download_file_with_metadata(
        self,
        message_id: str,
        file_key: str,
        *,
        resource_type: Literal["file", "image"] = "file",
    ) -> BinaryResponse:
        return await self._authorized_bytes(
            "GET",
            f"/open-apis/im/v1/messages/{quote(message_id, safe='')}/resources/{quote(file_key, safe='')}",
            headers={"Content-Type": "application/json; charset=utf-8"},
            params={"type": resource_type},
        )

    async def get_bot_identity(self) -> BotIdentity:
        response = await self._authorized_json("GET", "/open-apis/bot/v3/info")
        candidate = response.data.get("bot")
        if not isinstance(candidate, Mapping):
            candidate = response.data
        open_id = candidate.get("open_id")
        if not isinstance(open_id, str) or not open_id:
            raise FeishuApiError(0, "bot identity response has no open_id", response.request_id)
        return BotIdentity(open_id)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, JsonValue] | None = None,
        headers: Mapping[str, str] | None = None,
        access_token: str | None = None,
        retry: bool | None = None,
    ) -> ApiResponse:
        """Call a Feishu Open API endpoint that returns a standard JSON envelope."""
        self._validate_generic_request(path, headers, access_token)
        should_retry = self._should_retry(method, retry)
        if access_token is not None:
            return await self._http.request_json(
                method,
                path,
                headers=self._authorization_headers(access_token, headers),
                params=params,
                json_body=json_body,
                retry=should_retry,
            )
        return await self._authorized_json(
            method,
            path,
            params=params,
            json_body=json_body,
            headers=headers,
            retry=should_retry,
        )

    async def request_raw(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: JsonValue | None = None,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        headers: Mapping[str, str] | None = None,
        access_token: str | None = None,
        retry: bool | None = None,
    ) -> httpx.Response:
        """Call an arbitrary Feishu Open API endpoint and return its HTTP response."""
        self._validate_generic_request(path, headers, access_token)
        self._validate_raw_body(json_body, content, data, files)
        should_retry = self._should_retry(method, retry)
        if access_token is not None:
            return await self._http.request_raw(
                method,
                path,
                headers=self._authorization_headers(access_token, headers),
                params=params,
                json_body=json_body,
                content=content,
                data=data,
                files=files,
                retry=should_retry,
            )
        return await self._authorized_raw(
            method,
            path,
            params=params,
            json_body=json_body,
            content=content,
            data=data,
            files=files,
            headers=headers,
            retry=should_retry,
        )

    async def _authorized_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, JsonValue] | None = None,
        headers: Mapping[str, str] | None = None,
        retry: bool = True,
    ) -> ApiResponse:
        token = await self._tokens.get_token()
        try:
            return await self._http.request_json(
                method,
                path,
                headers=self._authorization_headers(token, headers),
                params=params,
                json_body=json_body,
                retry=retry,
            )
        except FeishuHttpStatusError as error:
            if error.status_code != 401:
                raise
        token = await self._tokens.get_token(force_refresh=True)
        return await self._http.request_json(
            method,
            path,
            headers=self._authorization_headers(token, headers),
            params=params,
            json_body=json_body,
            retry=retry,
        )

    async def _authorized_raw(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None,
        json_body: JsonValue | None,
        content: RequestContent | None,
        data: RequestData | None,
        files: RequestFiles | None,
        headers: Mapping[str, str] | None,
        retry: bool,
    ) -> httpx.Response:
        token = await self._tokens.get_token()
        try:
            return await self._http.request_raw(
                method,
                path,
                headers=self._authorization_headers(token, headers),
                params=params,
                json_body=json_body,
                content=content,
                data=data,
                files=files,
                retry=retry,
            )
        except FeishuHttpStatusError as error:
            if error.status_code != 401:
                raise
        token = await self._tokens.get_token(force_refresh=True)
        return await self._http.request_raw(
            method,
            path,
            headers=self._authorization_headers(token, headers),
            params=params,
            json_body=json_body,
            content=content,
            data=data,
            files=files,
            retry=retry,
        )

    @staticmethod
    def _validate_generic_request(
        path: str,
        headers: Mapping[str, str] | None,
        access_token: str | None,
    ) -> None:
        if not path.startswith("/open-apis/"):
            raise ValueError("path must begin with /open-apis/")
        if headers is not None and any(name.lower() == "authorization" for name in headers):
            raise ValueError("headers must not contain Authorization")
        if access_token == "":
            raise ValueError("access_token must not be empty")

    @staticmethod
    def _validate_raw_body(
        json_body: JsonValue | None,
        content: RequestContent | None,
        data: RequestData | None,
        files: RequestFiles | None,
    ) -> None:
        if json_body is not None and (content is not None or data is not None or files is not None):
            raise ValueError("json_body cannot be combined with content, data, or files")
        if content is not None and (data is not None or files is not None):
            raise ValueError("content cannot be combined with data or files")

    @staticmethod
    def _should_retry(method: str, retry: bool | None) -> bool:
        if retry is not None:
            return retry
        return method.upper() in {"GET", "HEAD", "OPTIONS", "TRACE"}

    async def _authorized_bytes(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> BinaryResponse:
        token = await self._tokens.get_token()
        try:
            return await self._http.request_bytes(method, path, headers=self._authorization_headers(token, headers), params=params)
        except FeishuHttpStatusError as error:
            if error.status_code != 401:
                raise
        token = await self._tokens.get_token(force_refresh=True)
        return await self._http.request_bytes(method, path, headers=self._authorization_headers(token, headers), params=params)

    @staticmethod
    def _authorization_headers(token: str, headers: Mapping[str, str] | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", **(headers or {})}

    @staticmethod
    def _receipt(response: ApiResponse) -> MessageReceipt:
        message_id = response.data.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            raise FeishuApiError(0, "message response has no message_id", response.request_id)
        root_id = response.data.get("root_id")
        parent_id = response.data.get("parent_id")
        return MessageReceipt(
            message_id,
            root_id if isinstance(root_id, str) else None,
            parent_id if isinstance(parent_id, str) else None,
        )
