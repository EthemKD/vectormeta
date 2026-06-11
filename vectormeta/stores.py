"""Sidecar storage backends."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from vectormeta.errors import SidecarStoreError
from vectormeta.models import StoredSidecar
from vectormeta.sizing import compact_json_bytes

_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")


class SidecarStore(Protocol):
    """Protocol implemented by sidecar storage backends."""

    def write(self, *, record_id: str, payload: Mapping[str, Any]) -> StoredSidecar:
        """Write a sidecar payload and return its stable content reference."""

    def read(self, ref: str) -> dict[str, Any]:
        """Read a sidecar payload by reference."""


class FileStore:
    """Content-addressed JSON sidecar store backed by a local directory."""

    ref_prefix = "file"

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def write(self, *, record_id: str, payload: Mapping[str, Any]) -> StoredSidecar:
        """Write a payload as content-addressed JSON."""
        stored_payload = _payload_for_storage(payload)
        digest = _payload_digest(stored_payload)
        path = self._path_for_digest(digest)
        deduplicated = path.exists()
        if not deduplicated:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(stored_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return StoredSidecar(
            record_id=record_id,
            ref=_format_ref(self.ref_prefix, digest),
            deduplicated=deduplicated,
        )

    def read(self, ref: str) -> dict[str, Any]:
        """Read a JSON payload from the file store."""
        digest = _digest_from_ref(ref, self.ref_prefix)
        path = self._path_for_digest(digest)
        if not path.exists():
            raise SidecarStoreError(f"Sidecar payload does not exist: {ref}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SidecarStoreError(f"Invalid sidecar JSON for ref '{ref}': {exc}") from exc
        if not isinstance(data, dict):
            raise SidecarStoreError(f"Sidecar payload must be a JSON object: {ref}")
        return dict(data)

    def _path_for_digest(self, digest: str) -> Path:
        return self.root_dir / f"{digest}.json"


class SQLiteStore:
    """Content-addressed sidecar store backed by SQLite."""

    ref_prefix = "sqlite"

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def write(self, *, record_id: str, payload: Mapping[str, Any]) -> StoredSidecar:
        """Write a payload into SQLite using its content hash as the key."""
        stored_payload = _payload_for_storage(payload)
        digest = _payload_digest(stored_payload)
        payload_json = json.dumps(stored_payload, ensure_ascii=False, separators=(",", ":"))
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            _ensure_sqlite_schema(connection)
            row = connection.execute(
                "SELECT 1 FROM sidecars WHERE digest = ?",
                (digest,),
            ).fetchone()
            deduplicated = row is not None
            if not deduplicated:
                connection.execute(
                    "INSERT INTO sidecars (digest, payload_json) VALUES (?, ?)",
                    (digest, payload_json),
                )
        return StoredSidecar(
            record_id=record_id,
            ref=_format_ref(self.ref_prefix, digest),
            deduplicated=deduplicated,
        )

    def read(self, ref: str) -> dict[str, Any]:
        """Read a JSON payload from SQLite."""
        digest = _digest_from_ref(ref, self.ref_prefix)
        with sqlite3.connect(self.database_path) as connection:
            _ensure_sqlite_schema(connection)
            row = connection.execute(
                "SELECT payload_json FROM sidecars WHERE digest = ?",
                (digest,),
            ).fetchone()
        if row is None:
            raise SidecarStoreError(f"Sidecar payload does not exist: {ref}")
        try:
            data = json.loads(str(row[0]))
        except json.JSONDecodeError as exc:
            raise SidecarStoreError(f"Invalid sidecar JSON for ref '{ref}': {exc}") from exc
        if not isinstance(data, dict):
            raise SidecarStoreError(f"Sidecar payload must be a JSON object: {ref}")
        return dict(data)


def _ensure_sqlite_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sidecars (
            digest TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _payload_for_storage(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in payload.items() if key != "id"}


def _payload_digest(payload: Mapping[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(compact_json_bytes(dict(payload))).hexdigest()


def _format_ref(prefix: str, digest: str) -> str:
    return f"{prefix}:{digest}"


def _digest_from_ref(ref: str, expected_prefix: str) -> str:
    prefix = f"{expected_prefix}:"
    if not ref.startswith(prefix):
        raise SidecarStoreError(f"Expected {expected_prefix} sidecar ref, got: {ref}")
    digest = ref.removeprefix(prefix)
    if _DIGEST_RE.fullmatch(digest) is None:
        raise SidecarStoreError(f"Invalid sidecar content hash: {ref}")
    return digest
