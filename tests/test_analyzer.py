from __future__ import annotations

import pytest

from vectormeta.analyzer import analyze_records, analyze_records_stream
from vectormeta.errors import InvalidInputError


def test_analyze_records_reports_oversized_records() -> None:
    records = [
        {"id": "small", "metadata": {"source": "a.pdf"}},
        {"_id": "large", "metadata": {"text": "x" * 200}},
    ]

    report = analyze_records(records, "custom", limit_bytes=80)

    assert report.total_records == 2
    assert report.oversized_count == 1
    assert report.oversized_records[0].record_id == "large"
    assert report.oversized_records[0].over_limit_by_bytes > 0


def test_analyze_records_requires_metadata_object() -> None:
    with pytest.raises(InvalidInputError, match="metadata object"):
        analyze_records([{"id": "bad", "metadata": "nope"}], "custom", limit_bytes=100)


def test_analyze_records_stream_counts_all_records_and_keeps_top_oversized() -> None:
    records = [
        {"id": "small", "metadata": {"source": "a.pdf"}},
        {"id": "large", "metadata": {"text": "x" * 200}},
        {"id": "larger", "metadata": {"text": "y" * 300}},
    ]

    report = analyze_records_stream(records, "custom", limit_bytes=80, top=1)

    assert report.total_records == 3
    assert report.oversized_count == 2
    assert [record.record_id for record in report.oversized_records] == ["larger"]
