"""Tests for storage interface."""

import pytest

from app.models.api import TimeRange
from app.storage.interface import InMemoryStorage


@pytest.mark.asyncio
async def test_in_memory_storage_connect():
    """Test InMemoryStorage connect."""
    storage = InMemoryStorage()
    await storage.connect()
    # Should not raise


@pytest.mark.asyncio
async def test_in_memory_storage_health_check():
    """Test InMemoryStorage health check."""
    storage = InMemoryStorage()
    health = await storage.health_check()
    assert health["type"] == "in-memory"
    assert "traces" in health
    assert "logs" in health
    assert "metrics" in health


@pytest.mark.asyncio
async def test_store_traces():
    """Test storing traces."""
    storage = InMemoryStorage()
    resource_spans = [
        {
            "resource": {"attributes": [{"key": "service.name", "value": "test"}]},
            "scope_spans": [
                {
                    "scope": {"name": "test-tracer"},
                    "spans": [
                        {
                            "trace_id": "0" * 32,
                            "span_id": "0" * 16,
                            "name": "test-span",
                            "kind": 1,
                            "start_time_unix_nano": 1000000000,
                            "end_time_unix_nano": 2000000000,
                        }
                    ],
                }
            ],
        }
    ]

    count = await storage.store_traces(resource_spans)
    assert count == 1
    assert len(storage.traces) == 1


@pytest.mark.asyncio
async def test_search_traces():
    """Test searching traces."""
    storage = InMemoryStorage()

    # Store a trace first
    await storage.store_traces(
        [
            {
                "resource": {},
                "scope_spans": [{"scope": {}, "spans": [{"trace_id": "abc123", "name": "test"}]}],
            }
        ]
    )

    # Search
    time_range = TimeRange(start_time=0, end_time=9999999999999999)
    traces, has_more, cursor = await storage.search_traces(time_range)

    assert len(traces) == 1
    assert has_more is False
    assert cursor is None


@pytest.mark.asyncio
async def test_get_trace_by_id():
    """Test getting trace by ID."""
    storage = InMemoryStorage()
    trace_id = "0" * 32

    # Store a trace
    await storage.store_traces(
        [
            {
                "resource": {},
                "scope_spans": [{"scope": {}, "spans": [{"trace_id": trace_id, "name": "test"}]}],
            }
        ]
    )

    # Retrieve by ID
    trace = await storage.get_trace_by_id(trace_id)
    assert trace is not None
    assert trace["trace_id"] == trace_id
    assert len(trace["spans"]) == 1


@pytest.mark.asyncio
async def test_store_logs():
    """Test storing logs."""
    storage = InMemoryStorage()
    resource_logs = [
        {
            "resource": {},
            "scope_logs": [
                {
                    "scope": {},
                    "log_records": [
                        {"time_unix_nano": 1000000000, "body": "test log 1"},
                        {"time_unix_nano": 2000000000, "body": "test log 2"},
                    ],
                }
            ],
        }
    ]

    count = await storage.store_logs(resource_logs)
    assert count == 2


@pytest.mark.asyncio
async def test_store_metrics():
    """Test storing metrics."""
    storage = InMemoryStorage()
    resource_metrics = [
        {
            "resource": {},
            "scope_metrics": [
                {
                    "scope": {},
                    "metrics": [
                        {"name": "metric1", "data_points": []},
                        {"name": "metric2", "data_points": []},
                    ],
                }
            ],
        }
    ]

    count = await storage.store_metrics(resource_metrics)
    assert count == 2


@pytest.mark.asyncio
async def test_get_services():
    """Test getting services."""
    storage = InMemoryStorage()
    services = await storage.get_services()
    assert isinstance(services, list)
    assert len(services) == 0  # Empty initially


@pytest.mark.asyncio
async def test_get_service_map():
    """Test getting service map."""
    storage = InMemoryStorage()
    time_range = TimeRange(start_time=0, end_time=9999999999999999)
    nodes, edges = await storage.get_service_map(time_range)
    assert isinstance(nodes, list)
    assert isinstance(edges, list)
    assert len(nodes) == 0  # Empty initially
    assert len(edges) == 0
