"""Custom exceptions for vectormeta."""

from __future__ import annotations


class VectorMetaError(Exception):
    """Base exception for expected vectormeta failures."""


class InvalidInputError(VectorMetaError):
    """Raised when input records or files are invalid."""


class UnsupportedTargetError(VectorMetaError):
    """Raised when a target is unknown or missing required configuration."""


class SidecarConflictError(VectorMetaError):
    """Raised when sidecar files would conflict or overwrite unexpectedly."""


class OutputExistsError(VectorMetaError):
    """Raised when an output file exists and overwrite was not enabled."""


class ValidationFailedError(VectorMetaError):
    """Raised when validation errors would make a safe upsert unsafe."""


class SidecarStoreError(VectorMetaError):
    """Raised when a sidecar store cannot write or read payloads."""
