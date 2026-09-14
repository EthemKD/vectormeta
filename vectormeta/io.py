"""Input and output helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, Literal

from vectormeta.errors import InvalidInputError, OutputExistsError, SidecarConflictError
from vectormeta.models import OutputFormat, Record, SidecarPayload

InputFormat = Literal["json", "jsonl"]


def detect_input_format(path: Path) -> InputFormat:
    """Detect whether a records file is a JSON array or JSONL stream."""
    _ensure_input_file(path)
    with path.open("r", encoding="utf-8-sig") as file:
        while True:
            char = file.read(1)
            if char == "":
                raise InvalidInputError(f"Input file is empty: {path}")
            if char.isspace():
                continue
            if char == "[":
                return "json"
            if char == "{":
                return "jsonl"
            raise InvalidInputError(
                f"Expected a JSON list or JSONL records in {path}; got {char!r}."
            )


def iter_jsonl_records(path: Path) -> Iterator[Record]:
    """Yield JSONL records one line at a time."""
    _ensure_input_file(path)
    found = False
    with path.open("r", encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            found = True
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InvalidInputError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(parsed, dict):
                raise InvalidInputError(
                    f"JSONL line {line_number} in {path} is not a record object."
                )
            yield dict(parsed)
    if not found:
        raise InvalidInputError(f"No records found in JSONL file: {path}")


def read_records(path: Path) -> tuple[list[Record], InputFormat]:
    """Read vector records from a JSON array file or JSONL file."""
    _ensure_input_file(path)

    text = path.read_text(encoding="utf-8-sig")
    stripped = text.lstrip()
    if not stripped:
        raise InvalidInputError(f"Input file is empty: {path}")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        if stripped.startswith("["):
            raise InvalidInputError(f"Invalid JSON array in {path}: {exc}") from exc
        return _read_jsonl(text, path), "jsonl"

    if isinstance(parsed, list):
        return _coerce_record_list(parsed, path), "json"

    if isinstance(parsed, dict):
        raise InvalidInputError(
            f"Expected a JSON list of records or JSONL records in {path}; got a single object."
        )

    raise InvalidInputError(f"Expected a JSON list of records in {path}.")


def write_records(
    records: Iterable[Mapping[str, Any]],
    path: Path,
    output_format: OutputFormat,
    *,
    overwrite: bool = False,
) -> None:
    """Write vector records as JSON or JSONL."""
    ensure_output_writable(path, overwrite=overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        content = json.dumps(list(records), ensure_ascii=False, indent=2) + "\n"
    elif output_format == "jsonl":
        write_jsonl_records(records, path, overwrite=True)
        return
    else:
        raise InvalidInputError(f"Unsupported output format: {output_format}")
    path.write_text(content, encoding="utf-8")


def write_jsonl_records(
    records: Iterable[Mapping[str, Any]],
    path: Path,
    *,
    overwrite: bool = False,
) -> None:
    """Write JSONL records one line at a time."""
    ensure_output_writable(path, overwrite=overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            file.write("\n")


def ensure_output_writable(path: Path, *, overwrite: bool) -> None:
    """Raise if a file exists and overwrite is disabled."""
    if path.exists() and not overwrite:
        raise OutputExistsError(
            f"Output file already exists: {path}. Pass --overwrite to replace it."
        )


def write_sidecars(sidecars: Iterable[SidecarPayload], *, overwrite: bool = False) -> None:
    """Write sidecar payloads as JSON files."""
    sidecar_list = list(sidecars)
    paths = [sidecar.path for sidecar in sidecar_list]
    seen_paths: set[Path] = set()
    duplicate_paths: set[Path] = set()
    for path in paths:
        if path in seen_paths:
            duplicate_paths.add(path)
        else:
            seen_paths.add(path)
    if duplicate_paths:
        conflicts = ", ".join(str(path) for path in sorted(duplicate_paths))
        raise SidecarConflictError(
            f"Multiple records would write the same sidecar path: {conflicts}"
        )

    existing = [path for path in paths if path.exists() and not overwrite]
    if existing:
        conflicts = ", ".join(str(path) for path in existing[:5])
        raise SidecarConflictError(
            f"Sidecar file already exists: {conflicts}. Pass --overwrite to replace sidecars."
        )

    for sidecar in sidecar_list:
        sidecar.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(sidecar.payload, ensure_ascii=False, indent=2) + "\n"
        sidecar.path.write_text(content, encoding="utf-8")


def read_sidecar(path: Path) -> dict[str, Any]:
    """Read one sidecar JSON object."""
    if not path.exists():
        raise InvalidInputError(f"Sidecar file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidInputError(f"Invalid sidecar JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidInputError(f"Sidecar must contain a JSON object: {path}")
    return data


def _ensure_input_file(path: Path) -> None:
    if not path.exists():
        raise InvalidInputError(f"Input file does not exist: {path}")
    if not path.is_file():
        raise InvalidInputError(f"Input path is not a file: {path}")


def _read_jsonl(text: str, path: Path) -> list[Record]:
    records: list[Record] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InvalidInputError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise InvalidInputError(f"JSONL line {line_number} in {path} is not a record object.")
        records.append(dict(parsed))
    if not records:
        raise InvalidInputError(f"No records found in JSONL file: {path}")
    return records


def _coerce_record_list(values: list[Any], path: Path) -> list[Record]:
    records: list[Record] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise InvalidInputError(f"Record at index {index} in {path} is not a JSON object.")
        records.append(dict(value))
    return records
