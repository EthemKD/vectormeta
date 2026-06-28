"""Shared domain models for vectormeta."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Record = dict[str, Any]
Metadata = Mapping[str, Any]
OutputFormat = Literal["json", "jsonl"]
ReportFormat = Literal["table", "json"]
HydrateMode = Literal["metadata", "content_field"]
LimitPolicy = Literal["strict", "advisory", "custom"]
ValidationSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class FieldSize:
    """Serialized size for one top-level metadata field."""

    field_name: str
    size_bytes: int

    @property
    def size_kb(self) -> float:
        """Return the field size in kibibytes."""
        return self.size_bytes / 1024


@dataclass(frozen=True)
class RecordAnalysis:
    """Metadata size analysis for one vector record."""

    record_id: str
    metadata_size_bytes: int
    limit_bytes: int
    largest_fields: list[FieldSize]

    @property
    def metadata_size_kb(self) -> float:
        """Return the metadata size in kibibytes."""
        return self.metadata_size_bytes / 1024

    @property
    def over_limit_by_bytes(self) -> int:
        """Return the number of bytes over the configured limit."""
        return max(0, self.metadata_size_bytes - self.limit_bytes)

    @property
    def is_oversized(self) -> bool:
        """Return whether this record exceeds the configured metadata limit."""
        return self.over_limit_by_bytes > 0


@dataclass(frozen=True)
class ScanReport:
    """Aggregate scan result."""

    target: str
    limit_bytes: int
    records: list[RecordAnalysis]

    @property
    def total_records(self) -> int:
        """Return the total number of records scanned."""
        return len(self.records)

    @property
    def oversized_count(self) -> int:
        """Return the number of records exceeding the limit."""
        return sum(record.is_oversized for record in self.records)

    @property
    def oversized_records(self) -> list[RecordAnalysis]:
        """Return oversized records, largest first."""
        return sorted(
            (record for record in self.records if record.is_oversized),
            key=lambda record: record.metadata_size_bytes,
            reverse=True,
        )


@dataclass(frozen=True)
class ValidationIssue:
    """One issue found during preflight validation."""

    record_id: str
    severity: ValidationSeverity
    code: str
    message: str
    field_path: str | None = None


@dataclass(frozen=True)
class RecordValidation:
    """Validation result for one vector record."""

    record_id: str
    metadata_size_bytes: int
    limit_bytes: int
    vector_dimension: int | None
    issues: list[ValidationIssue]

    @property
    def metadata_size_kb(self) -> float:
        """Return the metadata size in kibibytes."""
        return self.metadata_size_bytes / 1024

    @property
    def over_limit_by_bytes(self) -> int:
        """Return the number of bytes over the configured metadata limit."""
        return max(0, self.metadata_size_bytes - self.limit_bytes)

    @property
    def has_errors(self) -> bool:
        """Return whether this record has error-level validation issues."""
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def error_count(self) -> int:
        """Return the number of error-level issues."""
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        """Return the number of warning-level issues."""
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def is_oversized(self) -> bool:
        """Return whether metadata exceeds the configured limit."""
        return self.over_limit_by_bytes > 0


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate preflight validation result."""

    target: str
    limit_bytes: int
    expected_dim: int | None
    records: list[RecordValidation]

    @property
    def total_records(self) -> int:
        """Return the total number of records validated."""
        return len(self.records)

    @property
    def issues(self) -> list[ValidationIssue]:
        """Return all validation issues in record order."""
        return [issue for record in self.records for issue in record.issues]

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return all error-level validation issues."""
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return all warning-level validation issues."""
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def error_count(self) -> int:
        """Return the total number of error-level issues."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Return the total number of warning-level issues."""
        return len(self.warnings)

    @property
    def has_errors(self) -> bool:
        """Return whether any record has error-level validation issues."""
        return bool(self.errors)

    @property
    def records_with_errors(self) -> list[RecordValidation]:
        """Return records with error-level issues in input order."""
        return [record for record in self.records if record.has_errors]


@dataclass(frozen=True)
class TargetLimit:
    """Default metadata limit and note for a vector database target."""

    name: str
    limit_bytes: int | None
    note: str
    policy: LimitPolicy

    @property
    def limit_kb(self) -> float | None:
        """Return the limit in kibibytes when a default exists."""
        if self.limit_bytes is None:
            return None
        return self.limit_bytes / 1024


@dataclass(frozen=True)
class FixOptions:
    """Options used by the metadata fixer."""

    target: str
    limit_bytes: int
    sidecar_dir: Path
    output_path: Path | None = None
    move_fields: tuple[str, ...] | None = None
    keep_fields: tuple[str, ...] | None = None
    content_ref_field: str = "content_ref"


@dataclass(frozen=True)
class SidecarPayload:
    """A sidecar file planned by the fixer."""

    record_id: str
    path: Path
    ref: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class StoredSidecar:
    """A sidecar payload written to a store."""

    record_id: str
    ref: str
    deduplicated: bool


@dataclass(frozen=True)
class FixWarning:
    """A non-fatal warning produced during fixing."""

    record_id: str
    message: str


@dataclass(frozen=True)
class FixResult:
    """Cleaned records plus sidecar payloads."""

    cleaned_records: list[Record]
    sidecars: list[SidecarPayload]
    warnings: list[FixWarning] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        """Return how many records produced sidecar payloads."""
        return len(self.sidecars)


@dataclass(frozen=True)
class SafeUpsertResult:
    """Result produced by the safe upsert wrapper."""

    cleaned_records: list[Record]
    stored_sidecars: list[StoredSidecar]
    warnings: list[FixWarning]
    pre_validation_report: ValidationReport | None
    post_validation_report: ValidationReport | None
    upsert_result: Any

    @property
    def changed_count(self) -> int:
        """Return how many records wrote sidecar payloads."""
        return len(self.stored_sidecars)

    @property
    def total_records(self) -> int:
        """Return how many cleaned records were passed to upsert."""
        return len(self.cleaned_records)

    @property
    def stored_count(self) -> int:
        """Return how many sidecar references were written or reused."""
        return len(self.stored_sidecars)

    @property
    def deduplicated_count(self) -> int:
        """Return how many sidecar writes reused an existing payload."""
        return sum(sidecar.deduplicated for sidecar in self.stored_sidecars)

    @property
    def warning_count(self) -> int:
        """Return how many fixer warnings were produced."""
        return len(self.warnings)

    @property
    def pre_error_count(self) -> int:
        """Return pre-fix validation error count when validation ran."""
        if self.pre_validation_report is None:
            return 0
        return self.pre_validation_report.error_count

    @property
    def post_error_count(self) -> int:
        """Return post-fix validation error count when validation ran."""
        if self.post_validation_report is None:
            return 0
        return self.post_validation_report.error_count


@dataclass(frozen=True)
class SidecarMigrationResult:
    """Result of migrating legacy JSON sidecars into a SidecarStore."""

    records: list[Record]
    stored_sidecars: list[StoredSidecar]

    @property
    def migrated_count(self) -> int:
        """Return how many record references were migrated."""
        return len(self.stored_sidecars)

    @property
    def deduplicated_count(self) -> int:
        """Return how many migrations reused an existing payload."""
        return sum(sidecar.deduplicated for sidecar in self.stored_sidecars)
