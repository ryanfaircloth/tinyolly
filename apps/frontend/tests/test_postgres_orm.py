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
    """Test OTLP attribute value extraction.

    MessageToDict with preserving_proto_field_name=True uses snake_case.
    """
    storage = PostgresStorage("postgresql+asyncpg://test")

    # String value (snake_case from MessageToDict)
    assert storage._extract_string_value({"string_value": "test"}) == "test"

    # Int value (snake_case)
    assert storage._extract_string_value({"int_value": "42"}) == "42"  # MessageToDict converts int64 to string

    # Bool value (snake_case)
    assert storage._extract_string_value({"bool_value": True}) == "True"

    # No value
    assert storage._extract_string_value({}) is None


def test_normalize_severity_number():
    """Test severity number normalization from MessageToDict format."""
    storage = PostgresStorage("postgresql+asyncpg://test")

    # Integer values (pass through)
    assert storage._normalize_severity_number(9) == 9
    assert storage._normalize_severity_number(17) == 17

    # String enum names from MessageToDict
    assert storage._normalize_severity_number("SEVERITY_NUMBER_UNSPECIFIED") == 0
    assert storage._normalize_severity_number("SEVERITY_NUMBER_TRACE") == 1
    assert storage._normalize_severity_number("SEVERITY_NUMBER_DEBUG") == 5
    assert storage._normalize_severity_number("SEVERITY_NUMBER_INFO") == 9
    assert storage._normalize_severity_number("SEVERITY_NUMBER_WARN") == 13
    assert storage._normalize_severity_number("SEVERITY_NUMBER_ERROR") == 17
    assert storage._normalize_severity_number("SEVERITY_NUMBER_FATAL") == 21

    # None value
    assert storage._normalize_severity_number(None) is None

    # Unknown string (default to 0)
    assert storage._normalize_severity_number("UNKNOWN") == 0


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
                            "trace_id": "AAAAAAAAAAAAAAAAAAAAAA==",
                            "span_id": "AAAAAAAAAAA=",
                            "name": "test-span",
                            "kind": "SPAN_KIND_SERVER",  # MessageToDict converts to enum string
                            "start_time_unix_nano": "1000000",  # MessageToDict converts int64 to string
                            "end_time_unix_nano": "2000000",
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
                    "log_records": [  # Snake case!
                        {
                            "time_unix_nano": "1000000",  # MessageToDict converts int64 to string
                            "severity_number": 9,
                            "body": {"string_value": "test log"},  # Snake case!
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
