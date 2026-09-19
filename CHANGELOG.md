# Changelog

All notable changes to `feishulib` are documented here.

## [Unreleased]

### Added

- `FeishuClient.get_tenant_access_token(force_refresh=False)` for explicitly obtaining the managed tenant access token.
- `FeishuClient.download_file_with_metadata()` for downloading resource bytes together with response-derived filename and content type metadata.
- UTC-aware event creation timestamps and raw schema 2.0 header/event mappings on `MessageEvent` and `CardActionEvent`.

### Changed

- HTTP client moved from `httpx` to `httpx2`, the maintained continuation of `httpx 0.28.1`. `FeishuClient(session=...)` and `FeishuWebSocket(session=...)` now accept an `httpx2.AsyncClient`, and `request_raw()` returns an `httpx2.Response`.
- TLS verification now uses the operating system trust store via `truststore` instead of `certifi` bundled certificates. `SSL_CERT_FILE` and `SSL_CERT_DIR` remain supported.
- Default `User-Agent` is now `python-httpx2/<version>`, and transport loggers are `httpx2` and `httpcore2.*`.

### Fixed

- `feishulib.__version__` now reports the installed distribution version instead of a stale hardcoded value.

### Documentation

- Expanded the Quick Start guide with a complete asynchronous example, environment-based credentials, common entry points, and links to runnable examples.

### Compatibility

- Existing `FeishuClient.download_file()` behavior is unchanged: it continues to return `bytes`.
