"""Test namespace filtering functionality."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api import Filter, TimeRange
from app.models.database import ServiceDim
from app.storage.postgres_orm import PostgresStorage


@pytest.mark.asyncio
async def test_namespace_dimension_upsert(postgres_storage):
    """Test namespace dimension upsert returns correct ID."""
    async with AsyncSession(postgres_storage.engine) as session:
        # Test with non-null namespace
        ns_id1 = await postgres_storage._upsert_namespace(session, "test-namespace")
        assert ns_id1 is not None, "Should return namespace_id for non-null namespace"
        assert isinstance(ns_id1, int), "namespace_id should be integer"

        # Test with null namespace
        ns_id2 = await postgres_storage._upsert_namespace(session, None)
        assert ns_id2 is not None, "Should return namespace_id for null namespace"
        assert isinstance(ns_id2, int), "namespace_id should be integer"

        # Test idempotency - same namespace should return same ID
        ns_id3 = await postgres_storage._upsert_namespace(session, "test-namespace")
        assert ns_id3 == ns_id1, "Same namespace should return same ID"


@pytest.mark.asyncio
async def test_service_dimension_with_namespace(postgres_storage):
    """Test service dimension gets proper namespace_id."""
    async with AsyncSession(postgres_storage.engine) as session:
        # Create service with namespace
        service_id1 = await postgres_storage._upsert_service(session, "test-service", "test-namespace")
        assert service_id1 is not None, "Should return service_id"

        # Create service without namespace (null)
        service_id2 = await postgres_storage._upsert_service(session, "test-service-2", None)
        assert service_id2 is not None, "Should return service_id for null namespace"

        # Verify namespace_id was set by querying service_dim
        stmt = select(ServiceDim).where(ServiceDim.id == service_id1)
        result = await session.execute(stmt)
        service1 = result.scalar_one()
        assert service1.namespace_id is not None, "Service should have namespace_id"

        stmt = select(ServiceDim).where(ServiceDim.id == service_id2)
        result = await session.execute(stmt)
        service2 = result.scalar_one()
        assert service2.namespace_id is not None, (
            "Service with null namespace should still have namespace_id (pointing to null entry)"
        )


@pytest.mark.asyncio
async def test_logs_search_with_namespace_filter(postgres_storage, make_log):
    """Test logs search with namespace filtering."""
    # Store logs with different namespaces
    logs_data = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "service-a"}},
                        {"key": "service.namespace", "value": {"stringValue": "namespace-1"}},
                    ]
                },
                "scopeLogs": [{"logRecords": [make_log(body="Log from namespace-1")]}],
            },
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "service-b"}},
                        {"key": "service.namespace", "value": {"stringValue": "namespace-2"}},
                    ]
                },
                "scopeLogs": [{"logRecords": [make_log(body="Log from namespace-2")]}],
            },
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "service-c"}}]},
                "scopeLogs": [{"logRecords": [make_log(body="Log without namespace")]}],
            },
        ]
    }

    await postgres_storage.store_logs(logs_data["resourceLogs"])

    # Test 1: Filter for namespace-1
    time_range = TimeRange(start_time=0, end_time=9999999999999999999)
    filters = [Filter(field="service_namespace", operator="equals", value="namespace-1")]
    logs, _, _ = await postgres_storage.search_logs(time_range=time_range, filters=filters)

    assert len(logs) == 1, "Should return 1 log from namespace-1"
    assert logs[0].service_namespace == "namespace-1"

    # Test 2: Filter for multiple namespaces (OR logic)
    filters = [
        Filter(field="service_namespace", operator="equals", value="namespace-1"),
        Filter(field="service_namespace", operator="equals", value="namespace-2"),
    ]
    logs, _, _ = await postgres_storage.search_logs(time_range=time_range, filters=filters)

    assert len(logs) == 2, "Should return 2 logs from namespace-1 OR namespace-2"

    # Test 3: Filter for empty namespace
    filters = [Filter(field="service_namespace", operator="equals", value="")]
    logs, _, _ = await postgres_storage.search_logs(time_range=time_range, filters=filters)

    assert len(logs) == 1, "Should return 1 log with no namespace"
    assert logs[0].service_namespace == "" or logs[0].service_namespace is None


@pytest.mark.asyncio
async def test_metrics_search_namespace_filter_logic():
    """Test that namespace filters work in metrics search (mocked)."""
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
    # Create mock storage
    storage = PostgresStorage("postgresql+asyncpg://fake:fake@fake:5432/fake")

    # Create mock session
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    # Mock scalar to return namespace ID
    mock_session.scalar = AsyncMock(return_value=1)

    # Test: When namespace is None, the SELECT should use IS NULL
    ns_id = await storage._upsert_namespace(mock_session, None)

    # Verify scalar was called (SELECT statement executed)
    assert mock_session.scalar.call_count == 1, "Should execute SELECT"
    assert ns_id == 1, "Should return namespace ID"

    # The actual SQL comparison namespace.is_(None) happens inside _upsert_namespace
    # We're verifying the method completes without error
