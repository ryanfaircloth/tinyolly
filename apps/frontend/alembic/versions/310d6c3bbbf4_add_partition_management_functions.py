"""add_partition_management_functions

Revision ID: 310d6c3bbbf4
Revises: 29f08ce99e6e
Create Date: 2026-01-21 13:37:31.574142

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "310d6c3bbbf4"
down_revision: str | Sequence[str] | None = "29f08ce99e6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create partition management functions and initial partitions."""
    # Create function to create partitions for a time range
    op.execute("""
        CREATE OR REPLACE FUNCTION create_partitions_for_range(
            table_name TEXT,
            start_time BIGINT,
            end_time BIGINT,
            interval_hours INTEGER DEFAULT 24
        ) RETURNS INTEGER AS $$
        DECLARE
            partition_start BIGINT;
            partition_end BIGINT;
            partition_name TEXT;
            partitions_created INTEGER := 0;
        BEGIN
            -- Align start_time to day boundary (nanoseconds)
            partition_start := (start_time / (24::BIGINT * 3600::BIGINT * 1000000000::BIGINT)) *
                               (24::BIGINT * 3600::BIGINT * 1000000000::BIGINT);

            WHILE partition_start < end_time LOOP
                partition_end := partition_start + (interval_hours::BIGINT * 3600::BIGINT * 1000000000::BIGINT);

                -- Format: tablename_yYYYY_mMM_dDD
                partition_name := table_name || '_y' ||
                    TO_CHAR(TO_TIMESTAMP(partition_start / 1000000000.0), 'YYYY') || '_m' ||
                    TO_CHAR(TO_TIMESTAMP(partition_start / 1000000000.0), 'MM') || '_d' ||
                    TO_CHAR(TO_TIMESTAMP(partition_start / 1000000000.0), 'DD');

                -- Check if partition already exists
                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = partition_name AND n.nspname = 'public'
                ) THEN
                    EXECUTE format(
                        'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                        partition_name, table_name, partition_start, partition_end
                    );
                    partitions_created := partitions_created + 1;
                END IF;

                partition_start := partition_end;
            END LOOP;

            RETURN partitions_created;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create function to drop old partitions based on retention policy
    op.execute(r"""
        CREATE OR REPLACE FUNCTION drop_old_partitions(
            table_name TEXT,
            signal_type TEXT,
            tenant_id_param TEXT DEFAULT 'default'
        ) RETURNS INTEGER AS $$
        DECLARE
            retention_days INTEGER;
            cutoff_time BIGINT;
            partition_record RECORD;
            partitions_dropped INTEGER := 0;
        BEGIN
            -- Get retention policy
            SELECT retention_days_value INTO retention_days
            FROM retention_policy
            WHERE signal_type_value = signal_type AND tenant_id = tenant_id_param;

            IF retention_days IS NULL THEN
                RAISE NOTICE 'No retention policy found for signal_type=%, tenant_id=%',
                    signal_type, tenant_id_param;
                RETURN 0;
            END IF;

            -- Calculate cutoff time (nanoseconds)
            cutoff_time := EXTRACT(EPOCH FROM NOW() - (retention_days || ' days')::INTERVAL)::BIGINT * 1000000000;

            -- Find and drop partitions older than cutoff
            FOR partition_record IN
                SELECT c.relname AS partition_name,
                       pg_get_expr(c.relpartbound, c.oid) AS partition_bound
                FROM pg_class c
                JOIN pg_inherits i ON i.inhrelid = c.oid
                JOIN pg_class parent ON parent.oid = i.inhparent
                WHERE parent.relname = table_name
                  AND c.relkind = 'r'
            LOOP
                -- Extract upper bound from partition definition
                -- Format: FOR VALUES FROM ('start') TO ('end')
                DECLARE
                    upper_bound TEXT;
                    upper_bound_ns BIGINT;
                BEGIN
                    upper_bound := substring(partition_record.partition_bound from 'TO \(''([^'']+)''\)');
                    upper_bound_ns := upper_bound::BIGINT;

                    IF upper_bound_ns < cutoff_time THEN
                        EXECUTE format('DROP TABLE IF EXISTS %I', partition_record.partition_name);
                        partitions_dropped := partitions_dropped + 1;
                    END IF;
                EXCEPTION WHEN OTHERS THEN
                    -- Skip partitions we can't parse
                    RAISE NOTICE 'Could not parse partition bound for %: %',
                        partition_record.partition_name, SQLERRM;
                END;
            END LOOP;

            RETURN partitions_dropped;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create maintenance function to create future partitions
    op.execute("""
        CREATE OR REPLACE FUNCTION maintenance_create_partitions(
            days_ahead INTEGER DEFAULT 7
        ) RETURNS TABLE(table_name TEXT, partitions_created INTEGER) AS $$
        DECLARE
            start_time BIGINT;
            end_time BIGINT;
            created INTEGER;
        BEGIN
            -- Calculate time range (nanoseconds)
            start_time := EXTRACT(EPOCH FROM NOW())::BIGINT * 1000000000;
            end_time := EXTRACT(EPOCH FROM NOW() + (days_ahead || ' days')::INTERVAL)::BIGINT * 1000000000;

            -- Create partitions for each fact table
            SELECT 'spans_fact', create_partitions_for_range('spans_fact', start_time, end_time, 24)
            INTO table_name, partitions_created;
            RETURN NEXT;

            SELECT 'logs_fact', create_partitions_for_range('logs_fact', start_time, end_time, 24)
            INTO table_name, partitions_created;
            RETURN NEXT;

            SELECT 'metrics_fact', create_partitions_for_range('metrics_fact', start_time, end_time, 24)
            INTO table_name, partitions_created;
            RETURN NEXT;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create maintenance function to drop old partitions
    op.execute("""
        CREATE OR REPLACE FUNCTION maintenance_drop_partitions()
        RETURNS TABLE(table_name TEXT, signal_type TEXT, partitions_dropped INTEGER) AS $$
        BEGIN
            -- Drop old spans
            SELECT 'spans_fact', 'traces', drop_old_partitions('spans_fact', 'traces', 'default')
            INTO table_name, signal_type, partitions_dropped;
            RETURN NEXT;

            -- Drop old logs
            SELECT 'logs_fact', 'logs', drop_old_partitions('logs_fact', 'logs', 'default')
            INTO table_name, signal_type, partitions_dropped;
            RETURN NEXT;

            -- Drop old metrics
            SELECT 'metrics_fact', 'metrics', drop_old_partitions('metrics_fact', 'metrics', 'default')
            INTO table_name, signal_type, partitions_dropped;
            RETURN NEXT;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create initial partitions (7 days ahead)
    op.execute("SELECT * FROM maintenance_create_partitions(7)")


def downgrade() -> None:
    """Drop partition management functions."""
    op.execute("DROP FUNCTION IF EXISTS maintenance_drop_partitions()")
    op.execute("DROP FUNCTION IF EXISTS maintenance_create_partitions(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS drop_old_partitions(TEXT, TEXT, TEXT)")
    op.execute("DROP FUNCTION IF EXISTS create_partitions_for_range(TEXT, BIGINT, BIGINT, INTEGER)")
