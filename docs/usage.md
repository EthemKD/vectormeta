# Usage

`vectormeta` works with JSON arrays and newline-delimited JSON records.

## Scan

```bash
vectormeta scan chunks.json --target pinecone
```

Use JSON output in CI:

```bash
vectormeta scan chunks.json --target pinecone --format json
```

Use a custom limit:

```bash
vectormeta scan chunks.json --target custom --limit-kb 32
```

## Validate

```bash
vectormeta validate chunks.json --target pinecone --dim 1536
```

`validate` runs a preflight check for common upsert failures:

- metadata byte size
- missing, empty, or duplicate record IDs
- vector dimension consistency
- optional vector dimension match with `--dim`
- Pinecone metadata value shapes, including flat metadata and no `null` values

Use JSON output in CI:

```bash
vectormeta validate chunks.json --target pinecone --dim 1536 --format json
```

Exit codes:

- `0`: no error-level validation issues, or `--no-fail` was passed
- `1`: one or more error-level validation issues were found
- `2`: expected user-facing input, config, or target error

## Fix

```bash
vectormeta fix chunks.json --target pinecone --sidecar ./sidecar --out pinecone_ready.json
```

Move explicit fields:

```bash
vectormeta fix chunks.json \
  --target pinecone \
  --move-fields chunk_text,raw_html,summary \
  --keep-fields source,page,section,doc_id,chunk_id \
  --sidecar ./sidecar \
  --out pinecone_ready.json
```

Preview without writing:

```bash
vectormeta fix chunks.json --target pinecone --sidecar ./sidecar --out ready.json --dry-run
```

Use content-addressed local files:

```bash
vectormeta fix chunks.json \
  --target pinecone \
  --sidecar-store file \
  --sidecar ./.vectormeta-sidecars \
  --out ready.json
```

Use a single SQLite database:

```bash
vectormeta fix chunks.json \
  --target pinecone \
  --sidecar-store sqlite \
  --sidecar vectormeta-sidecars.sqlite \
  --out ready.json
```

## Hydrate

```bash
vectormeta hydrate pinecone_ready.json --sidecar ./sidecar --out hydrated.json
```

To keep restored content outside metadata:

```bash
vectormeta hydrate pinecone_ready.json \
  --sidecar ./sidecar \
  --mode content_field \
  --content-field payload \
  --out hydrated.json
```

Hydrate from SQLite:

```bash
vectormeta hydrate ready.json \
  --sidecar-store sqlite \
  --sidecar vectormeta-sidecars.sqlite \
  --out hydrated.json
```

## Python API

Use `safe_upsert()` to put validation and cleanup directly in an ingestion pipeline:

```python
from pathlib import Path

from vectormeta import FileStore, safe_upsert

store = FileStore(Path(".vectormeta-sidecars"))

result = safe_upsert(
    index,
    records,
    target="pinecone",
    sidecar_store=store,
    dim=1536,
)
```

Useful result counters include:

```python
result.total_records
result.stored_count
result.deduplicated_count
result.warning_count
result.pre_error_count
result.post_error_count
```

The index object is injected and must provide an upsert method compatible with:

```python
index.upsert(vectors=cleaned_records, **kwargs)
```

Use SQLite when you want a single local sidecar database:

```python
from pathlib import Path

from vectormeta import SQLiteStore

store = SQLiteStore(Path("vectormeta-sidecars.sqlite"))
```

Hydrate query matches from a sidecar store:

```python
from vectormeta import hydrate_results

response = index.query(vector=query_vector, top_k=5)
hydrated = hydrate_results(response["matches"], sidecar_store=store)
```

`hydrate_results()` accepts mappings and common SDK objects with `metadata` attributes.

Migrate existing per-record JSON sidecars into a content-addressed store:

```python
from pathlib import Path

from vectormeta import FileStore, migrate_sidecars_to_store

store = FileStore(Path(".vectormeta-sidecars"))
result = migrate_sidecars_to_store(
    cleaned_records,
    sidecar_dir=Path("sidecar"),
    input_base_dir=Path("."),
    store=store,
)
```

## Config

`fix` can load a small YAML config:

```yaml
target: pinecone
limit_kb: 40
move:
  - chunk_text
  - raw_html
  - summary
keep:
  - doc_id
  - chunk_id
  - source
  - page
  - section
content_ref_field: content_ref
sidecar_dir: sidecar
```

Run:

```bash
vectormeta fix chunks.json --config vectormeta.yml --out pinecone_ready.json
```
