"""Dependency injection for FastAPI routes."""

import os

from app.storage import PostgresStorage, StorageBackend

# Global storage instance
_storage: StorageBackend | None = None


async def get_storage() -> StorageBackend:
    """
    Get storage backend instance.

    Requires DATABASE_HOST environment variable to be set.

    Raises:
        RuntimeError: If DATABASE_HOST is not configured
    """
    global _storage

    if _storage is None:
        # Require DATABASE_HOST to be set
        if not os.getenv("DATABASE_HOST"):
            msg = "DATABASE_HOST environment variable must be set. PostgresStorage is required."
            raise RuntimeError(msg)

        _storage = PostgresStorage()

        # Connect to storage
        await _storage.connect()

    return _storage


async def close_storage():
    """Close storage backend connection."""
    global _storage
    if _storage is not None:
        await _storage.close()
        _storage = None
