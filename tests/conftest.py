"""Shared test fixtures for Feishu IM client tests."""

import httpx


def response_with_request(
    status_code: int,
    request: httpx.Request,
    **kwargs: object,
) -> httpx.Response:
    return httpx.Response(status_code, request=request, **kwargs)
