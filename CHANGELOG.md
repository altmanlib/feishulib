# Changelog

## Unreleased

### Added

- `FeishuClient.get_tenant_access_token()` to explicitly obtain the cached or freshly refreshed tenant access token.
- UTC-aware event creation timestamps and raw schema 2.0 header/event mappings on `MessageEvent` and `CardActionEvent`.
- `FeishuClient.download_file_with_metadata()` for resource bytes together with response-derived filename and content type metadata.

### Documentation

- Expanded the Quick Start guide with a complete asynchronous example, environment-based credentials, and common entry points.

### Compatibility

- Existing `FeishuClient.download_file()` behavior is unchanged: it returns `bytes`.
