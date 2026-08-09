"""Record analysis logic."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from vectormeta.errors import InvalidInputError
from vectormeta.models import RecordAnalysis, ScanReport
from vectormeta.sizing import field_sizes, metadata_size_bytes


def get_record_id(record: Mapping[str, Any]) -> str:
    """Return a vector record id from id or _id."""
    record_id = record.get("id", record.get("_id"))
    if record_id is None or str(record_id) == "":
        raise InvalidInputError("Each record must contain a non-empty 'id' or '_id'.")
    return str(record_id)


def get_metadata(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return metadata from a vector record."""
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        record_id = record.get("id", record.get("_id", "<unknown>"))
        raise InvalidInputError(f"Record '{record_id}' must contain a metadata object.")
    return metadata


def analyze_record(record: Mapping[str, Any], limit_bytes: int) -> RecordAnalysis:
    """Analyze metadata size for a single vector record."""
    metadata = get_metadata(record)
    return RecordAnalysis(
        record_id=get_record_id(record),
        metadata_size_bytes=metadata_size_bytes(metadata),
        limit_bytes=limit_bytes,
        largest_fields=field_sizes(metadata),
    )


def analyze_records(
    records: Iterable[Mapping[str, Any]],
    target: str,
    limit_bytes: int,
) -> ScanReport:
    """Analyze vector records for oversized metadata."""
    return ScanReport(
        target=target,
        limit_bytes=limit_bytes,
        records=[analyze_record(record, limit_bytes) for record in records],
    )


def analyze_records_stream(
    records: Iterable[Mapping[str, Any]],
    target: str,
    limit_bytes: int,
    *,
    top: int,
) -> ScanReport:
    """Analyze records while keeping only top oversized analyses in memory."""
    total_records = 0
    oversized_count = 0
    top_records: list[RecordAnalysis] = []

    for record in records:
        total_records += 1
        analysis = analyze_record(record, limit_bytes)
        if not analysis.is_oversized:
            continue
        oversized_count += 1
        top_records.append(analysis)
        top_records.sort(key=lambda item: item.metadata_size_bytes, reverse=True)
        if len(top_records) > top:
            top_records.pop()

    return ScanReport(
        target=target,
        limit_bytes=limit_bytes,
        records=top_records,
        total_records_count=total_records,
        oversized_records_count=oversized_count,
    )
