from __future__ import annotations

from pathlib import Path

import pytest

from vectormeta.errors import InvalidInputError
from vectormeta.fixer import FixOptions, fix_records
from vectormeta.hydrate import (
    hydrate_records,
    hydrate_results,
    migrate_sidecars_to_store,
)
from vectormeta.io import write_sidecars
from vectormeta.stores import FileStore


class FakeMatch:
    def __init__(self, *, match_id: str, metadata: dict[str, object], score: float) -> None:
        self.id = match_id
        self.metadata = metadata
        self.score = score


def test_hydrate_restores_sidecar_fields_to_metadata(tmp_path: Path) -> None:
    records = [{"id": "doc", "metadata": {"source": "paper.pdf", "chunk_text": "payload"}}]
    result = fix_records(
        records,
        FixOptions(
            target="custom",
            limit_bytes=1024,
            sidecar_dir=tmp_path / "sidecar",
            output_path=tmp_path / "ready.json",
        ),
    )
    write_sidecars(result.sidecars)

    hydrated = hydrate_records(
        result.cleaned_records,
        sidecar_dir=tmp_path / "sidecar",
        input_base_dir=tmp_path,
    )

    assert hydrated[0]["metadata"] == {"source": "paper.pdf", "chunk_text": "payload"}


def test_hydrate_can_restore_to_content_field(tmp_path: Path) -> None:
    records = [{"id": "doc", "metadata": {"source": "paper.pdf", "summary": "payload"}}]
    result = fix_records(
        records,
        FixOptions(
            target="custom",
            limit_bytes=1024,
            sidecar_dir=tmp_path / "sidecar",
            output_path=tmp_path / "ready.json",
        ),
    )
    write_sidecars(result.sidecars)

    hydrated = hydrate_records(
        result.cleaned_records,
        sidecar_dir=tmp_path / "sidecar",
        mode="content_field",
        content_field="payload",
        input_base_dir=tmp_path,
    )

    assert hydrated[0]["metadata"] == {"source": "paper.pdf"}
    assert hydrated[0]["payload"] == {"summary": "payload"}


def test_hydrate_rejects_sidecar_reference_outside_allowed_paths(tmp_path: Path) -> None:
    outside_path = tmp_path.parent / "outside-sidecar.json"
    outside_path.write_text('{"id":"doc","chunk_text":"secret"}\n', encoding="utf-8")
    records = [
        {
            "id": "doc",
            "metadata": {
                "source": "paper.pdf",
                "content_ref": str(outside_path.resolve()),
            },
        }
    ]

    with pytest.raises(InvalidInputError, match="allowed sidecar paths"):
        hydrate_records(
            records,
            sidecar_dir=tmp_path / "sidecar",
            input_base_dir=tmp_path,
        )


def test_hydrate_preserves_nested_sidecar_reference(tmp_path: Path) -> None:
    sidecar_dir = tmp_path / "sidecar"
    nested_dir = sidecar_dir / "subdir"
    nested_dir.mkdir(parents=True)
    (sidecar_dir / "doc.json").write_text(
        '{"id":"wrong","chunk_text":"wrong"}\n',
        encoding="utf-8",
    )
    (nested_dir / "doc.json").write_text(
        '{"id":"doc","chunk_text":"expected"}\n',
        encoding="utf-8",
    )
    records = [
        {
            "id": "doc",
            "metadata": {
                "source": "paper.pdf",
                "content_ref": "sidecar/subdir/doc.json",
            },
        }
    ]

    hydrated = hydrate_records(records, sidecar_dir=sidecar_dir)

    assert hydrated[0]["metadata"]["chunk_text"] == "expected"


def test_hydrate_results_accepts_sdk_style_match_objects(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "sidecars")
    stored = store.write(
        record_id="doc",
        payload={"id": "doc", "chunk_text": "restored"},
    )
    matches = [
        FakeMatch(
            match_id="doc",
            metadata={"source": "paper.pdf", "content_ref": stored.ref},
            score=0.98,
        )
    ]

    hydrated = hydrate_results(matches, sidecar_store=store)

    assert hydrated == [
        {
            "id": "doc",
            "score": 0.98,
            "metadata": {"source": "paper.pdf", "chunk_text": "restored"},
        }
    ]


def test_migrate_legacy_sidecars_to_content_addressed_store(tmp_path: Path) -> None:
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "doc-1.json").write_text(
        '{"id":"doc-1","raw_html":"<p>same</p>"}\n',
        encoding="utf-8",
    )
    (legacy_dir / "doc-2.json").write_text(
        '{"id":"doc-2","raw_html":"<p>same</p>"}\n',
        encoding="utf-8",
    )
    records = [
        {"id": "doc-1", "metadata": {"content_ref": "legacy/doc-1.json"}},
        {"id": "doc-2", "metadata": {"content_ref": "legacy/doc-2.json"}},
    ]
    store = FileStore(tmp_path / "content-addressed")

    result = migrate_sidecars_to_store(
        records,
        sidecar_dir=legacy_dir,
        store=store,
        input_base_dir=tmp_path,
    )

    refs = [record["metadata"]["content_ref"] for record in result.records]
    assert result.migrated_count == 2
    assert result.deduplicated_count == 1
    assert refs[0] == refs[1]
    assert store.read(refs[0]) == {"raw_html": "<p>same</p>"}
