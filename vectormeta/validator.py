"""Preflight validation for vector records before database upsert."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from vectormeta.errors import InvalidInputError
from vectormeta.models import (
    RecordValidation,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)
from vectormeta.sizing import metadata_size_bytes

VECTOR_FIELDS: tuple[str, ...] = ("values", "vector", "embedding")


def validate_records(
    records: Iterable[Mapping[str, Any]],
    target: str,
    limit_bytes: int,
    *,
    dim: int | None = None,
) -> ValidationReport:
    """Validate vector records for common upsert failures."""
    normalized_target = target.strip().lower()
    seen_ids: dict[str, int] = {}
    expected_dataset_dim: int | None = None
    validations: list[RecordValidation] = []

    for index, record in enumerate(records):
        record_id, usable_id, id_field = _record_id(record, index=index)
        issues: list[ValidationIssue] = []

        if usable_id is None:
            issues.append(
                _issue(
                    record_id,
                    "error",
                    "missing_id",
                    "Record must contain a non-empty 'id' or '_id'.",
                    id_field,
                )
            )
        elif usable_id in seen_ids:
            issues.append(
                _issue(
                    record_id,
                    "error",
                    "duplicate_id",
                    f"Record id '{usable_id}' duplicates record index {seen_ids[usable_id]}.",
                    id_field,
                )
            )
        else:
            seen_ids[usable_id] = index

        metadata_size = 0
        metadata = record.get("metadata")
        if not isinstance(metadata, Mapping):
            issues.append(
                _issue(
                    record_id,
                    "error",
                    "invalid_metadata",
                    "Record metadata must be a JSON object.",
                    "metadata",
                )
            )
        else:
            try:
                metadata_size = metadata_size_bytes(metadata)
            except InvalidInputError as exc:
                issues.append(
                    _issue(
                        record_id,
                        "error",
                        "metadata_not_serializable",
                        str(exc),
                        "metadata",
                    )
                )
            else:
                if metadata_size > limit_bytes:
                    over_by = metadata_size - limit_bytes
                    issues.append(
                        _issue(
                            record_id,
                            "error",
                            "metadata_too_large",
                            f"Metadata is {over_by} bytes over the configured limit.",
                            "metadata",
                        )
                    )

            if normalized_target == "pinecone":
                issues.extend(_validate_pinecone_metadata(metadata, record_id))

        vector_issue, vector_dim = _vector_dimension(record, record_id)
        if vector_issue is not None:
            issues.append(vector_issue)
        elif vector_dim is not None:
            if dim is not None and vector_dim != dim:
                issues.append(
                    _issue(
                        record_id,
                        "error",
                        "vector_dimension_mismatch",
                        f"Vector dimension is {vector_dim}, expected {dim}.",
                        _vector_field_name(record),
                    )
                )
            elif expected_dataset_dim is None:
                expected_dataset_dim = vector_dim
            elif vector_dim != expected_dataset_dim:
                issues.append(
                    _issue(
                        record_id,
                        "error",
                        "inconsistent_vector_dimension",
                        (
                            f"Vector dimension is {vector_dim}, but earlier records use "
                            f"{expected_dataset_dim}."
                        ),
                        _vector_field_name(record),
                    )
                )

        validations.append(
            RecordValidation(
                record_id=record_id,
                metadata_size_bytes=metadata_size,
                limit_bytes=limit_bytes,
                vector_dimension=vector_dim,
                issues=issues,
            )
        )

    return ValidationReport(
        target=normalized_target,
        limit_bytes=limit_bytes,
        expected_dim=dim,
        records=validations,
    )


def validate_records_stream(
    records: Iterable[Mapping[str, Any]],
    target: str,
    limit_bytes: int,
    *,
    dim: int | None = None,
    top: int,
) -> ValidationReport:
    """Validate records while keeping only problem records in memory."""
    normalized_target = target.strip().lower()
    seen_ids: dict[str, int] = {}
    expected_dataset_dim: int | None = None
    total_records = 0
    error_count = 0
    warning_count = 0
    problem_records: list[RecordValidation] = []

    for index, record in enumerate(records):
        total_records += 1
        record_id, usable_id, id_field = _record_id(record, index=index)
        issues: list[ValidationIssue] = []

        if usable_id is None:
            issues.append(
                _issue(
                    record_id,
                    "error",
                    "missing_id",
                    "Record must contain a non-empty 'id' or '_id'.",
                    id_field,
                )
            )
        elif usable_id in seen_ids:
            issues.append(
                _issue(
                    record_id,
                    "error",
                    "duplicate_id",
                    f"Record id '{usable_id}' duplicates record index {seen_ids[usable_id]}.",
                    id_field,
                )
            )
        else:
            seen_ids[usable_id] = index

        metadata_size = 0
        metadata = record.get("metadata")
        if not isinstance(metadata, Mapping):
            issues.append(
                _issue(
                    record_id,
                    "error",
                    "invalid_metadata",
                    "Record metadata must be a JSON object.",
                    "metadata",
                )
            )
        else:
            try:
                metadata_size = metadata_size_bytes(metadata)
            except InvalidInputError as exc:
                issues.append(
                    _issue(
                        record_id,
                        "error",
                        "metadata_not_serializable",
                        str(exc),
                        "metadata",
                    )
                )
            else:
                if metadata_size > limit_bytes:
                    over_by = metadata_size - limit_bytes
                    issues.append(
                        _issue(
                            record_id,
                            "error",
                            "metadata_too_large",
                            f"Metadata is {over_by} bytes over the configured limit.",
                            "metadata",
                        )
                    )

            if normalized_target == "pinecone":
                issues.extend(_validate_pinecone_metadata(metadata, record_id))

        vector_issue, vector_dim = _vector_dimension(record, record_id)
        if vector_issue is not None:
            issues.append(vector_issue)
        elif vector_dim is not None:
            if dim is not None and vector_dim != dim:
                issues.append(
                    _issue(
                        record_id,
                        "error",
                        "vector_dimension_mismatch",
                        f"Vector dimension is {vector_dim}, expected {dim}.",
                        _vector_field_name(record),
                    )
                )
            elif expected_dataset_dim is None:
                expected_dataset_dim = vector_dim
            elif vector_dim != expected_dataset_dim:
                issues.append(
                    _issue(
                        record_id,
                        "error",
                        "inconsistent_vector_dimension",
                        (
                            f"Vector dimension is {vector_dim}, but earlier records use "
                            f"{expected_dataset_dim}."
                        ),
                        _vector_field_name(record),
                    )
                )

        validation = RecordValidation(
            record_id=record_id,
            metadata_size_bytes=metadata_size,
            limit_bytes=limit_bytes,
            vector_dimension=vector_dim,
            issues=issues,
        )
        error_count += validation.error_count
        warning_count += validation.warning_count
        if issues and len(problem_records) < top:
            problem_records.append(validation)

    return ValidationReport(
        target=normalized_target,
        limit_bytes=limit_bytes,
        expected_dim=dim,
        records=problem_records,
        total_records_count=total_records,
        error_count_total=error_count,
        warning_count_total=warning_count,
    )


def _record_id(
    record: Mapping[str, Any],
    *,
    index: int,
) -> tuple[str, str | None, str | None]:
    raw_id = record.get("id")
    id_field = "id"
    if raw_id is None and "_id" in record:
        raw_id = record.get("_id")
        id_field = "_id"

    if raw_id is None or str(raw_id) == "":
        return f"<record {index}>", None, id_field
    usable_id = str(raw_id)
    return usable_id, usable_id, id_field


def _validate_pinecone_metadata(
    metadata: Mapping[Any, Any],
    record_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for key, value in metadata.items():
        field_path = _metadata_field_path(key)
        if not isinstance(key, str):
            issues.append(
                _issue(
                    record_id,
                    "error",
                    "invalid_metadata_key",
                    "Pinecone metadata field names must be strings.",
                    field_path,
                )
            )
        elif key.startswith("$"):
            issues.append(
                _issue(
                    record_id,
                    "error",
                    "invalid_metadata_key",
                    "Pinecone metadata field names cannot start with '$'.",
                    field_path,
                )
            )

        if _is_pinecone_metadata_value(value):
            continue

        issues.append(
            _issue(
                record_id,
                "error",
                "invalid_metadata_value",
                (
                    "Pinecone metadata values must be strings, finite numbers, booleans, "
                    "or lists of strings."
                ),
                field_path,
            )
        )
    return issues


def _is_pinecone_metadata_value(value: Any) -> bool:
    if isinstance(value, str | bool):
        return True
    if _is_number(value):
        return True
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)
    return False


def _vector_dimension(
    record: Mapping[str, Any],
    record_id: str,
) -> tuple[ValidationIssue | None, int | None]:
    vector_field = _vector_field_name(record)
    if vector_field is None:
        return (
            _issue(
                record_id,
                "warning",
                "missing_vector",
                "Record does not contain values, vector, or embedding.",
                None,
            ),
            None,
        )

    vector = record.get(vector_field)
    if isinstance(vector, str) or not isinstance(vector, Sequence):
        return (
            _issue(
                record_id,
                "error",
                "invalid_vector",
                "Vector must be a non-empty list of finite numbers.",
                vector_field,
            ),
            None,
        )

    if not vector:
        return (
            _issue(
                record_id,
                "error",
                "invalid_vector",
                "Vector must be a non-empty list of finite numbers.",
                vector_field,
            ),
            None,
        )

    if not all(_is_number(value) for value in vector):
        return (
            _issue(
                record_id,
                "error",
                "invalid_vector",
                "Vector must contain only finite numbers.",
                vector_field,
            ),
            None,
        )

    return None, len(vector)


def _vector_field_name(record: Mapping[str, Any]) -> str | None:
    for field_name in VECTOR_FIELDS:
        if field_name in record:
            return field_name
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _metadata_field_path(field_name: object) -> str:
    return f"metadata.{field_name}" if isinstance(field_name, str) else "metadata"


def _issue(
    record_id: str,
    severity: ValidationSeverity,
    code: str,
    message: str,
    field_path: str | None,
) -> ValidationIssue:
    return ValidationIssue(
        record_id=record_id,
        severity=severity,
        code=code,
        message=message,
        field_path=field_path,
    )
