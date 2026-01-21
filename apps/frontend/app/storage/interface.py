"""Storage layer abstraction for ollyScale v2."""

from abc import ABC, abstractmethod
from typing import Any

from app.models.api import (
    Filter,
    LogRecord,
    Metric,
    PaginationRequest,
    Service,
    ServiceMapEdge,
    ServiceMapNode,
    TimeRange,
)


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to storage backend."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connection to storage backend."""
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Check storage backend health."""
        pass

    # ==================== Trace Storage ====================

    @abstractmethod
    async def store_traces(self, resource_spans: list[dict[str, Any]]) -> int:
        """
        Store traces from OTLP ResourceSpans.

        Args:
            resource_spans: OTLP ResourceSpans array

        Returns:
            Number of spans stored
        """
        pass

    @abstractmethod
    async def search_traces(
        self,
        time_range: TimeRange,
        filters: list[Filter] | None = None,
        pagination: PaginationRequest | None = None,
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        """
        Search traces with filters and pagination.

        Args:
            time_range: Time range for query
            filters: Optional list of filters
            pagination: Optional pagination parameters

        Returns:
            Tuple of (traces, has_more, next_cursor)
        """
        pass

    @abstractmethod
    async def get_trace_by_id(self, trace_id: str) -> dict[str, Any] | None:
        """
        Get trace by ID.

        Args:
            trace_id: Trace ID (hex string)

        Returns:
            Trace with spans or None if not found
        """
        pass

    # ==================== Log Storage ====================

    @abstractmethod
    async def store_logs(self, resource_logs: list[dict[str, Any]]) -> int:
        """
        Store logs from OTLP ResourceLogs.

        Args:
            resource_logs: OTLP ResourceLogs array

        Returns:
            Number of log records stored
        """
        pass

    @abstractmethod
    async def search_logs(
        self,
        time_range: TimeRange,
        filters: list[Filter] | None = None,
        pagination: PaginationRequest | None = None,
    ) -> tuple[list[LogRecord], bool, str | None]:
        """
        Search logs with filters and pagination.

        Args:
            time_range: Time range for query
            filters: Optional list of filters
            pagination: Optional pagination parameters

        Returns:
            Tuple of (logs, has_more, next_cursor)
        """
        pass

    # ==================== Metric Storage ====================

    @abstractmethod
    async def store_metrics(self, resource_metrics: list[dict[str, Any]]) -> int:
        """
        Store metrics from OTLP ResourceMetrics.

        Args:
            resource_metrics: OTLP ResourceMetrics array

        Returns:
            Number of metric data points stored
        """
        pass

    @abstractmethod
    async def search_metrics(
        self,
        time_range: TimeRange,
        metric_names: list[str] | None = None,
        filters: list[Filter] | None = None,
        pagination: PaginationRequest | None = None,
    ) -> tuple[list[Metric], bool, str | None]:
        """
        Search metrics with filters and pagination.

        Args:
            time_range: Time range for query
            metric_names: Optional list of metric names to filter
            filters: Optional list of filters
            pagination: Optional pagination parameters

        Returns:
            Tuple of (metrics, has_more, next_cursor)
        """
        pass

    # ==================== Service Catalog ====================

    @abstractmethod
    async def get_services(self, time_range: TimeRange | None = None) -> list[Service]:
        """
        Get service catalog with RED metrics.

        Args:
            time_range: Optional time range for RED metrics calculation

        Returns:
            List of services with metrics
        """
        pass

    @abstractmethod
    async def get_service_map(self, time_range: TimeRange) -> tuple[list[ServiceMapNode], list[ServiceMapEdge]]:
        """
        Get service dependency map.

        Args:
            time_range: Time range for map generation

        Returns:
            Tuple of (nodes, edges)
        """
        pass


class InMemoryStorage(StorageBackend):
    """In-memory storage backend for testing."""

    def __init__(self):
        self.traces: list[dict[str, Any]] = []
        self.logs: list[LogRecord] = []
        self.metrics: list[Metric] = []
        self.services: list[Service] = []

    async def connect(self) -> None:
        """No-op for in-memory storage."""
        pass

    async def close(self) -> None:
        """No-op for in-memory storage."""
        pass

    async def health_check(self) -> dict[str, Any]:
        """Return in-memory storage stats."""
        return {
            "type": "in-memory",
            "traces": len(self.traces),
            "logs": len(self.logs),
            "metrics": len(self.metrics),
            "services": len(self.services),
        }

    async def store_traces(self, resource_spans: list[dict[str, Any]]) -> int:
        """Store traces in memory."""
        count = 0
        for rs in resource_spans:
            for scope_span in rs.get("scope_spans", []):
                for span in scope_span.get("spans", []):
                    self.traces.append({"resource": rs.get("resource"), "scope": scope_span.get("scope"), "span": span})
                    count += 1
        return count

    async def search_traces(
        self,
        _time_range: TimeRange,
        _filters: list[Filter] | None = None,
        _pagination: PaginationRequest | None = None,
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        """Search traces in memory."""
        # Simplified: just return all traces for now
        return self.traces, False, None

    async def get_trace_by_id(self, trace_id: str) -> dict[str, Any] | None:
        """Get trace by ID from memory."""
        matching_spans = [t for t in self.traces if t["span"].get("trace_id") == trace_id]
        if matching_spans:
            return {"trace_id": trace_id, "spans": matching_spans}
        return None

    async def store_logs(self, resource_logs: list[dict[str, Any]]) -> int:
        """Store logs in memory."""
        count = 0
        for rl in resource_logs:
            for scope_log in rl.get("scope_logs", []):
                count += len(scope_log.get("log_records", []))
        return count

    async def search_logs(
        self,
        _time_range: TimeRange,
        _filters: list[Filter] | None = None,
        _pagination: PaginationRequest | None = None,
    ) -> tuple[list[LogRecord], bool, str | None]:
        """Search logs in memory."""
        return self.logs, False, None

    async def store_metrics(self, resource_metrics: list[dict[str, Any]]) -> int:
        """Store metrics in memory."""
        count = 0
        for rm in resource_metrics:
            for scope_metric in rm.get("scope_metrics", []):
                count += len(scope_metric.get("metrics", []))
        return count

    async def search_metrics(
        self,
        _time_range: TimeRange,
        _metric_names: list[str] | None = None,
        _filters: list[Filter] | None = None,
        _pagination: PaginationRequest | None = None,
    ) -> tuple[list[Metric], bool, str | None]:
        """Search metrics in memory."""
        return self.metrics, False, None

    async def get_services(self, _time_range: TimeRange | None = None) -> list[Service]:
        """Get services from memory."""
        return self.services

    async def get_service_map(self, _time_range: TimeRange) -> tuple[list[ServiceMapNode], list[ServiceMapEdge]]:
        """Get service map from memory."""
        return [], []
