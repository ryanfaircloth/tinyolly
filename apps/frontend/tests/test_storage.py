from unittest.mock import AsyncMock, patch

import pytest

from app.storage import Storage


@pytest.mark.asyncio
async def test_store_trace_calls_db():
    storage = Storage()
    fake_trace = {"foo": "bar"}
    mock_execute = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.execute = mock_execute
    mock_acquire = AsyncMock()
    mock_acquire.__aenter__.return_value = mock_conn
    mock_pool = AsyncMock()
    mock_pool.__aenter__.return_value = mock_pool
    mock_pool.acquire.return_value = mock_acquire
    with patch("asyncpg.create_pool", return_value=mock_pool) as mock_create_pool:
        await storage.store_trace(fake_trace)
        assert mock_create_pool.called
        mock_conn.execute.assert_awaited()
        args, _ = mock_conn.execute.call_args
        assert "INSERT INTO trace" in args[0]


@pytest.mark.asyncio
async def test_store_log_calls_db():
    storage = Storage()
    fake_log = {"bar": "baz"}
    mock_execute = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.execute = mock_execute
    mock_acquire = AsyncMock()
    mock_acquire.__aenter__.return_value = mock_conn
    mock_pool = AsyncMock()
    mock_pool.__aenter__.return_value = mock_pool
    mock_pool.acquire.return_value = mock_acquire
    with patch("asyncpg.create_pool", return_value=mock_pool) as mock_create_pool:
        await storage.store_log(fake_log)
        assert mock_create_pool.called
        mock_conn.execute.assert_awaited()
        args, _ = mock_conn.execute.call_args
        assert "INSERT INTO log" in args[0]


@pytest.mark.asyncio
async def test_store_metric_calls_db():
    storage = Storage()
    fake_metric = {"baz": "qux"}
    mock_execute = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.execute = mock_execute
    mock_acquire = AsyncMock()
    mock_acquire.__aenter__.return_value = mock_conn
    mock_pool = AsyncMock()
    mock_pool.__aenter__.return_value = mock_pool
    mock_pool.acquire.return_value = mock_acquire
    with patch("asyncpg.create_pool", return_value=mock_pool) as mock_create_pool:
        await storage.store_metric(fake_metric)
        assert mock_create_pool.called
        mock_conn.execute.assert_awaited()
        args, _ = mock_conn.execute.call_args
        assert "INSERT INTO metric" in args[0]
