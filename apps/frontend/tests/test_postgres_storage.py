"""Tests for PostgresStorage backend."""

import os
from datetime import UTC, datetime

import pytest

from app.models.api import TimeRange
from app.storage.postgres import PostgresStorage


@pytest.fixture
async def storage():
    """Create PostgresStorage instance for testing."""
    # Set test database environment variables if not set
    if "DATABASE_NAME" not in os.environ:
        os.environ["DATABASE_NAME"] = "ollyscale_test"

    storage = PostgresStorage()
    await storage.connect()
    yield storage
    await storage.close()


@pytest.mark.asyncio
async def test_health_check(storage):
    """Test database health check."""
    health = await storage.health_check()
    assert health["type"] == "postgresql"
    assert health["status"] == "healthy"
    assert "spans" in health
    assert "logs" in health


@pytest.mark.asyncio
async def test_store_and_retrieve_traces(storage):
    """Test storing and retrieving traces."""
    # Create sample OTLP ResourceSpans
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
                            "traceId": "AQIDBAUGBwgJCgsMDQ4PEA==",  # base64 encoded 16 bytes
                            "spanId": "AQIDBAUGBwg=",  # base64 encoded 8 bytes
                            "parentSpanId": "",
                            "name": "test-operation",
                            "kind": 2,  # SERVER
                            "startTimeUnixNano": "1700000000000000000",
                            "endTimeUnixNano": "1700000001000000000",
                            "attributes": [
                                {"key": "http.method", "value": {"stringValue": "GET"}},
                            ],
                            "status": {"code": 1},  # OK
                        }
                    ],
                }
            ],
        }
    ]

    # Store traces
    count = await storage.store_traces(resource_spans)
    assert count == 1

    # Retrieve trace by ID
    trace_id = "0102030405060708090a0b0c0d0e0f10"  # hex representation
    trace = await storage.get_trace_by_id(trace_id)
    assert trace is not None
    assert trace["traceId"] == trace_id
    assert len(trace["spans"]) == 1
    assert trace["spans"][0]["serviceName"] == "test-service"
    assert trace["spans"][0]["operationName"] == "test-operation"


@pytest.mark.asyncio
async def test_store_and_search_logs(storage):
    """Test storing and searching logs."""
    # Create sample OTLP ResourceLogs
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
                            "severityNumber": 9,  # INFO
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

    # Store logs
    count = await storage.store_logs(resource_logs)
    assert count == 1

    # Search logs
    now_ns = int(datetime.now(UTC).timestamp() * 1e9)
    time_range = TimeRange(start_ns=now_ns - int(1e9 * 3600), end_ns=now_ns + int(1e9 * 3600))  # ±1 hour

    logs, has_more, _cursor = await storage.search_logs(time_range)
    assert len(logs) >= 1
    assert has_more is False
    # Find our test log
    test_log = next((log for log in logs if log.body == "Test log message"), None)
    assert test_log is not None
    assert test_log.service_name == "log-service"


@pytest.mark.asyncio
async def test_get_services(storage):
    """Test getting service catalog with RED metrics."""
    # First store some traces
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

    # Get services
    now_ns = int(datetime.now(UTC).timestamp() * 1e9)
    time_range = TimeRange(start_ns=now_ns - int(1e9 * 3600 * 24), end_ns=now_ns + int(1e9 * 3600))

    services = await storage.get_services(time_range)
    assert len(services) >= 1

    # Find our test service
    test_service = next((s for s in services if s.name == "catalog-service"), None)
    assert test_service is not None
    assert test_service.request_count >= 1


@pytest.mark.asyncio
async def test_get_service_map(storage):
    """Test getting service dependency map."""
    # Store traces with parent-child relationships
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
                            "parentSpanId": "AQIDBAUGBwg=",  # Parent is frontend span
                            "name": "database-query",
                            "kind": 3,  # CLIENT
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

    # Get service map
    now_ns = int(datetime.now(UTC).timestamp() * 1e9)
    time_range = TimeRange(start_ns=now_ns - int(1e9 * 3600 * 24), end_ns=now_ns + int(1e9 * 3600))

    nodes, edges = await storage.get_service_map(time_range)
    assert len(nodes) >= 2
    assert len(edges) >= 1

    # Check for frontend -> backend edge
    edge = next((e for e in edges if e.source == "frontend" and e.target == "backend"), None)
    assert edge is not None
    assert edge.call_count >= 1


@pytest.mark.asyncio
async def test_batch_insert_performance(storage):
    """Test batch insert performance with multiple spans."""
    # Create 100 spans in one batch
    spans = []
    for i in range(100):
        span = {
            "traceId": f"{i:032x}",  # Different trace IDs
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

    # Store all spans in one batch
    count = await storage.store_traces(resource_spans)
    assert count == 100

    # Verify they're all stored
    services = await storage.get_services()
    batch_service = next((s for s in services if s.name == "batch-service"), None)
    assert batch_service is not None
    assert batch_service.request_count >= 100
