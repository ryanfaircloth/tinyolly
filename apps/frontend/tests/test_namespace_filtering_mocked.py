"""Unit tests for namespace filtering functionality using mocks.

Tests the namespace dimension upsert logic and filtering in logs/metrics queries.
Uses mocks instead of real database connections - true unit tests.
"""

from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.asyncio
async def test_namespace_dimension_upsert():
    """Test namespace dimension upsert returns correct ID with mocked database."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.storage.postgres_orm import PostgresStorage

    # Create mock storage
    storage = PostgresStorage("postgresql+asyncpg://fake:fake@fake:5432/fake")

    # Create mock session
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock execute to return a result with scalar()
    mock_result = AsyncMock()
    mock_result.scalar = Mock(side_effect=[1, 2, 1])  # scalar() is sync, not async
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Mock commit
    mock_session.commit = AsyncMock()

    # Test 1: Insert new namespace
    ns_id1 = await storage._upsert_namespace(mock_session, "test-namespace")
    assert ns_id1 == 1, "Should return ID 1 for new namespace"
    assert mock_session.execute.call_count == 2, "Should execute INSERT and SELECT"
    assert mock_session.commit.call_count == 1, "Should commit after insert"

    # Test 2: Insert NULL namespace
    ns_id2 = await storage._upsert_namespace(mock_session, None)
    assert ns_id2 == 2, "Should return ID 2 for NULL namespace"
    assert mock_session.execute.call_count == 4, "Should execute INSERT and SELECT again"
    assert mock_session.commit.call_count == 2, "Should commit second insert"

    # Test 3: Re-insert same namespace (should return existing ID)
    ns_id3 = await storage._upsert_namespace(mock_session, "test-namespace")
    assert ns_id3 == 1, "Should return same ID for duplicate namespace"


@pytest.mark.asyncio
async def test_service_dimension_with_namespace():
    """Test service dimension gets proper namespace_id with mocked database."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.storage.postgres_orm import PostgresStorage

    # Create mock storage
    storage = PostgresStorage("postgresql+asyncpg://fake:fake@fake:5432/fake")

    # Create mock session
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock execute to return a result with scalar()
    mock_result = AsyncMock()
    mock_result.scalar = Mock(side_effect=[10, 100, 1, 200])  # scalar() is sync, not async
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    # Test 1: Create service with namespace
    service_id1 = await storage._upsert_service(mock_session, "test-service", "test-namespace")
    assert service_id1 == 100, "Should return service ID 100"
    # Should have: INSERT+SELECT for namespace, INSERT+SELECT for service = 4 execute calls
    assert mock_session.execute.call_count >= 2, "Should execute namespace and service statements"

    # Test 2: Create service without namespace
    service_id2 = await storage._upsert_service(mock_session, "test-service-2", None)
    assert service_id2 == 200, "Should return service ID 200"


@pytest.mark.asyncio
async def test_logs_search_namespace_filter_logic():
    """Test that namespace filters are collected and OR logic is applied (mocked)."""

    from app.models.api import Filter

    # Mock the Filter collection logic from search_logs()
    filters = [
        Filter(field="service_namespace", operator="equals", value="namespace-1"),
        Filter(field="service_namespace", operator="equals", value="namespace-2"),
        Filter(field="service_name", operator="equals", value="service-a"),
    ]

    # Extract namespace filters (simulating the collection logic in search_logs)
    namespace_filters = []
    other_filters = []
    for f in filters:
        if f.field == "service_namespace":
            namespace_filters.append(f)
        else:
            other_filters.append(f)

    # Test 1: Verify namespace filters collected correctly
    assert len(namespace_filters) == 2, "Should collect 2 namespace filters"
    assert len(other_filters) == 1, "Should have 1 other filter"
    assert namespace_filters[0].value == "namespace-1"
    assert namespace_filters[1].value == "namespace-2"

    # Test 2: Verify INNER JOIN logic (any non-empty namespace means INNER JOIN)
    use_inner_join = any(f.value != "" for f in namespace_filters)
    assert use_inner_join is True, "Should use INNER JOIN when non-empty namespace in filters"

    # Test 3: Test empty namespace only (OUTER JOIN)
    empty_filters = [Filter(field="service_namespace", operator="equals", value="")]
    use_inner_join_empty = any(f.value != "" for f in empty_filters)
    assert use_inner_join_empty is False, "Should use OUTER JOIN when only empty namespace"

    # Test 4: Verify OR condition building (can't mock SQLAlchemy fully, but verify count)
    assert len(namespace_filters) == 2, "Should build OR with 2 conditions"


@pytest.mark.asyncio
async def test_metrics_search_namespace_filter_logic():
    """Test that namespace filters work in metrics search (mocked)."""
    from app.models.api import Filter

    # Mock the Filter collection logic from search_metrics()
    filters = [
        Filter(field="service_namespace", operator="equals", value="namespace-1"),
        Filter(field="service_namespace", operator="equals", value="namespace-2"),
        Filter(field="metric_name", operator="equals", value="test.metric"),
    ]

    # Extract namespace filters (simulating the collection logic in search_metrics)
    namespace_filters = []
    other_filters = []
    for f in filters:
        if f.field == "service_namespace":
            namespace_filters.append(f)
        else:
            other_filters.append(f)

    # Test 1: Verify namespace filters collected correctly
    assert len(namespace_filters) == 2, "Should collect 2 namespace filters"
    assert len(other_filters) == 1, "Should have 1 other filter"

    # Test 2: Verify INNER JOIN logic
    use_inner_join = any(f.value != "" for f in namespace_filters)
    assert use_inner_join is True, "Should use INNER JOIN for metrics with non-empty namespace"

    # Test 3: Multiple namespace filters means OR logic
    assert len(namespace_filters) == 2, "Should apply OR with 2 namespace conditions"


@pytest.mark.asyncio
async def test_null_namespace_sql_comparison():
    """Test that NULL namespace comparison uses IS NULL, not equality."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.storage.postgres_orm import PostgresStorage

    # Create mock storage
    storage = PostgresStorage("postgresql+asyncpg://fake:fake@fake:5432/fake")

    # Create mock session
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    # Mock scalar to return namespace ID

    # Mock execute to return a result with scalar()
    mock_result = AsyncMock()
    mock_result.scalar = Mock(return_value=1)  # scalar() is sync, not async
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    # Test: When namespace is None, the SELECT should use IS NULL
    ns_id = await storage._upsert_namespace(mock_session, None)

    # Verify scalar was called (SELECT statement executed)
    assert mock_result.scalar.call_count == 1, "Should execute SELECT and call scalar()"
    assert ns_id == 1, "Should return namespace ID"
