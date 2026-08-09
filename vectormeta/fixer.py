"""Metadata cleanup and sidecar planning logic."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from vectormeta.analyzer import get_metadata, get_record_id
from vectormeta.errors import SidecarConflictError
from vectormeta.models import FixOptions, FixResult, FixSavings, FixWarning, Record, SidecarPayload
from vectormeta.sizing import field_sizes, metadata_size_bytes

DEFAULT_MOVE_FIELDS: tuple[str, ...] = (
    "text",
    "chunk_text",
    "content",
    "page_content",
    "raw_text",
    "raw_html",
    "html",
    "markdown",
    "summary",
    "tables",
    "table_data",
    "ocr_text",
    "full_document",
    "document_text",
    "body",
)

DEFAULT_KEEP_FIELDS: tuple[str, ...] = (
    "doc_id",
    "chunk_id",
    "source",
    "url",
    "file_name",
    "file_path",
    "page",
    "page_number",
    "section",
    "title",
    "author",
    "created_at",
    "updated_at",
    "tags",
    "category",
    "language",
)

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def fix_records(records: Iterable[Mapping[str, Any]], options: FixOptions) -> FixResult:
    """Return cleaned records and sidecar payloads without writing files."""
    cleaned_records: list[Record] = []
    sidecars: list[SidecarPayload] = []
    warnings: list[FixWarning] = []
    savings: list[FixSavings] = []

    for cleaned_record, sidecar, record_warnings, record_savings in fix_records_iter(
        records, options
    ):
        cleaned_records.append(cleaned_record)
        warnings.extend(record_warnings)
        savings.append(record_savings)
        if sidecar is not None:
            sidecars.append(sidecar)

    return FixResult(
        cleaned_records=cleaned_records,
        sidecars=sidecars,
        warnings=warnings,
        savings=savings,
    )


def fix_records_iter(
    records: Iterable[Mapping[str, Any]],
    options: FixOptions,
) -> Iterator[tuple[Record, SidecarPayload | None, list[FixWarning], FixSavings]]:
    """Yield fixed records one at a time while preserving sidecar filename uniqueness."""
    used_names: set[str] = set()
    for record in records:
        yield _fix_record(record, options, used_names)


def sanitize_sidecar_filename(record_id: str) -> str:
    """Return a filesystem-safe filename stem for a record id."""
    sanitized = _SAFE_FILENAME_RE.sub("_", record_id).strip("._-")
    if not sanitized:
        sanitized = "record"
    return sanitized[:120]


def parse_field_list(value: str | None) -> tuple[str, ...] | None:
    """Parse a comma-separated field list."""
    if value is None:
        return None
    fields = tuple(field.strip() for field in value.split(",") if field.strip())
    return fields or None


def _fix_record(
    record: Mapping[str, Any],
    options: FixOptions,
    used_names: set[str],
) -> tuple[Record, SidecarPayload | None, list[FixWarning], FixSavings]:
    record_id = get_record_id(record)
    metadata = dict(get_metadata(record))
    before_bytes = metadata_size_bytes(metadata)
    cleaned_record = dict(record)
    payload_fields: dict[str, Any] = {}
    warnings: list[FixWarning] = []

    sidecar_path = _unique_sidecar_path(record_id, options.sidecar_dir, used_names)
    sidecar_ref = _content_ref(sidecar_path, options.output_path)

    def ensure_ref() -> None:
        if (
            options.content_ref_field in metadata
            and metadata[options.content_ref_field] != sidecar_ref
        ):
            raise SidecarConflictError(
                f"Record '{record_id}' already has metadata field "
                f"'{options.content_ref_field}'. Pass --content-ref-field with a different "
                "name to avoid overwriting existing metadata."
            )
        metadata[options.content_ref_field] = sidecar_ref

    def move_field(field_name: str) -> bool:
        if field_name == options.content_ref_field:
            return False
        if field_name not in metadata:
            return False
        payload_fields[field_name] = metadata.pop(field_name)
        ensure_ref()
        return True

    move_fields = options.move_fields if options.move_fields is not None else DEFAULT_MOVE_FIELDS
    for field_name in move_fields:
        move_field(field_name)

    keep_fields = set(
        options.keep_fields if options.keep_fields is not None else DEFAULT_KEEP_FIELDS
    )
    _move_until_under_limit(
        metadata=metadata,
        move_field=move_field,
        limit_bytes=options.limit_bytes,
        protected_fields=keep_fields | {options.content_ref_field},
    )

    if metadata_size_bytes(metadata) > options.limit_bytes:
        keep_candidates = [
            size
            for size in field_sizes(metadata)
            if size.field_name in keep_fields and size.field_name != options.content_ref_field
        ]
        if keep_candidates:
            warnings.append(
                FixWarning(
                    record_id=record_id,
                    message=(
                        "Metadata remained oversized after moving heavy and non-keep fields; "
                        "moving keep fields was required."
                    ),
                )
            )
            _move_until_under_limit(
                metadata=metadata,
                move_field=move_field,
                limit_bytes=options.limit_bytes,
                protected_fields={options.content_ref_field},
            )

    if metadata_size_bytes(metadata) > options.limit_bytes:
        warnings.append(
            FixWarning(
                record_id=record_id,
                message=(
                    "Record still exceeds the metadata limit after moving all movable fields. "
                    "Increase --limit-kb or shorten filterable metadata."
                ),
            )
        )

    cleaned_record["metadata"] = metadata
    savings = FixSavings(
        record_id=record_id,
        before_bytes=before_bytes,
        after_bytes=metadata_size_bytes(metadata),
        moved_field_count=len(payload_fields),
    )
    if not payload_fields:
        return cleaned_record, None, warnings, savings

    payload = {"id": record_id, **payload_fields}
    return (
        cleaned_record,
        SidecarPayload(record_id=record_id, path=sidecar_path, ref=sidecar_ref, payload=payload),
        warnings,
        savings,
    )


def _move_until_under_limit(
    *,
    metadata: dict[str, Any],
    move_field: Callable[[str], bool],
    limit_bytes: int,
    protected_fields: set[str],
) -> None:
    candidates = [
        size.field_name for size in field_sizes(metadata) if size.field_name not in protected_fields
    ]
    candidate_index = 0
    while metadata_size_bytes(metadata) > limit_bytes and candidate_index < len(candidates):
        move_field(candidates[candidate_index])
        candidate_index += 1


def _unique_sidecar_path(record_id: str, sidecar_dir: Path, used_names: set[str]) -> Path:
    base = sanitize_sidecar_filename(record_id)
    filename = f"{base}.json"
    if filename in used_names:
        digest = hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:12]
        filename = f"{base}-{digest}.json"
    counter = 2
    while filename in used_names:
        filename = f"{base}-{counter}.json"
        counter += 1
    used_names.add(filename)
    return sidecar_dir / filename


def _content_ref(sidecar_path: Path, output_path: Path | None) -> str:
    if output_path is not None:
        start = output_path.parent
    else:
        start = Path.cwd()
    try:
        ref = os.path.relpath(sidecar_path, start=start)
    except ValueError:
        ref = str(sidecar_path)
    return Path(ref).as_posix()
