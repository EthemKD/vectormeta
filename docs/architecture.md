# Architecture

`vectormeta` keeps CLI concerns separate from core behavior.

## Modules

- `cli.py`: Typer commands, Rich output, exit codes
- `models.py`: typed dataclasses shared by core modules
- `limits.py`: target presets and limit resolution
- `sizing.py`: compact UTF-8 JSON byte sizing
- `analyzer.py`: metadata size analysis and scan reports
- `validator.py`: preflight validation for metadata, IDs, and vectors
- `fixer.py`: metadata cleanup and sidecar planning
- `stores.py`: content-addressed sidecar store backends
- `upsert.py`: SDK-agnostic safe upsert wrapper
- `hydrate.py`: sidecar restoration from files or stores
- `io.py`: JSON, JSONL, sidecar, and overwrite-safe writes
- `config.py`: small YAML config loader
- `reporting.py`: human and machine report rendering
- `errors.py`: expected user-facing exceptions

The core modules do not depend on Typer. Most functions accept standard mappings,
paths, and dataclasses so they are easy to unit test and reuse in other tools.

## Sizing Rule

Metadata size is calculated as compact UTF-8 JSON bytes:

```python
json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
```

This avoids misleading estimates from `len(str(metadata))`, especially for Unicode
and nested metadata.

## Sidecar References

When fixing records with an output path, `content_ref` is relative to the output file's
parent directory. For example, writing `examples/pinecone_ready.json` with sidecars in
`examples/sidecar` stores refs like `sidecar/doc_123.json`.

Sidecar filenames are sanitized from record IDs so IDs with slashes or unsafe
characters do not create unexpected paths.
