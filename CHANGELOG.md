# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Added

- Added `safe_upsert()` as an SDK-agnostic Python API for validation, metadata fixing,
  sidecar persistence, and injected index upsert calls.
- Added `FileStore` and `SQLiteStore` sidecar backends with content-addressed
  deduplication.
- Added `hydrate_records_from_store()` for restoring records from store-backed
  `content_ref` values.

## 0.2.0 - 2026-06-11

### Added

- Added `vectormeta validate` for preflight record checks before vector database upsert.
- Added `validate_records()` as a reusable Python API.
- Added validation reports with error and warning severity.
- Added checks for metadata size, missing IDs, duplicate IDs, vector shape, vector
  dimension consistency, optional `--dim` matching, and Pinecone metadata value rules.

## 0.1.0 - 2026-06-07

Initial public MVP release.

### Added

- Added `vectormeta scan` for JSON and JSONL vector records.
- Added compact UTF-8 JSON byte sizing for metadata and top-level fields.
- Added oversized-record reporting with stable JSON output and Rich table output.
- Added `vectormeta fix` to move heavy metadata fields into local JSON sidecars.
- Added `vectormeta hydrate` to restore sidecar payloads into metadata or a separate
  content field.
- Added `vectormeta limits` for Pinecone, Chroma, Qdrant, Weaviate, and custom target
  presets.
- Added optional YAML config support for fix options.
- Added example records, example config, and end-to-end CLI usage docs.
- Added a static project website under `site/` with a GitHub Pages deployment workflow.

### Improved

- Preserved unknown record fields and original record order during fix/hydrate workflows.
- Added advisory warnings for non-Pinecone target presets in human output.
- Added documentation for metadata reduction logic, architecture, testing, vector DB
  limit notes, contribution flow, security reporting, and roadmap.
- Added GitHub Actions CI for tests, Ruff linting/formatting, Mypy, and package build.

### Hardened

- Added output overwrite protection for generated records and sidecar files.
- Added sanitized sidecar filenames for record IDs with unsafe path characters.
- Added duplicate sidecar path detection.
- Added `content_ref` collision protection with `--content-ref-field` escape hatch.
- Added sidecar hydration path checks to reduce path traversal risk.

### Tested

- Added tests for Unicode byte sizing, nested metadata sizing, analyzer behavior, JSON and
  JSONL input, fixer output, sidecar overwrite protection, hydration, CLI exit codes,
  advisory warnings, and oversized-after-fix warnings.

### Known Limitations

- Sidecars are local JSON files and one file per changed record.
- Repeated payload deduplication, streaming JSONL processing, SQLite sidecars, and S3
  sidecars are planned follow-ups.
- Non-Pinecone target limits are advisory defaults and should be verified against each
  deployment.
