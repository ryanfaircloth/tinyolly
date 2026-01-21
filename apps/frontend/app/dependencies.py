"""Dependency injection for FastAPI routes."""

import os

from app.storage import InMemoryStorage, PostgresStorage, StorageBackend

# Global storage instance
_storage: StorageBackend | None = None


async def get_storage() -> StorageBackend:
    """
    Get storage backend instance.

    Returns PostgresStorage if DATABASE_HOST is set, otherwise InMemoryStorage.
    """
    global _storage

    if _storage is None:
        # Determine storage backend from environment
        if os.getenv("DATABASE_HOST"):
            _storage = PostgresStorage()
        else:
            _storage = InMemoryStorage()

        # Connect to storage
        await _storage.connect()

    return _storage


async def close_storage():
    """Close storage backend connection."""
    global _storage
    if _storage is not None:
        await _storage.close()
        _storage = None
