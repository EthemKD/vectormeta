# Metadata Reduction Logic

This document explains exactly how `vectormeta` detects oversized metadata and reduces
record size.

## Size Measurement

Metadata size is measured as compact UTF-8 JSON bytes:

```python
json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
```

This is implemented in `vectormeta/sizing.py`.

The tool does not use `len(str(metadata))` because Python string representations are not
the payload that vector database clients serialize. Compact JSON byte sizing is more
predictable and handles Unicode correctly.

## Field Size Measurement

Field sizes are measured at the top-level metadata key:

```python
{"chunk_text": "..."}
{"raw_html": "..."}
{"nested_payload": {"tables": [...], "summary": "..."}}
```

Nested values are not split into subpaths. A nested object is measured as the serialized
JSON value of its top-level field. This keeps reports stable and makes move decisions
simple for an MVP.

## Scan Logic

`vectormeta scan` performs this flow:

1. Read records from JSON or JSONL.
2. Require each record to contain `id` or `_id`.
3. Require each record to contain a `metadata` object.
4. Resolve the target metadata limit.
5. Measure total metadata bytes.
6. Measure top-level field sizes.
7. Mark records as oversized when `metadata_size_bytes > limit_bytes`.
8. Render table output or stable JSON output.

## Validate Logic

`vectormeta validate` performs preflight checks for common upsert failures:

1. Read records from JSON or JSONL.
2. Resolve the target metadata limit.
3. Measure metadata with the same compact UTF-8 JSON byte sizing used by `scan`.
4. Report error-level issues for oversized metadata.
5. Report missing, empty, or duplicate `id` / `_id` values.
6. Check that vectors in `values`, `vector`, or `embedding` are non-empty finite numeric
   sequences.
7. Check that all vectors share the same dimension.
8. If `--dim` is provided, check that every vector matches that dimension.
9. For Pinecone, check documented metadata value rules: flat metadata, string keys, no
   keys starting with `$`, and values limited to strings, finite numbers, booleans, or
   lists of strings.
10. Render table output or stable JSON output.

Validation returns structured issues with `error` or `warning` severity. Error-level
issues make the CLI exit `1`, unless `--no-fail` is passed.

## Fix Logic

`vectormeta fix` performs this flow for each record:

1. Copy the record so unknown fields are preserved.
2. Copy metadata into a mutable dictionary.
3. Choose move fields:
   - Explicit `--move-fields`, if provided.
   - Otherwise the built-in heavy field list.
4. Move matching fields from metadata into a sidecar payload.
5. Add `content_ref` only when at least one field is moved.
6. Recalculate metadata size.
7. If the record is still oversized, move the largest non-keep fields one at a time.
8. If the record is still oversized and keep fields are the only remaining candidates,
   move keep fields with a warning.
9. If the record still cannot fit, return a warning for that record.
10. Return cleaned records, sidecar payloads, and warnings.

Default move fields:

```text
text, chunk_text, content, page_content, raw_text, raw_html, html, markdown,
summary, tables, table_data, ocr_text, full_document, document_text, body
```

Default keep fields:

```text
doc_id, chunk_id, source, url, file_name, file_path, page, page_number,
section, title, author, created_at, updated_at, tags, category, language
```

## Sidecar Safety

Sidecar behavior is designed to avoid common filesystem mistakes:

- Sidecar filenames are sanitized from record IDs.
- Duplicate sidecar filenames get deterministic suffixes.
- Existing `content_ref` metadata is not overwritten. Use `--content-ref-field` to choose
  another field name when inputs already use `content_ref`.
- Existing sidecar files are not overwritten unless `--overwrite` is passed.
- Output files are not overwritten unless `--overwrite` is passed.
- `content_ref` is relative to the output file's parent directory when possible.

## Sidecar Policy

The CLI `fix` command writes one sidecar JSON file per changed record. This keeps the
file-based scan/fix/hydrate workflow simple and predictable: every cleaned record points
to one sidecar file that contains the fields removed from that record.

The Python API also provides store-backed sidecars:

- `FileStore` writes content-addressed JSON payloads to a local directory.
- `SQLiteStore` writes content-addressed payloads to a local SQLite database.

Store-backed sidecars deduplicate identical moved payloads. For example, if 20 chunks
from the same document move the same `raw_html` value, the store can keep one payload and
reference it from many cleaned records. The payload hash ignores the record `id`, so
chunks with different IDs can still share identical moved content.

## Large File Policy

JSON arrays and JSONL files are currently loaded into memory before scanning or fixing.
This is acceptable for small and medium migration checks, but it is not the right shape
for millions of embedding chunks. Streaming JSONL scan/fix is a planned follow-up so
large pipelines can process records one at a time.

## Hydration Logic

`vectormeta hydrate` reads `content_ref`, loads the matching sidecar JSON file, and then
either:

- merges sidecar fields back into metadata, or
- writes sidecar fields to a separate record field such as `payload`.

Hydration removes `content_ref` after restoring the payload.

Sidecar references are resolved only inside the provided sidecar directory or input base
directory. Resolution preserves nested references. If a reference includes the sidecar
directory name, such as `sidecar/subdir/doc.json`, hydration may strip that leading
directory segment and resolve `subdir/doc.json` inside the provided sidecar directory.
It does not fall back to a bare filename before trying the nested path. This reduces
path traversal risk while avoiding accidental hydration from the wrong sidecar file.

For store-backed sidecars, `hydrate_records_from_store()` resolves `content_ref` through
the provided `FileStore` or `SQLiteStore` instead of reading from a sidecar directory.

## Correctness Checks

The test suite covers:

- Unicode byte sizing.
- Nested metadata field sizing.
- Oversized scan reporting.
- JSON array input.
- JSONL input.
- Fixer sidecar output.
- Largest non-keep field movement.
- Unsafe sidecar filename sanitization.
- Sidecar overwrite protection.
- Hydration into metadata.
- Hydration into a separate content field.
- Rejection of sidecar references outside allowed paths.
- CLI scan exit codes.
- CLI fix and hydrate round trip.
- Validation of Pinecone metadata value rules.
- Validation of duplicate/missing IDs.
- Validation of vector dimensions and invalid vector values.
- CLI validate exit codes and JSON output.
- FileStore and SQLiteStore sidecar deduplication.
- Store-backed hydration.
- Safe upsert validation, fixing, sidecar persistence, and injected index calls.

The local acceptance workflow also verifies that the included oversized example becomes
small enough after fixing:

```bash
vectormeta scan examples/oversized_pinecone_records.json --target pinecone --no-fail
vectormeta fix examples/oversized_pinecone_records.json --target pinecone --sidecar examples/sidecar --out examples/pinecone_ready.json --overwrite
vectormeta scan examples/pinecone_ready.json --target pinecone --no-fail
```

Expected result: the first scan reports an oversized record, and the second scan reports
zero oversized records.
