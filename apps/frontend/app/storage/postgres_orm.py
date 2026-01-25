"""PostgreSQL storage implementation using SQLModel ORM.

This replaces raw SQL construction with type-safe ORM operations.
No more field name mismatches or manual SQL string building.
"""

import hashlib
import json
import logging
from base64 import b64decode
from typing import Any

from sqlalchemy import func, select
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
                # Use ORM select instead of text()
                result = await session.execute(select(func.count()).select_from(SpansFact).limit(1))
                result.scalar()
            return {"status": "healthy", "message": "Database connection OK"}
        except Exception as e:
            logging.error(f"Database health check failed: {e}")
            return {"status": "unhealthy", "message": str(e)}

    @staticmethod
    def _base64_to_hex(b64_str: str) -> str:
        """Convert base64 trace/span ID to hex.

        If input is already hex (all hex digits), return as-is.
        Otherwise, decode from base64 to bytes, then to hex.
        """
        if not b64_str:
            return b64_str

        # Check if already hex (all chars are 0-9a-fA-F)
        if all(c in "0123456789abcdefABCDEF" for c in b64_str):
            return b64_str.lower()

        # Otherwise decode from base64
        try:
            return b64decode(b64_str).hex()
        except Exception:
            return b64_str  # Invalid format, return as-is

    @staticmethod
    def _bytes_to_hex(value: bytes | str | None) -> str | None:
        """Convert bytes to hex string, or pass through if already string."""
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.hex()
        return value

    @staticmethod
    def _normalize_span_kind(kind: int | str | None) -> int:
        """Convert span kind to integer."""
        if isinstance(kind, int):
            return kind
        if isinstance(kind, str):
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
        """Convert status code to integer."""
        if code is None:
            return None
        if isinstance(code, int):
            return code
        if isinstance(code, str):
            code_map = {
                "STATUS_CODE_UNSET": 0,
                "STATUS_CODE_OK": 1,
                "STATUS_CODE_ERROR": 2,
            }
            return code_map.get(code, 0)
        return 0

    @staticmethod
    def _normalize_severity_number(severity: int | str | None) -> int | None:
        """Convert severity number to integer."""
        if severity is None:
            return None
        if isinstance(severity, int):
            return severity
        if isinstance(severity, str):
            severity_map = {
                "SEVERITY_NUMBER_UNSPECIFIED": 0,
                "SEVERITY_NUMBER_TRACE": 1,
                "SEVERITY_NUMBER_DEBUG": 5,
                "SEVERITY_NUMBER_INFO": 9,
                "SEVERITY_NUMBER_WARN": 13,
                "SEVERITY_NUMBER_ERROR": 17,
                "SEVERITY_NUMBER_FATAL": 21,
            }
            return severity_map.get(severity, 0)
        return 0

    @staticmethod
    def _extract_string_value(attr_value: dict) -> str | None:
        """Extract string from OTLP attribute value."""
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
        return operation_id
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
        return resource_id

    async def store_traces(self, resource_spans: list[dict]) -> int:
        """Store OTLP traces using SQLModel ORM."""
        if not resource_spans:
            return 0

        logging.info(f"store_traces called with {len(resource_spans)} resource_spans")

        spans_to_insert = []

        async with AsyncSession(self.engine) as session:
            for resource_span in resource_spans:
                resource = resource_span.get("resource", {})
                resource_attrs = resource.get("attributes", [])
                resource_dict = {attr["key"]: attr.get("value") for attr in resource_attrs}

                service_name = "unknown"
                service_namespace = None
                for attr in resource_attrs:
                    key = attr.get("key")
                    value = attr.get("value", {})
                    if key == "service.name":
                        service_name = self._extract_string_value(value) or "unknown"
                    elif key == "service.namespace":
                        service_namespace = self._extract_string_value(value)

                service_id = await self._upsert_service(session, service_name, service_namespace)
                resource_id = await self._upsert_resource(session, resource_dict)

                for scope_span in resource_span.get("scope_spans", []):
                    scope = scope_span.get("scope", {})

                    for span in scope_span.get("spans", []):
                        trace_id_raw = span.get("traceId", "")
                        span_id_raw = span.get("spanId", "")

                        # OTLP spec: trace_id is 16 bytes (32 hex), span_id is 8 bytes (16 hex)
                        # If already hex (32 or 16 chars), use as-is. If base64, convert.
                        if len(trace_id_raw) == 32:
                            trace_id = trace_id_raw
                        else:
                            trace_id = self._base64_to_hex(trace_id_raw) if trace_id_raw else ""

                        if len(span_id_raw) == 16:
                            span_id = span_id_raw
                        else:
                            span_id = self._base64_to_hex(span_id_raw) if span_id_raw else ""

                        parent_span_id_raw = span.get("parentSpanId")
                        if parent_span_id_raw:
                            if len(parent_span_id_raw) == 16:
                                parent_span_id = parent_span_id_raw
                            else:
                                parent_span_id = self._base64_to_hex(parent_span_id_raw)
                        else:
                            parent_span_id = None

                        logging.debug(f"Storing span: trace_id={trace_id}, span_id={span_id}, parent={parent_span_id}")

                        name = span.get("name", "unknown")
                        kind_raw = span.get("kind", 0)
                        kind = self._normalize_span_kind(kind_raw)

                        start_time_raw = span.get("start_time_unix_nano", "0")
                        end_time_raw = span.get("end_time_unix_nano", "0")
                        start_time = int(start_time_raw) if start_time_raw else 0
                        end_time = int(end_time_raw) if end_time_raw else 0

                        operation_id = await self._upsert_operation(session, service_id, name, kind)

                        status = span.get("status", {})
                        status_code = self._normalize_status_code(status.get("code"))
                        status_message = status.get("message")

                        attrs_list = span.get("attributes", [])
                        attributes = {attr["key"]: attr.get("value") for attr in attrs_list}

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

            if spans_to_insert:
                session.add_all(spans_to_insert)
                await session.commit()

        return len(spans_to_insert)

    async def store_logs(self, resource_logs: list[dict]) -> int:
        """Store OTLP logs using SQLModel ORM."""
        if not resource_logs:
            return 0

        logs_to_insert = []

        async with AsyncSession(self.engine) as session:
            for resource_log in resource_logs:
                resource = resource_log.get("resource", {})
                resource_attrs = resource.get("attributes", [])
                resource_dict = {attr["key"]: attr.get("value") for attr in resource_attrs}

                # Extract service info for normalization
                service_name = "unknown"
                service_namespace = None
                for attr in resource_attrs:
                    if attr["key"] == "service.name":
                        value = attr.get("value", {})
                        service_name = self._extract_string_value(value) or "unknown"
                    elif attr["key"] == "service.namespace":
                        value = attr.get("value", {})
                        service_namespace = self._extract_string_value(value)
                service_id = await self._upsert_service(session, service_name, service_namespace)

                for scope_log in resource_log.get("scope_logs", []):
                    scope = scope_log.get("scope", {})

                    for log_record in scope_log.get("logRecords", scope_log.get("log_records", [])):
                        trace_id = log_record.get("traceId")
                        span_id = log_record.get("spanId")
                        if trace_id:
                            trace_id = self._base64_to_hex(trace_id)
                        if span_id:
                            span_id = self._base64_to_hex(span_id)

                        # OTLP spec uses camelCase: timeUnixNano, observedTimeUnixNano
                        time_unix_nano_raw = log_record.get("timeUnixNano", "0")
                        observed_time_unix_nano_raw = log_record.get("observedTimeUnixNano")
                        time_unix_nano = int(time_unix_nano_raw) if time_unix_nano_raw else 0
                        observed_time_unix_nano = (
                            int(observed_time_unix_nano_raw) if observed_time_unix_nano_raw else None
                        )

                        # If time_unix_nano is 0 or missing, use observed_time_unix_nano or current time
                        if time_unix_nano == 0:
                            if observed_time_unix_nano:
                                time_unix_nano = observed_time_unix_nano
                            else:
                                import time

                                time_unix_nano = int(time.time() * 1_000_000_000)

                        # OTLP spec uses camelCase: severityNumber, severityText
                        severity_number = self._normalize_severity_number(log_record.get("severityNumber"))
                        severity_text = log_record.get("severityText")

                        body = log_record.get("body", {})

                        attrs_list = log_record.get("attributes", [])
                        attributes = {attr["key"]: attr.get("value") for attr in attrs_list}

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
                            service_id=service_id,
                            flags=log_record.get("flags", 0),
                            dropped_attributes_count=log_record.get("droppedAttributesCount", 0),
                        )
                        logs_to_insert.append(log_obj)

            if logs_to_insert:
                session.add_all(logs_to_insert)
                await session.commit()

        return len(logs_to_insert)

    async def store_metrics(self, resource_metrics: list[dict]) -> int:
        """Store OTLP metrics using SQLModel ORM."""
        if not resource_metrics:
            return 0

        metrics_to_insert = []

        async with AsyncSession(self.engine) as session:
            for resource_metric in resource_metrics:
                resource = resource_metric.get("resource", {})
                resource_attrs_list = resource.get("attributes", [])
                resource_dict = {attr["key"]: attr.get("value") for attr in resource_attrs_list}
                # Extract service info for normalization
                service_name = "unknown"
                service_namespace = None
                for attr in resource_attrs_list:
                    if attr["key"] == "service.name":
                        value = attr.get("value", {})
                        service_name = self._extract_string_value(value) or "unknown"
                    elif attr["key"] == "service.namespace":
                        value = attr.get("value", {})
                        service_namespace = self._extract_string_value(value)
                service_id = await self._upsert_service(session, service_name, service_namespace)
                for scope_metric in resource_metric.get("scope_metrics", []):
                    scope = scope_metric.get("scope", {})

                    for metric in scope_metric.get("metrics", []):
                        metric_name = metric.get("name", "unknown")
                        unit = metric.get("unit", "")
                        description = metric.get("description", "")

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
                            temporality_raw = sum_data.get("aggregation_temporality", "")
                            temporality = (
                                temporality_raw.replace("AGGREGATION_TEMPORALITY_", "") if temporality_raw else None
                            )
                            is_monotonic = sum_data.get("is_monotonic", False)
                        elif "histogram" in metric:
                            metric_type = "histogram"
                            histogram_data = metric["histogram"]
                            data_points_list = histogram_data.get("data_points", [])
                            temporality_raw = histogram_data.get("aggregation_temporality", "")
                            temporality = (
                                temporality_raw.replace("AGGREGATION_TEMPORALITY_", "") if temporality_raw else None
                            )

                        for dp in data_points_list:
                            time_unix_nano_str = dp.get("time_unix_nano", "0")
                            time_unix_nano = int(time_unix_nano_str) if time_unix_nano_str else 0

                            start_time_unix_nano_str = dp.get("start_time_unix_nano")
                            start_time_unix_nano = int(start_time_unix_nano_str) if start_time_unix_nano_str else None

                            dp_attrs_list = dp.get("attributes", [])
                            dp_attributes = {attr["key"]: attr.get("value") for attr in dp_attrs_list}

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
                                data_points=dp,
                                temporality=temporality,
                                is_monotonic=is_monotonic,
                                service_id=service_id,
                            )
                            metrics_to_insert.append(metric_obj)

            if metrics_to_insert:
                session.add_all(metrics_to_insert)
                await session.commit()

        return len(metrics_to_insert)

    async def search_traces(
        self,
        time_range: Any,
        filters: list | None = None,
        pagination: Any | None = None,
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        """Search traces with filters and pagination using ORM."""
        if not self.engine:
            return [], False, None

        async with AsyncSession(self.engine) as session:
            limit = pagination.limit if pagination else 100

            # ORM query for distinct trace IDs with min start time for ordering
            # Use GROUP BY to get earliest span per trace for ordering
            stmt = (
                select(SpansFact.trace_id, func.min(SpansFact.start_time_unix_nano).label("earliest_span"))
                .where(
                    SpansFact.start_time_unix_nano >= time_range.start_time,
                    SpansFact.start_time_unix_nano < time_range.end_time,
                    SpansFact.tenant_id == "default",
                )
                .group_by(SpansFact.trace_id)
                .order_by(func.min(SpansFact.start_time_unix_nano).desc())
                .limit(limit + 1)
            )

            result = await session.execute(stmt)
            trace_ids = [row[0] for row in result.fetchall()]

            has_more = len(trace_ids) > limit
            if has_more:
                trace_ids = trace_ids[:limit]

            traces = []
            for trace_id in trace_ids:
                trace = await self.get_trace_by_id(trace_id)
                if trace:
                    traces.append(trace)

            return traces, has_more, None

    async def get_trace_by_id(self, trace_id: str) -> dict[str, Any] | None:
        """Get trace by ID with all spans using ORM."""
        if not self.engine:
            return None

        async with AsyncSession(self.engine) as session:
            # ORM query with outer join to ServiceDim
            stmt = (
                select(SpansFact, ServiceDim.name)
                .outerjoin(ServiceDim, SpansFact.service_id == ServiceDim.id)
                .where(
                    SpansFact.trace_id == trace_id,
                    SpansFact.tenant_id == "default",
                )
                .order_by(SpansFact.start_time_unix_nano.asc())
            )

            result = await session.execute(stmt)
            rows = result.fetchall()

            if not rows:
                return None

            spans = []
            for span, service_name in rows:
                span_dict = {
                    "trace_id": self._bytes_to_hex(span.trace_id),
                    "span_id": self._bytes_to_hex(span.span_id),
                    "parent_span_id": self._bytes_to_hex(span.parent_span_id),
                    "name": span.name,
                    "kind": span.kind,
                    "status": {"code": span.status_code, "message": span.status_message}
                    if span.status_code is not None
                    else None,
                    "start_time_unix_nano": span.start_time_unix_nano,
                    "end_time_unix_nano": span.end_time_unix_nano,
                    "attributes": span.attributes if span.attributes else {},
                    "events": span.events if span.events else [],
                    "links": span.links if span.links else [],
                    "service_name": service_name,
                    "resource": span.resource if span.resource else {},
                }
                spans.append(span_dict)

            return {"trace_id": trace_id, "spans": spans}

    async def search_logs(
        self,
        time_range: Any,
        filters: list | None = None,
        pagination: Any | None = None,
    ) -> tuple[list, bool, str | None]:
        """Search logs with filters and pagination using ORM."""
        if not self.engine:
            return [], False, None

        async with AsyncSession(self.engine) as session:
            limit = pagination.limit if pagination else 100

            # ORM query with JOIN to ServiceDim
            stmt = (
                select(LogsFact, ServiceDim.name)
                .outerjoin(ServiceDim, LogsFact.service_id == ServiceDim.id)
                .where(
                    LogsFact.time_unix_nano >= time_range.start_time,
                    LogsFact.time_unix_nano < time_range.end_time,
                    LogsFact.tenant_id == "default",
                )
                .order_by(LogsFact.time_unix_nano.desc())
                .limit(limit + 1)
            )

            result = await session.execute(stmt)
            rows = result.fetchall()

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            from app.models.api import LogRecord

            logs = []
            for log, service_name in rows:
                # Extract body string per OTLP spec: body.stringValue
                body = log.body
                if isinstance(body, dict):
                    body_text = body.get("stringValue", body.get("string_value", str(body)))
                else:
                    body_text = str(body) if body else ""

                # Convert attributes dict to list of {key, value} pairs for API model
                attributes_dict = log.attributes if log.attributes else {}
                attributes_list = []
                for key, value in attributes_dict.items():
                    attributes_list.append({"key": key, "value": value})

                log_record = LogRecord(
                    log_id=str(log.id),
                    time_unix_nano=log.time_unix_nano,
                    observed_time_unix_nano=log.observed_time_unix_nano,
                    severity_number=log.severity_number,
                    severity_text=log.severity_text,
                    body=body_text,
                    attributes=attributes_list,
                    trace_id=log.trace_id,
                    span_id=log.span_id,
                    service_name=service_name,
                    resource=log.resource if log.resource else {},
                )
                logs.append(log_record)

            return logs, has_more, None

    async def search_metrics(
        self,
        time_range: Any,
        metric_names: list[str] | None = None,
        filters: list | None = None,
        pagination: Any | None = None,
    ) -> tuple[list, bool, str | None]:
        """Search metrics with filters and pagination using ORM."""
        if not self.engine:
            return [], False, None

        async with AsyncSession(self.engine) as session:
            limit = pagination.limit if pagination else 100

            # ORM query with JOIN to ServiceDim and optional metric name filter
            stmt = (
                select(MetricsFact, ServiceDim.name)
                .outerjoin(ServiceDim, MetricsFact.service_id == ServiceDim.id)
                .where(
                    MetricsFact.time_unix_nano >= time_range.start_time,
                    MetricsFact.time_unix_nano < time_range.end_time,
                    MetricsFact.tenant_id == "default",
                )
            )

            if metric_names:
                stmt = stmt.where(MetricsFact.metric_name.in_(metric_names))

            stmt = stmt.order_by(MetricsFact.time_unix_nano.desc()).limit(limit + 1)

            result = await session.execute(stmt)
            rows = result.fetchall()

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            from app.models.api import Metric

            metrics = []
            for m, service_name in rows:
                metric = Metric(
                    metric_id=str(m.id),
                    name=m.metric_name,
                    description=m.description,
                    unit=m.unit,
                    metric_type=m.metric_type,
                    aggregation_temporality=m.temporality,
                    timestamp_ns=m.time_unix_nano,
                    data_points=m.data_points if m.data_points else [],
                    attributes=m.attributes if m.attributes else {},
                    service_name=service_name,
                    resource=m.resource if m.resource else {},
                    value=0.0,
                    exemplars=[],
                )
                metrics.append(metric)

            return metrics, has_more, None

    async def get_services(self, time_range: Any | None = None) -> list:
        """Get service catalog with RED metrics using ORM."""
        if not self.engine:
            return []

        async with AsyncSession(self.engine) as session:
            # ORM query with aggregations
            stmt = (
                select(
                    ServiceDim.name,
                    func.count().label("request_count"),
                    func.count().filter(SpansFact.status_code == 2).label("error_count"),
                    func.percentile_cont(0.50)
                    .within_group(SpansFact.end_time_unix_nano - SpansFact.start_time_unix_nano)
                    .label("p50_ns"),
                    func.percentile_cont(0.95)
                    .within_group(SpansFact.end_time_unix_nano - SpansFact.start_time_unix_nano)
                    .label("p95_ns"),
                    func.min(SpansFact.start_time_unix_nano).label("first_seen_ns"),
                    func.max(SpansFact.start_time_unix_nano).label("last_seen_ns"),
                )
                .select_from(SpansFact)
                .join(ServiceDim, SpansFact.service_id == ServiceDim.id)
                .where(SpansFact.tenant_id == "default")
            )

            if time_range:
                stmt = stmt.where(
                    SpansFact.start_time_unix_nano >= time_range.start_time,
                    SpansFact.start_time_unix_nano < time_range.end_time,
                )

            stmt = stmt.group_by(ServiceDim.name).order_by(func.count().desc())

            result = await session.execute(stmt)
            rows = result.fetchall()

            from app.models.api import Service

            services = []
            for row in rows:
                error_rate = (row.error_count / row.request_count) * 100 if row.request_count > 0 else 0.0

                service = Service(
                    name=row.name,
                    request_count=row.request_count,
                    error_count=row.error_count,
                    error_rate=round(error_rate, 2),
                    p50_latency_ms=round(row.p50_ns / 1_000_000, 2) if row.p50_ns else 0.0,
                    p95_latency_ms=round(row.p95_ns / 1_000_000, 2) if row.p95_ns else 0.0,
                    first_seen=row.first_seen_ns,
                    last_seen=row.last_seen_ns,
                )
                services.append(service)

            return services

    async def get_service_map(self, time_range: Any) -> tuple[list, list]:
        """Get service dependency map from spans using ORM."""
        if not self.engine:
            return [], []

        from sqlalchemy import alias

        async with AsyncSession(self.engine) as session:
            # Create aliases for self-join
            s_child = alias(SpansFact, name="s_child")
            s_parent = alias(SpansFact, name="s_parent")
            srv_child = alias(ServiceDim, name="srv_child")
            srv_parent = alias(ServiceDim, name="srv_parent")

            # ORM query with self-join for parent-child relationships
            stmt = (
                select(
                    srv_parent.c.name.label("source"),
                    srv_child.c.name.label("target"),
                    func.count().label("call_count"),
                    s_child.c.kind.label("span_kind"),
                )
                .select_from(s_child)
                .outerjoin(
                    s_parent,
                    (s_child.c.trace_id == s_parent.c.trace_id)
                    & (s_child.c.parent_span_id == s_parent.c.span_id)
                    & (s_parent.c.tenant_id == "default"),
                )
                .outerjoin(srv_parent, s_parent.c.service_id == srv_parent.c.id)
                .join(srv_child, s_child.c.service_id == srv_child.c.id)
                .where(
                    s_child.c.start_time_unix_nano >= time_range.start_time,
                    s_child.c.start_time_unix_nano < time_range.end_time,
                    s_child.c.tenant_id == "default",
                    srv_parent.c.name.isnot(None),
                    srv_parent.c.name != srv_child.c.name,
                )
                .group_by(srv_parent.c.name, srv_child.c.name, s_child.c.kind)
            )

            result = await session.execute(stmt)
            rows = result.fetchall()

            from app.models.api import ServiceMapEdge, ServiceMapNode

            nodes_dict = {}
            edges = []

            for row in rows:
                source, target, call_count, span_kind = row

                if source not in nodes_dict:
                    nodes_dict[source] = ServiceMapNode(id=source, name=source, type="service")
                if target not in nodes_dict:
                    nodes_dict[target] = ServiceMapNode(id=target, name=target, type="service")

                # Reverse edge direction for CONSUMER spans
                if span_kind == 5:
                    edges.append(ServiceMapEdge(source=target, target=source, call_count=call_count))
                else:
                    edges.append(ServiceMapEdge(source=source, target=target, call_count=call_count))

            return list(nodes_dict.values()), edges
