# BSD 3-Clause License
#
# Postgres async storage for ollyScale v2 (star schema)
#
# Implements upsert helpers and fact/dimension table logic for traces, logs, metrics.


import asyncpg


class PostgresStorage:
    """Async Postgres storage layer for OpenTelemetry data (star schema)."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=10)

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    # --- Dimension upserts ---
    async def upsert_service(self, service_name: str) -> int:
        sql = """
        INSERT INTO service_dim (service_name)
        VALUES ($1)
        ON CONFLICT (service_name) DO UPDATE SET service_name=EXCLUDED.service_name
        RETURNING service_id;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, service_name)
            return row["service_id"]

    async def upsert_operation(self, operation_name: str) -> int:
        sql = """
        INSERT INTO operation_dim (operation_name)
        VALUES ($1)
        ON CONFLICT (operation_name) DO UPDATE SET operation_name=EXCLUDED.operation_name
        RETURNING operation_id;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, operation_name)
            return row["operation_id"]

    async def upsert_resource(self, resource_jsonb: dict) -> int:
        sql = """
        INSERT INTO resource_dim (resource_jsonb)
        VALUES ($1::jsonb)
        ON CONFLICT (resource_jsonb) DO UPDATE SET resource_jsonb=EXCLUDED.resource_jsonb
        RETURNING resource_id;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, resource_jsonb)
            return row["resource_id"]

    # --- Fact table inserts ---
    async def insert_span_fact(self, span: dict, service_id: int, operation_id: int, resource_id: int):
        sql = """
        INSERT INTO spans_fact (
            trace_id, span_id, parent_span_id, service_id, operation_id, resource_id,
            start_time_unix_nano, end_time_unix_nano, duration, status_code, kind,
            attributes, events, links, tenant_id, connection_id
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11,
            $12, $13, $14, $15, $16
        )
        ON CONFLICT (span_id) DO NOTHING;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                sql,
                span.get("trace_id"),
                span.get("span_id"),
                span.get("parent_span_id"),
                service_id,
                operation_id,
                resource_id,
                span.get("start_time_unix_nano"),
                span.get("end_time_unix_nano"),
                span.get("duration"),
                span.get("status_code"),
                span.get("kind"),
                span.get("attributes"),
                span.get("events"),
                span.get("links"),
                span.get("tenant_id"),
                span.get("connection_id"),
            )

    # --- Fact table inserts for logs and metrics ---
    async def insert_log_fact(
        self, log: dict, service_id: int | None = None, operation_id: int | None = None, resource_id: int | None = None
    ):
        sql = """
        INSERT INTO logs_fact (
            time_unix_nano, observed_time, trace_id, span_id, service_id, operation_id, resource_id,
            severity_number, severity_text, body, attributes, resource_jsonb, flags, dropped_attrs
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7,
            $8, $9, $10, $11, $12, $13, $14
        )
        ON CONFLICT (span_id) DO NOTHING;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                sql,
                log.get("time_unix_nano"),
                log.get("observed_time"),
                log.get("traceId"),
                log.get("spanId"),
                service_id,
                operation_id,
                resource_id,
                log.get("severityNumber"),
                log.get("severityText"),
                log.get("body"),
                log.get("attributes"),
                log.get("resource"),
                log.get("flags"),
                log.get("droppedAttributesCount"),
            )

    async def insert_metric_fact(self, metric: dict, resource_id: int | None = None):
        sql = """
        INSERT INTO metrics_fact (
            metric_name, metric_type, unit, description, data_points, attributes, resource_id, time_unix_nano, start_time_unix_nano
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9
        )
        ON CONFLICT (metric_name, time_unix_nano) DO NOTHING;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                sql,
                metric.get("name"),
                metric.get("type"),
                metric.get("unit"),
                metric.get("description"),
                metric.get("dataPoints"),
                metric.get("attributes"),
                resource_id,
                metric.get("time_unix_nano"),
                metric.get("start_time_unix_nano"),
            )

    # --- High-level ingest helpers ---
    async def store_trace(self, span: dict):
        await self.connect()
        service_id = await self.upsert_service(span["service_name"])
        operation_id = await self.upsert_operation(span["name"])
        resource_id = await self.upsert_resource(span.get("resource", {}))
        await self.insert_span_fact(span, service_id, operation_id, resource_id)

    async def store_log(self, log: dict):
        await self.connect()
        # Optional: upsert service/operation/resource if present in log
        service_id = None
        operation_id = None
        resource_id = None
        if "service_name" in log:
            service_id = await self.upsert_service(log["service_name"])
        if "operation_name" in log:
            operation_id = await self.upsert_operation(log["operation_name"])
        if "resource" in log:
            resource_id = await self.upsert_resource(log["resource"])
        await self.insert_log_fact(log, service_id, operation_id, resource_id)

    async def store_metric(self, metric: dict):
        await self.connect()
        resource_id = None
        if "resource" in metric:
            resource_id = await self.upsert_resource(metric["resource"])
        await self.insert_metric_fact(metric, resource_id)
