# Unit tests for PostgresStorage (star schema) using asyncpg mocks
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.storage import PostgresStorage


@pytest.mark.asyncio
class TestPostgresStorage:
    @pytest.fixture(autouse=True)
    def setup_storage(self):
        self.storage = PostgresStorage(dsn="postgresql://postgres:postgres@localhost:5432/ollyscale")
        self.storage.pool = MagicMock()

    @patch("app.storage.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_connect(self, mock_create_pool):
        storage = PostgresStorage(dsn="postgresql://postgres:postgres@localhost:5432/ollyscale")
        await storage.connect()
        mock_create_pool.assert_awaited_once()
        assert storage.pool is not None

    @patch("app.storage.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_close(self, mock_create_pool):
        storage = PostgresStorage(dsn="postgresql://postgres:postgres@localhost:5432/ollyscale")
        await storage.connect()
        pool_mock = storage.pool
        await storage.close()
        pool_mock.close.assert_awaited_once()
        assert storage.pool is None

    @patch("app.storage.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_upsert_service(self, mock_create_pool):
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"service_id": 42}

        class AcquireCtx:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc, tb):
                pass

        self.storage.pool.acquire = AcquireCtx
        service_id = await self.storage.upsert_service("svc")
        assert service_id == 42
        mock_conn.fetchrow.assert_awaited()

    @patch("app.storage.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_upsert_operation(self, mock_create_pool):
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"operation_id": 7}

        class AcquireCtx:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc, tb):
                pass

        self.storage.pool.acquire = AcquireCtx
        op_id = await self.storage.upsert_operation("op")
        assert op_id == 7
        mock_conn.fetchrow.assert_awaited()

    @patch("app.storage.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_upsert_resource(self, mock_create_pool):
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"resource_id": 99}

        class AcquireCtx:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc, tb):
                pass

        self.storage.pool.acquire = AcquireCtx
        res_id = await self.storage.upsert_resource({"foo": "bar"})
        assert res_id == 99
        mock_conn.fetchrow.assert_awaited()

    @patch("app.storage.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_insert_span_fact(self, mock_create_pool):
        mock_conn = AsyncMock()

        class AcquireCtx:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc, tb):
                pass

        self.storage.pool.acquire = AcquireCtx
        span = {
            "trace_id": "abc",
            "span_id": "def",
            "parent_span_id": None,
            "start_time_unix_nano": 1,
            "end_time_unix_nano": 2,
            "duration": 1,
            "status_code": 0,
            "kind": 2,
            "attributes": {},
            "events": [],
            "links": [],
            "tenant_id": None,
            "connection_id": None,
        }
        await self.storage.insert_span_fact(span, 1, 2, 3)
        mock_conn.execute.assert_awaited()
