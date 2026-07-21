# Preserve Event Metadata Implementation Plan

**Goal:** Expose schema 2.0 event timestamps and controlled raw protocol mappings while preserving message resource metadata returned by Feishu downloads

**Architecture:** Parse `header.create_time` as a UTC-aware `datetime`, accepting Unix seconds and milliseconds and returning `None` when absent or malformed. Copy `header` and `event` into typed DTO mappings so new protocol fields remain available without changing trust boundaries. Keep `download_file()` byte-compatible and add an opt-in method returning the existing `BinaryResponse` metadata parsed from response headers

**Tech Stack:** Python 3.12, dataclasses, pytest, httpx mock transport, Ruff, Pyright

## Global Constraints

- `create_time` is UTC-aware and accepts Unix seconds and milliseconds
- Missing or malformed `header.create_time` returns `None`; event structural validation remains unchanged
- Raw protocol mappings are untrusted and must not be used as an identity-authentication source
- `im.message.receive_v1` supplies `file_key`; it does not supply an authoritative filename or MIME type in message content
- Never derive filename or MIME type from `file_key`
- `download_file()` continues to return `bytes`

---

### Task 1: Add event-metadata regression tests

**Files:**

- Modify: `tests/unit/test_events.py`
- Modify: `tests/fixtures/message_receive.json`
- Modify: `tests/fixtures/card_action.json`

**Interfaces:**

- Consumes: `parse_event_payload(payload: bytes) -> MessageEvent | CardActionEvent`
- Produces: tests requiring `create_time: datetime | None`, `raw_header`, and `raw_event` on both event DTOs

- [ ] **Step 1: Write the failing tests**

```python
from datetime import UTC, datetime

assert event.create_time == datetime(2026, 7, 21, 6, 30, tzinfo=UTC)
assert event.raw_header["create_time"] == "1784615400"
assert event.raw_event["message"] == {
    "message_id": "om_message",
    "chat_id": "oc_chat",
    "chat_type": "group",
    "message_type": "text",
    "content": "{\"text\":\"hello\"}",
}
```

Add inline JSON payload tests for `1784615400123` milliseconds and invalid `create_time` returning `None`

- [ ] **Step 2: Run the focused test target and verify RED**

Run: `uv run pytest tests/unit/test_events.py -q`

Expected: FAIL because event DTOs do not expose `create_time`, `raw_header`, or `raw_event`

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_events.py tests/fixtures/message_receive.json tests/fixtures/card_action.json
git commit -m "test: add event metadata regressions"
```

### Task 2: Parse and expose event metadata

**Files:**

- Modify: `src/feishulib/events.py`

**Interfaces:**

- Consumes: validated schema 2.0 `header: Mapping[str, object]` and `event: Mapping[str, object]`
- Produces: `MessageEvent.create_time`, `CardActionEvent.create_time`, `MessageEvent.raw_header`, `CardActionEvent.raw_header`, `MessageEvent.raw_event`, and `CardActionEvent.raw_event`

- [ ] **Step 1: Implement the minimum parser and DTO fields**

```python
from datetime import UTC, datetime


def _create_time(value: object) -> datetime | None:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    try:
        timestamp = int(value)
    except ValueError:
        return None
    if timestamp < 0:
        return None
    if timestamp >= 10_000_000_000:
        timestamp /= 1_000
    try:
        return datetime.fromtimestamp(timestamp, UTC)
    except (OverflowError, OSError, ValueError):
        return None
```

Append defaulted fields to both DTOs and populate them using copied mappings cast to `Mapping[str, JsonValue]`

- [ ] **Step 2: Run the focused test target and verify GREEN**

Run: `uv run pytest tests/unit/test_events.py -q`

Expected: PASS

- [ ] **Step 3: Commit the GREEN checkpoint**

```bash
git add src/feishulib/events.py
git commit -m "feat: preserve event metadata"
```

### Task 3: Return download response metadata without breaking bytes API

**Files:**

- Modify: `tests/unit/test_client.py`
- Modify: `src/feishulib/client.py`

**Interfaces:**

- Consumes: `FeishuClient._authorized_bytes(...) -> BinaryResponse`
- Produces: `FeishuClient.download_file_with_metadata(message_id, file_key, *, resource_type="file") -> BinaryResponse`

- [ ] **Step 1: Write the failing integration test**

```python
response = await client.download_file_with_metadata("om/a", "key/a")
assert response.content == b"file"
assert response.filename == "x.txt"
assert response.content_type == "text/plain"
```

Set the mocked resource response header `Content-Type` to `text/plain; charset=utf-8`

- [ ] **Step 2: Run the focused test target and verify RED**

Run: `uv run pytest tests/unit/test_client.py -q`

Expected: FAIL because `download_file_with_metadata` does not exist

- [ ] **Step 3: Implement the opt-in metadata method**

```python
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
        params={"type": resource_type},
    )
```

Keep `download_file()` returning `response.content` from this method

- [ ] **Step 4: Run the focused test target and verify GREEN**

Run: `uv run pytest tests/unit/test_client.py -q`

Expected: PASS

- [ ] **Step 5: Commit the GREEN checkpoint**

```bash
git add tests/unit/test_client.py src/feishulib/client.py
git commit -m "feat: expose downloaded resource metadata"
```

### Task 4: Document public behavior and validate the project

**Files:**

- Modify: `README.md`
- Create: `CHANGELOG.md`

**Interfaces:**

- Documents: DTO metadata fields and `download_file_with_metadata()` return value

- [ ] **Step 1: Document the event metadata contract**

Add a README section stating that `create_time` is a UTC-aware timestamp parsed from Unix seconds or milliseconds, invalid/missing values are `None`, and raw mappings are untrusted protocol input that must not authenticate identities

- [ ] **Step 2: Document resource metadata provenance**

Add a README example for `download_file_with_metadata()`. State that message content supplies only `file_key`; `BinaryResponse.filename` and `content_type` come from the download HTTP response and can be `None`

- [ ] **Step 3: Add release notes**

```markdown
# Changelog

## Unreleased

### Added

- UTC-aware event creation timestamps and raw schema 2.0 header/event mappings
- `FeishuClient.download_file_with_metadata()` returning download bytes and response metadata

### Compatibility

- Existing `download_file()` continues to return `bytes`
```

- [ ] **Step 4: Run the complete quality gate**

Run: `uv sync --all-groups && bash scripts/verify`

Expected: all tests, Ruff, Pyright, and coverage checks pass

- [ ] **Step 5: Commit documentation and verification-ready changes**

```bash
git add README.md CHANGELOG.md docs/plan/2026-07-21-preserve-event-metadata.md
git commit -m "docs: describe event and resource metadata"
```
