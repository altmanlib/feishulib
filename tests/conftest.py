"""Shared test fixtures for Feishu IM client tests."""

import httpx2


def response_with_request(
    status_code: int,
    request: httpx2.Request,
    **kwargs: object,
) -> httpx2.Response:
    return httpx2.Response(status_code, request=request, **kwargs)
