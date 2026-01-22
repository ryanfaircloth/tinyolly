"""Tests for PostgresStorage backend with mocked database."""

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
async def test_health_check(storage):
    """Test database health check returns healthy status."""
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
    mock_session.execute.assert_awaited()


@pytest.mark.asyncio
async def test_store_and_retrieve_traces(storage):
    """Test storing and retrieving traces."""
    # Mock session with upsert and insert operations
    mock_session = MagicMock()

    # Mock upsert results (service_id, operation_id, resource_id)
    upsert_result = MagicMock()
    upsert_result.scalar = MagicMock(side_effect=[1, 2, 3])
    mock_session.execute = AsyncMock(return_value=upsert_result)
    mock_session.commit = AsyncMock()

    # Mock session context manager
    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    resource_spans = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "test-service"}},
                ]
            },
            "scopeSpans": [
                {
                    "scope": {"name": "test-scope"},
                    "spans": [
                        {
                            "traceId": "AQIDBAUGBwgJCgsMDQ4PEA==",
                            "spanId": "AQIDBAUGBwg=",
                            "parentSpanId": "",
                            "name": "test-operation",
                            "kind": 2,
                            "startTimeUnixNano": "1700000000000000000",
                            "endTimeUnixNano": "1700000001000000000",
                            "attributes": [
                                {"key": "http.method", "value": {"stringValue": "GET"}},
                            ],
                            "status": {"code": 1},
                        }
                    ],
                }
            ],
        }
    ]

    count = await storage.store_traces(resource_spans)

    assert count == 1

    # Test retrieve - mock get_trace_by_id
    trace_result = MagicMock()
    trace_result.fetchall = MagicMock(
        return_value=[
            (
                b"\x01\x02\x03\x04\x05\x06\x07\x08",  # span_id (row[0])
                None,  # parent_span_id (row[1])
                1700000000000000000,  # start_time_ns (row[2])
                1700000001000000000,  # end_time_ns (row[3])
                1000000000,  # duration_ns (row[4])
                1,  # status_code (row[5])
                2,  # kind (row[6])
                "{}",  # attributes JSON string (row[7])
                "[]",  # events JSON string (row[8])
                "[]",  # links JSON string (row[9])
                "test-service",  # service_name (row[10])
                "test-operation",  # operation_name (row[11])
                {},  # resource (row[12])
            )
        ]
    )
    mock_session.execute = AsyncMock(return_value=trace_result)

    trace = await storage.get_trace_by_id("0102030405060708090a0b0c0d0e0f10")

    assert trace is not None
    assert trace["traceId"] == "0102030405060708090a0b0c0d0e0f10"


@pytest.mark.asyncio
async def test_store_and_search_logs(storage):
    """Test storing and searching logs."""
    # Mock session for store
    mock_session = MagicMock()
    upsert_result = MagicMock()
    upsert_result.scalar = MagicMock(side_effect=[1, 2])  # service_id, resource_id
    mock_session.execute = AsyncMock(return_value=upsert_result)
    mock_session.commit = AsyncMock()

    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    resource_logs = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "log-service"}},
                ]
            },
            "scopeLogs": [
                {
                    "scope": {"name": "test-logger"},
                    "logRecords": [
                        {
                            "timeUnixNano": "1700000000000000000",
                            "observedTimeUnixNano": "1700000000000000000",
                            "severityNumber": 9,
                            "severityText": "INFO",
                            "body": {"stringValue": "Test log message"},
                            "attributes": [
                                {"key": "log.source", "value": {"stringValue": "test"}},
                            ],
                        }
                    ],
                }
            ],
        }
    ]

    count = await storage.store_logs(resource_logs)

    assert count == 1

    # Test search
    search_result = MagicMock()
    search_result.fetchall = MagicMock(return_value=[])
    mock_session.execute = AsyncMock(return_value=search_result)

    time_range = TimeRange(start_time=1000000000, end_time=2000000000)
    logs, has_more, _cursor = await storage.search_logs(time_range)

    assert isinstance(logs, list)
    assert has_more is False


@pytest.mark.asyncio
async def test_get_services(storage):
    """Test getting service catalog with RED metrics."""
    # Mock session for store
    mock_session = MagicMock()
    upsert_result = MagicMock()
    upsert_result.scalar = MagicMock(side_effect=[1, 2, 3])
    mock_session.execute = AsyncMock(return_value=upsert_result)
    mock_session.commit = AsyncMock()

    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    resource_spans = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "catalog-service"}},
                ]
            },
            "scopeSpans": [
                {
                    "scope": {"name": "test-scope"},
                    "spans": [
                        {
                            "traceId": "AQIDBAUGBwgJCgsMDQ4PEA==",
                            "spanId": "AQIDBAUGBwg=",
                            "name": "catalog-operation",
                            "kind": 2,
                            "startTimeUnixNano": "1700000000000000000",
                            "endTimeUnixNano": "1700000001000000000",
                            "status": {"code": 1},
                        }
                    ],
                }
            ],
        }
    ]

    await storage.store_traces(resource_spans)

    # Mock get_services result
    services_result = MagicMock()
    services_result.fetchall = MagicMock(
        return_value=[
            (
                "catalog-service",  # service_name
                10,  # request_count
                1,  # error_count
                500000000,  # p50_duration_ns
                1000000000,  # p95_duration_ns
                1700000000000000000,  # first_seen_ns
                1700000010000000000,  # last_seen_ns
            )
        ]
    )
    mock_session.execute = AsyncMock(return_value=services_result)

    time_range = TimeRange(start_time=1000000000, end_time=2000000000)
    services = await storage.get_services(time_range)

    assert len(services) >= 1
    assert services[0].name == "catalog-service"
    assert services[0].request_count == 10


@pytest.mark.asyncio
async def test_get_service_map(storage):
    """Test getting service dependency map."""
    # Mock session for store
    mock_session = MagicMock()
    upsert_result = MagicMock()
    upsert_result.scalar = MagicMock(side_effect=[1, 2, 3, 4, 5, 6])
    mock_session.execute = AsyncMock(return_value=upsert_result)
    mock_session.commit = AsyncMock()

    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    resource_spans = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "frontend"}},
                ]
            },
            "scopeSpans": [
                {
                    "scope": {"name": "test-scope"},
                    "spans": [
                        {
                            "traceId": "AQIDBAUGBwgJCgsMDQ4PEA==",
                            "spanId": "AQIDBAUGBwg=",
                            "name": "http-request",
                            "kind": 2,
                            "startTimeUnixNano": "1700000000000000000",
                            "endTimeUnixNano": "1700000001000000000",
                            "status": {"code": 1},
                        }
                    ],
                }
            ],
        },
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "backend"}},
                ]
            },
            "scopeSpans": [
                {
                    "scope": {"name": "test-scope"},
                    "spans": [
                        {
                            "traceId": "AQIDBAUGBwgJCgsMDQ4PEA==",
                            "spanId": "CQoLDA0ODxA=",
                            "parentSpanId": "AQIDBAUGBwg=",
                            "name": "database-query",
                            "kind": 3,
                            "startTimeUnixNano": "1700000000100000000",
                            "endTimeUnixNano": "1700000000900000000",
                            "status": {"code": 1},
                        }
                    ],
                }
            ],
        },
    ]

    await storage.store_traces(resource_spans)

    # Mock get_service_map result
    map_result = MagicMock()
    map_result.fetchall = MagicMock(
        return_value=[
            ("frontend", "backend", 5),  # source, target, call_count
        ]
    )
    mock_session.execute = AsyncMock(return_value=map_result)

    time_range = TimeRange(start_time=1000000000, end_time=2000000000)
    nodes, edges = await storage.get_service_map(time_range)

    assert len(nodes) == 2
    assert len(edges) == 1
    assert edges[0].source == "frontend"
    assert edges[0].target == "backend"
    assert edges[0].call_count == 5


@pytest.mark.asyncio
async def test_batch_insert_performance(storage):
    """Test batch insert performance with multiple spans."""
    # Mock session
    mock_session = MagicMock()
    upsert_result = MagicMock()
    # Create side_effect for 100 spans * 3 upserts each = 300 calls
    upsert_result.scalar = MagicMock(side_effect=[i % 3 + 1 for i in range(300)])
    mock_session.execute = AsyncMock(return_value=upsert_result)
    mock_session.commit = AsyncMock()

    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    # Create 100 spans
    spans = []
    for i in range(100):
        span = {
            "traceId": f"{i:032x}",
            "spanId": f"{i:016x}",
            "name": f"batch-operation-{i}",
            "kind": 2,
            "startTimeUnixNano": f"{1700000000000000000 + i * 1000000}",
            "endTimeUnixNano": f"{1700000001000000000 + i * 1000000}",
            "status": {"code": 1},
        }
        spans.append(span)

    resource_spans = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "batch-service"}},
                ]
            },
            "scopeSpans": [
                {
                    "scope": {"name": "test-scope"},
                    "spans": spans,
                }
            ],
        }
    ]

    count = await storage.store_traces(resource_spans)

    assert count == 100
