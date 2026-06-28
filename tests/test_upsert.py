from __future__ import annotations

from typing import Any

import pytest

from vectormeta.errors import ValidationFailedError
from vectormeta.hydrate import hydrate_records_from_store, hydrate_results
from vectormeta.models import Record
from vectormeta.stores import FileStore
from vectormeta.upsert import safe_upsert


class FakeIndex:
    def __init__(self) -> None:
        self.vectors: list[Record] = []
        self.kwargs: dict[str, Any] = {}

    def upsert(self, *, vectors: list[Record], **kwargs: Any) -> dict[str, int]:
        self.vectors = vectors
        self.kwargs = dict(kwargs)
        return {"upserted_count": len(vectors)}

    def query(self) -> dict[str, list[Record]]:
        return {"matches": self.vectors}


def test_safe_upsert_fixes_oversized_metadata_and_writes_to_store(tmp_path) -> None:
    index = FakeIndex()
    store = FileStore(tmp_path / "sidecars")
    records = [
        {
            "id": "doc",
            "values": [0.1, 0.2],
            "metadata": {
                "source": "paper.pdf",
                "chunk_text": "x" * 220,
            },
        }
    ]

    result = safe_upsert(
        index,
        records,
        target="custom",
        sidecar_store=store,
        limit_kb=0.2,
        dim=2,
        upsert_kwargs={"namespace": "docs"},
    )

    assert result.upsert_result == {"upserted_count": 1}
    assert result.changed_count == 1
    assert result.total_records == 1
    assert result.stored_count == 1
    assert result.deduplicated_count == 0
    assert result.warning_count == 0
    assert result.pre_error_count == 1
    assert result.post_error_count == 0
    assert index.kwargs == {"namespace": "docs"}
    metadata = index.vectors[0]["metadata"]
    assert metadata["source"] == "paper.pdf"
    assert metadata["content_ref"].startswith("file:")
    assert "chunk_text" not in metadata
    assert store.read(metadata["content_ref"]) == {"chunk_text": "x" * 220}

    hydrated = hydrate_records_from_store(index.vectors, store=store)
    assert hydrated[0]["metadata"]["chunk_text"] == "x" * 220

    query_result = index.query()
    hydrated_matches = hydrate_results(query_result["matches"], sidecar_store=store)
    assert hydrated_matches[0]["metadata"]["chunk_text"] == "x" * 220


def test_safe_upsert_blocks_unfixable_validation_errors(tmp_path) -> None:
    index = FakeIndex()
    store = FileStore(tmp_path / "sidecars")
    records = [
        {
            "id": "doc",
            "values": [0.1],
            "metadata": {"nested": {"page": 1}},
        }
    ]

    with pytest.raises(ValidationFailedError, match="invalid_metadata_value"):
        safe_upsert(index, records, target="pinecone", sidecar_store=store)

    assert index.vectors == []


def test_safe_upsert_blocks_records_that_remain_oversized_after_fix(tmp_path) -> None:
    index = FakeIndex()
    sidecar_dir = tmp_path / "sidecars"
    store = FileStore(sidecar_dir)
    records = [{"id": "doc", "values": [0.1], "metadata": {"notes": "payload"}}]

    with pytest.raises(ValidationFailedError, match="metadata_too_large"):
        safe_upsert(
            index,
            records,
            target="custom",
            sidecar_store=store,
            limit_kb=0.001,
            move_fields=(),
            keep_fields=(),
        )

    assert index.vectors == []
    assert not sidecar_dir.exists()


def test_safe_upsert_force_allows_validation_errors(tmp_path) -> None:
    index = FakeIndex()
    store = FileStore(tmp_path / "sidecars")
    records = [
        {
            "id": "doc",
            "values": [0.1],
            "metadata": {"nested": {"page": 1}},
        }
    ]

    result = safe_upsert(
        index,
        records,
        target="pinecone",
        sidecar_store=store,
        force=True,
    )

    assert result.upsert_result == {"upserted_count": 1}
    assert result.pre_validation_report is not None
    assert result.pre_validation_report.has_errors
