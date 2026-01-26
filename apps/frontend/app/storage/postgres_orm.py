"""PostgreSQL storage implementation using SQLModel ORM.

This replaces raw SQL construction with type-safe ORM operations.
No more field name mismatches or manual SQL string building.
"""

import hashlib
import json
import logging
from base64 import b64decode
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.models.database import LogsFact, MetricsFact, OperationDim, ResourceDim, ServiceDim, SpansFact


def _timestamp_to_rfc3339(ts: datetime, nanos_fraction: int = 0) -> str:
    """Convert Python datetime + nanosecond fraction to RFC3339 timestamp string.

    Args:
        ts: Python datetime object (microsecond precision from PostgreSQL TIMESTAMPTZ)
        nanos_fraction: Additional nanoseconds (0-999) beyond microsecond precision

    Returns:
        RFC3339 formatted timestamp string with nanosecond precision
        Example: "2026-01-25T17:30:45.123456789Z"
    """
    # Get microseconds from datetime (PostgreSQL TIMESTAMPTZ has microsecond precision)
    micros = ts.microsecond
    # Convert to nanoseconds and add the additional nanos_fraction
    nanos = micros * 1000 + nanos_fraction
    # Format with full nanosecond precision
    return f"{ts.strftime('%Y-%m-%dT%H:%M:%S')}.{nanos:09d}Z"


def _rfc3339_to_timestamp_nanos(rfc: str) -> tuple[datetime, int]:
    """Convert RFC3339 timestamp string to Python datetime + nanosecond fraction.

    Args:
        rfc: RFC3339 formatted timestamp string
        Examples: "2026-01-25T17:30:45.123456789Z", "2026-01-25T17:30:45Z"

    Returns:
        Tuple of (datetime with microsecond precision, nanos_fraction 0-999)
    """
    # Remove 'Z' suffix if present
    rfc = rfc.rstrip("Z")

    # Split seconds and fractional part
    if "." in rfc:
        base, frac = rfc.rsplit(".", 1)
        # Pad or truncate to 9 digits (nanoseconds)
        frac = frac.ljust(9, "0")[:9]
        # Split into microseconds (first 6 digits) and nanos_fraction (last 3 digits)
        micros = int(frac[:6])
        nanos_fraction = int(frac[6:9])
    else:
        base = rfc
        micros = 0
        nanos_fraction = 0

    # Parse datetime with microsecond precision
    dt = datetime.fromisoformat(base)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC, microsecond=micros)
    else:
        dt = dt.replace(microsecond=micros)

    return dt, nanos_fraction


def _nanoseconds_to_timestamp_nanos(ns: int) -> tuple[datetime, int]:
    """Convert nanoseconds since Unix epoch to Python datetime + nanosecond fraction.

    Used for converting OTLP nanosecond timestamps to PostgreSQL TIMESTAMPTZ + nanos_fraction.

    Args:
        ns: Nanoseconds since Unix epoch (1970-01-01T00:00:00Z)

    Returns:
        Tuple of (datetime with microsecond precision, nanos_fraction 0-999)
    """
    # Split nanoseconds into seconds, microseconds, and nanos_fraction
    seconds = ns // 1_000_000_000
    remainder_nanos = ns % 1_000_000_000
    micros = remainder_nanos // 1000
    nanos_fraction = remainder_nanos % 1000

    # Create datetime with microsecond precision
    dt = datetime.fromtimestamp(seconds, tz=UTC)
    dt = dt.replace(microsecond=micros)

    return dt, nanos_fraction


def _timestamp_nanos_to_nanoseconds(ts: datetime, nanos_fraction: int = 0) -> int:
    """Convert Python datetime + nanosecond fraction to nanoseconds since Unix epoch.

    Used for API time range queries (which still use nanosecond integers).

    Args:
        ts: Python datetime object
        nanos_fraction: Additional nanoseconds (0-999)

    Returns:
        Nanoseconds since Unix epoch (1970-01-01T00:00:00Z)
    """
    seconds = int(ts.timestamp())
    micros = ts.microsecond
    return seconds * 1_000_000_000 + micros * 1000 + nanos_fraction


def _calculate_duration_seconds(start_ts: datetime, start_nanos: int, end_ts: datetime, end_nanos: int) -> float:
    """Calculate duration in seconds from timestamp + nanos_fraction pairs.

    Args:
        start_ts: Start datetime
        start_nanos: Start nanosecond fraction (0-999)
        end_ts: End datetime
        end_nanos: End nanosecond fraction (0-999)

    Returns:
        Duration in seconds with fractional precision
        Example: 1.234567890 (1 second and 234567890 nanoseconds)
    """
    start_ns = _timestamp_nanos_to_nanoseconds(start_ts, start_nanos)
    end_ns = _timestamp_nanos_to_nanoseconds(end_ts, end_nanos)
    return (end_ns - start_ns) / 1_000_000_000


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
            return attr_value["int_value"]
        if "double_value" in attr_value:
            return attr_value["double_value"]
        if "bool_value" in attr_value:
            return attr_value["bool_value"]
        return None

    @staticmethod
    def _apply_namespace_filtering(stmt: Any, filters: list | None) -> tuple[Any, list]:
        """Apply namespace filtering with proper JOIN strategy and OR logic.

        Returns:
            tuple: (modified statement, list of namespace filters)
        """
        from sqlalchemy import or_

        from app.models.database import NamespaceDim, ServiceDim

        # Extract namespace filters
        namespace_filters = []
        if filters:
            namespace_filters = [f for f in filters if f.field == "service_namespace"]

        # Determine if we need INNER or OUTER join to NamespaceDim
        # Use INNER join if filtering for any non-empty namespace, else OUTER join
        use_inner_join = any(f.value != "" for f in namespace_filters)

        if use_inner_join:
            stmt = stmt.join(NamespaceDim, ServiceDim.namespace_id == NamespaceDim.id)
        else:
            stmt = stmt.outerjoin(NamespaceDim, ServiceDim.namespace_id == NamespaceDim.id)

        # Apply namespace filters with OR logic
        if namespace_filters:
            namespace_conditions = []
            for f in namespace_filters:
                if f.value == "":
                    namespace_conditions.append(ServiceDim.namespace_id.is_(None))
                else:
                    namespace_conditions.append(NamespaceDim.namespace == f.value)

            if namespace_conditions:
                stmt = stmt.where(or_(*namespace_conditions))

        return stmt, namespace_filters

    @staticmethod
    def _apply_traceid_filter(fact_model: Any, stmt: Any, filters: list | None) -> tuple[Any, list]:
        """Apply trace_id filtering with support for NULL values (valid for logs).

        Args:
            fact_model: The fact table model class (LogsFact, SpansFact, etc.)
            stmt: SQLAlchemy select statement
            filters: List of Filter objects

        Returns:
            tuple: (modified statement, list of traceid filters)
        """
        from sqlalchemy import or_

        # Extract trace_id filters
        traceid_filters = []
        if filters:
            traceid_filters = [f for f in filters if f.field == "trace_id"]

        # Apply trace_id filters with OR logic
        if traceid_filters:
            traceid_conditions = []
            for f in traceid_filters:
                if f.value == "" or f.value is None or f.value.lower() == "null":
                    # NULL trace_id is valid for logs (not correlated with traces)
                    traceid_conditions.append(fact_model.trace_id.is_(None))
                else:
                    traceid_conditions.append(fact_model.trace_id == f.value)

            if traceid_conditions:
                stmt = stmt.where(or_(*traceid_conditions))

        return stmt, traceid_filters

    @staticmethod
    def _apply_spanid_filter(fact_model: Any, stmt: Any, filters: list | None) -> tuple[Any, list]:
        """Apply span_id filtering. NULL span_id is never valid, always filter by value.

        Args:
            fact_model: The fact table model class (LogsFact, SpansFact, etc.)
            stmt: SQLAlchemy select statement
            filters: List of Filter objects

        Returns:
            tuple: (modified statement, list of spanid filters)
        """
        from sqlalchemy import or_

        # Extract span_id filters (never allow NULL)
        spanid_filters = []
        if filters:
            spanid_filters = [f for f in filters if f.field == "span_id" and f.value and f.value.lower() != "null"]

        # Apply span_id filters with OR logic
        if spanid_filters:
            spanid_conditions = [fact_model.span_id == f.value for f in spanid_filters]
            if spanid_conditions:
                stmt = stmt.where(or_(*spanid_conditions))

        return stmt, spanid_filters

    @staticmethod
    def _apply_log_level_filter(stmt: Any, filters: list | None) -> tuple[Any, list]:
        """Apply log level filtering using OTel severity_number ranges.

        OTel Severity Mapping:
        - TRACE: 1-4
        - DEBUG: 5-8
        - INFO: 9-12
        - WARN: 13-16
        - ERROR: 17-20
        - FATAL: 21-24

        Args:
            stmt: SQLAlchemy select statement
            filters: List of Filter objects

        Returns:
            tuple: (modified statement, list of log_level filters)
        """
        from sqlalchemy import or_

        from app.models.database import LogsFact

        # Define severity_number ranges per OTel spec
        SEVERITY_RANGES = {
            "TRACE": (1, 4),
            "DEBUG": (5, 8),
            "INFO": (9, 12),
            "WARN": (13, 16),
            "ERROR": (17, 20),
            "FATAL": (21, 24),
        }

        # Extract log_level filters
        log_level_filters = []
        if filters:
            log_level_filters = [f for f in filters if f.field == "log_level"]

        # Apply log level filters with OR logic using severity_number ranges
        if log_level_filters:
            level_conditions = []
            for f in log_level_filters:
                level_upper = f.value.upper()
                if level_upper in SEVERITY_RANGES:
                    min_sev, max_sev = SEVERITY_RANGES[level_upper]
                    level_conditions.append(LogsFact.severity_number.between(min_sev, max_sev))

            if level_conditions:
                stmt = stmt.where(or_(*level_conditions))

        return stmt, log_level_filters

    @staticmethod
    def _apply_http_status_filter(stmt: Any, filters: list | None) -> tuple[Any, list]:
        """Apply HTTP status code filtering using ranges (2xx, 4xx, 5xx) or unknown (NULL).

        Status code is extracted from span attributes (http.status_code).

        Args:
            stmt: SQLAlchemy select statement
            filters: List of Filter objects

        Returns:
            tuple: (modified statement, list of http_status filters)
        """
        from sqlalchemy import cast, or_
        from sqlalchemy.dialects.postgresql import INTEGER

        from app.models.database import SpansFact

        # Extract http_status filters
        http_status_filters = []
        if filters:
            http_status_filters = [f for f in filters if f.field == "http_status"]

        # Apply HTTP status filters with OR logic
        if http_status_filters:
            status_conditions = []
            for f in http_status_filters:
                value = f.value.lower()
                if value == "2xx":
                    # Match 200-299 in attributes->'http.status_code'
                    status_conditions.append(
                        cast(SpansFact.attributes["http.status_code"].as_string(), INTEGER).between(200, 299)
                    )
                elif value == "4xx":
                    # Match 400-499
                    status_conditions.append(
                        cast(SpansFact.attributes["http.status_code"].as_string(), INTEGER).between(400, 499)
                    )
                elif value == "5xx":
                    # Match 500-599
                    status_conditions.append(
                        cast(SpansFact.attributes["http.status_code"].as_string(), INTEGER).between(500, 599)
                    )
                elif value == "unknown":
                    # Match NULL or missing http.status_code
                    status_conditions.append(
                        or_(
                            SpansFact.attributes["http.status_code"].is_(None),
                            ~SpansFact.attributes.has_key("http.status_code"),
                        )
                    )

            if status_conditions:
                stmt = stmt.where(or_(*status_conditions))

        return stmt, http_status_filters

    async def _get_unknown_tenant_id(self, session: AsyncSession) -> int:
        """Get the ID for the 'unknown' tenant from tenant_dim."""
        from app.models.database import TenantDim

        stmt = select(TenantDim.id).where(TenantDim.name == "unknown")
        result = await session.execute(stmt)
        tenant_id = result.scalar()
        if tenant_id is None:
            msg = "No 'unknown' tenant found in tenant_dim - database not properly seeded"
            raise ValueError(msg)
        return tenant_id

    async def _get_unknown_connection_id(self, session: AsyncSession) -> int:
        """Get the ID for the 'unknown' connection from connection_dim."""
        from app.models.database import ConnectionDim

        stmt = select(ConnectionDim.id).where(ConnectionDim.name == "unknown")
        result = await session.execute(stmt)
        connection_id = result.scalar()
        if connection_id is None:
            msg = "No 'unknown' connection found in connection_dim - database not properly seeded"
            raise ValueError(msg)
        return connection_id

    async def _upsert_namespace(self, session: AsyncSession, namespace: str | None = None) -> int:
        """Upsert namespace and return ID. Commits immediately for multi-process safety."""
        from datetime import datetime, timedelta

        from app.models.database import NamespaceDim

        now = datetime.utcnow()
        threshold = now - timedelta(minutes=30)

        # Get the 'unknown' tenant_id
        tenant_id = await self._get_unknown_tenant_id(session)

        # Insert or update
        stmt = (
            insert(NamespaceDim)
            .values(tenant_id=tenant_id, namespace=namespace, first_seen=now, last_seen=now)
            .on_conflict_do_update(
                index_elements=["tenant_id", "namespace"],
                set_={"last_seen": now},
                where=NamespaceDim.last_seen < threshold,
            )
        )
        await session.execute(stmt)
        await session.commit()  # Commit immediately for multi-process safety

        # Now SELECT to get the ID (handle NULL namespace with IS NULL)
        if namespace is None:
            stmt = select(NamespaceDim.id).where(NamespaceDim.namespace.is_(None))
        else:
            stmt = select(NamespaceDim.id).where(NamespaceDim.namespace == namespace)
        result = await session.execute(stmt)
        namespace_id = result.scalar()
        logging.info(f"_upsert_namespace: namespace={namespace} returned namespace_id={namespace_id}")
        return namespace_id

    async def _upsert_service(self, session: AsyncSession, name: str, namespace: str | None = None) -> int:
        """Upsert service and return ID. Commits immediately for multi-process safety."""
        from datetime import datetime, timedelta

        # First upsert namespace (commits internally)
        namespace_id = await self._upsert_namespace(session, namespace)
        logging.info(f"_upsert_service: name={name}, namespace={namespace}, got namespace_id={namespace_id}")

        now = datetime.utcnow()
        threshold = now - timedelta(minutes=30)

        # Get the 'unknown' tenant_id
        tenant_id = await self._get_unknown_tenant_id(session)

        # Then upsert service with namespace_id
        stmt = (
            insert(ServiceDim)
            .values(tenant_id=tenant_id, name=name, namespace_id=namespace_id, first_seen=now, last_seen=now)
            .on_conflict_do_update(
                index_elements=["name", "namespace_id"],
                set_={"last_seen": now},
                where=ServiceDim.last_seen < threshold,
            )
        )
        await session.execute(stmt)
        await session.commit()  # Commit immediately for multi-process safety

        # Now SELECT to get the ID
        stmt = select(ServiceDim.id).where(ServiceDim.name == name, ServiceDim.namespace_id == namespace_id)
        result = await session.execute(stmt)
        service_id = result.scalar()
        logging.info(
            f"_upsert_service: inserted/updated service_id={service_id} for name={name}, namespace_id={namespace_id}"
        )
        return service_id

    async def _upsert_operation(
        self, session: AsyncSession, service_id: int, name: str, span_kind: int | None = None
    ) -> int:
        """Upsert operation and return ID. Commits immediately for multi-process safety."""
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        threshold = now - timedelta(minutes=30)

        # Get the 'unknown' tenant_id
        tenant_id = await self._get_unknown_tenant_id(session)

        stmt = (
            insert(OperationDim)
            .values(
                tenant_id=tenant_id,
                service_id=service_id,
                name=name,
                span_kind=span_kind,
                first_seen=now,
                last_seen=now,
            )
            .on_conflict_do_update(
                index_elements=["tenant_id", "service_id", "name", "span_kind"],
                set_={"last_seen": now},
                where=OperationDim.last_seen < threshold,
            )
        )
        await session.execute(stmt)
        await session.commit()  # Commit immediately

        # SELECT to get ID
        stmt = select(OperationDim.id).where(
            OperationDim.tenant_id == tenant_id,
            OperationDim.service_id == service_id,
            OperationDim.name == name,
            OperationDim.span_kind == span_kind,
        )
        result = await session.execute(stmt)
        operation_id = result.scalar()
        return operation_id

    async def _upsert_resource(self, session: AsyncSession, attributes: dict) -> int:
        """Upsert resource and return ID. Only update last_seen if >30 min since last update."""
        from datetime import datetime, timedelta

        resource_json = json.dumps(attributes, sort_keys=True)
        resource_hash = hashlib.sha256(resource_json.encode()).hexdigest()

        now = datetime.utcnow()
        threshold = now - timedelta(minutes=30)

        # Get the 'unknown' tenant_id
        tenant_id = await self._get_unknown_tenant_id(session)

        stmt = (
            insert(ResourceDim)
            .values(
                tenant_id=tenant_id,
                resource_hash=resource_hash,
                attributes=attributes,
                first_seen=now,
                last_seen=now,
            )
            .on_conflict_do_update(
                index_elements=["tenant_id", "resource_hash"],
                set_={"last_seen": now},
                where=ResourceDim.last_seen < threshold,
            )
            .returning(ResourceDim.id)
        )
        result = await session.execute(stmt)
        resource_id = result.scalar()
        return resource_id

    async def store_traces(self, resource_spans: list[dict]) -> int:
        """Store OTLP traces using SQLModel ORM.

        OTLP structure (with preserving_proto_field_name=True):
        resource_spans: []
          ├─ resource: { attributes: [] }
          └─ scope_spans: []  # snake_case
              ├─ scope: {}
              └─ spans: []
        """
        if not resource_spans:
            return 0

        logging.info(f"store_traces called with {len(resource_spans)} resource_spans")

        spans_to_insert = []

        async with AsyncSession(self.engine) as session:
            # Get unknown tenant_id and connection_id once for all spans
            tenant_id = await self._get_unknown_tenant_id(session)
            connection_id = await self._get_unknown_connection_id(session)

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

                # Use snake_case (preserving_proto_field_name=True)
                for scope_span in resource_span.get("scope_spans", []):
                    scope = scope_span.get("scope", {})

                    for span in scope_span.get("spans", []):
                        # IDs - convert base64 to hex
                        trace_id_raw = span.get("trace_id", "")
                        span_id_raw = span.get("span_id", "")

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

                        parent_span_id_raw = span.get("parent_span_id")
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

                        # Timestamps - use snake_case
                        start_time_raw = span.get("start_time_unix_nano", "0")
                        end_time_raw = span.get("end_time_unix_nano", "0")
                        start_time_ns = int(start_time_raw) if start_time_raw else 0
                        end_time_ns = int(end_time_raw) if end_time_raw else 0

                        # Convert nanoseconds to timestamp + nanos_fraction
                        start_timestamp, start_nanos_fraction = _nanoseconds_to_timestamp_nanos(start_time_ns)
                        end_timestamp, end_nanos_fraction = _nanoseconds_to_timestamp_nanos(end_time_ns)

                        operation_id = await self._upsert_operation(session, service_id, name, kind)

                        status = span.get("status", {})
                        status_code = self._normalize_status_code(status.get("code"))
                        status_message = status.get("message")

                        attrs_list = span.get("attributes", [])
                        attributes = {attr["key"]: attr.get("value") for attr in attrs_list}

                        span_obj = SpansFact(
                            tenant_id=tenant_id,
                            connection_id=connection_id,
                            trace_id=trace_id,
                            span_id=span_id,
                            parent_span_id=parent_span_id,
                            name=name,
                            kind=kind,
                            status_code=status_code,
                            status_message=status_message,
                            start_timestamp=start_timestamp,
                            start_nanos_fraction=start_nanos_fraction,
                            end_timestamp=end_timestamp,
                            end_nanos_fraction=end_nanos_fraction,
                            service_id=service_id,
                            operation_id=operation_id,
                            resource_id=resource_id,
                            attributes=attributes,
                            events=span.get("events", []),
                            links=span.get("links", []),
                            resource=resource_dict,
                            scope=scope,
                            flags=span.get("flags", 0),
                            dropped_attributes_count=span.get("dropped_attributes_count", 0),
                            dropped_events_count=span.get("dropped_events_count", 0),
                            dropped_links_count=span.get("dropped_links_count", 0),
                        )
                        spans_to_insert.append(span_obj)

            if spans_to_insert:
                session.add_all(spans_to_insert)
                await session.commit()

        return len(spans_to_insert)

    async def store_logs(self, resource_logs: list[dict]) -> int:
        """Store OTLP logs using SQLModel ORM.

        OTLP structure (with preserving_proto_field_name=True):
        resource_logs: []
          ├─ resource: { attributes: [] }
          └─ scope_logs: []  # snake_case
              ├─ scope: {}
              └─ log_records: []  # snake_case
        """
        if not resource_logs:
            return 0

        logs_to_insert = []

        async with AsyncSession(self.engine) as session:
            # Get unknown tenant_id and connection_id once for all logs
            tenant_id = await self._get_unknown_tenant_id(session)
            connection_id = await self._get_unknown_connection_id(session)

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

                # Use snake_case (preserving_proto_field_name=True)
                for scope_log in resource_log.get("scope_logs", []):
                    scope = scope_log.get("scope", {})

                    for log_record in scope_log.get("log_records", []):
                        # IDs - convert base64 to hex
                        trace_id = log_record.get("trace_id")
                        span_id = log_record.get("span_id")
                        if trace_id:
                            trace_id = self._base64_to_hex(trace_id)
                        if span_id:
                            span_id = self._base64_to_hex(span_id)

                        # Timestamps - use snake_case
                        time_unix_nano_raw = log_record.get("time_unix_nano", "0")
                        observed_time_unix_nano_raw = log_record.get("observed_time_unix_nano")
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

                        # Convert nanoseconds to timestamp + nanos_fraction
                        timestamp, nanos_fraction = _nanoseconds_to_timestamp_nanos(time_unix_nano)
                        if observed_time_unix_nano:
                            observed_timestamp, observed_nanos_fraction = _nanoseconds_to_timestamp_nanos(
                                observed_time_unix_nano
                            )
                        else:
                            observed_timestamp = None
                            observed_nanos_fraction = 0

                        # Severity - use snake_case
                        severity_number = self._normalize_severity_number(log_record.get("severity_number"))
                        severity_text = log_record.get("severity_text")

                        body = log_record.get("body", {})

                        attrs_list = log_record.get("attributes", [])
                        attributes = {attr["key"]: attr.get("value") for attr in attrs_list}

                        log_obj = LogsFact(
                            tenant_id=tenant_id,
                            connection_id=connection_id,
                            trace_id=trace_id,
                            span_id=span_id,
                            timestamp=timestamp,
                            nanos_fraction=nanos_fraction,
                            observed_timestamp=observed_timestamp,
                            observed_nanos_fraction=observed_nanos_fraction,
                            severity_number=severity_number,
                            severity_text=severity_text,
                            body=body,
                            attributes=attributes,
                            resource=resource_dict,
                            scope=scope,
                            service_id=service_id,
                            flags=log_record.get("flags", 0),
                            dropped_attributes_count=log_record.get("dropped_attributes_count", 0),
                        )
                        logs_to_insert.append(log_obj)

            if logs_to_insert:
                session.add_all(logs_to_insert)
                await session.commit()

        return len(logs_to_insert)

    async def store_metrics(self, resource_metrics: list[dict]) -> int:
        """Store OTLP metrics using SQLModel ORM.

        OTLP structure (with preserving_proto_field_name=True):
        resource_metrics: []
          ├─ resource: { attributes: [] }
          └─ scope_metrics: []  # snake_case
              ├─ scope: {}
              └─ metrics: []
                  └─ [gauge|sum|histogram|summary]: { data_points: [] }  # snake_case
        """
        if not resource_metrics:
            return 0

        metrics_to_insert = []

        async with AsyncSession(self.engine) as session:
            # Get unknown tenant_id and connection_id once for all metrics
            tenant_id = await self._get_unknown_tenant_id(session)
            connection_id = await self._get_unknown_connection_id(session)

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

                # Use snake_case (preserving_proto_field_name=True)
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

                        # Use snake_case for data_points
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
                            # Timestamps - use snake_case
                            time_unix_nano_str = dp.get("time_unix_nano", "0")
                            time_unix_nano = int(time_unix_nano_str) if time_unix_nano_str else 0

                            start_time_unix_nano_str = dp.get("start_time_unix_nano")
                            start_time_unix_nano = int(start_time_unix_nano_str) if start_time_unix_nano_str else None

                            # Convert nanoseconds to timestamp + nanos_fraction
                            timestamp, nanos_fraction = _nanoseconds_to_timestamp_nanos(time_unix_nano)
                            if start_time_unix_nano:
                                start_timestamp, start_nanos_fraction = _nanoseconds_to_timestamp_nanos(
                                    start_time_unix_nano
                                )
                            else:
                                start_timestamp = None
                                start_nanos_fraction = 0

                            dp_attrs_list = dp.get("attributes", [])
                            dp_attributes = {attr["key"]: attr.get("value") for attr in dp_attrs_list}

                            metric_obj = MetricsFact(
                                tenant_id=tenant_id,
                                connection_id=connection_id,
                                metric_name=metric_name,
                                metric_type=metric_type,
                                unit=unit,
                                description=description,
                                timestamp=timestamp,
                                nanos_fraction=nanos_fraction,
                                start_timestamp=start_timestamp,
                                start_nanos_fraction=start_nanos_fraction,
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

        # Convert RFC3339 to timestamps
        from datetime import datetime

        start_ts = datetime.fromisoformat(time_range.start_time.replace("Z", "+00:00"))
        end_ts = datetime.fromisoformat(time_range.end_time.replace("Z", "+00:00"))

        async with AsyncSession(self.engine) as session:
            # Get the unknown tenant_id
            tenant_id = await self._get_unknown_tenant_id(session)

            limit = pagination.limit if pagination else 100

            # ORM query for distinct trace IDs with min start time for ordering
            # Use GROUP BY to get earliest span per trace for ordering
            stmt = select(SpansFact.trace_id, func.min(SpansFact.start_timestamp).label("earliest_span")).where(
                SpansFact.start_timestamp >= start_ts,
                SpansFact.start_timestamp < end_ts,
                SpansFact.tenant_id == tenant_id,
            )

            # Apply trace_id filtering (never NULL for spans)
            stmt, _ = self._apply_traceid_filter(SpansFact, stmt, filters)

            # Apply span_id filtering (never NULL)
            stmt, _ = self._apply_spanid_filter(SpansFact, stmt, filters)

            # Apply HTTP status filtering
            stmt, _ = self._apply_http_status_filter(stmt, filters)

            stmt = (
                stmt.group_by(SpansFact.trace_id).order_by(func.min(SpansFact.start_timestamp).desc()).limit(limit + 1)
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
            # Get the unknown tenant_id
            tenant_id = await self._get_unknown_tenant_id(session)

            # ORM query with outer join to ServiceDim
            stmt = (
                select(SpansFact, ServiceDim.name)
                .outerjoin(ServiceDim, SpansFact.service_id == ServiceDim.id)
                .where(
                    SpansFact.trace_id == trace_id,
                    SpansFact.tenant_id == tenant_id,
                )
                .order_by(SpansFact.start_timestamp.asc())
            )

            result = await session.execute(stmt)
            rows = result.fetchall()

            if not rows:
                return None

            spans = []
            for span, service_name in rows:
                # Convert timestamps to RFC3339
                start_time = _timestamp_to_rfc3339(span.start_timestamp, span.start_nanos_fraction)
                end_time = _timestamp_to_rfc3339(span.end_timestamp, span.end_nanos_fraction)
                duration_seconds = _calculate_duration_seconds(
                    span.start_timestamp, span.start_nanos_fraction, span.end_timestamp, span.end_nanos_fraction
                )

                span_dict = {
                    "trace_id": self._bytes_to_hex(span.trace_id),
                    "span_id": self._bytes_to_hex(span.span_id),
                    "parent_span_id": self._bytes_to_hex(span.parent_span_id),
                    "name": span.name,
                    "kind": span.kind,
                    "status": {"code": span.status_code, "message": span.status_message}
                    if span.status_code is not None
                    else None,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_seconds": duration_seconds,
                    "attributes": span.attributes if span.attributes else {},
                    "events": span.events if span.events else [],
                    "links": span.links if span.links else [],
                    "service_name": service_name,
                    "resource": span.resource if span.resource else {},
                }
                spans.append(span_dict)

            return {"trace_id": trace_id, "spans": spans}

    async def search_spans(
        self,
        time_range: Any,
        filters: list | None = None,
        pagination: Any | None = None,
    ) -> tuple[list, bool, str | None]:
        """Search spans with filters and pagination using ORM."""
        if not self.engine:
            return [], False, None

        async with AsyncSession(self.engine) as session:
            # Get the unknown tenant_id
            tenant_id = await self._get_unknown_tenant_id(session)

            from app.models.database import NamespaceDim

            limit = pagination.limit if pagination else 100

            # ORM query with JOIN to ServiceDim and NamespaceDim
            stmt = (
                select(SpansFact, ServiceDim.name, NamespaceDim.namespace)
                .outerjoin(ServiceDim, SpansFact.service_id == ServiceDim.id)
                .outerjoin(NamespaceDim, ServiceDim.namespace_id == NamespaceDim.id)
            )

            # Apply namespace filtering
            if filters:
                namespace_filters = [f for f in filters if f.field == "service_namespace"]
                if namespace_filters:
                    from sqlalchemy import or_

                    namespace_conditions = []
                    for f in namespace_filters:
                        if f.value == "":
                            namespace_conditions.append(ServiceDim.namespace_id.is_(None))
                        else:
                            namespace_conditions.append(NamespaceDim.namespace == f.value)
                    if namespace_conditions:
                        stmt = stmt.where(or_(*namespace_conditions))

            # Apply trace_id filtering (never NULL for spans)
            stmt, _ = self._apply_traceid_filter(SpansFact, stmt, filters)

            # Apply span_id filtering (never NULL)
            stmt, _ = self._apply_spanid_filter(SpansFact, stmt, filters)

            # Apply HTTP status filtering
            stmt, _ = self._apply_http_status_filter(stmt, filters)

            # Convert RFC3339 to timestamps
            from datetime import datetime

            start_timestamp = datetime.fromisoformat(time_range.start_time.replace("Z", "+00:00"))
            end_timestamp = datetime.fromisoformat(time_range.end_time.replace("Z", "+00:00"))

            stmt = stmt.where(
                SpansFact.start_timestamp >= start_timestamp,
                SpansFact.start_timestamp < end_timestamp,
                SpansFact.tenant_id == tenant_id,
            )

            # Apply other filters (non-namespace, non-traceid, non-spanid, non-http_status)
            if filters:
                excluded_fields = {"service_namespace", "trace_id", "span_id", "http_status"}
                for f in filters:
                    if f.field in excluded_fields:
                        continue  # Already handled by filter helpers
                    elif f.field == "service_name":
                        if f.operator == "equals":
                            stmt = stmt.where(ServiceDim.name == f.value)
                        elif f.operator == "contains":
                            stmt = stmt.where(ServiceDim.name.contains(f.value))

            stmt = stmt.order_by(SpansFact.start_timestamp.desc()).limit(limit + 1)

            result = await session.execute(stmt)
            rows = result.fetchall()

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            from app.models.api import Span, SpanAttribute

            spans = []
            for span, _service_name, _service_namespace in rows:
                # Convert attributes dict to list of {key, value} pairs for API model
                attributes_dict = span.attributes if span.attributes else {}
                attributes_list = []
                for key, value in attributes_dict.items():
                    attributes_list.append(SpanAttribute(key=key, value=value))

                # Convert timestamps to RFC3339
                start_time = _timestamp_to_rfc3339(span.start_timestamp, span.start_nanos_fraction)
                end_time = _timestamp_to_rfc3339(span.end_timestamp, span.end_nanos_fraction)
                duration_seconds = _calculate_duration_seconds(
                    span.start_timestamp, span.start_nanos_fraction, span.end_timestamp, span.end_nanos_fraction
                )

                span_obj = Span(
                    trace_id=self._bytes_to_hex(span.trace_id),
                    span_id=self._bytes_to_hex(span.span_id),
                    parent_span_id=self._bytes_to_hex(span.parent_span_id) if span.parent_span_id else None,
                    name=span.name,
                    kind=span.kind,
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=duration_seconds,
                    attributes=attributes_list,
                    events=span.events if span.events else [],
                    links=span.links if span.links else [],
                    status={"code": span.status_code, "message": span.status_message}
                    if span.status_code is not None
                    else None,
                    resource=span.resource if span.resource else {},
                )
                spans.append(span_obj)

            return spans, has_more, None

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
            # Get the unknown tenant_id
            tenant_id = await self._get_unknown_tenant_id(session)

            from app.models.database import NamespaceDim

            limit = pagination.limit if pagination else 100

            # ORM query with JOIN to ServiceDim (NamespaceDim JOIN handled by _apply_namespace_filtering)
            stmt = select(LogsFact, ServiceDim.name, NamespaceDim.namespace).outerjoin(
                ServiceDim, LogsFact.service_id == ServiceDim.id
            )

            # Apply namespace filtering with proper JOIN strategy (adds NamespaceDim JOIN)
            stmt, _ = self._apply_namespace_filtering(stmt, filters)

            # Apply trace_id filtering (NULL is valid for logs)
            stmt, _ = self._apply_traceid_filter(LogsFact, stmt, filters)

            # Apply span_id filtering (never NULL)
            stmt, _ = self._apply_spanid_filter(LogsFact, stmt, filters)

            # Apply log level filtering using severity_number ranges
            stmt, _ = self._apply_log_level_filter(stmt, filters)

            # Convert RFC3339 strings to timestamps for query
            from datetime import datetime

            start_timestamp = datetime.fromisoformat(time_range.start_time.replace("Z", "+00:00"))
            end_timestamp = datetime.fromisoformat(time_range.end_time.replace("Z", "+00:00"))

            stmt = stmt.where(
                LogsFact.timestamp >= start_timestamp,
                LogsFact.timestamp < end_timestamp,
                LogsFact.tenant_id == tenant_id,
            )

            # Apply other filters (non-namespace, non-traceid, non-spanid, non-log_level)
            if filters:
                excluded_fields = {"service_namespace", "trace_id", "span_id", "log_level"}
                for f in filters:
                    if f.field in excluded_fields:
                        continue  # Already handled by filter helpers
                    elif f.field == "service_name":
                        if f.operator == "equals":
                            stmt = stmt.where(ServiceDim.name == f.value)
                        elif f.operator == "contains":
                            stmt = stmt.where(ServiceDim.name.contains(f.value))

            stmt = stmt.order_by(LogsFact.timestamp.desc()).limit(limit + 1)

            result = await session.execute(stmt)
            rows = result.fetchall()

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            from app.models.api import LogRecord

            logs = []
            for log, service_name, service_namespace in rows:
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

                # Convert timestamps to RFC3339
                timestamp = _timestamp_to_rfc3339(log.timestamp, log.nanos_fraction)
                observed_timestamp = (
                    _timestamp_to_rfc3339(log.observed_timestamp, log.observed_nanos_fraction)
                    if log.observed_timestamp
                    else None
                )

                log_record = LogRecord(
                    log_id=str(log.id),
                    timestamp=timestamp,
                    observed_timestamp=observed_timestamp,
                    severity_number=log.severity_number,
                    severity_text=log.severity_text,
                    body=body_text,
                    attributes=attributes_list,
                    trace_id=log.trace_id,
                    span_id=log.span_id,
                    service_name=service_name,
                    service_namespace=service_namespace,
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
            # Get the unknown tenant_id
            tenant_id = await self._get_unknown_tenant_id(session)

            from app.models.database import NamespaceDim

            limit = pagination.limit if pagination else 100

            # ORM query with JOIN to ServiceDim and NamespaceDim
            stmt = (
                select(MetricsFact, ServiceDim.name, NamespaceDim.namespace)
                .outerjoin(ServiceDim, MetricsFact.service_id == ServiceDim.id)
                .outerjoin(NamespaceDim, ServiceDim.namespace_id == NamespaceDim.id)
            )

            # Apply namespace filtering
            if filters:
                namespace_filters = [f for f in filters if f.field == "service_namespace"]
                if namespace_filters:
                    from sqlalchemy import or_

                    namespace_conditions = []
                    for f in namespace_filters:
                        if f.value == "":
                            namespace_conditions.append(ServiceDim.namespace_id.is_(None))
                        else:
                            namespace_conditions.append(NamespaceDim.namespace == f.value)
                    if namespace_conditions:
                        stmt = stmt.where(or_(*namespace_conditions))

            # Convert RFC3339 to timestamps
            from datetime import datetime

            start_timestamp = datetime.fromisoformat(time_range.start_time.replace("Z", "+00:00"))
            end_timestamp = datetime.fromisoformat(time_range.end_time.replace("Z", "+00:00"))

            stmt = stmt.where(
                MetricsFact.timestamp >= start_timestamp,
                MetricsFact.timestamp < end_timestamp,
                MetricsFact.tenant_id == tenant_id,
            )

            if metric_names:
                stmt = stmt.where(MetricsFact.metric_name.in_(metric_names))

            # Apply other filters (non-namespace)
            if filters:
                for f in filters:
                    if f.field == "service_namespace":
                        continue  # Already handled by _apply_namespace_filtering
                    elif f.field == "service_name":
                        if f.operator == "equals":
                            stmt = stmt.where(ServiceDim.name == f.value)
                        elif f.operator == "contains":
                            stmt = stmt.where(ServiceDim.name.contains(f.value))

            stmt = stmt.order_by(MetricsFact.timestamp.desc()).limit(limit + 1)

            result = await session.execute(stmt)
            rows = result.fetchall()

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            from app.models.api import Metric

            metrics = []
            for m, service_name, service_namespace in rows:
                # Convert timestamp back to nanoseconds for API
                timestamp_ns = _timestamp_nanos_to_nanoseconds(m.timestamp, m.nanos_fraction)
                metric = Metric(
                    metric_id=str(m.id),
                    name=m.metric_name,
                    description=m.description,
                    unit=m.unit,
                    metric_type=m.metric_type,
                    aggregation_temporality=m.temporality,
                    timestamp_ns=timestamp_ns,
                    data_points=m.data_points if m.data_points else [],
                    attributes=m.attributes if m.attributes else {},
                    service_name=service_name,
                    service_namespace=service_namespace,
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
            # Get the unknown tenant_id
            tenant_id = await self._get_unknown_tenant_id(session)

            # ORM query with aggregations
            stmt = (
                select(
                    ServiceDim.name,
                    func.count().label("request_count"),
                    func.count().filter(SpansFact.status_code == 2).label("error_count"),
                    # Duration in microseconds: EXTRACT(EPOCH FROM end_timestamp - start_timestamp) * 1000000 + (end_nanos_fraction - start_nanos_fraction) / 1000
                    func.percentile_cont(0.50)
                    .within_group(
                        func.extract("epoch", SpansFact.end_timestamp - SpansFact.start_timestamp) * 1000000
                        + (SpansFact.end_nanos_fraction - SpansFact.start_nanos_fraction) / 1000
                    )
                    .label("p50_micros"),
                    func.percentile_cont(0.95)
                    .within_group(
                        func.extract("epoch", SpansFact.end_timestamp - SpansFact.start_timestamp) * 1000000
                        + (SpansFact.end_nanos_fraction - SpansFact.start_nanos_fraction) / 1000
                    )
                    .label("p95_micros"),
                    func.min(SpansFact.start_timestamp).label("first_seen_ts"),
                    func.max(SpansFact.start_timestamp).label("last_seen_ts"),
                )
                .select_from(SpansFact)
                .join(ServiceDim, SpansFact.service_id == ServiceDim.id)
                .where(SpansFact.tenant_id == tenant_id)
            )

            if time_range:
                from datetime import datetime

                start_timestamp = datetime.fromisoformat(time_range.start_time.replace("Z", "+00:00"))
                end_timestamp = datetime.fromisoformat(time_range.end_time.replace("Z", "+00:00"))
                stmt = stmt.where(
                    SpansFact.start_timestamp >= start_timestamp,
                    SpansFact.start_timestamp < end_timestamp,
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
                    # Convert microseconds to milliseconds
                    p50_latency_ms=round(row.p50_micros / 1_000, 2) if row.p50_micros else 0.0,
                    p95_latency_ms=round(row.p95_micros / 1_000, 2) if row.p95_micros else 0.0,
                    # Convert timestamp to nanoseconds for API compatibility
                    first_seen=_timestamp_nanos_to_nanoseconds(row.first_seen_ts, 0),
                    last_seen=_timestamp_nanos_to_nanoseconds(row.last_seen_ts, 0),
                )
                services.append(service)

            return services

    async def get_service_map(self, time_range: Any) -> tuple[list, list]:
        """Get service dependency map from spans using ORM."""
        if not self.engine:
            return [], []

        # Convert RFC3339 to timestamps
        from datetime import datetime

        start_ts = datetime.fromisoformat(time_range.start_time.replace("Z", "+00:00"))
        end_ts = datetime.fromisoformat(time_range.end_time.replace("Z", "+00:00"))

        from sqlalchemy import alias

        async with AsyncSession(self.engine) as session:
            # Get the unknown tenant_id
            tenant_id = await self._get_unknown_tenant_id(session)

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
                    & (s_parent.c.tenant_id == tenant_id),
                )
                .outerjoin(srv_parent, s_parent.c.service_id == srv_parent.c.id)
                .join(srv_child, s_child.c.service_id == srv_child.c.id)
                .where(
                    s_child.c.start_timestamp >= start_ts,
                    s_child.c.start_timestamp < end_ts,
                    s_child.c.tenant_id == tenant_id,
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

    async def get_namespaces(self) -> list[str]:
        """Get list of all namespaces from namespace_dim table."""
        if not self.engine:
            return []

        async with AsyncSession(self.engine) as session:
            from app.models.database import NamespaceDim

            stmt = select(NamespaceDim.namespace).order_by(NamespaceDim.namespace.asc())

            result = await session.execute(stmt)
            rows = result.fetchall()

            # Convert rows to list of namespace strings, handle NULL as empty string
            namespaces = [row[0] if row[0] is not None else "" for row in rows]
            return namespaces
