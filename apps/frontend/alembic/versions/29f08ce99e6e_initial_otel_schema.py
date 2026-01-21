"""initial_otel_schema

Revision ID: 29f08ce99e6e
Revises:
Create Date: 2026-01-21

Creates OpenTelemetry-native schema with:
- Fact tables: spans_fact, logs_fact, metrics_fact
- Dimension tables: service_dim, operation_dim, resource_dim
- Retention policy table
- Partitioning and indexes

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "29f08ce99e6e"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create OTEL schema with dimension tables, fact tables, and indexes."""
    # ====================
    # Dimension Tables
    # ====================

    # service_dim - Service catalog
    op.execute(
        """
        CREATE TABLE service_dim (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
            name VARCHAR(255) NOT NULL,
            namespace VARCHAR(255),
            version VARCHAR(255),
            attributes JSONB,
            first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(tenant_id, name, namespace)
        )
        """
    )

    # operation_dim - Operation (span name) catalog
    op.execute(
        """
        CREATE TABLE operation_dim (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
            service_id INTEGER REFERENCES service_dim(id) ON DELETE CASCADE,
            name VARCHAR(1024) NOT NULL,
            span_kind SMALLINT,
            first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(tenant_id, service_id, name, span_kind)
        )
        """
    )

    # resource_dim - Resource attributes catalog
    op.execute(
        """
        CREATE TABLE resource_dim (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
            resource_hash VARCHAR(64) NOT NULL,
            attributes JSONB NOT NULL,
            first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(tenant_id, resource_hash)
        )
        """
    )
    op.execute("CREATE INDEX idx_resource_attributes ON resource_dim USING GIN (attributes)")

    # ====================
    # Fact Tables (Partitioned)
    # ====================

    # spans_fact - Distributed trace spans
    op.execute(
        """
        CREATE TABLE spans_fact (
            id BIGSERIAL,
            tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
            connection_id VARCHAR(255),
            trace_id VARCHAR(32) NOT NULL,
            span_id VARCHAR(16) NOT NULL,
            parent_span_id VARCHAR(16),

            -- Core OTEL fields
            name VARCHAR(1024) NOT NULL,
            kind SMALLINT NOT NULL,
            status_code SMALLINT,
            status_message TEXT,

            -- Timing
            start_time_unix_nano BIGINT NOT NULL,
            end_time_unix_nano BIGINT NOT NULL,
            duration BIGINT GENERATED ALWAYS AS (end_time_unix_nano - start_time_unix_nano) STORED,

            -- References
            service_id INTEGER REFERENCES service_dim(id) ON DELETE SET NULL,
            operation_id INTEGER REFERENCES operation_dim(id) ON DELETE SET NULL,
            resource_id INTEGER REFERENCES resource_dim(id) ON DELETE SET NULL,

            -- OTEL structures as JSONB
            attributes JSONB,
            events JSONB,
            links JSONB,
            resource JSONB,
            scope JSONB,

            -- Flags
            flags INTEGER DEFAULT 0,
            dropped_attributes_count INTEGER DEFAULT 0,
            dropped_events_count INTEGER DEFAULT 0,
            dropped_links_count INTEGER DEFAULT 0,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            PRIMARY KEY (id, start_time_unix_nano)
        ) PARTITION BY RANGE (start_time_unix_nano)
        """
    )
    op.execute("CREATE INDEX idx_spans_trace_id ON spans_fact(trace_id)")
    op.execute("CREATE INDEX idx_spans_service ON spans_fact(service_id)")
    op.execute("CREATE INDEX idx_spans_time ON spans_fact(start_time_unix_nano)")
    op.execute("CREATE INDEX idx_spans_attributes ON spans_fact USING GIN (attributes)")
    op.execute("CREATE INDEX idx_spans_span_id ON spans_fact(span_id)")

    # logs_fact - Log entries
    op.execute(
        """
        CREATE TABLE logs_fact (
            id BIGSERIAL,
            tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
            connection_id VARCHAR(255),

            -- OTEL correlation
            trace_id VARCHAR(32),
            span_id VARCHAR(16),

            -- Timing
            time_unix_nano BIGINT NOT NULL,
            observed_time_unix_nano BIGINT,

            -- Severity
            severity_number SMALLINT,
            severity_text VARCHAR(64),

            -- Content
            body JSONB,

            -- OTEL structures
            attributes JSONB,
            resource JSONB,
            scope JSONB,

            -- Flags
            flags INTEGER DEFAULT 0,
            dropped_attributes_count INTEGER DEFAULT 0,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            PRIMARY KEY (id, time_unix_nano)
        ) PARTITION BY RANGE (time_unix_nano)
        """
    )
    op.execute("CREATE INDEX idx_logs_trace_id ON logs_fact(trace_id)")
    op.execute("CREATE INDEX idx_logs_time ON logs_fact(time_unix_nano)")
    op.execute("CREATE INDEX idx_logs_severity ON logs_fact(severity_number)")
    op.execute("CREATE INDEX idx_logs_attributes ON logs_fact USING GIN (attributes)")

    # metrics_fact - Metrics
    op.execute(
        """
        CREATE TABLE metrics_fact (
            id BIGSERIAL,
            tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
            connection_id VARCHAR(255),

            -- Metric identity
            metric_name VARCHAR(1024) NOT NULL,
            metric_type VARCHAR(32) NOT NULL,
            unit VARCHAR(64),
            description TEXT,

            -- Timing
            time_unix_nano BIGINT NOT NULL,
            start_time_unix_nano BIGINT,

            -- OTEL structures
            resource JSONB,
            scope JSONB,
            attributes JSONB,
            data_points JSONB,

            -- Aggregation temporality (for sum/histogram)
            temporality VARCHAR(32),

            -- Monotonicity (for sum)
            is_monotonic BOOLEAN,

            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            PRIMARY KEY (id, time_unix_nano)
        ) PARTITION BY RANGE (time_unix_nano)
        """
    )
    op.execute("CREATE INDEX idx_metrics_name ON metrics_fact(metric_name)")
    op.execute("CREATE INDEX idx_metrics_time ON metrics_fact(time_unix_nano)")
    op.execute("CREATE INDEX idx_metrics_attributes ON metrics_fact USING GIN (attributes)")

    # ====================
    # Retention Policy
    # ====================

    op.execute(
        """
        CREATE TABLE retention_policy (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
            signal_type VARCHAR(32) NOT NULL,
            retention_days INTEGER NOT NULL DEFAULT 7,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(tenant_id, signal_type)
        )
        """
    )

    # Insert default retention policies
    op.execute(
        """
        INSERT INTO retention_policy (tenant_id, signal_type, retention_days) VALUES
            ('default', 'traces', 7),
            ('default', 'logs', 3),
            ('default', 'metrics', 30)
        """
    )


def downgrade() -> None:
    """Drop all OTEL schema tables."""
    # Drop fact tables first (they reference dimension tables)
    op.execute("DROP TABLE IF EXISTS metrics_fact CASCADE")
    op.execute("DROP TABLE IF EXISTS logs_fact CASCADE")
    op.execute("DROP TABLE IF EXISTS spans_fact CASCADE")

    # Drop retention policy
    op.execute("DROP TABLE IF EXISTS retention_policy CASCADE")

    # Drop dimension tables
    op.execute("DROP TABLE IF EXISTS operation_dim CASCADE")
    op.execute("DROP TABLE IF EXISTS resource_dim CASCADE")
    op.execute("DROP TABLE IF EXISTS service_dim CASCADE")
