"""Safe upsert helpers for vector database clients."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from vectormeta.errors import ValidationFailedError
from vectormeta.fixer import DEFAULT_KEEP_FIELDS, fix_records
from vectormeta.limits import normalize_target, resolve_limit_bytes
from vectormeta.models import (
    FixOptions,
    Record,
    SafeUpsertResult,
    ValidationIssue,
    ValidationReport,
)
from vectormeta.stores import (
    SidecarStore,
    planned_sidecar_refs,
    replace_content_refs,
    write_sidecar_payloads,
)
from vectormeta.validator import validate_records


class UpsertIndex(Protocol):
    """Protocol for vector index clients with a Pinecone-style upsert method."""

    def upsert(self, *, vectors: list[Record], **kwargs: Any) -> Any:
        """Upsert cleaned vector records."""


def safe_upsert(
    index: UpsertIndex,
    records: Iterable[Mapping[str, Any]],
    *,
    target: str = "pinecone",
    sidecar_store: SidecarStore,
    limit_kb: float | None = None,
    dim: int | None = None,
    validate: bool = True,
    force: bool = False,
    move_fields: tuple[str, ...] | None = None,
    keep_fields: tuple[str, ...] | None = None,
    content_ref_field: str = "content_ref",
    upsert_kwargs: Mapping[str, Any] | None = None,
) -> SafeUpsertResult:
    """Validate, fix, persist sidecars, and upsert cleaned records."""
    normalized_target = normalize_target(target)
    limit_bytes = resolve_limit_bytes(normalized_target, limit_kb)
    record_list = [dict(record) for record in records]

    pre_validation_report: ValidationReport | None = None
    if validate:
        pre_validation_report = validate_records(
            record_list,
            normalized_target,
            limit_bytes,
            dim=dim,
        )
        blocking_errors = _blocking_errors(pre_validation_report, allow_oversized=True)
        if blocking_errors and not force:
            raise ValidationFailedError(_validation_error_message(blocking_errors))

    fix_result = fix_records(
        record_list,
        FixOptions(
            target=normalized_target,
            limit_bytes=limit_bytes,
            sidecar_dir=Path(".vectormeta-sidecars"),
            output_path=None,
            move_fields=move_fields,
            keep_fields=keep_fields if keep_fields is not None else DEFAULT_KEEP_FIELDS,
            content_ref_field=content_ref_field,
        ),
    )

    final_refs = planned_sidecar_refs(sidecar_store, fix_result.sidecars)
    cleaned_records = replace_content_refs(
        fix_result.cleaned_records,
        old_refs=[sidecar.ref for sidecar in fix_result.sidecars],
        new_refs=final_refs,
        content_ref_field=content_ref_field,
    )

    post_validation_report: ValidationReport | None = None
    if validate:
        post_validation_report = validate_records(
            cleaned_records,
            normalized_target,
            limit_bytes,
            dim=dim,
        )
        blocking_errors = _blocking_errors(post_validation_report, allow_oversized=False)
        if blocking_errors and not force:
            raise ValidationFailedError(_validation_error_message(blocking_errors))

    stored_sidecars = write_sidecar_payloads(sidecar_store, fix_result.sidecars)
    upsert_result = index.upsert(vectors=cleaned_records, **dict(upsert_kwargs or {}))
    return SafeUpsertResult(
        cleaned_records=cleaned_records,
        stored_sidecars=stored_sidecars,
        warnings=fix_result.warnings,
        pre_validation_report=pre_validation_report,
        post_validation_report=post_validation_report,
        upsert_result=upsert_result,
    )


def _blocking_errors(
    report: ValidationReport,
    *,
    allow_oversized: bool,
) -> list[ValidationIssue]:
    if allow_oversized:
        return [issue for issue in report.errors if issue.code != "metadata_too_large"]
    return report.errors


def _validation_error_message(errors: list[ValidationIssue]) -> str:
    preview = ", ".join(f"{issue.record_id}:{issue.code}" for issue in errors[:5])
    if len(errors) > 5:
        preview += f", and {len(errors) - 5} more"
    return f"Safe upsert blocked by validation errors: {preview}"
