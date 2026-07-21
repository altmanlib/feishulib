# Generic Open API Request Implementation Plan

**Goal:** Expose stable asynchronous generic request methods for every Feishu Open API request and response shape without giving up token management, safe retry behavior, envelope validation, or typed JSON convenience results.

**Architecture:** `FeishuClient.request()` is the JSON-envelope convenience facade and returns `ApiResponse`. `FeishuClient.request_raw()` is the universal facade for multipart uploads, raw content, arbitrary JSON values, and binary responses; it returns a successful `httpx.Response` without parsing a business envelope. Both delegate to private authorized transport helpers, use a managed tenant token by default, and accept an explicit user or app bearer token that is never refreshed. Generic safe methods retry transient failures by default; generic unsafe methods require an explicit `retry=True` opt-in.

**Tech Stack:** Python 3.12, `httpx`, dataclasses, pytest + pytest-asyncio mock transport, Ruff, Pyright

## Global Constraints

- Python version floor remains `>=3.12`.
- Do not add runtime dependencies.
- The public method must only target relative Feishu Open API paths beginning with `/open-apis/`; absolute URLs and callback endpoints are not exposed through this facade.
- `request()` returns `ApiResponse` and validates Feishu's JSON `code` envelope; `request_raw()` returns an unparsed successful `httpx.Response` for multipart, raw-content, arbitrary-JSON, and binary-response endpoints.
- Default authentication uses the managed tenant access token and retries once after a 401; a non-empty explicit `access_token` is sent as `Bearer <access_token>` and is not refreshed on 401.
- Generic safe methods (`GET`, `HEAD`, `OPTIONS`, and `TRACE`) retry transient failures by default. Generic unsafe methods make exactly one transport attempt unless the caller passes `retry=True`.
- Caller headers are retained except that `Authorization` is rejected case-insensitively, so credential source is unambiguous and is never accidentally logged or overridden.
- Existing `FeishuClient` methods and private transport behavior must remain backward compatible.
- All new production behavior is test-first; the relevant test target must demonstrate RED before implementation and GREEN after implementation.

---

## Public API Contract

```python
from collections.abc import Mapping
from feishulib.models import ApiResponse, JsonValue

class FeishuClient:
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, JsonValue] | None = None,
        headers: Mapping[str, str] | None = None,
        access_token: str | None = None,
    ) -> ApiResponse: ...
```

Example for an endpoint that is not otherwise wrapped by the library:

```python
response = await client.request(
    "GET",
    "/open-apis/contact/v3/users",
    params={"user_id_type": "open_id", "page_size": "50"},
)
users = response.data["items"]
```

Example for a user-token endpoint:

```python
response = await client.request(
    "GET",
    "/open-apis/authen/v1/user_info",
    access_token=user_access_token,
)
```

`request_raw()` is the escape hatch for endpoint-specific payload and response shapes. It accepts mutually exclusive `json_body` and `content` inputs, or `data` together with `files` for multipart forms. Its response is already fully read by `httpx.AsyncClient`; streaming response lifetime management remains outside this client contract.

## File Structure

- Modify: `src/feishulib/client.py` — add the public facade and a small authorization helper shared by JSON callers.
- Modify: `tests/unit/test_client.py` — unit/integration-style mock-transport coverage of the public method's request construction and auth semantics.
- Modify: `tests/unit/test_public_api.py` — assert the public package continues to expose the intended client surface without exporting transport internals.
- Modify: `README.md` — document scope, signatures by example, managed tenant authentication, and explicit-token behavior.
- Create: `docs/plan/2026-07-21-generic-open-api-request.md` — this implementation plan.

### Task 1: Add a RED test suite for generic JSON requests

**Files:**

- Modify: `tests/unit/test_client.py`

**Interfaces:**

- Consumes: existing `FeishuClient(config, session=...)` and `httpx.MockTransport` test pattern.
- Produces: executable behavioral specifications for `FeishuClient.request()`.

- [ ] **Step 1: Add the tenant-token request test**

Append this test to `tests/unit/test_client.py`:

```python
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
```

- [ ] **Step 2: Add explicit-token, 401, and input-validation tests**

Append this test to `tests/unit/test_client.py`:

```python
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
```

- [ ] **Step 3: Run the new tests and confirm the RED gate**

Run: `uv run pytest tests/unit/test_client.py -q`

Expected: FAIL because `FeishuClient` has no `request` method. The failure must occur after pytest collects and executes the newly added tests, not because of an import or syntax failure.

- [ ] **Step 4: Commit the validated RED checkpoint**

```bash
git add tests/unit/test_client.py
git commit -m "test: add reproducer for generic Open API request"
```

### Task 2: Implement the public generic JSON facade

**Files:**

- Modify: `src/feishulib/client.py:157-190`
- Test: `tests/unit/test_client.py`

**Interfaces:**

- Consumes: `TenantAccessTokenManager.get_token(force_refresh=False | True)`, `FeishuHttpClient.request_json(...)`, `FeishuHttpStatusError`, and the tests in Task 1.
- Produces: `FeishuClient.request(method, path, *, params, json_body, headers, access_token) -> ApiResponse`.

- [ ] **Step 1: Add the public method immediately before `_authorized_json`**

Insert this method in `src/feishulib/client.py` after `get_bot_identity`:

```python
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, JsonValue] | None = None,
        headers: Mapping[str, str] | None = None,
        access_token: str | None = None,
    ) -> ApiResponse:
        """Call a Feishu Open API endpoint that returns a standard JSON envelope."""
        self._validate_generic_request(path, headers, access_token)
        if access_token is not None:
            return await self._http.request_json(
                method,
                path,
                headers=self._authorization_headers(access_token, headers),
                params=params,
                json_body=json_body,
            )
        return await self._authorized_json(method, path, params=params, json_body=json_body, headers=headers)
```

- [ ] **Step 2: Replace `_authorized_json` with a header-aware implementation and add validation**

Replace the existing `_authorized_json` definition with the following code, retaining `_authorized_bytes` below it unchanged:

```python
    async def _authorized_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, JsonValue] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ApiResponse:
        token = await self._tokens.get_token()
        try:
            return await self._http.request_json(
                method,
                path,
                headers=self._authorization_headers(token, headers),
                params=params,
                json_body=json_body,
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
```

- [ ] **Step 3: Preserve authorization precedence in the existing helper**

Ensure `_authorization_headers` continues to return the managed or explicit bearer credential together with non-auth caller headers:

```python
    @staticmethod
    def _authorization_headers(token: str, headers: Mapping[str, str] | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", **(headers or {})}
```

The public validation in Step 2 makes this merge safe for `request()`. Existing typed methods do not provide caller headers and therefore retain their behavior.

- [ ] **Step 4: Run the focused test file and confirm GREEN**

Run: `uv run pytest tests/unit/test_client.py -q`

Expected: PASS, including all tests added in Task 1 and all pre-existing client tests.

- [ ] **Step 5: Run static checks**

Run: `uv run ruff check src/feishulib/client.py tests/unit/test_client.py && uv run pyright`

Expected: both commands exit with status 0.

- [ ] **Step 6: Commit the validated GREEN checkpoint**

```bash
git add src/feishulib/client.py tests/unit/test_client.py
git commit -m "feat: add generic Open API request method"
```

### Task 3: Document and lock down the public contract

**Files:**

- Modify: `README.md:32-113`
- Modify: `tests/unit/test_public_api.py`

**Interfaces:**

- Consumes: `FeishuClient.request(...) -> ApiResponse` completed in Task 2.
- Produces: discoverable user documentation and regression protection for the intentionally small public surface.

- [ ] **Step 1: Add a README section after `## REST API`**

Insert this Markdown directly before `### Sending Messages` in `README.md`:

```markdown
### Generic Open API Requests

Use `request()` for a Feishu Open API JSON endpoint that is not yet available as a dedicated typed method. It accepts an HTTP method, a relative `/open-apis/` path, optional string query parameters, a JSON object body, and extra non-authentication headers.

```python
response = await client.request(
    "GET",
    "/open-apis/contact/v3/users",
    params={"user_id_type": "open_id", "page_size": "50"},
)
print(response.data["items"])
```

By default, the client obtains, caches, and refreshes a tenant access token. For an endpoint requiring a user or app access token, provide it explicitly; explicit tokens are not refreshed by the client:

```python
response = await client.request(
    "GET",
    "/open-apis/authen/v1/user_info",
    access_token=user_access_token,
)
```

`request()` only supports endpoints that use Feishu's standard JSON response envelope. It returns `ApiResponse` and raises the same transport and business exceptions as the dedicated methods. The `path` must begin with `/open-apis/`; do not supply an `Authorization` header because `access_token` is the explicit credential input.
```

- [ ] **Step 2: Add a public-surface regression assertion**

Read the complete current `tests/unit/test_public_api.py`, then add this isolated assertion using its existing import and assertion style:

```python
def test_feishu_client_exposes_generic_request() -> None:
    assert callable(feishulib.FeishuClient.request)
```

Do not export `FeishuHttpClient` or any new transport-only helper from `feishulib.__init__`; the public facade is the contract.

- [ ] **Step 3: Run documentation-adjacent regression tests**

Run: `uv run pytest tests/unit/test_public_api.py tests/unit/test_client.py -q`

Expected: PASS.

- [ ] **Step 4: Run the full quality gate and coverage measurement**

Run: `uv run pytest --cov=feishulib --cov-report=term-missing && uv run ruff check . && uv run pyright`

Expected: all tests and static checks pass; total coverage is at least 80% and the new branch paths (managed token, explicit token, 401 refresh, and validation rejection) are covered by `test_client.py`.

- [ ] **Step 5: Commit documentation and contract coverage**

```bash
git add README.md tests/unit/test_public_api.py
git commit -m "docs: describe generic Open API requests"
```

## Design Decisions and Non-Goals

1. **Use `request`, not a public transport class.** It is discoverable beside the existing high-level methods while keeping retry mechanics, response parsing, and session ownership private.
2. **Return `ApiResponse`.** The existing DTO already carries `data`, response headers, HTTP status, and request ID. This preserves current exception semantics and avoids exposing unvalidated JSON payloads as a second API style.
3. **Accept an explicit token rather than an authorization header.** A parameter makes the tenant-token versus caller-token behavior explicit, prevents conflicting credentials, and allows a documented no-refresh rule for user/app tokens.
4. **Constrain the path.** The library is a Feishu client, not a general HTTP proxy. Requiring a relative `/open-apis/` path avoids credential exfiltration through an arbitrary host and prevents presenting callback endpoints as externally callable REST APIs.
5. **Provide a raw escape hatch instead of overloading `ApiResponse`.** `request_raw()` carries multipart, raw, and binary traffic while `request()` retains strict business-envelope validation. This keeps both response contracts explicit; streaming response lifetime management remains outside this client contract.

## Self-Review

- **Spec coverage:** Task 1 specifies arbitrary method/path/query/body/header forwarding, managed tenant authentication, explicit-token authentication including non-refreshing 401 behavior, managed-token 401 refresh, and invalid input behavior. Task 2 implements those behaviors without altering existing typed calls. Task 3 documents the public contract and verifies the package surface.
- **Placeholder scan:** Every implementation and test step contains its intended signature or code; none defer behavior to a later unspecified step.
- **Type consistency:** All tasks use the same `request(method, path, *, params, json_body, headers, access_token) -> ApiResponse` signature. `ApiResponse` and `JsonValue` already exist in `feishulib.models`.
