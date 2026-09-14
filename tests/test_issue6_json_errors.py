from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vectormeta.cli import app
from vectormeta.errors import InvalidInputError
from vectormeta.io import read_records


@pytest.mark.parametrize(
    "payload",
    [
        '[{"id":"a"}',
        '[{"id":"a"},]',
        '\ufeff  \n[{"id":"a"},]',
    ],
)
def test_malformed_json_arrays_report_json_errors(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "records.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(InvalidInputError, match="Invalid JSON array"):
        read_records(path)


def test_malformed_jsonl_keeps_line_numbered_error(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"id":"a"}\n{"id":}\n', encoding="utf-8")

    with pytest.raises(InvalidInputError, match=r"Invalid JSONL at .*:2"):
        read_records(path)


def test_cli_reports_malformed_json_array_without_traceback(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text('[{"id":"a"},]', encoding="utf-8")

    result = CliRunner().invoke(app, ["scan", str(path)])

    assert result.exit_code == 2
    assert "Invalid JSON array" in result.output
    assert "Traceback" not in result.output
