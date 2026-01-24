"""PostgreSQL storage implementation using SQLModel ORM.

This replaces raw SQL construction with type-safe ORM operations.
No more field name mismatches or manual SQL string building.
"""

import hashlib
import json
import logging
from base64 import b64decode
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.models.database import LogsFact, MetricsFact, OperationDim, ResourceDim, ServiceDim, SpansFact


class PostgresStorage:
    """PostgreSQL storage backend using SQLModel ORM."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.engine: AsyncEngine | None = None

    async def connect(self) -> None:
        """Initialize database engine."""
        self.engine = create_async_engine(
            self.connection_string,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        logging.info("PostgreSQL storage engine created")

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logging.info("PostgreSQL storage closed")

    async def health_check(self) -> dict[str, Any]:
        """Check database connectivity."""
        if not self.engine:
            return {"status": "not_connected", "message": "Engine not initialized"}

        try:
            async with AsyncSession(self.engine) as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()
            return {"status": "healthy", "message": "Database connection OK"}
        except Exception as e:
            logging.error(f"Database health check failed: {e}")
            return {"status": "unhealthy", "message": str(e)}

    @staticmethod
    def _base64_to_hex(b64_str: str) -> str:
        """Convert base64 trace/span ID to hex."""
        try:
            return b64decode(b64_str).hex()
        except Exception:
            return b64_str  # Already hex or invalid

    @staticmethod
    def _normalize_span_kind(kind: int | str | None) -> int:
        """Convert span kind to integer.

        Handles both integer values and string constants like 'SPAN_KIND_SERVER'.
        Returns 0 (UNSPECIFIED) for unknown values.
        """
        if isinstance(kind, int):
            return kind
        if isinstance(kind, str):
            # Map from OTLP string constants to integers
            kind_map = {
                "SPAN_KIND_UNSPECIFIED": 0,
                "SPAN_KIND_INTERNAL": 1,
                "SPAN_KIND_SERVER": 2,
                "SPAN_KIND_CLIENT": 3,
                "SPAN_KIND_PRODUCER": 4,
                "SPAN_KIND_CONSUMER": 5,
            }
            return kind_map.get(kind, 0)
        return 0

    @staticmethod
    def _normalize_status_code(code: int | str | None) -> int | None:
        """Convert status code to integer.

        Handles both integer values and string constants like 'STATUS_CODE_ERROR'.
        Returns None for null values.
        """
        if code is None:
            return None
        if isinstance(code, int):
            return code
        if isinstance(code, str):
            # Map from OTLP string constants to integers
            code_map = {
                "STATUS_CODE_UNSET": 0,
                "STATUS_CODE_OK": 1,
                "STATUS_CODE_ERROR": 2,
            }
            return code_map.get(code, 0)
        return 0

    @staticmethod
    def _normalize_severity_number(severity: int | str | None) -> int | None:
        """Convert severity number to integer.

        Handles both integer values and string constants like 'SEVERITY_NUMBER_INFO'.
        Returns None for null values.

        OTLP severity numbers range from 0-24:
        - 0: UNSPECIFIED
        - 1-4: TRACE
        - 5-8: DEBUG
        - 9-12: INFO
        - 13-16: WARN
        - 17-20: ERROR
        - 21-24: FATAL
        """
        if severity is None:
            return None
        if isinstance(severity, int):
            return severity
        if isinstance(severity, str):
            # Map from OTLP string constants to integers
            severity_map = {
                "SEVERITY_NUMBER_UNSPECIFIED": 0,
                "SEVERITY_NUMBER_TRACE": 1,
                "SEVERITY_NUMBER_TRACE2": 2,
                "SEVERITY_NUMBER_TRACE3": 3,
                "SEVERITY_NUMBER_TRACE4": 4,
                "SEVERITY_NUMBER_DEBUG": 5,
                "SEVERITY_NUMBER_DEBUG2": 6,
                "SEVERITY_NUMBER_DEBUG3": 7,
                "SEVERITY_NUMBER_DEBUG4": 8,
                "SEVERITY_NUMBER_INFO": 9,
                "SEVERITY_NUMBER_INFO2": 10,
                "SEVERITY_NUMBER_INFO3": 11,
                "SEVERITY_NUMBER_INFO4": 12,
                "SEVERITY_NUMBER_WARN": 13,
                "SEVERITY_NUMBER_WARN2": 14,
                "SEVERITY_NUMBER_WARN3": 15,
                "SEVERITY_NUMBER_WARN4": 16,
                "SEVERITY_NUMBER_ERROR": 17,
                "SEVERITY_NUMBER_ERROR2": 18,
                "SEVERITY_NUMBER_ERROR3": 19,
                "SEVERITY_NUMBER_ERROR4": 20,
                "SEVERITY_NUMBER_FATAL": 21,
                "SEVERITY_NUMBER_FATAL2": 22,
                "SEVERITY_NUMBER_FATAL3": 23,
                "SEVERITY_NUMBER_FATAL4": 24,
            }
            return severity_map.get(severity, 0)
        return 0

    @staticmethod
    def _extract_string_value(attr_value: dict) -> str | None:
        """Extract string from OTLP attribute value.

        MessageToDict with preserving_proto_field_name=True uses snake_case.
        Also converts int64 to string, so int_value will be a string.
        """
        if "string_value" in attr_value:
            return attr_value["string_value"]
        if "int_value" in attr_value:
            return str(attr_value["int_value"])
        if "double_value" in attr_value:
            return str(attr_value["double_value"])
        if "bool_value" in attr_value:
            return str(attr_value["bool_value"])
        return None

    async def _upsert_service(self, session: AsyncSession, name: str, namespace: str | None = None) -> int:
        """Upsert service and return ID using ON CONFLICT."""
        stmt = (
            insert(ServiceDim)
            .values(tenant_id="default", name=name, namespace=namespace or "")
            .on_conflict_do_update(
                index_elements=["tenant_id", "name", "namespace"],
                set_={"last_seen": ServiceDim.last_seen},
            )
            .returning(ServiceDim.id)
        )
        result = await session.execute(stmt)
        service_id = result.scalar()
        await session.commit()
        return service_id

    async def _upsert_operation(
        self, session: AsyncSession, service_id: int, name: str, span_kind: int | None = None
    ) -> int:
        """Upsert operation and return ID."""
        stmt = (
            insert(OperationDim)
            .values(tenant_id="default", service_id=service_id, name=name, span_kind=span_kind)
            .on_conflict_do_update(
                index_elements=["tenant_id", "service_id", "name", "span_kind"],
                set_={"last_seen": OperationDim.last_seen},
            )
            .returning(OperationDim.id)
        )
        result = await session.execute(stmt)
        operation_id = result.scalar()
        await session.commit()
        return operation_id

    async def _upsert_resource(self, session: AsyncSession, attributes: dict) -> int:
        """Upsert resource and return ID."""
        resource_json = json.dumps(attributes, sort_keys=True)
        resource_hash = hashlib.sha256(resource_json.encode()).hexdigest()

        stmt = (
            insert(ResourceDim)
            .values(tenant_id="default", resource_hash=resource_hash, attributes=attributes)
            .on_conflict_do_update(
                index_elements=["tenant_id", "resource_hash"],
                set_={"last_seen": ResourceDim.last_seen},
            )
            .returning(ResourceDim.id)
        )
        result = await session.execute(stmt)
        resource_id = result.scalar()
        await session.commit()
        return resource_id

    async def store_traces(self, resource_spans: list[dict]) -> int:
        """Store OTLP traces using SQLModel ORM.

        Args:
            resource_spans: List of OTLP ResourceSpans (matches interface)

        Returns:
            Number of spans stored
        """
        if not resource_spans:
            return 0

        logging.info(f"store_traces called with {len(resource_spans)} resource_spans")

        spans_to_insert = []

        async with AsyncSession(self.engine) as session:
            for resource_span in resource_spans:
                # Extract resource attributes
                resource = resource_span.get("resource", {})
                resource_attrs = resource.get("attributes", [])
                resource_dict = {attr["key"]: attr.get("value") for attr in resource_attrs}

                # Extract service name and namespace
                service_name = "unknown"
                service_namespace = None
                for attr in resource_attrs:
                    key = attr.get("key")
                    value = attr.get("value", {})
                    if key == "service.name":
                        service_name = self._extract_string_value(value) or "unknown"
                    elif key == "service.namespace":
                        service_namespace = self._extract_string_value(value)

                # Upsert dimension tables
                service_id = await self._upsert_service(session, service_name, service_namespace)
                resource_id = await self._upsert_resource(session, resource_dict)

                # Process scope_spans (snake_case, not camelCase!)
                for scope_span in resource_span.get("scope_spans", []):
                    scope = scope_span.get("scope", {})

                    for span in scope_span.get("spans", []):
                        # Convert IDs
                        trace_id = self._base64_to_hex(span.get("traceId", ""))
                        span_id = self._base64_to_hex(span.get("spanId", ""))
                        parent_span_id_b64 = span.get("parentSpanId")
                        parent_span_id = self._base64_to_hex(parent_span_id_b64) if parent_span_id_b64 else None

                        # Extract span fields
                        name = span.get("name", "unknown")
                        kind_raw = span.get("kind", 0)
                        kind = self._normalize_span_kind(kind_raw)

                        # Parse timestamps - MessageToDict converts int64 to string
                        start_time_raw = span.get("start_time_unix_nano", "0")
                        end_time_raw = span.get("end_time_unix_nano", "0")
                        start_time = int(start_time_raw) if start_time_raw else 0
                        end_time = int(end_time_raw) if end_time_raw else 0

                        # Upsert operation
                        operation_id = await self._upsert_operation(session, service_id, name, kind)

                        # Status - normalize status_code to integer
                        status = span.get("status", {})
                        status_code = self._normalize_status_code(status.get("code"))
                        status_message = status.get("message")

                        # Attributes (convert OTLP format to dict)
                        attrs_list = span.get("attributes", [])
                        attributes = {attr["key"]: attr.get("value") for attr in attrs_list}

                        # Create SpansFact model instance
                        span_obj = SpansFact(
                            trace_id=trace_id,
                            span_id=span_id,
                            parent_span_id=parent_span_id,
                            name=name,
                            kind=kind,
                            status_code=status_code,
                            status_message=status_message,
                            start_time_unix_nano=start_time,
                            end_time_unix_nano=end_time,
                            service_id=service_id,
                            operation_id=operation_id,
                            resource_id=resource_id,
                            attributes=attributes,
                            events=span.get("events", []),
                            links=span.get("links", []),
                            resource=resource_dict,
                            scope=scope,
                            flags=span.get("flags", 0),
                            dropped_attributes_count=span.get("droppedAttributesCount", 0),
                            dropped_events_count=span.get("droppedEventsCount", 0),
                            dropped_links_count=span.get("droppedLinksCount", 0),
                        )
                        spans_to_insert.append(span_obj)

            # Bulk insert using ORM
            if spans_to_insert:
                session.add_all(spans_to_insert)
                await session.commit()

        return len(spans_to_insert)

    async def store_logs(self, resource_logs: list[dict]) -> int:
        """Store OTLP logs using SQLModel ORM.

        Args:
            resource_logs: List of OTLP ResourceLogs (matches interface)

        Returns:
            Number of log records stored
        """
        if not resource_logs:
            return 0

        logs_to_insert = []

        async with AsyncSession(self.engine) as session:
            for resource_log in resource_logs:
                # Extract resource attributes
                resource = resource_log.get("resource", {})
                resource_attrs = resource.get("attributes", [])
                resource_dict = {attr["key"]: attr.get("value") for attr in resource_attrs}

                # Process scope_logs (snake_case!)
                for scope_log in resource_log.get("scope_logs", []):
                    scope = scope_log.get("scope", {})

                    for log_record in scope_log.get("logRecords", scope_log.get("log_records", [])):
                        # Convert IDs
                        trace_id = log_record.get("traceId")
                        span_id = log_record.get("spanId")
                        if trace_id:
                            trace_id = self._base64_to_hex(trace_id)
                        if span_id:
                            span_id = self._base64_to_hex(span_id)

                        # Timing - MessageToDict converts int64 to string
                        time_unix_nano_raw = log_record.get("time_unix_nano", "0")
                        observed_time_unix_nano_raw = log_record.get("observed_time_unix_nano")
                        time_unix_nano = int(time_unix_nano_raw) if time_unix_nano_raw else 0
                        observed_time_unix_nano = (
                            int(observed_time_unix_nano_raw) if observed_time_unix_nano_raw else None
                        )

                        # Severity - normalize enum strings to integers
                        severity_number = self._normalize_severity_number(log_record.get("severity_number"))
                        severity_text = log_record.get("severity_text")

                        # Body (can be string or structured)
                        body = log_record.get("body", {})

                        # Attributes
                        attrs_list = log_record.get("attributes", [])
                        attributes = {attr["key"]: attr.get("value") for attr in attrs_list}

                        # Create LogsFact model instance
                        log_obj = LogsFact(
                            trace_id=trace_id,
                            span_id=span_id,
                            time_unix_nano=time_unix_nano,
                            observed_time_unix_nano=observed_time_unix_nano,
                            severity_number=severity_number,
                            severity_text=severity_text,
                            body=body,
                            attributes=attributes,
                            resource=resource_dict,
                            scope=scope,
                            flags=log_record.get("flags", 0),
                            dropped_attributes_count=log_record.get("droppedAttributesCount", 0),
                        )
                        logs_to_insert.append(log_obj)

            # Bulk insert using ORM
            if logs_to_insert:
                session.add_all(logs_to_insert)
                await session.commit()

        return len(logs_to_insert)

    async def store_metrics(self, resource_metrics: list[dict]) -> int:
        """Store OTLP metrics using SQLModel ORM.

        Args:
            resource_metrics: List of OTLP ResourceMetrics (matches interface)

        Returns:
            Number of metric data points stored
        """
        if not resource_metrics:
            return 0

        metrics_to_insert = []

        async with AsyncSession(self.engine) as session:
            for resource_metric in resource_metrics:
                # Extract resource attributes - convert OTLP attribute list to dict
                resource = resource_metric.get("resource", {})
                resource_attrs_list = resource.get("attributes", [])
                resource_dict = {attr["key"]: attr.get("value") for attr in resource_attrs_list}

                # Process scope_metrics (snake_case!)
                for scope_metric in resource_metric.get("scope_metrics", []):
                    scope = scope_metric.get("scope", {})

                    # Process metrics
                    for metric in scope_metric.get("metrics", []):
                        metric_name = metric.get("name", "unknown")
                        unit = metric.get("unit", "")
                        description = metric.get("description", "")

                        # Determine metric type and get data_points
                        metric_type = None
                        data_points_list = []
                        temporality = None
                        is_monotonic = None

                        if "gauge" in metric:
                            metric_type = "gauge"
                            data_points_list = metric["gauge"].get("data_points", [])
                        elif "sum" in metric:
                            metric_type = "sum"
                            sum_data = metric["sum"]
                            data_points_list = sum_data.get("data_points", [])
                            # Strip AGGREGATION_TEMPORALITY_ prefix to fit VARCHAR(32)
                            temporality_raw = sum_data.get("aggregation_temporality", "")
                            temporality = (
                                temporality_raw.replace("AGGREGATION_TEMPORALITY_", "") if temporality_raw else None
                            )
                            is_monotonic = sum_data.get("is_monotonic", False)
                        elif "histogram" in metric:
                            metric_type = "histogram"
                            histogram_data = metric["histogram"]
                            data_points_list = histogram_data.get("data_points", [])
                            # Strip AGGREGATION_TEMPORALITY_ prefix to fit VARCHAR(32)
                            temporality_raw = histogram_data.get("aggregation_temporality", "")
                            temporality = (
                                temporality_raw.replace("AGGREGATION_TEMPORALITY_", "") if temporality_raw else None
                            )

                        # Insert each data point as a separate row
                        for dp in data_points_list:
                            # Extract timing (snake_case strings from MessageToDict)
                            time_unix_nano_str = dp.get("time_unix_nano", "0")
                            time_unix_nano = int(time_unix_nano_str) if time_unix_nano_str else 0

                            start_time_unix_nano_str = dp.get("start_time_unix_nano")
                            start_time_unix_nano = int(start_time_unix_nano_str) if start_time_unix_nano_str else None

                            # Extract data point attributes - convert list to dict
                            dp_attrs_list = dp.get("attributes", [])
                            dp_attributes = {attr["key"]: attr.get("value") for attr in dp_attrs_list}

                            # Create MetricsFact model instance using SQLModel ORM
                            metric_obj = MetricsFact(
                                metric_name=metric_name,
                                metric_type=metric_type,
                                unit=unit,
                                description=description,
                                time_unix_nano=time_unix_nano,
                                start_time_unix_nano=start_time_unix_nano,
                                resource=resource_dict,
                                scope=scope,
                                attributes=dp_attributes,
                                data_points=dp,  # Store entire data point as JSONB
                                temporality=temporality,
                                is_monotonic=is_monotonic,
                            )
                            metrics_to_insert.append(metric_obj)

            # Bulk insert using ORM
            if metrics_to_insert:
                session.add_all(metrics_to_insert)
                await session.commit()

        return len(metrics_to_insert)

    async def search_traces(self, _filters: dict) -> list[dict]:
        """Search traces (stub - implement with SQLAlchemy queries)."""
        # TODO: Implement with session.execute(select(...))
        return []

    async def search_logs(self, _filters: dict) -> list[dict]:
        """Search logs (stub - implement with SQLAlchemy queries)."""
        # TODO: Implement with session.execute(select(...))
        return []

    async def get_services(self) -> list[dict]:
        """Get services (stub - implement with SQLAlchemy queries)."""
        # TODO: Implement with session.execute(select(...))
        return []

    async def get_service_map(self, _start_time: int, _end_time: int) -> dict:
        """Get service map (stub - implement with SQLAlchemy queries)."""
        # TODO: Implement with session.execute(select(...))
        return {"nodes": [], "edges": []}
