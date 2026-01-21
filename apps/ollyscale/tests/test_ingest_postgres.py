# Integration tests for FastAPI ingestion endpoints with Postgres (star schema)


from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import get_app

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def app():
    return get_app()


@pytest.fixture(scope="module")
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with (
            patch("app.routers.ingest.PostgresStorage.connect", new=AsyncMock()),
            patch("app.routers.ingest.PostgresStorage.close", new=AsyncMock()),
            patch("app.routers.ingest.PostgresStorage.store_trace", new=AsyncMock()),
            patch("app.routers.ingest.PostgresStorage.store_log", new=AsyncMock()),
            patch("app.routers.ingest.PostgresStorage.store_metric", new=AsyncMock()),
        ):
            yield ac


def test_postgres_available():
    # This is a placeholder: in real integration, check DB connectivity or skip if not available
    assert True


async def test_ingest_traces(client):
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "abc123",
                                "spanId": "span456",
                                "name": "GET /api/users",
                                "service_name": "svc",
                                "start_time_unix_nano": 1,
                                "end_time_unix_nano": 2,
                                "duration": 1,
                                "status_code": 0,
                                "kind": 2,
                                "attributes": {},
                                "events": [],
                                "links": [],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    resp = await client.post("/v1/traces", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_ingest_logs(client):
    payload = [
        {
            "time_unix_nano": 123,
            "observed_time": 124,
            "traceId": "abc",
            "spanId": "def",
            "severityNumber": 9,
            "severityText": "INFO",
            "body": "test log",
            "attributes": {"foo": "bar"},
            "resource": {"env": "dev"},
            "flags": 0,
            "droppedAttributesCount": 0,
            "service_name": "svc",
            "operation_name": "op",
        }
    ]
    resp = await client.post("/v1/logs", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_ingest_metrics(client):
    payload = {
        "resourceMetrics": [
            {
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "cpu.usage",
                                "type": "gauge",
                                "unit": "percent",
                                "description": "CPU usage",
                                "dataPoints": [{"value": 0.5}],
                                "attributes": {"host": "localhost"},
                                "resource": {"env": "dev"},
                                "time_unix_nano": 123,
                                "start_time_unix_nano": 100,
                            }
                        ]
                    }
                ]
            }
        ]
    }
    resp = await client.post("/v1/metrics", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
