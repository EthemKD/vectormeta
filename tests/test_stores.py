from __future__ import annotations

from pathlib import Path

import pytest

from vectormeta.errors import SidecarStoreError
from vectormeta.stores import FileStore, SQLiteStore


def test_file_store_deduplicates_payloads_by_content(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "sidecars")

    first = store.write(record_id="doc-1", payload={"id": "doc-1", "raw_html": "<p>same</p>"})
    second = store.write(record_id="doc-2", payload={"id": "doc-2", "raw_html": "<p>same</p>"})

    assert first.ref == second.ref
    assert first.deduplicated is False
    assert second.deduplicated is True
    assert len(list((tmp_path / "sidecars").glob("*.json"))) == 1
    assert store.read(first.ref) == {"raw_html": "<p>same</p>"}


def test_file_store_rejects_wrong_ref_prefix(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "sidecars")

    with pytest.raises(SidecarStoreError, match="Expected file sidecar ref"):
        store.read("sqlite:" + ("a" * 64))


def test_sqlite_store_deduplicates_payloads_by_content(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "sidecars.sqlite")

    first = store.write(record_id="doc-1", payload={"id": "doc-1", "summary": "same"})
    second = store.write(record_id="doc-2", payload={"id": "doc-2", "summary": "same"})

    assert first.ref == second.ref
    assert first.deduplicated is False
    assert second.deduplicated is True
    assert store.read(first.ref) == {"summary": "same"}


def test_sqlite_store_rejects_missing_payload(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "sidecars.sqlite")

    with pytest.raises(SidecarStoreError, match="does not exist"):
        store.read("sqlite:" + ("a" * 64))
