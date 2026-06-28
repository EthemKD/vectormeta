<p align="center">
  <img
    src="https://raw.githubusercontent.com/Achal13jain/vectormeta/main/site/assets/banner.png"
    alt="vectormeta banner showing oversized vector metadata reduced into clean sidecar references"
  >
</p>

<h1 align="center">vectormeta</h1>

<p align="center">
  <strong>Stop vector DB metadata limit errors before upsert.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/vectormeta/"><img alt="PyPI" src="https://img.shields.io/pypi/v/vectormeta"></a>
  <a href="https://pypi.org/project/vectormeta/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/vectormeta"></a>
  <a href="https://github.com/Achal13jain/vectormeta/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Achal13jain/vectormeta/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/Achal13jain/vectormeta/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
  <a href="https://achal13jain.github.io/vectormeta/"><img alt="Website" src="https://img.shields.io/badge/website-live-2ea44f"></a>
</p>

<p align="center">
  <a href="https://achal13jain.github.io/vectormeta/">Website</a>
  &middot;
  <a href="https://github.com/Achal13jain/vectormeta/blob/main/docs/usage.md">Usage</a>
  &middot;
  <a href="https://github.com/Achal13jain/vectormeta/blob/main/docs/metadata-reduction.md">Reduction logic</a>
  &middot;
  <a href="https://pypi.org/project/vectormeta/">PyPI</a>
</p>

`vectormeta` is a Python CLI package for detecting, validating, and fixing problematic
metadata in vector database records. It scans JSON or JSONL vector records, reports the
largest metadata fields, validates common upsert-failure cases, and can move heavy
content fields into local JSON sidecar files while leaving clean filterable metadata in
the vector database payload.

The project is designed for developers preparing records for Pinecone, Chroma, Qdrant,
Weaviate, or a custom metadata policy. Pinecone is the clearest strict-limit target in
the MVP. Other targets use conservative advisory limits that should be adjusted for each
deployment.

```bash
vectormeta scan records.json --target pinecone
vectormeta validate records.json --target pinecone --dim 1536
vectormeta fix records.json --target pinecone --sidecar ./sidecar --out ready.json
vectormeta hydrate ready.json --sidecar ./sidecar --out hydrated.json
```

## Why This Exists

Vector database metadata should usually stay small and filterable:

- `source`
- `page`
- `section`
- `doc_id`
- `chunk_id`
- `tags`
- `language`

Large payloads such as full chunk text, raw HTML, Markdown, OCR text, summaries, tables,
or full documents can push records over service metadata limits and make upserts fail.
`vectormeta` catches that problem before upload and can rewrite records into a safer
shape:

```text
vector record metadata -> small filterable fields + content_ref
sidecar JSON file      -> large text, HTML, tables, summaries, payloads
```

## Features

- Scan JSON arrays and newline-delimited JSON records.
- Measure metadata using compact UTF-8 JSON bytes.
- Report oversized records, largest fields, byte counts, KB counts, and suggested moves.
- Exit with code `1` when oversized records are found, which makes scans useful in CI.
- Validate records for common upsert failures before upload.
- Check Pinecone metadata value shapes, duplicate IDs, missing IDs, vector shape, and
  vector dimensions.
- Move heavy metadata fields into sidecar JSON files.
- Preserve unknown record fields and original record order.
- Sanitize sidecar filenames derived from record IDs.
- Protect output files and sidecars from accidental overwrite.
- Hydrate records back from sidecar references for debugging and migrations.
- Use `safe_upsert()` from Python to validate, fix, persist sidecars, and call an
  injected vector index client.
- Store sidecar payloads in content-addressed local files or SQLite.
- Keep core logic independent from Typer and Rich so it can be tested and reused.

## Tech Stack

- Python 3.10+
- Typer for the CLI
- Rich for human-readable terminal reports
- Pydantic for YAML config validation
- PyYAML for config loading
- Pytest for tests
- Ruff for linting and formatting
- Mypy for strict type checks
- Setuptools and `python -m build` for packaging

## Installation

Install from PyPI:

```bash
pip install vectormeta
```

Install with the optional Pinecone SDK:

```bash
pip install "vectormeta[pinecone]"
```

Check the CLI:

```bash
vectormeta --help
vectormeta --version
```

For local development, clone the repository and install the development extras:

```bash
git clone https://github.com/Achal13jain/vectormeta.git
cd vectormeta
pip install -e ".[dev]"
```

Then verify the module entry point as well:

```bash
python -m vectormeta --help
```

## Input Format

JSON array:

```json
[
  {
    "id": "doc_1_chunk_1",
    "values": [0.1, 0.2, 0.3],
    "metadata": {
      "source": "paper.pdf",
      "page": 1,
      "chunk_text": "large text..."
    }
  }
]
```

JSONL:

```jsonl
{"id":"doc_1","values":[0.1],"metadata":{"text":"large text..."}}
{"id":"doc_2","values":[0.2],"metadata":{"text":"large text..."}}
```

Each record must contain:

- `id` or `_id`
- `metadata` as a JSON object

Vector fields such as `values`, `vector`, or `embedding` are preserved by scan/fix
workflows. The `validate` command can check that vectors are finite numeric lists and
that dimensions are consistent.

## Quickstart

Scan the included oversized Pinecone example:

```bash
vectormeta scan examples/oversized_pinecone_records.json --target pinecone --no-fail
```

Run a preflight validation pass:

```bash
vectormeta validate examples/oversized_pinecone_records.json --target pinecone --no-fail
```

Fix the records:

```bash
vectormeta fix examples/oversized_pinecone_records.json \
  --target pinecone \
  --sidecar examples/sidecar \
  --out examples/pinecone_ready.json \
  --overwrite
```

Verify the cleaned file now fits the Pinecone-sized policy:

```bash
vectormeta scan examples/pinecone_ready.json --target pinecone --no-fail
vectormeta validate examples/pinecone_ready.json --target pinecone --no-fail
```

Hydrate records for local inspection:

```bash
vectormeta hydrate examples/pinecone_ready.json \
  --sidecar examples/sidecar \
  --out examples/hydrated.json \
  --overwrite
```

## Commands

### Scan

```bash
vectormeta scan chunks.json --target pinecone
```

Useful options:

- `--target pinecone|chroma|qdrant|weaviate|custom`
- `--limit-kb <number>` for custom or overridden limits
- `--top <number>` for the largest oversized records to show
- `--format table|json`
- `--no-fail` to exit `0` even when oversized records are found

Exit codes:

- `0`: all records fit, or `--no-fail` was passed
- `1`: oversized records were found
- `2`: expected user-facing input, config, target, or overwrite error

### Validate

```bash
vectormeta validate chunks.json --target pinecone --dim 1536
```

`validate` checks metadata size, ID hygiene, duplicate IDs, vector shape, vector
dimension consistency, and optional dimension matching with `--dim`.

For Pinecone, it also checks metadata format rules documented by Pinecone: flat metadata
objects, string keys that do not start with `$`, and values that are strings, finite
numbers, booleans, or lists of strings.

Useful options:

- `--target pinecone|chroma|qdrant|weaviate|custom`
- `--limit-kb <number>` for custom or overridden limits
- `--dim <number>` for the expected vector dimension
- `--top <number>` for validation issues to show
- `--format table|json`
- `--no-fail` to exit `0` even when error-level issues are found

Exit codes:

- `0`: no error-level validation issues, or `--no-fail` was passed
- `1`: one or more error-level validation issues were found
- `2`: expected user-facing input, config, target, or overwrite error

### Fix

```bash
vectormeta fix chunks.json --target pinecone --sidecar ./sidecar --out pinecone_ready.json
```

Move explicit fields:

```bash
vectormeta fix chunks.json \
  --target pinecone \
  --move-fields chunk_text,raw_html,summary \
  --keep-fields source,page,section,doc_id,chunk_id \
  --content-ref-field content_ref \
  --sidecar ./sidecar \
  --out pinecone_ready.json
```

Preview without writing:

```bash
vectormeta fix chunks.json --target pinecone --sidecar ./sidecar --out ready.json --dry-run
```

`fix` does not overwrite files unless `--overwrite` is passed.

Use content-addressed sidecars from the CLI:

```bash
vectormeta fix chunks.json \
  --target pinecone \
  --sidecar-store file \
  --sidecar ./.vectormeta-sidecars \
  --out ready.json
```

Use a single SQLite sidecar database:

```bash
vectormeta fix chunks.json \
  --target pinecone \
  --sidecar-store sqlite \
  --sidecar vectormeta-sidecars.sqlite \
  --out ready.json
```

If your input metadata already contains `content_ref`, choose another reference field:

```bash
vectormeta fix chunks.json \
  --target pinecone \
  --content-ref-field vectormeta_content_ref \
  --sidecar ./sidecar \
  --out pinecone_ready.json
```

### Hydrate

```bash
vectormeta hydrate pinecone_ready.json --sidecar ./sidecar --out hydrated.json
```

Hydrate from a SQLite sidecar database:

```bash
vectormeta hydrate ready.json \
  --sidecar-store sqlite \
  --sidecar vectormeta-sidecars.sqlite \
  --out hydrated.json
```

Hydrate sidecar content into a separate record field:

```bash
vectormeta hydrate pinecone_ready.json \
  --sidecar ./sidecar \
  --mode content_field \
  --content-field payload \
  --out hydrated.json
```

### Limits

```bash
vectormeta limits
```

Current MVP defaults:

| Target | Default | Meaning |
| --- | ---: | --- |
| `pinecone` | 40 KB | Primary strict-limit target for this MVP |
| `chroma` | 256 KB | Advisory local/configurable policy |
| `qdrant` | 64 KB | Conservative advisory policy |
| `weaviate` | 64 KB | Conservative advisory policy |
| `custom` | none | Requires `--limit-kb` |

Limits and provider behavior can change. Verify official vector database documentation
before treating any preset as a production guarantee.

## Python API

Use `safe_upsert()` when you want vectormeta in the ingestion path instead of as a
separate CLI step:

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
    upsert_kwargs={"namespace": "docs"},
)
```

The result exposes useful ingestion counters:

```python
result.total_records
result.stored_count
result.deduplicated_count
result.warning_count
result.pre_error_count
result.post_error_count
```

The index object is injected. `vectormeta` expects an object with a Pinecone-style
method such as:

```python
index.upsert(vectors=cleaned_records, **kwargs)
```

This keeps vendor SDKs optional and outside the core dependency set.

To hydrate matches returned from your own query path:

```python
from vectormeta import hydrate_results

response = index.query(vector=query_vector, top_k=5)
hydrated = hydrate_results(response["matches"], sidecar_store=store)
```

For a single-file local backend:

```python
from pathlib import Path

from vectormeta import SQLiteStore

store = SQLiteStore(Path("vectormeta-sidecars.sqlite"))
```

`FileStore` and `SQLiteStore` are content-addressed. Identical moved payloads are stored
once and can be referenced by many records.

Migrate legacy per-record JSON sidecars into a content-addressed store:

```python
from vectormeta import migrate_sidecars_to_store

migration = migrate_sidecars_to_store(
    cleaned_records,
    sidecar_dir=Path("sidecar"),
    input_base_dir=Path("."),
    store=store,
)
```

## How Metadata Reduction Works

`vectormeta` sizes metadata exactly as compact UTF-8 JSON:

```python
json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
```

The fixer reduces metadata in this order:

1. Move explicit `--move-fields`, if provided.
2. Otherwise move known heavy fields such as `text`, `chunk_text`, `raw_html`,
   `markdown`, `summary`, `tables`, and `ocr_text`.
3. If metadata is still above the limit, move the largest non-keep fields one at a
   time until the record fits.
4. Keep fields such as `source`, `page`, `doc_id`, and `tags` are preserved unless the
   record cannot fit without moving them.
5. When fields are moved, metadata receives a `content_ref`, and moved fields are
   written to a sidecar JSON payload.

The logic is covered by tests for Unicode byte sizing, nested metadata sizing,
JSON/JSONL input, fixer output, sidecar overwrite protection, hydration, and CLI exit
codes. See [docs/metadata-reduction.md](docs/metadata-reduction.md).

## Preflight Validation

`vectormeta validate` is a linter for vector records before upsert. It reuses the same
compact UTF-8 JSON byte sizing as `scan`, then adds checks for IDs, duplicate IDs, vector
dimensions, invalid vector values, and Pinecone metadata value types.

For non-Pinecone targets, size presets remain advisory and provider-specific metadata
schema validation is intentionally limited. Use `--limit-kb` and `--dim` to match your
deployment policy.

## Local Verification

Run the same checks used in CI:

```bash
python -m pytest
ruff check .
ruff format --check .
mypy vectormeta
python -m build
```

Run the acceptance workflow:

```bash
vectormeta scan examples/oversized_pinecone_records.json --target pinecone --no-fail
vectormeta validate examples/oversized_pinecone_records.json --target pinecone --no-fail
vectormeta fix examples/oversized_pinecone_records.json --target pinecone --sidecar examples/sidecar --out examples/pinecone_ready.json --overwrite
vectormeta scan examples/pinecone_ready.json --target pinecone --no-fail
vectormeta validate examples/pinecone_ready.json --target pinecone --no-fail
vectormeta hydrate examples/pinecone_ready.json --sidecar examples/sidecar --out examples/hydrated.json --overwrite
```

Expected result:

- The original example reports one oversized record and one validation error.
- The fixed output reports zero oversized records and zero validation errors.
- Sidecar files are created under `examples/sidecar`.
- Hydration restores moved fields for inspection.

## Documentation

- [Project website](https://achal13jain.github.io/vectormeta/)
- [Architecture overview](docs/architecture.md)
- [Metadata reduction logic](docs/metadata-reduction.md)
- [Usage guide](docs/usage.md)
- [Testing checklist](docs/testing.md)
- [Vector database notes](docs/vector-db-notes.md)

## Limitations

- The default CLI sidecar mode is local JSON files. Keep cleaned output files and their
  sidecar location together unless you opt into `--sidecar-store file` or
  `--sidecar-store sqlite`.
- Store-backed sidecars deduplicate identical moved payloads, but distributed/cloud
  stores such as S3 are not included yet.
- Input support is JSON arrays and JSONL records, but files are currently read into
  memory. Streaming JSONL scan/fix is planned for larger embedding datasets.
- Vector validation covers dense numeric vector lists and dimensions. It does not infer
  index configuration unless you provide `--dim`.
- Provider-specific metadata schema validation is currently strictest for Pinecone.
- Non-Pinecone target limits are conservative advisory defaults, not vendor claims.
- The fixer is policy-based; review cleaned outputs before production ingestion.

## Roadmap

Planned ideas include:

- Streaming JSONL scan/fix
- More provider-specific validation rules
- S3 sidecar backend
- LangChain `Document` adapter
- LlamaIndex `Node` adapter
- Pinecone upsert wrapper
- GitHub Action for metadata checks
- HTML report output

See [ROADMAP.md](ROADMAP.md).

## License

MIT. See [LICENSE](LICENSE).
