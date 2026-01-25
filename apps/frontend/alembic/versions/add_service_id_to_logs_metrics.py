"""add_service_id_to_logs_metrics

Revision ID: add_service_fk
Revises: 310d6c3bbbf4
Create Date: 2026-01-25

Add service_id foreign key to logs_fact and metrics_fact for normalized service catalog.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_service_fk"
down_revision: str | Sequence[str] | None = "310d6c3bbbf4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add service_id FK to logs_fact and metrics_fact."""
    # Add service_id column to logs_fact
    op.execute(
        """
        ALTER TABLE logs_fact ADD COLUMN service_id INTEGER REFERENCES service_dim(id) ON DELETE SET NULL
        """
    )
    op.execute("CREATE INDEX idx_logs_service ON logs_fact(service_id)")

    # Add service_id column to metrics_fact
    op.execute(
        """
        ALTER TABLE metrics_fact ADD COLUMN service_id INTEGER REFERENCES service_dim(id) ON DELETE SET NULL
        """
    )
    op.execute("CREATE INDEX idx_metrics_service ON metrics_fact(service_id)")


def downgrade() -> None:
    """Remove service_id FK from logs_fact and metrics_fact."""
    op.execute("DROP INDEX IF EXISTS idx_metrics_service")
    op.execute("ALTER TABLE metrics_fact DROP COLUMN IF EXISTS service_id")

    op.execute("DROP INDEX IF EXISTS idx_logs_service")
    op.execute("ALTER TABLE logs_fact DROP COLUMN IF EXISTS service_id")
