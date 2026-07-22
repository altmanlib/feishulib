# Changelog

All notable changes to `feishulib` are documented here.

## [Unreleased]

### Added

- `FeishuClient.get_tenant_access_token(force_refresh=False)` for explicitly obtaining the managed tenant access token.
- `FeishuClient.download_file_with_metadata()` for downloading resource bytes together with response-derived filename and content type metadata.
- UTC-aware event creation timestamps and raw schema 2.0 header/event mappings on `MessageEvent` and `CardActionEvent`.

### Documentation

- Expanded the Quick Start guide with a complete asynchronous example, environment-based credentials, common entry points, and links to runnable examples.

### Compatibility

- Existing `FeishuClient.download_file()` behavior is unchanged: it continues to return `bytes`.
