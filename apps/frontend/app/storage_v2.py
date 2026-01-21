# storage_v2.py: Storage abstraction for ollyScale v2 API
# This is a stub for future Postgres backend (async, SQLAlchemy/asyncpg)

from typing import Any


class StorageV2:
    """Abstract storage interface for traces, logs, metrics."""

    async def store_trace(self, trace: Any) -> None:
        # TODO: Implement Postgres logic
        pass

    async def store_log(self, log: Any) -> None:
        # TODO: Implement Postgres logic
        pass

    async def store_metric(self, metric: Any) -> None:
        # TODO: Implement Postgres logic
        pass

    async def health(self) -> dict:
        # TODO: Implement DB health check
        return {"status": "unimplemented"}
