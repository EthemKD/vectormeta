"""Human and machine report rendering."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from vectormeta.limits import advisory_limit_message, get_target_limit, get_target_limits
from vectormeta.models import (
    FixResult,
    RecordAnalysis,
    RecordValidation,
    ScanReport,
    ValidationIssue,
    ValidationReport,
)


def bytes_to_kb(size_bytes: int) -> float:
    """Convert bytes to KiB."""
    return size_bytes / 1024


def scan_report_to_dict(report: ScanReport, *, top: int) -> dict[str, Any]:
    """Convert a scan report to stable JSON-serializable data."""
    target_limit = get_target_limit(report.target)
    advisory_message = advisory_limit_message(report.target, report.limit_bytes)
    return {
        "target": report.target,
        "limit_bytes": report.limit_bytes,
        "limit_kb": round(bytes_to_kb(report.limit_bytes), 3),
        "limit_policy": target_limit.policy,
        "limit_note": target_limit.note,
        "limit_warning": advisory_message,
        "total_records": report.total_records,
        "oversized_count": report.oversized_count,
        "oversized_records": [
            _record_analysis_to_dict(record) for record in report.oversized_records[:top]
        ],
    }


def validation_report_to_dict(report: ValidationReport, *, top: int) -> dict[str, Any]:
    """Convert a validation report to stable JSON-serializable data."""
    target_limit = get_target_limit(report.target)
    advisory_message = advisory_limit_message(report.target, report.limit_bytes)
    return {
        "target": report.target,
        "limit_bytes": report.limit_bytes,
        "limit_kb": round(bytes_to_kb(report.limit_bytes), 3),
        "limit_policy": target_limit.policy,
        "limit_note": target_limit.note,
        "limit_warning": advisory_message,
        "expected_dim": report.expected_dim,
        "total_records": report.total_records,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "has_errors": report.has_errors,
        "top_issues": [_validation_issue_to_dict(issue) for issue in report.issues[:top]],
        "records": [_record_validation_to_dict(record) for record in report.records],
    }


def render_limit_warning(console: Console, *, target: str, limit_bytes: int) -> None:
    """Render advisory limit warnings for human-readable command output."""
    advisory_message = advisory_limit_message(target, limit_bytes)
    if advisory_message is not None:
        console.print(f"[yellow]Warning:[/yellow] {advisory_message}")


def render_scan_report(console: Console, report: ScanReport, *, top: int) -> None:
    """Render a human-readable scan report."""
    console.print(f"[bold]Target:[/bold] {report.target}")
    console.print(
        f"[bold]Metadata limit:[/bold] {report.limit_bytes} bytes "
        f"({bytes_to_kb(report.limit_bytes):.2f} KB)"
    )
    render_limit_warning(console, target=report.target, limit_bytes=report.limit_bytes)
    console.print(f"[bold]Records scanned:[/bold] {report.total_records}")
    color = "red" if report.oversized_count else "green"
    console.print(f"[bold]Oversized records:[/bold] [{color}]{report.oversized_count}[/{color}]")

    table = Table(title=f"Top {top} Oversized Records")
    table.add_column("Record ID", overflow="fold")
    table.add_column("Metadata", justify="right")
    table.add_column("Over Limit", justify="right")
    table.add_column("Largest Fields", overflow="fold")
    table.add_column("Suggested Moves", overflow="fold")

    for record in report.oversized_records[:top]:
        largest = ", ".join(
            f"{field.field_name} ({field.size_kb:.1f} KB)" for field in record.largest_fields[:3]
        )
        suggestions = ", ".join(field.field_name for field in record.largest_fields[:3])
        table.add_row(
            record.record_id,
            f"{record.metadata_size_bytes} B / {record.metadata_size_kb:.2f} KB",
            f"{record.over_limit_by_bytes} B",
            largest,
            suggestions,
        )

    if report.oversized_count:
        console.print(table)
    else:
        console.print("[green]All records are within the configured metadata limit.[/green]")


def render_validation_report(console: Console, report: ValidationReport, *, top: int) -> None:
    """Render a human-readable preflight validation report."""
    console.print(f"[bold]Target:[/bold] {report.target}")
    console.print(
        f"[bold]Metadata limit:[/bold] {report.limit_bytes} bytes "
        f"({bytes_to_kb(report.limit_bytes):.2f} KB)"
    )
    render_limit_warning(console, target=report.target, limit_bytes=report.limit_bytes)
    if report.expected_dim is not None:
        console.print(f"[bold]Expected vector dimension:[/bold] {report.expected_dim}")
    console.print(f"[bold]Records validated:[/bold] {report.total_records}")
    error_color = "red" if report.error_count else "green"
    warning_color = "yellow" if report.warning_count else "green"
    console.print(f"[bold]Errors:[/bold] [{error_color}]{report.error_count}[/{error_color}]")
    console.print(
        f"[bold]Warnings:[/bold] [{warning_color}]{report.warning_count}[/{warning_color}]"
    )

    if not report.issues:
        console.print("[green]No validation issues found.[/green]")
        return

    table = Table(title=f"Top {top} Validation Issues")
    table.add_column("Severity", no_wrap=True)
    table.add_column("Code", no_wrap=True)
    table.add_column("Record ID", overflow="fold")
    table.add_column("Field", overflow="fold", no_wrap=True)
    table.add_column("Message", overflow="fold")

    for issue in report.issues[:top]:
        severity_style = "red" if issue.severity == "error" else "yellow"
        table.add_row(
            f"[{severity_style}]{issue.severity}[/{severity_style}]",
            issue.code,
            issue.record_id,
            issue.field_path or "-",
            issue.message,
        )
    console.print(table)


def render_fix_summary(console: Console, result: FixResult, *, dry_run: bool) -> None:
    """Render a human-readable fix summary."""
    action = "would update" if dry_run else "updated"
    console.print(
        f"[bold]Fix summary:[/bold] {action} {len(result.cleaned_records)} records; "
        f"{result.changed_count} records have sidecar payloads."
    )
    if result.savings:
        console.print(
            "[bold]Metadata reduction:[/bold] "
            f"{result.reduced_bytes} B ({bytes_to_kb(result.reduced_bytes):.2f} KB) removed; "
            f"{result.reduction_ratio:.1%} smaller metadata."
        )
    if result.warnings:
        warning_table = Table(title="Warnings")
        warning_table.add_column("Record ID", overflow="fold")
        warning_table.add_column("Message", overflow="fold")
        for warning in result.warnings:
            warning_table.add_row(warning.record_id, warning.message)
        console.print(warning_table)


def render_limits(console: Console) -> None:
    """Render known target metadata limits."""
    table = Table(title="Vector DB Metadata Limit Presets")
    table.add_column("Target")
    table.add_column("Default Limit", justify="right")
    table.add_column("Policy")
    table.add_column("Note", overflow="fold")
    for target_limit in get_target_limits():
        if target_limit.limit_bytes is None:
            limit = "custom"
        else:
            limit = f"{target_limit.limit_bytes} B / {target_limit.limit_bytes / 1024:.0f} KB"
        table.add_row(target_limit.name, limit, target_limit.policy, target_limit.note)
    console.print(table)
    console.print(
        "[dim]Limits and service behavior can change. Verify official vector database docs "
        "for production limits.[/dim]"
    )


def _record_analysis_to_dict(record: RecordAnalysis) -> dict[str, Any]:
    return {
        "id": record.record_id,
        "metadata_size_bytes": record.metadata_size_bytes,
        "metadata_size_kb": round(record.metadata_size_kb, 3),
        "over_limit_by_bytes": record.over_limit_by_bytes,
        "largest_fields": [
            {
                "field": field.field_name,
                "size_bytes": field.size_bytes,
                "size_kb": round(field.size_kb, 3),
            }
            for field in record.largest_fields
        ],
        "suggested_move_fields": [field.field_name for field in record.largest_fields[:3]],
    }


def _record_validation_to_dict(record: RecordValidation) -> dict[str, Any]:
    return {
        "id": record.record_id,
        "metadata_size_bytes": record.metadata_size_bytes,
        "metadata_size_kb": round(record.metadata_size_kb, 3),
        "over_limit_by_bytes": record.over_limit_by_bytes,
        "vector_dimension": record.vector_dimension,
        "error_count": record.error_count,
        "warning_count": record.warning_count,
        "has_errors": record.has_errors,
        "issues": [_validation_issue_to_dict(issue) for issue in record.issues],
    }


def _validation_issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    return {
        "record_id": issue.record_id,
        "severity": issue.severity,
        "code": issue.code,
        "field_path": issue.field_path,
        "message": issue.message,
    }
