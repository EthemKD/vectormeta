"""Restore records from sidecar payloads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from vectormeta.analyzer import get_metadata
from vectormeta.errors import InvalidInputError
from vectormeta.io import read_sidecar
from vectormeta.models import HydrateMode, Record
from vectormeta.stores import SidecarStore


def hydrate_records(
    records: Iterable[Mapping[str, Any]],
    *,
    sidecar_dir: Path,
    mode: HydrateMode = "metadata",
    content_field: str = "payload",
    content_ref_field: str = "content_ref",
    input_base_dir: Path | None = None,
) -> list[Record]:
    """Hydrate records by loading sidecar payloads referenced by metadata."""
    hydrated: list[Record] = []
    for record in records:
        hydrated.append(
            hydrate_record(
                record,
                sidecar_dir=sidecar_dir,
                mode=mode,
                content_field=content_field,
                content_ref_field=content_ref_field,
                input_base_dir=input_base_dir,
            )
        )
    return hydrated


def hydrate_record(
    record: Mapping[str, Any],
    *,
    sidecar_dir: Path,
    mode: HydrateMode = "metadata",
    content_field: str = "payload",
    content_ref_field: str = "content_ref",
    input_base_dir: Path | None = None,
) -> Record:
    """Hydrate one record from its content_ref sidecar."""
    if mode not in ("metadata", "content_field"):
        raise InvalidInputError("--mode must be 'metadata' or 'content_field'.")

    metadata = dict(get_metadata(record))
    content_ref = metadata.get(content_ref_field)
    hydrated = dict(record)
    if content_ref is None:
        hydrated["metadata"] = metadata
        return hydrated
    if not isinstance(content_ref, str) or not content_ref:
        raise InvalidInputError(f"Metadata field '{content_ref_field}' must be a non-empty string.")

    sidecar_path = _resolve_sidecar_path(content_ref, sidecar_dir, input_base_dir)
    sidecar_payload = read_sidecar(sidecar_path)
    content_payload = {key: value for key, value in sidecar_payload.items() if key != "id"}
    metadata.pop(content_ref_field, None)

    if mode == "metadata":
        metadata.update(content_payload)
    else:
        hydrated[content_field] = content_payload

    hydrated["metadata"] = metadata
    return hydrated


def hydrate_records_from_store(
    records: Iterable[Mapping[str, Any]],
    *,
    store: SidecarStore,
    mode: HydrateMode = "metadata",
    content_field: str = "payload",
    content_ref_field: str = "content_ref",
) -> list[Record]:
    """Hydrate records by loading sidecar payloads from a SidecarStore."""
    return [
        hydrate_record_from_store(
            record,
            store=store,
            mode=mode,
            content_field=content_field,
            content_ref_field=content_ref_field,
        )
        for record in records
    ]


def hydrate_record_from_store(
    record: Mapping[str, Any],
    *,
    store: SidecarStore,
    mode: HydrateMode = "metadata",
    content_field: str = "payload",
    content_ref_field: str = "content_ref",
) -> Record:
    """Hydrate one record from a SidecarStore content reference."""
    if mode not in ("metadata", "content_field"):
        raise InvalidInputError("--mode must be 'metadata' or 'content_field'.")

    metadata = dict(get_metadata(record))
    content_ref = metadata.get(content_ref_field)
    hydrated = dict(record)
    if content_ref is None:
        hydrated["metadata"] = metadata
        return hydrated
    if not isinstance(content_ref, str) or not content_ref:
        raise InvalidInputError(f"Metadata field '{content_ref_field}' must be a non-empty string.")

    sidecar_payload = store.read(content_ref)
    content_payload = {key: value for key, value in sidecar_payload.items() if key != "id"}
    metadata.pop(content_ref_field, None)

    if mode == "metadata":
        metadata.update(content_payload)
    else:
        hydrated[content_field] = content_payload

    hydrated["metadata"] = metadata
    return hydrated


def _resolve_sidecar_path(
    content_ref: str,
    sidecar_dir: Path,
    input_base_dir: Path | None,
) -> Path:
    ref_path = Path(content_ref)
    candidates: list[Path] = []
    allowed_roots = [sidecar_dir]
    if input_base_dir is not None:
        allowed_roots.append(input_base_dir)

    def add_candidate(candidate: Path) -> None:
        if candidate not in candidates:
            candidates.append(candidate)

    if ref_path.is_absolute():
        add_candidate(ref_path)
    else:
        if input_base_dir is not None:
            add_candidate(input_base_dir / ref_path)
        add_candidate(sidecar_dir / ref_path)
        stripped_ref = _strip_sidecar_dir_prefix(ref_path, sidecar_dir)
        if stripped_ref != ref_path:
            add_candidate(sidecar_dir / stripped_ref)

    for candidate in candidates:
        if candidate.exists() and _is_allowed_sidecar_path(candidate, allowed_roots):
            return candidate
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise InvalidInputError(
        f"Could not resolve sidecar reference '{content_ref}' inside allowed sidecar paths. "
        f"Checked: {checked}"
    )


def _is_allowed_sidecar_path(candidate: Path, allowed_roots: list[Path]) -> bool:
    resolved_candidate = candidate.resolve()
    return any(
        resolved_candidate == root.resolve() or resolved_candidate.is_relative_to(root.resolve())
        for root in allowed_roots
    )


def _strip_sidecar_dir_prefix(ref_path: Path, sidecar_dir: Path) -> Path:
    if ref_path.parts and ref_path.parts[0] == sidecar_dir.name:
        return Path(*ref_path.parts[1:])
    return ref_path
