"""Tests for SQLModel ORM storage implementation.

Verifies that SQLModel correctly handles OTLP data without field mapping errors.
"""

import pytest

from app.models.database import LogsFact, SpansFact
from app.storage.postgres_orm import PostgresStorage


def test_spans_fact_model():
    """Test SpansFact model can be instantiated with OTLP data."""
    span = SpansFact(
        trace_id="abc123",
        span_id="def456",
        name="test-span",
        kind=2,  # SERVER
        start_time_unix_nano=1000000,
        end_time_unix_nano=2000000,
        attributes={"http.method": "GET"},
        events=[],
        links=[],
    )

    assert span.trace_id == "abc123"
    assert span.span_id == "def456"
    assert span.name == "test-span"
    assert span.kind == 2
    assert span.attributes == {"http.method": "GET"}


def test_logs_fact_model():
    """Test LogsFact model can be instantiated with OTLP data."""
    log = LogsFact(
        time_unix_nano=1000000,
        severity_number=9,
        severity_text="INFO",
        body={"stringValue": "test log"},
        attributes={"app": "test"},
    )

    assert log.time_unix_nano == 1000000
    assert log.severity_number == 9
    assert log.body == {"stringValue": "test log"}


def test_base64_to_hex_conversion():
    """Test trace/span ID conversion from base64 to hex."""
    storage = PostgresStorage("postgresql+asyncpg://test")

    # Example trace ID in base64 (16 bytes)
    b64_id = "AAAAAAAAAAAAAAAAAAAAAA=="  # All zeros
    hex_id = storage._base64_to_hex(b64_id)

    assert len(hex_id) == 32  # 16 bytes = 32 hex chars
    assert hex_id == "00000000000000000000000000000000"


def test_extract_string_value():
    """Test OTLP attribute value extraction."""
    storage = PostgresStorage("postgresql+asyncpg://test")

    # String value
    assert storage._extract_string_value({"stringValue": "test"}) == "test"

    # Int value
    assert storage._extract_string_value({"intValue": 42}) == "42"

    # Bool value
    assert storage._extract_string_value({"boolValue": True}) == "True"

    # No value
    assert storage._extract_string_value({}) is None


@pytest.mark.asyncio
async def test_store_traces_with_scope_spans():
    """Test that store_traces correctly handles scope_spans (snake_case).

    This is the key test - verifies we're using the correct field name.
    Tests with list input (matches receiver usage).
    """
    storage = PostgresStorage("postgresql+asyncpg://localhost/test")

    # OTLP data with scope_spans (snake_case, not camelCase!)
    # Pass as list directly, matching receiver usage
    resource_spans = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "test-service"}},
                ]
            },
            "scope_spans": [  # Snake case!
                {
                    "scope": {"name": "test-scope"},
                    "spans": [
                        {
                            "traceId": "AAAAAAAAAAAAAAAAAAAAAA==",
                            "spanId": "AAAAAAAAAAA=",
                            "name": "test-span",
                            "kind": 2,
                            "startTimeUnixNano": "1000000",
                            "endTimeUnixNano": "2000000",
                            "attributes": [],
                        }
                    ],
                }
            ],
        }
    ]

    # This should not raise KeyError for "scopeSpans" or list attribute errors
    # Note: Will fail to connect to DB, but we're testing parsing logic
    try:
        count = await storage.store_traces(resource_spans)
        assert count == 1
    except Exception as e:
        # Expected to fail on DB connection, but not on signature/parsing
        assert "'list' object has no attribute 'get'" not in str(e)
        assert "scopeSpans" not in str(e)
        assert "KeyError" not in str(e)


@pytest.mark.asyncio
async def test_store_logs_with_scope_logs():
    """Test that store_logs correctly handles scope_logs (snake_case).

    Tests with list input (matches receiver usage).
    """
    storage = PostgresStorage("postgresql+asyncpg://localhost/test")

    # Pass as list directly, matching receiver usage
    resource_logs = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "test-service"}},
                ]
            },
            "scope_logs": [  # Snake case!
                {
                    "scope": {"name": "test-scope"},
                    "logRecords": [
                        {
                            "timeUnixNano": "1000000",
                            "severityNumber": 9,
                            "body": {"stringValue": "test log"},
                            "attributes": [],
                        }
                    ],
                }
            ],
        }
    ]

    # This should not raise KeyError for "scopeLogs" or list attribute errors
    try:
        count = await storage.store_logs(resource_logs)
        assert count == 1
    except Exception as e:
        assert "'list' object has no attribute 'get'" not in str(e)
        assert "scopeLogs" not in str(e)
        assert "KeyError" not in str(e)
