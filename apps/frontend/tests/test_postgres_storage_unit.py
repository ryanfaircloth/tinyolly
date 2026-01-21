"""Minimal unit tests for PostgresStorage with mocked dependencies.

NOTE: Full testing of PostgresStorage requires integration tests with real database
(see test_postgres_storage.py) due to complex SQLAlchemy async session patterns and
Postgres-specific SQL features (JSONB, partitions, etc.).

These unit tests verify basic connectivity and structure, not SQL execution.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.api import TimeRange
from app.storage.postgres import PostgresStorage


@pytest.fixture
def storage():
    """Create PostgresStorage with mocked database."""
    storage_inst = PostgresStorage()

    # Mock the Database instance
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()

    # Replace the db instance
    storage_inst.db = mock_db

    return storage_inst


@pytest.mark.asyncio
async def test_connect(storage):
    """Test PostgresStorage connect calls database connect."""
    await storage.connect()
    storage.db.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_close(storage):
    """Test PostgresStorage close calls database close."""
    await storage.close()
    storage.db.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_check_healthy(storage):
    """Test health check with successful database query."""
    # Mock session and result
    mock_session = MagicMock()
    result = MagicMock()
    result.scalar = MagicMock(return_value=1)
    mock_session.execute = AsyncMock(return_value=result)

    # Mock session context manager
    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    health = await storage.health_check()

    assert health["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_unhealthy(storage):
    """Test health check with database error."""
    # Mock session that raises exception
    storage.db.session.return_value.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))

    health = await storage.health_check()

    assert health["status"] == "unhealthy"
    assert "Connection failed" in health["error"]


@pytest.mark.asyncio
async def test_store_metrics_stub(storage):
    """Test metrics storage stub returns 0 (not implemented)."""
    count = await storage.store_metrics([])
    assert count == 0


@pytest.mark.asyncio
async def test_search_metrics_stub(storage):
    """Test metrics search stub returns empty results (not implemented)."""
    time_range = TimeRange(start_time=1000000000, end_time=2000000000)
    metrics, has_more, cursor = await storage.search_metrics(time_range)

    assert metrics == []
    assert has_more is False
    assert cursor is None


# Additional tests for other methods should be integration tests with real database
# due to complex SQL queries, JSONB operations, and async session management.
# See test_postgres_storage.py for full integration test suite.
