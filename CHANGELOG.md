# Changelog

## Unreleased

### Added

- UTC-aware event creation timestamps and raw schema 2.0 header/event mappings on `MessageEvent` and `CardActionEvent`.
- `FeishuClient.download_file_with_metadata()` for resource bytes together with response-derived filename and content type metadata.

### Compatibility

- Existing `FeishuClient.download_file()` behavior is unchanged: it returns `bytes`.
