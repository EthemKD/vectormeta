"""Command line interface for vectormeta."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from vectormeta import __version__
from vectormeta.analyzer import analyze_records
from vectormeta.config import load_config
from vectormeta.errors import VectorMetaError
from vectormeta.fixer import DEFAULT_KEEP_FIELDS, fix_records, parse_field_list
from vectormeta.hydrate import hydrate_records, hydrate_records_from_store
from vectormeta.io import ensure_output_writable, read_records, write_records, write_sidecars
from vectormeta.limits import normalize_target, resolve_limit_bytes
from vectormeta.models import FixOptions, HydrateMode, OutputFormat
from vectormeta.reporting import (
    render_fix_summary,
    render_limit_warning,
    render_limits,
    render_scan_report,
    render_validation_report,
    scan_report_to_dict,
    validation_report_to_dict,
)
from vectormeta.stores import (
    FileStore,
    SidecarStore,
    SQLiteStore,
    replace_content_refs,
    write_sidecar_payloads,
)
from vectormeta.validator import validate_records

app = typer.Typer(help="Detect and fix oversized vector database metadata.")
console = Console()


class ScanFormat(str, Enum):
    """Supported scan report formats."""

    table = "table"
    json = "json"


class RecordOutputFormat(str, Enum):
    """Supported record output formats."""

    json = "json"
    jsonl = "jsonl"


class HydrateModeOption(str, Enum):
    """Supported hydration modes."""

    metadata = "metadata"
    content_field = "content_field"


class SidecarStoreOption(str, Enum):
    """Supported CLI sidecar storage backends."""

    json = "json"
    file = "file"
    sqlite = "sqlite"


TargetOption = Annotated[
    str,
    typer.Option(
        "--target",
        help="Target vector DB: pinecone, chroma, qdrant, weaviate, or custom.",
    ),
]
LimitOption = Annotated[
    float | None,
    typer.Option("--limit-kb", help="Override metadata size limit in KB."),
]


def main() -> None:
    """Run the CLI application."""
    app()


def _version_callback(value: bool | None) -> None:
    if value:
        console.print(f"vectormeta {__version__}")
        raise typer.Exit()


@app.callback()
def app_callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed vectormeta version and exit.",
        ),
    ] = None,
) -> None:
    """Detect and fix oversized vector database metadata."""


@app.command()
def scan(
    input_path: Annotated[Path, typer.Argument(help="JSON or JSONL vector records file.")],
    target: TargetOption = "pinecone",
    limit_kb: LimitOption = None,
    top: Annotated[
        int, typer.Option("--top", min=1, help="Number of oversized records to show.")
    ] = 10,
    output_format: Annotated[
        ScanFormat,
        typer.Option("--format", help="Output format: table or json."),
    ] = ScanFormat.table,
    no_fail: Annotated[
        bool,
        typer.Option("--no-fail", help="Exit 0 even when oversized records are found."),
    ] = False,
) -> None:
    """Scan records and report oversized metadata."""
    try:
        normalized_target = normalize_target(target)
        limit_bytes = resolve_limit_bytes(normalized_target, limit_kb)
        records, _ = read_records(input_path)
        report = analyze_records(records, normalized_target, limit_bytes)
        if output_format == ScanFormat.json:
            console.print_json(
                json.dumps(scan_report_to_dict(report, top=top), ensure_ascii=False, sort_keys=True)
            )
        elif output_format == ScanFormat.table:
            render_scan_report(console, report, top=top)

        if report.oversized_count and not no_fail:
            raise typer.Exit(1)
    except VectorMetaError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command()
def validate(
    input_path: Annotated[Path, typer.Argument(help="JSON or JSONL vector records file.")],
    target: TargetOption = "pinecone",
    limit_kb: LimitOption = None,
    dim: Annotated[
        int | None,
        typer.Option("--dim", min=1, help="Expected vector dimension for every record."),
    ] = None,
    top: Annotated[
        int, typer.Option("--top", min=1, help="Number of validation issues to show.")
    ] = 20,
    output_format: Annotated[
        ScanFormat,
        typer.Option("--format", help="Output format: table or json."),
    ] = ScanFormat.table,
    no_fail: Annotated[
        bool,
        typer.Option("--no-fail", help="Exit 0 even when validation errors are found."),
    ] = False,
) -> None:
    """Validate records for common vector DB upsert failures."""
    try:
        normalized_target = normalize_target(target)
        limit_bytes = resolve_limit_bytes(normalized_target, limit_kb)
        records, _ = read_records(input_path)
        report = validate_records(records, normalized_target, limit_bytes, dim=dim)
        if output_format == ScanFormat.json:
            console.print_json(
                json.dumps(
                    validation_report_to_dict(report, top=top),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        elif output_format == ScanFormat.table:
            render_validation_report(console, report, top=top)

        if report.has_errors and not no_fail:
            raise typer.Exit(1)
    except VectorMetaError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command()
def fix(
    input_path: Annotated[Path, typer.Argument(help="JSON or JSONL vector records file.")],
    out: Annotated[Path, typer.Option("--out", help="Cleaned output records path.")],
    target: Annotated[
        str | None,
        typer.Option(
            "--target",
            help="Target vector DB. Overrides config when provided.",
        ),
    ] = None,
    limit_kb: LimitOption = None,
    sidecar: Annotated[
        Path | None,
        typer.Option(
            "--sidecar",
            help=(
                "Directory for json/file sidecars, or SQLite database path when "
                "--sidecar-store sqlite is used."
            ),
        ),
    ] = None,
    sidecar_store: Annotated[
        SidecarStoreOption,
        typer.Option(
            "--sidecar-store",
            help="Sidecar backend: json, file, or sqlite.",
        ),
    ] = SidecarStoreOption.json,
    output_format: Annotated[
        RecordOutputFormat,
        typer.Option("--format", help="Output record format: json or jsonl."),
    ] = RecordOutputFormat.json,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan changes without writing output or sidecars."),
    ] = False,
    move_fields: Annotated[
        str | None,
        typer.Option("--move-fields", help="Comma-separated metadata fields to move."),
    ] = None,
    keep_fields: Annotated[
        str | None,
        typer.Option("--keep-fields", help="Comma-separated metadata fields to keep filterable."),
    ] = None,
    content_ref_field: Annotated[
        str | None,
        typer.Option("--content-ref-field", help="Metadata field used for sidecar references."),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Optional vectormeta.yml config file."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Allow replacing output and sidecar files."),
    ] = False,
) -> None:
    """Move heavy metadata fields into sidecar files."""
    try:
        loaded_config = load_config(config)
        resolved_target = normalize_target(target or loaded_config.target or "pinecone")
        resolved_limit_kb = limit_kb if limit_kb is not None else loaded_config.limit_kb
        limit_bytes = resolve_limit_bytes(resolved_target, resolved_limit_kb)
        render_limit_warning(console, target=resolved_target, limit_bytes=limit_bytes)
        resolved_sidecar = _default_sidecar_path(sidecar, loaded_config.sidecar_dir, sidecar_store)
        resolved_ref_field = content_ref_field or loaded_config.content_ref_field or "content_ref"
        resolved_move_fields = parse_field_list(move_fields)
        if resolved_move_fields is None and loaded_config.move is not None:
            resolved_move_fields = tuple(loaded_config.move)
        resolved_keep_fields = parse_field_list(keep_fields)
        if resolved_keep_fields is None:
            resolved_keep_fields = tuple(loaded_config.keep or DEFAULT_KEEP_FIELDS)

        records, _ = read_records(input_path)
        result = fix_records(
            records,
            FixOptions(
                target=resolved_target,
                limit_bytes=limit_bytes,
                sidecar_dir=resolved_sidecar,
                output_path=out,
                move_fields=resolved_move_fields,
                keep_fields=resolved_keep_fields,
                content_ref_field=resolved_ref_field,
            ),
        )

        render_fix_summary(console, result, dry_run=dry_run)
        if dry_run:
            return

        ensure_output_writable(out, overwrite=overwrite)
        cleaned_records = result.cleaned_records
        if sidecar_store == SidecarStoreOption.json:
            write_sidecars(result.sidecars, overwrite=overwrite)
        else:
            store = _sidecar_store(sidecar_store, resolved_sidecar)
            stored_sidecars = write_sidecar_payloads(store, result.sidecars)
            cleaned_records = replace_content_refs(
                result.cleaned_records,
                old_refs=[sidecar.ref for sidecar in result.sidecars],
                new_refs=[stored.ref for stored in stored_sidecars],
                content_ref_field=resolved_ref_field,
            )
        write_records(
            cleaned_records, out, _record_output_format(output_format), overwrite=overwrite
        )
        console.print(f"[green]Wrote cleaned records to {out}.[/green]")
        if result.sidecars:
            _print_sidecar_write_summary(sidecar_store, resolved_sidecar, len(result.sidecars))
    except VectorMetaError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command()
def hydrate(
    input_path: Annotated[Path, typer.Argument(help="Cleaned JSON or JSONL vector records file.")],
    sidecar: Annotated[
        Path,
        typer.Option(
            "--sidecar",
            help=(
                "Directory containing sidecar files, or SQLite database path when "
                "--sidecar-store sqlite is used."
            ),
        ),
    ],
    out: Annotated[Path, typer.Option("--out", help="Hydrated output records path.")],
    sidecar_store: Annotated[
        SidecarStoreOption,
        typer.Option(
            "--sidecar-store",
            help="Sidecar backend: json, file, or sqlite.",
        ),
    ] = SidecarStoreOption.json,
    mode: Annotated[
        HydrateModeOption,
        typer.Option("--mode", help="Hydration mode: metadata or content_field."),
    ] = HydrateModeOption.metadata,
    content_field: Annotated[
        str,
        typer.Option("--content-field", help="Record field for content_field hydration mode."),
    ] = "payload",
    content_ref_field: Annotated[
        str,
        typer.Option(
            "--content-ref-field", help="Metadata field containing the sidecar reference."
        ),
    ] = "content_ref",
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Allow replacing the output file."),
    ] = False,
) -> None:
    """Restore records by loading content_ref sidecar files."""
    try:
        records, input_format = read_records(input_path)
        if sidecar_store == SidecarStoreOption.json:
            hydrated = hydrate_records(
                records,
                sidecar_dir=sidecar,
                mode=_hydrate_mode(mode),
                content_field=content_field,
                content_ref_field=content_ref_field,
                input_base_dir=input_path.parent,
            )
        else:
            hydrated = hydrate_records_from_store(
                records,
                store=_sidecar_store(sidecar_store, sidecar),
                mode=_hydrate_mode(mode),
                content_field=content_field,
                content_ref_field=content_ref_field,
            )
        output_format: OutputFormat = "jsonl" if input_format == "jsonl" else "json"
        write_records(hydrated, out, output_format, overwrite=overwrite)
        console.print(f"[green]Wrote hydrated records to {out}.[/green]")
    except VectorMetaError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command(name="limits")
def limits_command() -> None:
    """Show known metadata limit presets and notes."""
    render_limits(console)


def _print_error(exc: Exception) -> None:
    console.print(f"[red]Error:[/red] {exc}")


def _record_output_format(output_format: RecordOutputFormat) -> OutputFormat:
    return "jsonl" if output_format == RecordOutputFormat.jsonl else "json"


def _hydrate_mode(mode: HydrateModeOption) -> HydrateMode:
    return "content_field" if mode == HydrateModeOption.content_field else "metadata"


def _default_sidecar_path(
    sidecar: Path | None,
    config_sidecar: Path | None,
    store_option: SidecarStoreOption,
) -> Path:
    if sidecar is not None:
        return sidecar
    if config_sidecar is not None:
        return config_sidecar
    if store_option == SidecarStoreOption.sqlite:
        return Path("sidecar.sqlite")
    return Path("sidecar")


def _sidecar_store(store_option: SidecarStoreOption, path: Path) -> SidecarStore:
    if store_option == SidecarStoreOption.file:
        return FileStore(path)
    if store_option == SidecarStoreOption.sqlite:
        return SQLiteStore(path)
    raise ValueError("json sidecar backend does not use SidecarStore")


def _print_sidecar_write_summary(
    store_option: SidecarStoreOption,
    sidecar_path: Path,
    count: int,
) -> None:
    if store_option == SidecarStoreOption.json:
        console.print(f"[green]Wrote {count} sidecar files to {sidecar_path}.[/green]")
    elif store_option == SidecarStoreOption.file:
        console.print(
            f"[green]Stored {count} content-addressed sidecar refs in {sidecar_path}.[/green]"
        )
    else:
        console.print(
            f"[green]Stored {count} content-addressed sidecar refs in {sidecar_path}.[/green]"
        )


if __name__ == "__main__":
    main()
