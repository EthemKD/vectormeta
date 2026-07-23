from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vectormeta.cli import app


def test_scan_exits_one_when_oversized(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    input_path.write_text(
        '[{"id":"doc","metadata":{"text":"' + ("x" * 200) + '"}}]',
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["scan", str(input_path), "--target", "custom", "--limit-kb", "0.05"],
    )

    assert result.exit_code == 1
    assert "Oversized records" in result.output


def test_version_option() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "vectormeta 0.3.0" in result.output


def test_scan_no_fail_exits_zero_when_oversized(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    input_path.write_text(
        '[{"id":"doc","metadata":{"text":"' + ("x" * 200) + '"}}]',
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["scan", str(input_path), "--target", "custom", "--limit-kb", "0.05", "--no-fail"],
    )

    assert result.exit_code == 0
    assert "Oversized records" in result.output


def test_scan_prints_advisory_warning_for_non_pinecone_target(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    input_path.write_text('[{"id":"doc","metadata":{"source":"paper.pdf"}}]', encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["scan", str(input_path), "--target", "chroma"])

    assert result.exit_code == 0
    assert "chroma limit is advisory" in result.output


def test_scan_json_includes_limit_policy_for_advisory_target(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    input_path.write_text('[{"id":"doc","metadata":{"source":"paper.pdf"}}]', encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["scan", str(input_path), "--target", "qdrant", "--format", "json"])

    assert result.exit_code == 0
    assert '"limit_policy": "advisory"' in result.output
    assert "qdrant limit is advisory" in result.output


def test_validate_exits_one_when_errors_are_found(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    input_path.write_text(
        '[{"id":"doc","values":[0.1],"metadata":{"nested":{"page":1}}}]',
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["validate", str(input_path), "--target", "pinecone", "--format", "json"],
    )

    assert result.exit_code == 1
    assert "invalid_metadata_value" in result.output


def test_validate_no_fail_exits_zero_when_errors_are_found(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    input_path.write_text(
        '[{"id":"doc","values":[0.1],"metadata":{"nested":{"page":1}}}]',
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["validate", str(input_path), "--target", "pinecone", "--no-fail", "--format", "json"],
    )

    assert result.exit_code == 0
    assert "invalid_metadata_value" in result.output


def test_validate_json_reports_errors(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    input_path.write_text(
        '[{"id":"doc","values":[0.1,0.2],"metadata":{"source":"paper.pdf"}}]',
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["validate", str(input_path), "--target", "pinecone", "--dim", "3", "--format", "json"],
    )

    assert result.exit_code == 1
    assert '"error_count": 1' in result.output
    assert "vector_dimension_mismatch" in result.output


def test_fix_prints_advisory_warning_for_non_pinecone_target(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    ready_path = tmp_path / "ready.json"
    sidecar_path = tmp_path / "sidecar"
    input_path.write_text(
        '[{"id":"doc","values":[0.1],"metadata":{"source":"paper.pdf","chunk_text":"payload"}}]',
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "fix",
            str(input_path),
            "--target",
            "chroma",
            "--sidecar",
            str(sidecar_path),
            "--out",
            str(ready_path),
        ],
    )

    assert result.exit_code == 0
    assert "chroma limit is advisory" in result.output


def test_fix_and_hydrate_cli_round_trip(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    ready_path = tmp_path / "ready.json"
    hydrated_path = tmp_path / "hydrated.json"
    sidecar_path = tmp_path / "sidecar"
    input_path.write_text(
        '[{"id":"doc","values":[0.1],"metadata":{"source":"paper.pdf","chunk_text":"payload"}}]',
        encoding="utf-8",
    )
    runner = CliRunner()

    fix_result = runner.invoke(
        app,
        [
            "fix",
            str(input_path),
            "--target",
            "pinecone",
            "--sidecar",
            str(sidecar_path),
            "--out",
            str(ready_path),
        ],
    )
    hydrate_result = runner.invoke(
        app,
        [
            "hydrate",
            str(ready_path),
            "--sidecar",
            str(sidecar_path),
            "--out",
            str(hydrated_path),
        ],
    )

    assert fix_result.exit_code == 0
    assert hydrate_result.exit_code == 0
    assert ready_path.exists()
    assert (sidecar_path / "doc.json").exists()
    assert "chunk_text" in hydrated_path.read_text(encoding="utf-8")


def test_fix_and_hydrate_cli_round_trip_with_sqlite_store(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    ready_path = tmp_path / "ready.json"
    hydrated_path = tmp_path / "hydrated.json"
    sqlite_path = tmp_path / "sidecars.sqlite"
    input_path.write_text(
        '[{"id":"doc","values":[0.1],"metadata":{"source":"paper.pdf","chunk_text":"payload"}}]',
        encoding="utf-8",
    )
    runner = CliRunner()

    fix_result = runner.invoke(
        app,
        [
            "fix",
            str(input_path),
            "--target",
            "pinecone",
            "--sidecar-store",
            "sqlite",
            "--sidecar",
            str(sqlite_path),
            "--out",
            str(ready_path),
        ],
    )
    hydrate_result = runner.invoke(
        app,
        [
            "hydrate",
            str(ready_path),
            "--sidecar-store",
            "sqlite",
            "--sidecar",
            str(sqlite_path),
            "--out",
            str(hydrated_path),
        ],
    )

    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    assert fix_result.exit_code == 0
    assert hydrate_result.exit_code == 0
    assert sqlite_path.exists()
    assert ready[0]["metadata"]["content_ref"].startswith("sqlite:")
    assert "chunk_text" in hydrated_path.read_text(encoding="utf-8")


def test_fix_with_file_store_deduplicates_repeated_payloads(tmp_path: Path) -> None:
    input_path = tmp_path / "records.json"
    ready_path = tmp_path / "ready.json"
    sidecar_path = tmp_path / "content-sidecars"
    input_path.write_text(
        json.dumps(
            [
                {
                    "id": "doc-1",
                    "values": [0.1],
                    "metadata": {"source": "paper.pdf", "raw_html": "<p>same</p>"},
                },
                {
                    "id": "doc-2",
                    "values": [0.2],
                    "metadata": {"source": "paper.pdf", "raw_html": "<p>same</p>"},
                },
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "fix",
            str(input_path),
            "--target",
            "pinecone",
            "--sidecar-store",
            "file",
            "--sidecar",
            str(sidecar_path),
            "--out",
            str(ready_path),
        ],
    )

    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    refs = [record["metadata"]["content_ref"] for record in ready]
    assert result.exit_code == 0
    assert refs[0] == refs[1]
    assert refs[0].startswith("file:")
    assert len(list(sidecar_path.glob("*.json"))) == 1


def test_fix_streaming_jsonl_with_sqlite_store_deduplicates_payloads(tmp_path: Path) -> None:
    input_path = tmp_path / "records.jsonl"
    ready_path = tmp_path / "ready.jsonl"
    sqlite_path = tmp_path / "sidecars.sqlite"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "doc-1",
                        "values": [0.1],
                        "metadata": {"source": "paper.pdf", "raw_html": "<p>same</p>"},
                    }
                ),
                json.dumps(
                    {
                        "id": "doc-2",
                        "values": [0.2],
                        "metadata": {"source": "paper.pdf", "raw_html": "<p>same</p>"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "fix",
            str(input_path),
            "--target",
            "pinecone",
            "--stream",
            "--format",
            "jsonl",
            "--sidecar-store",
            "sqlite",
            "--sidecar",
            str(sqlite_path),
            "--out",
            str(ready_path),
        ],
    )

    lines = [json.loads(line) for line in ready_path.read_text(encoding="utf-8").splitlines()]
    refs = [record["metadata"]["content_ref"] for record in lines]
    assert result.exit_code == 0
    assert "Metadata reduction" in result.output
    assert "deduplicated refs: 1" in result.output
    assert refs[0] == refs[1]
    assert refs[0].startswith("sqlite:")


def test_fix_streaming_requires_jsonl_output(tmp_path: Path) -> None:
    input_path = tmp_path / "records.jsonl"
    ready_path = tmp_path / "ready.json"
    input_path.write_text('{"id":"doc","metadata":{"chunk_text":"payload"}}\n', encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "fix",
            str(input_path),
            "--stream",
            "--out",
            str(ready_path),
        ],
    )

    assert result.exit_code == 2
    assert "--stream requires --format jsonl" in result.output
