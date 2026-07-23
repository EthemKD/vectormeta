from __future__ import annotations

from pathlib import Path

import pytest

from vectormeta.errors import OutputExistsError
from vectormeta.io import (
    detect_input_format,
    iter_jsonl_records,
    read_records,
    write_jsonl_records,
    write_records,
)


def test_read_records_supports_json_array(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text('[{"id":"a","metadata":{"text":"one"}}]', encoding="utf-8")

    records, input_format = read_records(path)

    assert input_format == "json"
    assert records == [{"id": "a", "metadata": {"text": "one"}}]


def test_read_records_supports_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(
        '{"id":"a","metadata":{"text":"one"}}\n{"id":"b","metadata":{"text":"two"}}\n',
        encoding="utf-8",
    )

    records, input_format = read_records(path)

    assert input_format == "jsonl"
    assert [record["id"] for record in records] == ["a", "b"]


def test_write_records_protects_existing_output(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        write_records([], path, "json", overwrite=False)


def test_detect_input_format_distinguishes_json_and_jsonl(tmp_path: Path) -> None:
    json_path = tmp_path / "records.json"
    jsonl_path = tmp_path / "records.jsonl"
    json_path.write_text('[{"id":"a","metadata":{}}]', encoding="utf-8")
    jsonl_path.write_text('{"id":"a","metadata":{}}\n', encoding="utf-8")

    assert detect_input_format(json_path) == "json"
    assert detect_input_format(jsonl_path) == "jsonl"


def test_iter_jsonl_records_streams_records(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(
        '{"id":"a","metadata":{"text":"one"}}\n\n{"id":"b","metadata":{"text":"two"}}\n',
        encoding="utf-8",
    )

    records = list(iter_jsonl_records(path))

    assert [record["id"] for record in records] == ["a", "b"]


def test_write_jsonl_records_writes_one_record_per_line(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"

    write_jsonl_records(
        [{"id": "a", "metadata": {"text": "one"}}, {"id": "b", "metadata": {}}],
        path,
    )

    assert path.read_text(encoding="utf-8").splitlines() == [
        '{"id":"a","metadata":{"text":"one"}}',
        '{"id":"b","metadata":{}}',
    ]
