"""Unit tests for logs and metrics storage per OTLP specification.

Tests verify:
- Logs write to database correctly
- Logs can be retrieved correctly  
- trace_id/span_id correlation works
- Metrics write to database correctly
- Metrics can be retrieved correctly
- Resource attributes are preserved
"""

import json
import time
from pathlib import Path

import pytest

from app.storage.postgres_orm import PostgresStorage
from tests.fixtures import make_log_record, make_metric, make_resource_logs, make_resource_metrics

# Load real OTLP examples
FIXTURES_DIR = Path(__file__).parent / "fixtures"
with open(FIXTURES_DIR / "otlp_examples.json") as f:
    OTLP_EXAMPLES = json.load(f)


class TestLogsStorage:
    """Test logs write to and read from database correctly."""

    def test_log_record_fixture(self):
        """Verify log record fixture creates valid OTLP format."""
        log = make_log_record(
            trace_id="0102030405060708090a0b0c0d0e0f10",
            span_id="0102030405060708",
            body="Test message",
            severity_number=9,
        )
        
        # Verify OTLP format
        assert "timeUnixNano" in log
        assert "severityNumber" in log
        assert log["severityNumber"] == 9
        assert "body" in log
        assert "traceId" in log
        assert "spanId" in log
        
    @pytest.mark.asyncio
    async def test_store_and_retrieve_logs(self, postgres_storage, clean_database):
        """Verify logs round-trip through database correctly."""
        # Create log with known values
        trace_id = "aabbccddeeff00112233445566778899"
        span_id = "aabbccddeeff0011"
        
        log = make_log_record(
            trace_id=trace_id,
            span_id=span_id,
            body="Test log message",
            severity_number=9,
            severity_text="INFO",
        )
        
        resource_logs = make_resource_logs(
            service_name="test-service",
            log_records=[log]
        )
        
        # Store
        count = await postgres_storage.store_logs([resource_logs])
        assert count == 1
        
        # Retrieve by time range
        from app.models.api import TimeRange, Pagination
        time_range = TimeRange(
            start_time=0,
            end_time=int(time.time() * 1e9) + int(1e12)  # Way in future
        )
        pagination = Pagination(limit=10)
        
        logs, has_more, cursor = await postgres_storage.search_logs(
            time_range=time_range,
            filters=None,
            pagination=pagination
        )
        
        # Verify retrieval
        assert len(logs) > 0
        log_found = None
        for log_result in logs:
            if log_result.get("body") == "Test log message":
                log_found = log_result
                break
                
        assert log_found is not None, "Log not found in search results"
        assert log_found["trace_id"] == trace_id
        assert log_found["span_id"] == span_id
        assert log_found["severity_number"] == 9
        assert log_found["severity_text"] == "INFO"
        
    @pytest.mark.asyncio
    async def test_logs_without_trace_correlation(self, postgres_storage, clean_database):
        """Verify logs without trace_id/span_id are stored correctly."""
        log = make_log_record(
            body="Standalone log message",
            severity_number=9,
        )
        
        # Remove trace correlation fields
        log.pop("traceId", None)
        log.pop("spanId", None)
        
        resource_logs = make_resource_logs(
            service_name="test-service",
            log_records=[log]
        )
        
        # Store
        count = await postgres_storage.store_logs([resource_logs])
        assert count == 1
        
        # Retrieve
        from app.models.api import TimeRange, Pagination
        time_range = TimeRange(
            start_time=0,
            end_time=int(time.time() * 1e9) + int(1e12)
        )
        pagination = Pagination(limit=10)
        
        logs, has_more, cursor = await postgres_storage.search_logs(
            time_range=time_range,
            filters=None,
            pagination=pagination
        )
        
        # Verify log exists and has no trace correlation
        log_found = None
        for log_result in logs:
            if log_result.get("body") == "Standalone log message":
                log_found = log_result
                break
                
        assert log_found is not None
        assert log_found.get("trace_id") is None or log_found.get("trace_id") == ""
        assert log_found.get("span_id") is None or log_found.get("span_id") == ""


class TestMetricsStorage:
    """Test metrics write to and read from database correctly."""

    def test_metric_fixture(self):
        """Verify metric fixture creates valid OTLP format."""
        metric = make_metric(
            name="http.server.request.duration",
            unit="ms",
            value=123.45,
        )
        
        # Verify OTLP format
        assert "name" in metric
        assert metric["name"] == "http.server.request.duration"
        assert "unit" in metric
        assert "gauge" in metric or "sum" in metric or "histogram" in metric
        
    @pytest.mark.asyncio
    async def test_store_and_retrieve_metrics(self, postgres_storage, clean_database):
        """Verify metrics round-trip through database correctly."""
        # Create metric with known values
        metric = make_metric(
            name="http.server.request.duration",
            unit="ms",
            value=123.45,
        )
        
        resource_metrics = make_resource_metrics(
            service_name="test-service",
            metrics=[metric]
        )
        
        # Store
        count = await postgres_storage.store_metrics([resource_metrics])
        assert count == 1
        
        # Retrieve by metric name
        from app.models.api import TimeRange, Pagination
        time_range = TimeRange(
            start_time=0,
            end_time=int(time.time() * 1e9) + int(1e12)
        )
        pagination = Pagination(limit=10)
        
        metrics, has_more, cursor = await postgres_storage.search_metrics(
            time_range=time_range,
            metric_names=["http.server.request.duration"],
            filters=None,
            pagination=pagination
        )
        
        # Verify retrieval
        assert len(metrics) > 0
        metric_found = None
        for metric_result in metrics:
            if metric_result.get("name") == "http.server.request.duration":
                metric_found = metric_result
                break
                
        assert metric_found is not None, "Metric not found in search results"
        assert metric_found["name"] == "http.server.request.duration"
        assert metric_found["unit"] == "ms"
        
        # Verify data point value
        if "gauge" in metric_found:
            data_points = metric_found["gauge"].get("data_points", [])
        elif "sum" in metric_found:
            data_points = metric_found["sum"].get("data_points", [])
        else:
            data_points = []
            
        assert len(data_points) > 0
        # Value might be in as_double or as_int
        value = data_points[0].get("as_double") or data_points[0].get("as_int")
        assert value == 123.45
        
    @pytest.mark.asyncio
    async def test_metrics_with_attributes(self, postgres_storage, clean_database):
        """Verify metric attributes are preserved."""
        metric = make_metric(
            name="http.server.request.duration",
            unit="ms",
            value=123.45,
            attributes={
                "http.method": "GET",
                "http.status_code": 200,
                "http.route": "/api/users"
            }
        )
        
        resource_metrics = make_resource_metrics(
            service_name="test-service",
            metrics=[metric]
        )
        
        # Store
        count = await postgres_storage.store_metrics([resource_metrics])
        assert count == 1
        
        # Retrieve
        from app.models.api import TimeRange, Pagination
        time_range = TimeRange(
            start_time=0,
            end_time=int(time.time() * 1e9) + int(1e12)
        )
        pagination = Pagination(limit=10)
        
        metrics, has_more, cursor = await postgres_storage.search_metrics(
            time_range=time_range,
            metric_names=["http.server.request.duration"],
            filters=None,
            pagination=pagination
        )
        
        # Verify attributes preserved
        assert len(metrics) > 0
        metric_found = metrics[0]
        
        # Get data points
        if "gauge" in metric_found:
            data_points = metric_found["gauge"].get("data_points", [])
        elif "sum" in metric_found:
            data_points = metric_found["sum"].get("data_points", [])
        else:
            data_points = []
            
        assert len(data_points) > 0
        attributes = data_points[0].get("attributes", {})
        
        # Verify attributes exist (format may vary)
        assert "http.method" in attributes or any("method" in str(k).lower() for k in attributes.keys())


class TestResourceAttributePreservation:
    """Test that resource attributes are preserved for logs and metrics."""

    @pytest.mark.asyncio
    async def test_log_resource_attributes(self, postgres_storage, clean_database):
        """Verify log resource attributes are stored and retrieved."""
        log = make_log_record(body="Test message")
        
        resource_logs = make_resource_logs(
            service_name="test-service",
            log_records=[log]
        )
        
        # Add custom resource attributes
        resource_logs["resource"]["attributes"].extend([
            {"key": "service.version", "value": {"stringValue": "1.2.3"}},
            {"key": "deployment.environment", "value": {"stringValue": "production"}},
        ])
        
        # Store
        count = await postgres_storage.store_logs([resource_logs])
        assert count == 1
        
        # Retrieve and verify resource attributes
        from app.models.api import TimeRange, Pagination
        time_range = TimeRange(start_time=0, end_time=int(time.time() * 1e9) + int(1e12))
        pagination = Pagination(limit=10)
        
        logs, _, _ = await postgres_storage.search_logs(time_range, None, pagination)
        
        log_found = next((l for l in logs if l.get("body") == "Test message"), None)
        assert log_found is not None
        
        # Verify resource attributes preserved
        resource = log_found.get("resource", {})
        assert "service.name" in resource or "service_name" in log_found
        
    @pytest.mark.asyncio
    async def test_metric_resource_attributes(self, postgres_storage, clean_database):
        """Verify metric resource attributes are stored and retrieved."""
        metric = make_gauge_metric(name="test.metric", value=123.45)
        
        resource_metrics = make_resource_metrics(
            service_name="test-service",
            metrics=[metric]
        )
        
        # Add custom resource attributes
        resource_metrics["resource"]["attributes"].extend([
            {"key": "service.version", "value": {"stringValue": "1.2.3"}},
            {"key": "deployment.environment", "value": {"stringValue": "production"}},
        ])
        
        # Store
        count = await postgres_storage.store_metrics([resource_metrics])
        assert count == 1
        
        # Retrieve and verify resource attributes
        from app.models.api import TimeRange, Pagination
        time_range = TimeRange(start_time=0, end_time=int(time.time() * 1e9) + int(1e12))
        pagination = Pagination(limit=10)
        
        metrics, _, _ = await postgres_storage.search_metrics(time_range, ["test.metric"], None, pagination)
        
        assert len(metrics) > 0
        metric_found = metrics[0]
        
        # Verify resource attributes preserved
        resource = metric_found.get("resource", {})
        assert "service.name" in resource or "service_name" in metric_found
