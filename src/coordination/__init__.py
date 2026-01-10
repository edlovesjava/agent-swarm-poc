"""Coordination layer - file locks and branch management."""

from .file_locks import FileCoordinator, LockResult

__all__ = [
    "FileCoordinator",
    "LockResult",
]
