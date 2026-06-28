"""Tools for detecting and fixing oversized vector database metadata."""

from vectormeta.hydrate import (
    hydrate_records_from_store,
    hydrate_results,
    migrate_sidecars_to_store,
)
from vectormeta.stores import FileStore, SQLiteStore
from vectormeta.upsert import safe_upsert
from vectormeta.validator import validate_records

__version__ = "0.2.0"

__all__ = [
    "FileStore",
    "SQLiteStore",
    "__version__",
    "hydrate_records_from_store",
    "hydrate_results",
    "migrate_sidecars_to_store",
    "safe_upsert",
    "validate_records",
]
