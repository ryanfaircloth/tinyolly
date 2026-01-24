"""Tests for OTLP data parsing in storage layer."""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.storage.postgres import PostgresStorage


@pytest.fixture
def storage_with_detailed_mocks():
    """Create PostgresStorage with mocks that capture SQL calls."""
    storage_inst = PostgresStorage()

    # Mock the Database instance
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()
    storage_inst.db = mock_db

    return storage_inst


@pytest.mark.asyncio
async def test_store_traces_parses_multiple_resource_spans(storage_with_detailed_mocks):
    """Test that store_traces correctly iterates through ALL resource_spans, not just the last one."""
    storage = storage_with_detailed_mocks

    # Mock session
    mock_session = MagicMock()
    execute_calls = []

    async def track_execute(stmt, params=None):
        """Track all execute calls."""
        result = MagicMock()
        # For upsert queries, return incrementing IDs
        if params is None or isinstance(params, dict):
            result.scalar = MagicMock(return_value=len(execute_calls) + 1)
        execute_calls.append({"stmt": str(stmt), "params": params})
        return result

    mock_session.execute = AsyncMock(side_effect=track_execute)
    mock_session.commit = AsyncMock()

    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    # Create test data with TWO resource_spans, each with spans
    resource_spans = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "service-1"}},
                ]
            },
            "scope_spans": [
                {
                    "scope": {"name": "scope-1"},
                    "spans": [
                        {
                            "traceId": "AQIDBAUGBwgJCgsMDQ4PEA==",
                            "spanId": "AQIDBAUGBwg=",
                            "parentSpanId": "",
                            "name": "span-from-service-1",
                            "kind": 2,
                            "startTimeUnixNano": "1700000000000000000",
                            "endTimeUnixNano": "1700000001000000000",
                            "attributes": [],
                            "status": {"code": 1},
                        }
                    ],
                }
            ],
        },
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "service-2"}},
                ]
            },
            "scope_spans": [
                {
                    "scope": {"name": "scope-2"},
                    "spans": [
                        {
                            "traceId": "AQIDBAUGBwgJCgsMDQ4PEB==",
                            "spanId": "AQIDBAUGBwk=",
                            "parentSpanId": "",
                            "name": "span-from-service-2",
                            "kind": 2,
                            "startTimeUnixNano": "1700000002000000000",
                            "endTimeUnixNano": "1700000003000000000",
                            "attributes": [],
                            "status": {"code": 1},
                        }
                    ],
                }
            ],
        },
    ]

    count = await storage.store_traces(resource_spans)

    # CRITICAL: We should have stored 2 spans (one from each resource_span)
    assert count == 2, f"Expected 2 spans stored, got {count}"

    # Verify the INSERT statement was called with 2 span records
    insert_calls = [c for c in execute_calls if "INSERT INTO spans_fact" in c["stmt"]]
    assert len(insert_calls) == 1, "Should have one batch insert call"

    # The batch insert should contain both spans
    insert_params = insert_calls[0]["params"]
    assert isinstance(insert_params, list), "Insert params should be a list of records"
    assert len(insert_params) == 2, f"Should insert 2 span records, got {len(insert_params)}"

    # Verify both span names are present
    span_names = [p["name"] for p in insert_params]
    assert "span-from-service-1" in span_names, "Missing span from first resource_span"
    assert "span-from-service-2" in span_names, "Missing span from second resource_span"


@pytest.mark.asyncio
async def test_store_traces_handles_empty_scope_spans(storage_with_detailed_mocks):
    """Test that store_traces handles resource_spans with empty scope_spans."""
    storage = storage_with_detailed_mocks

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=1)))
    mock_session.commit = AsyncMock()

    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    resource_spans = [
        {
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "service-1"}}]},
            "scope_spans": [],  # Empty
        }
    ]

    count = await storage.store_traces(resource_spans)
    assert count == 0, "Should return 0 for empty scope_spans"


@pytest.mark.asyncio
async def test_store_logs_parses_multiple_resource_logs(storage_with_detailed_mocks):
    """Test that store_logs correctly iterates through ALL resource_logs."""
    storage = storage_with_detailed_mocks

    mock_session = MagicMock()
    execute_calls = []

    async def track_execute(stmt, params=None):
        result = MagicMock()
        if params is None or isinstance(params, dict):
            result.scalar = MagicMock(return_value=len(execute_calls) + 1)
        execute_calls.append({"stmt": str(stmt), "params": params})
        return result

    mock_session.execute = AsyncMock(side_effect=track_execute)
    mock_session.commit = AsyncMock()

    storage.db.session = MagicMock()
    storage.db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    storage.db.session.return_value.__aexit__ = AsyncMock(return_value=None)

    resource_logs = [
        {
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "log-service-1"}}]},
            "scope_logs": [
                {
                    "scope": {"name": "logger-1"},
                    "logRecords": [
                        {
                            "timeUnixNano": "1700000000000000000",
                            "observedTimeUnixNano": "1700000000000000000",
                            "severityNumber": 9,
                            "severityText": "INFO",
                            "body": {"stringValue": "Log from service 1"},
                            "attributes": [],
                        }
                    ],
                }
            ],
        },
        {
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "log-service-2"}}]},
            "scope_logs": [
                {
                    "scope": {"name": "logger-2"},
                    "logRecords": [
                        {
                            "timeUnixNano": "1700000001000000000",
                            "observedTimeUnixNano": "1700000001000000000",
                            "severityNumber": 13,
                            "severityText": "ERROR",
                            "body": {"stringValue": "Log from service 2"},
                            "attributes": [],
                        }
                    ],
                }
            ],
        },
    ]

    count = await storage.store_logs(resource_logs)

    # Should store 2 logs (one from each resource_log)
    assert count == 2, f"Expected 2 logs stored, got {count}"

    # Verify INSERT was called with both log records
    insert_calls = [c for c in execute_calls if "INSERT INTO logs_fact" in c["stmt"]]
    assert len(insert_calls) == 1
    insert_params = insert_calls[0]["params"]
    assert len(insert_params) == 2, f"Should insert 2 log records, got {len(insert_params)}"
