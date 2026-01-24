"""PostgreSQL storage backend implementation."""

import base64
import json
from typing import Any

from sqlalchemy import text

from app.db.session import Database
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
from app.storage.interface import StorageBackend


class PostgresStorage(StorageBackend):
    """PostgreSQL storage backend using async SQLAlchemy."""

    def __init__(self):
        """Initialize PostgreSQL storage backend."""
        self.db = Database()

    async def connect(self) -> None:
        """Establish connection to PostgreSQL."""
        await self.db.connect()

    async def close(self) -> None:
        """Close connection to PostgreSQL."""
        await self.db.close()

    async def health_check(self) -> dict[str, Any]:
        """Check PostgreSQL health."""
        try:
            async with self.db.session() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()

                # Get storage stats
                stats_query = text("""
                    SELECT
                        (SELECT COUNT(*) FROM spans_fact) AS spans_count,
                        (SELECT COUNT(*) FROM logs_fact) AS logs_count,
                        (SELECT COUNT(*) FROM metrics_fact) AS metrics_count,
                        (SELECT COUNT(*) FROM service_dim) AS services_count
                """)
                stats = await session.execute(stats_query)
                row = stats.fetchone()

                return {
                    "type": "postgresql",
                    "status": "healthy",
                    "spans": row[0] if row else 0,
                    "logs": row[1] if row else 0,
                    "metrics": row[2] if row else 0,
                    "services": row[3] if row else 0,
                }
        except Exception as e:
            return {
                "type": "postgresql",
                "status": "unhealthy",
                "error": str(e),
            }

    # ==================== Helper Methods ====================

    async def _upsert_service(self, session, service_name: str, namespace: str | None = None) -> int:
        """Upsert service dimension and return service id."""
        query = text("""
            INSERT INTO service_dim (name, namespace, tenant_id)
            VALUES (:name, :namespace, :tenant_id)
            ON CONFLICT (tenant_id, name, namespace)
            DO UPDATE SET last_seen = NOW()
            RETURNING id
        """)

        result = await session.execute(
            query,
            {
                "name": service_name,
                "namespace": namespace or "",  # Store empty string for missing namespace
                "tenant_id": "default",
            },
        )
        return result.scalar()

    async def _upsert_operation(self, session, service_id: int, operation_name: str, span_kind: int) -> int:
        """Upsert operation dimension and return operation id."""
        query = text("""
            INSERT INTO operation_dim (name, service_id, span_kind, tenant_id)
            VALUES (:name, :service_id, :span_kind, :tenant_id)
            ON CONFLICT (tenant_id, service_id, name, span_kind)
            DO UPDATE SET last_seen = NOW()
            RETURNING id
        """)

        result = await session.execute(
            query, {"name": operation_name, "service_id": service_id, "span_kind": span_kind, "tenant_id": "default"}
        )
        return result.scalar()

    async def _upsert_resource(self, session, resource_attrs: dict) -> int:
        """Upsert resource dimension and return resource id."""
        import hashlib

        # Create hash of resource attributes for uniqueness
        resource_json = json.dumps(resource_attrs, sort_keys=True)
        resource_hash = hashlib.sha256(resource_json.encode()).hexdigest()

        query = text("""
            INSERT INTO resource_dim (resource_hash, attributes, tenant_id)
            VALUES (:resource_hash, :attributes, :tenant_id)
            ON CONFLICT (tenant_id, resource_hash)
            DO UPDATE SET last_seen = NOW()
            RETURNING id
        """)

        result = await session.execute(
            query, {"resource_hash": resource_hash, "attributes": json.dumps(resource_attrs), "tenant_id": "default"}
        )
        return result.scalar()

    def _hex_to_bytes(self, hex_str: str) -> bytes:
        """Convert hex string to bytes (for trace/span IDs)."""
        return bytes.fromhex(hex_str)

    def _bytes_to_hex(self, byte_data: bytes) -> str:
        """Convert bytes to hex string."""
        return byte_data.hex()

    def _base64_to_hex(self, b64_str: str) -> str:
        """Convert base64 encoded ID to hex string."""
        return base64.b64decode(b64_str).hex()

    # ==================== Trace Storage ====================

    async def store_traces(self, resource_spans: list[dict[str, Any]]) -> int:
        """
        Store traces from OTLP ResourceSpans.

        Parses OTLP format, upserts dimensions, and batch inserts spans into spans_fact.
        """
        if not resource_spans:
            return 0

        spans_to_insert = []

        try:
            import logging

            logging.info(f"store_traces called with {len(resource_spans)} resource_spans")
            if resource_spans:
                logging.info(f"First resource_span keys: {list(resource_spans[0].keys())}")

            async with self.db.session() as session:
                for resource_span in resource_spans:
                    resource = resource_span.get("resource", {})
                    resource_attrs = resource.get("attributes", [])
                    resource_dict = {attr.get("key"): attr.get("value") for attr in resource_attrs}

                    # Extract service.name and service.namespace from resource attributes (OTEL semantic conventions)
                    service_name = "unknown"
                    service_namespace = None
                    for attr in resource_attrs:
                        key = attr.get("key")
                        value = attr.get("value", {})
                        if key == "service.name":
                            service_name = value.get("stringValue", "unknown")
                        elif key == "service.namespace":
                            service_namespace = value.get("stringValue")

                    # Upsert service with namespace
                    service_id = await self._upsert_service(session, service_name, service_namespace)
                    resource_id = await self._upsert_resource(session, resource_dict)

                    for scope_span in resource_span.get("scope_spans", []):
                        for span in scope_span.get("spans", []):
                            # Parse span IDs
                            trace_id_b64 = span.get("traceId", "")
                            span_id_b64 = span.get("spanId", "")
                            parent_span_id_b64 = span.get("parentSpanId", "")

                            trace_id = self._base64_to_hex(trace_id_b64) if trace_id_b64 else None
                            span_id = self._base64_to_hex(span_id_b64) if span_id_b64 else None
                            parent_span_id = self._base64_to_hex(parent_span_id_b64) if parent_span_id_b64 else None

                            # Get operation name and span kind
                            operation_name = span.get("name", "unknown")
                            span_kind = span.get("kind", 0)  # 0=UNSPECIFIED, 1=INTERNAL, 2=SERVER, 3=CLIENT, etc.
                            operation_id = await self._upsert_operation(session, service_id, operation_name, span_kind)

                            # Parse attributes
                            attributes = {}
                            for attr in span.get("attributes", []):
                                key = attr.get("key")
                                value = attr.get("value", {})
                                # Extract value based on type
                                if "stringValue" in value:
                                    attributes[key] = value["stringValue"]
                                elif "intValue" in value:
                                    attributes[key] = value["intValue"]
                                elif "doubleValue" in value:
                                    attributes[key] = value["doubleValue"]
                                elif "boolValue" in value:
                                    attributes[key] = value["boolValue"]

                            # Parse status
                            status = span.get("status", {})
                            status_code = status.get("code", 0)  # 0=UNSET, 1=OK, 2=ERROR

                            # Prepare span data (using schema column names)
                            span_data = {
                                "trace_id": trace_id,
                                "span_id": span_id,
                                "parent_span_id": parent_span_id,
                                "name": operation_name,
                                "kind": span_kind,
                                "service_id": service_id,
                                "operation_id": operation_id,
                                "resource_id": resource_id,
                                "start_time_unix_nano": int(span.get("startTimeUnixNano", 0)),
                                "end_time_unix_nano": int(span.get("endTimeUnixNano", 0)),
                                "status_code": status_code,
                                "status_message": span.get("status", {}).get("message"),
                                "tenant_id": "default",
                                "attributes": json.dumps(attributes),
                                "events": json.dumps(span.get("events", [])),
                                "links": json.dumps(span.get("links", [])),
                                "resource": json.dumps(resource_dict),
                                "scope": json.dumps(scope_span.get("scope", {})),
                            }
                            spans_to_insert.append(span_data)

                # Batch insert spans
                if spans_to_insert:
                    insert_stmt = text("""
                        INSERT INTO spans_fact (
                            trace_id, span_id, parent_span_id, name, kind, service_id, operation_id, resource_id,
                            start_time_unix_nano, end_time_unix_nano, status_code, status_message,
                            tenant_id, attributes, events, links, resource, scope
                        ) VALUES (
                            :trace_id, :span_id, :parent_span_id, :name, :kind, :service_id, :operation_id, :resource_id,
                            :start_time_unix_nano, :end_time_unix_nano, :status_code, :status_message,
                            :tenant_id, :attributes::jsonb, :events::jsonb, :links::jsonb, :resource::jsonb, :scope::jsonb
                        )
                    """)
                    await session.execute(insert_stmt, spans_to_insert)

            return len(spans_to_insert)
        except Exception as e:
            import logging

            logging.error(f"Failed to store traces: {e}", exc_info=True)
            return 0

    async def search_traces(
        self,
        time_range: TimeRange,
        filters: list[Filter] | None = None,
        pagination: PaginationRequest | None = None,
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        """
        Search traces with filters and pagination.

        Queries spans_fact with time range and optional attribute filters.
        """
        async with self.db.session() as session:
            # Build base query
            query = text("""
                SELECT DISTINCT trace_id
                FROM spans_fact
                WHERE start_time_unix_nano >= :start_ns
                  AND start_time_unix_nano < :end_ns
                  AND tenant_id = :tenant_id
            """)

            params = {
                "start_ns": time_range.start_time,
                "end_ns": time_range.end_time,
                "tenant_id": "default",
            }

            # Apply filters (simplified - full implementation would parse filter operators)
            if filters:
                for f in filters:
                    if f.field.startswith("attributes."):
                        attr_key = f.field.replace("attributes.", "")
                        query = text(str(query) + f' AND attributes @> \'{{ "{attr_key}": "{f.value}" }}\'')

            # Apply pagination
            limit = pagination.limit if pagination else 100
            query = text(str(query) + f" LIMIT {limit + 1}")

            result = await session.execute(query, params)
            trace_ids = [row[0] for row in result.fetchall()]

            has_more = len(trace_ids) > limit
            if has_more:
                trace_ids = trace_ids[:limit]

            # Fetch full traces for each trace_id
            traces = []
            for trace_id in trace_ids:
                trace = await self.get_trace_by_id(trace_id)
                if trace:
                    traces.append(trace)

            return traces, has_more, None

    async def get_trace_by_id(self, trace_id: str) -> dict[str, Any] | None:
        """
        Get trace by ID with all spans.

        Returns trace with spans ordered by start time.
        """
        async with self.db.session() as session:
            query = text("""
                SELECT
                    s.span_id, s.parent_span_id, s.start_time_unix_nano, s.end_time_unix_nano, s.duration,
                    s.status_code, s.kind, s.attributes, s.events, s.links,
                    srv.name, op.name, res.attributes
                FROM spans_fact s
                JOIN service_dim srv ON s.service_id = srv.id
                JOIN operation_dim op ON s.operation_id = op.id
                JOIN resource_dim res ON s.resource_id = res.id
                WHERE s.trace_id = :trace_id
                ORDER BY s.start_time_unix_nano
            """)

            result = await session.execute(query, {"trace_id": trace_id})
            rows = result.fetchall()

            if not rows:
                return None

            spans = []
            for row in rows:
                span = {
                    "spanId": row[0],
                    "parentSpanId": row[1],
                    "startTimeUnixNano": str(row[2]),
                    "endTimeUnixNano": str(row[3]),
                    "durationNs": row[4],
                    "statusCode": row[5],
                    "kind": row[6],
                    "attributes": json.loads(row[7]) if row[7] else {},
                    "events": json.loads(row[8]) if row[8] else [],
                    "links": json.loads(row[9]) if row[9] else [],
                    "serviceName": row[10],
                    "operationName": row[11],
                    "resource": row[12],
                }
                spans.append(span)

            return {
                "traceId": trace_id,
                "spans": spans,
            }

    # ==================== Log Storage ====================

    async def store_logs(self, resource_logs: list[dict[str, Any]]) -> int:
        """
        Store logs from OTLP ResourceLogs.

        Parses OTLP format and batch inserts log records into logs_fact.
        """
        if not resource_logs:
            return 0

        logs_to_insert = []

        try:
            async with self.db.session() as session:
                for resource_log in resource_logs:
                    resource = resource_log.get("resource", {})
                    resource_attrs = resource.get("attributes", [])
                    resource_dict = {attr.get("key"): attr.get("value") for attr in resource_attrs}

                    # Extract service.name and service.namespace from resource attributes
                    service_name = "unknown"
                    service_namespace = None
                    for attr in resource_attrs:
                        key = attr.get("key")
                        value = attr.get("value", {})
                        if key == "service.name":
                            service_name = value.get("stringValue", "unknown")
                        elif key == "service.namespace":
                            service_namespace = value.get("stringValue")

                    service_id = await self._upsert_service(session, service_name, service_namespace)
                    resource_id = await self._upsert_resource(session, resource_dict)

                    for scope_log in resource_log.get("scope_logs", []):
                        for log in scope_log.get("logRecords", []):
                            # Parse log attributes
                            attributes = {}
                            for attr in log.get("attributes", []):
                                key = attr.get("key")
                                value = attr.get("value", {})
                                if "stringValue" in value:
                                    attributes[key] = value["stringValue"]
                                elif "intValue" in value:
                                    attributes[key] = value["intValue"]

                            # Get trace/span context if present
                            trace_id = self._base64_to_hex(log.get("traceId", "")) if log.get("traceId") else None
                            span_id = self._base64_to_hex(log.get("spanId", "")) if log.get("spanId") else None

                            # Get body
                            body = log.get("body", {})
                            body_text = body.get("stringValue", "") if body else ""

                            log_data = {
                                "time_unix_nano": int(log.get("timeUnixNano", 0)),
                                "observed_time_unix_nano": int(log.get("observedTimeUnixNano", 0)),
                                "severity_number": log.get("severityNumber", 0),
                                "severity_text": log.get("severityText", ""),
                                "body": json.dumps({"stringValue": body_text}),
                                "attributes": json.dumps(attributes),
                                "resource": json.dumps(resource_dict),
                                "scope": json.dumps(scope_log.get("scope", {})),
                                "trace_id": trace_id,
                                "span_id": span_id,
                                "tenant_id": "default",
                            }
                            logs_to_insert.append(log_data)

                # Batch insert logs
                if logs_to_insert:
                    insert_stmt = text("""
                        INSERT INTO logs_fact (
                            time_unix_nano, observed_time_unix_nano,
                            severity_number, severity_text, body, attributes, resource, scope,
                            trace_id, span_id, tenant_id
                        ) VALUES (
                            :time_unix_nano, :observed_time_unix_nano,
                            :severity_number, :severity_text, :body::jsonb, :attributes::jsonb, :resource::jsonb, :scope::jsonb,
                            :trace_id, :span_id, :tenant_id
                        )
                    """)
                    await session.execute(insert_stmt, logs_to_insert)

            return len(logs_to_insert)
        except Exception as e:
            import logging

            logging.error(f"Failed to store logs: {e}", exc_info=True)
            return 0

    async def search_logs(
        self,
        time_range: TimeRange,
        _filters: list[Filter] | None = None,
        pagination: PaginationRequest | None = None,
    ) -> tuple[list[LogRecord], bool, str | None]:
        """Search logs with filters and pagination."""
        async with self.db.session() as session:
            query = text("""
                SELECT
                    l.id, l.time_unix_nano, l.observed_time_unix_nano,
                    l.severity_number, l.severity_text, l.body, l.attributes,
                    l.trace_id, l.span_id, l.resource
                FROM logs_fact l
                WHERE l.time_unix_nano >= :start_ns
                  AND l.time_unix_nano < :end_ns
                  AND l.tenant_id = :tenant_id
                ORDER BY l.time_unix_nano DESC
                LIMIT :limit
            """)

            limit = pagination.limit if pagination else 100
            params = {
                "start_ns": time_range.start_time,
                "end_ns": time_range.end_time,
                "tenant_id": "default",
                "limit": limit + 1,
            }

            result = await session.execute(query, params)
            rows = result.fetchall()

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            logs = []
            for row in rows:
                # Parse body JSONB
                body_jsonb = json.loads(row[5]) if row[5] else {}
                body_text = body_jsonb.get("stringValue", "") if isinstance(body_jsonb, dict) else str(body_jsonb)

                log_record = LogRecord(
                    log_id=str(row[0]),
                    timestamp_ns=row[1],
                    observed_timestamp_ns=row[2],
                    severity_number=row[3],
                    severity_text=row[4],
                    body=body_text,
                    attributes=json.loads(row[6]) if row[6] else {},
                    trace_id=row[7],
                    span_id=row[8],
                    service_name="unknown",  # Extract from resource if needed
                    resource=row[9],
                )
                logs.append(log_record)

            return logs, has_more, None

    # ==================== Metric Storage ====================

    async def store_metrics(self, _resource_metrics: list[dict[str, Any]]) -> int:
        """Store metrics from OTLP ResourceMetrics (simplified implementation)."""
        # For now, return 0 - full metric implementation is complex
        return 0

    async def search_metrics(
        self,
        _time_range: TimeRange,
        _metric_names: list[str] | None = None,
        _filters: list[Filter] | None = None,
        _pagination: PaginationRequest | None = None,
    ) -> tuple[list[Metric], bool, str | None]:
        """Search metrics (simplified implementation)."""
        return [], False, None

    # ==================== Service Catalog ====================

    async def get_services(self, time_range: TimeRange | None = None) -> list[Service]:
        """
        Get service catalog with RED metrics.

        Calculates Rate, Errors, Duration from spans_fact.
        """
        async with self.db.session() as session:
            # Build query with optional time range
            where_clause = "WHERE s.tenant_id = 'default'"
            params = {}

            if time_range:
                where_clause += " AND s.start_time_unix_nano >= :start_ns AND s.start_time_unix_nano < :end_ns"
                params["start_ns"] = time_range.start_time
                params["end_ns"] = time_range.end_time

            query = text(f"""
                SELECT
                    srv.name,
                    COUNT(*) AS request_count,
                    COUNT(*) FILTER (WHERE s.status_code = 2) AS error_count,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY s.duration) AS p50_duration_ns,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY s.duration) AS p95_duration_ns,
                    MIN(s.start_time_unix_nano) AS first_seen_ns,
                    MAX(s.start_time_unix_nano) AS last_seen_ns
                FROM spans_fact s
                JOIN service_dim srv ON s.service_id = srv.id
                {where_clause}
                GROUP BY srv.name
                ORDER BY request_count DESC
            """)

            result = await session.execute(query, params)
            rows = result.fetchall()

            services = []
            for row in rows:
                error_rate = (row[2] / row[1]) * 100 if row[1] > 0 else 0.0

                service = Service(
                    name=row[0],
                    request_count=row[1],
                    error_count=row[2],
                    error_rate=round(error_rate, 2),
                    p50_latency_ms=round(row[3] / 1_000_000, 2) if row[3] else 0.0,
                    p95_latency_ms=round(row[4] / 1_000_000, 2) if row[4] else 0.0,
                    first_seen=row[5],
                    last_seen=row[6],
                )
                services.append(service)

            return services

    async def get_service_map(self, time_range: TimeRange) -> tuple[list[ServiceMapNode], list[ServiceMapEdge]]:
        """
        Get service dependency map from spans.

        Builds graph from parent-child span relationships.
        """
        async with self.db.session() as session:
            # Get service-to-service edges
            query = text("""
                SELECT
                    srv_parent.name AS source,
                    srv_child.name AS target,
                    COUNT(*) AS call_count
                FROM spans_fact s_child
                JOIN spans_fact s_parent ON s_child.parent_span_id = s_parent.span_id
                    AND s_child.trace_id = s_parent.trace_id
                JOIN service_dim srv_child ON s_child.service_id = srv_child.id
                JOIN service_dim srv_parent ON s_parent.service_id = srv_parent.id
                WHERE s_child.start_time_unix_nano >= :start_ns
                  AND s_child.start_time_unix_nano < :end_ns
                  AND s_child.tenant_id = :tenant_id
                  AND srv_child.name != srv_parent.name
                GROUP BY srv_parent.name, srv_child.name
            """)

            result = await session.execute(
                query, {"start_ns": time_range.start_time, "end_ns": time_range.end_time, "tenant_id": "default"}
            )
            rows = result.fetchall()

            # Build nodes and edges
            node_map = {}
            edges = []

            for row in rows:
                source = row[0]
                target = row[1]
                call_count = row[2]

                # Add nodes if not exists
                if source not in node_map:
                    node_map[source] = ServiceMapNode(id=source, name=source, type="service")
                if target not in node_map:
                    node_map[target] = ServiceMapNode(id=target, name=target, type="service")

                # Add edge
                edge = ServiceMapEdge(source=source, target=target, call_count=call_count)
                edges.append(edge)

            nodes = list(node_map.values())
            return nodes, edges
