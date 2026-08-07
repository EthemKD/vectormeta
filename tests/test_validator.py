from __future__ import annotations

from vectormeta.validator import validate_records, validate_records_stream


def test_validate_records_reports_pinecone_metadata_type_errors() -> None:
    records = [
        {
            "id": "doc",
            "values": [0.1, 0.2],
            "metadata": {
                "source": "paper.pdf",
                "score": 0.99,
                "published": True,
                "tags": ["rag", "metadata"],
                "$bad": "reserved",
                "nested": {"page": 1},
                "none": None,
                "mixed": ["ok", 1],
            },
        }
    ]

    report = validate_records(records, "pinecone", 4096)

    codes = [issue.code for issue in report.errors]
    assert report.has_errors
    assert codes.count("invalid_metadata_key") == 1
    assert codes.count("invalid_metadata_value") == 3
    assert {issue.field_path for issue in report.errors} == {
        "metadata.$bad",
        "metadata.nested",
        "metadata.none",
        "metadata.mixed",
    }


def test_validate_records_reports_duplicate_and_missing_ids() -> None:
    records = [
        {"id": "dup", "values": [0.1], "metadata": {}},
        {"_id": "dup", "values": [0.2], "metadata": {}},
        {"id": "", "values": [0.3], "metadata": {}},
        {"values": [0.4], "metadata": {}},
    ]

    report = validate_records(records, "pinecone", 4096)

    codes = [issue.code for issue in report.errors]
    assert codes.count("duplicate_id") == 1
    assert codes.count("missing_id") == 2


def test_validate_records_reports_vector_dimension_errors() -> None:
    records = [
        {"id": "doc-1", "values": [0.1, 0.2, 0.3], "metadata": {}},
        {"id": "doc-2", "values": [0.1, 0.2], "metadata": {}},
        {"id": "doc-3", "embedding": [0.1, "bad", 0.3], "metadata": {}},
    ]

    report = validate_records(records, "pinecone", 4096, dim=3)

    assert [issue.code for issue in report.errors] == [
        "vector_dimension_mismatch",
        "invalid_vector",
    ]
    assert report.records[0].vector_dimension == 3
    assert report.records[1].vector_dimension == 2
    assert report.records[2].vector_dimension is None


def test_validate_records_reports_inconsistent_vector_dimensions_without_expected_dim() -> None:
    records = [
        {"id": "doc-1", "values": [0.1, 0.2, 0.3], "metadata": {}},
        {"id": "doc-2", "values": [0.1, 0.2], "metadata": {}},
    ]

    report = validate_records(records, "pinecone", 4096)

    assert [issue.code for issue in report.errors] == ["inconsistent_vector_dimension"]


def test_validate_records_warns_when_vector_is_missing() -> None:
    report = validate_records([{"id": "doc", "metadata": {"source": "paper.pdf"}}], "qdrant", 4096)

    assert report.error_count == 0
    assert report.warning_count == 1
    assert report.warnings[0].code == "missing_vector"


def test_validate_records_marks_oversized_metadata() -> None:
    report = validate_records(
        [{"id": "doc", "values": [0.1], "metadata": {"text": "x" * 100}}],
        "custom",
        50,
    )

    assert report.has_errors
    assert report.errors[0].code == "metadata_too_large"
    assert report.records[0].over_limit_by_bytes > 0


def test_validate_records_stream_counts_all_errors_and_keeps_problem_records() -> None:
    records = [
        {"id": "doc", "values": [0.1], "metadata": {"nested": {"bad": True}}},
        {"id": "doc", "values": [0.2], "metadata": {"source": "paper.pdf"}},
        {"id": "ok", "values": [0.3], "metadata": {"source": "paper.pdf"}},
    ]

    report = validate_records_stream(records, "pinecone", 4096, top=1)

    assert report.total_records == 3
    assert report.error_count == 2
    assert report.warning_count == 0
    assert len(report.records) == 1
    assert report.records[0].record_id == "doc"
    assert report.records[0].issues[0].code == "invalid_metadata_value"


def test_validate_records_stream_has_errors_uses_aggregate_count() -> None:
    records = [
        {"id": "warn", "metadata": {"source": "paper.pdf"}},
        {"id": "bad", "values": [0.1], "metadata": {"nested": {}}},
    ]

    report = validate_records_stream(records, "pinecone", 4096, top=1)

    assert report.warning_count == 1
    assert report.error_count == 1
    assert report.records[0].record_id == "warn"
    assert report.has_errors
