# BSD 3-Clause License
#
# Copyright (c) 2025, Infrastructure Architects, LLC
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""OTLP ingestion endpoints"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status

from models import ErrorResponse, IngestResponse

from ..core.telemetry import get_metrics
from ..dependencies import get_alert_manager
from ..managers.alerts import AlertManager
from ..storage import PostgresStorage

router = APIRouter(prefix="/v1", tags=["Ingestion"])

# Get metrics
_metrics = None


def get_ingestion_metrics():
    """Get metrics for ingestion endpoints"""
    global _metrics
    if _metrics is None:
        _metrics = get_metrics()
    return _metrics


@router.post(
    "/traces",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    operation_id="ingest_traces",
    summary="Ingest traces",
    responses={
        200: {"description": "Traces successfully ingested"},
        400: {"model": ErrorResponse, "description": "Invalid JSON payload"},
        413: {"model": ErrorResponse, "description": "Payload too large (max 5MB)"},
    },
)
async def ingest_traces(
    request: Request,
    alert_manager: AlertManager = Depends(get_alert_manager),
):
    """
    Accept traces in OTLP JSON format (OpenTelemetry Protocol).

    Supports both full OTLP format with `resourceSpans` or simplified format with `spans` array.
    Maximum payload size is 5MB.

    **OTLP Format Example:**
    ```json
    {
      "resourceSpans": [{
        "scopeSpans": [{
          "spans": [{
            "traceId": "abc123",
            "spanId": "span456",
            "name": "GET /api/users"
          }]
        }]
      }]
    }
    ```
    """
    metrics = get_ingestion_metrics()

    # Check content length
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")

    try:
        data = await request.json()
        if not data:
            raise HTTPException(status_code=400, detail="Invalid JSON")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e!s}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e!s}")

    spans_to_store = []
    if "resourceSpans" in data:
        for resource_span in data["resourceSpans"]:
            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    spans_to_store.append(span)
    elif "spans" in data:
        spans_to_store = data["spans"]
    else:
        spans_to_store = [data]

    # Use PostgresStorage for ingestion
    pg_storage = PostgresStorage(dsn="postgresql://postgres:postgres@localhost:5432/ollyscale")
    await pg_storage.connect()
    for span in spans_to_store:
        await pg_storage.store_trace(span)
        await alert_manager.check_span_error(span)
    await pg_storage.close()

    # Track ingestion metrics
    metrics["ingestion_counter"].add(len(spans_to_store), {"type": "spans"})
    metrics["storage_operations_counter"].add(1, {"operation": "store_spans", "count": len(spans_to_store)})
    return {"status": "ok"}


@router.post(
    "/logs",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    operation_id="ingest_logs",
    summary="Ingest logs",
    responses={
        200: {"description": "Logs successfully ingested"},
        400: {"model": ErrorResponse, "description": "Invalid JSON payload"},
        413: {"model": ErrorResponse, "description": "Payload too large (max 5MB)"},
    },
)
async def ingest_logs(request: Request):
    """
    Accept logs in OTLP JSON format (OpenTelemetry Protocol).

    Supports both array of logs or single log entry.
    Maximum payload size is 5MB.

    **Example:**
    ```json
    [{
      "timestamp": 1638360000,
      "traceId": "trace-xyz",
      "spanId": "span-abc",
      "severityText": "INFO",
      "body": "User logged in",
      "attributes": {"user_id": "123"}
    }]
    ```
    """
    metrics = get_ingestion_metrics()
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")

    try:
        data = await request.json()
        if not data:
            raise HTTPException(status_code=400, detail="Invalid JSON")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e!s}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e!s}")

    logs = data if isinstance(data, list) else [data]
    valid_logs = [log for log in logs if isinstance(log, dict)]

    pg_storage = PostgresStorage(dsn="postgresql://postgres:postgres@localhost:5432/ollyscale")
    await pg_storage.connect()
    for log in valid_logs:
        await pg_storage.store_log(log)
    await pg_storage.close()

    metrics["ingestion_counter"].add(len(valid_logs), {"type": "logs"})
    metrics["storage_operations_counter"].add(1, {"operation": "store_logs", "count": len(valid_logs)})
    return {"status": "ok"}


@router.post(
    "/metrics",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    operation_id="ingest_metrics",
    summary="Ingest metrics",
    responses={
        200: {"description": "Metrics successfully ingested"},
        400: {"model": ErrorResponse, "description": "Invalid JSON payload"},
        413: {"model": ErrorResponse, "description": "Payload too large (max 5MB)"},
    },
)
async def ingest_metrics(request: Request):
    """
    Accept metrics in OTLP JSON format (OpenTelemetry Protocol).

    Supports both full OTLP format with `resourceMetrics` or simplified legacy format.
    Maximum payload size is 5MB.

    **OTLP Format Example:**
    ```json
    {
      "resourceMetrics": [{
        "scopeMetrics": [{
          "metrics": [{
            "name": "http.server.duration",
            "unit": "ms",
            "histogram": {...}
          }]
        }]
      }]
    }
    ```
    """
    metrics = get_ingestion_metrics()
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")

    try:
        data = await request.json()
        if not data:
            raise HTTPException(status_code=400, detail="Invalid JSON")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e!s}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e!s}")

    pg_storage = PostgresStorage(dsn="postgresql://postgres:postgres@localhost:5432/ollyscale")
    await pg_storage.connect()
    metric_count = 0
    if isinstance(data, dict) and "resourceMetrics" in data:
        for resource_metric in data.get("resourceMetrics", []):
            for scope_metric in resource_metric.get("scopeMetrics", []):
                for metric in scope_metric.get("metrics", []):
                    await pg_storage.store_metric(metric)
                    metric_count += 1
    else:
        metrics_data = data if isinstance(data, list) else [data]
        valid_metrics = [m for m in metrics_data if isinstance(m, dict) and "name" in m]
        for metric in valid_metrics:
            await pg_storage.store_metric(metric)
        metric_count = len(valid_metrics)
    await pg_storage.close()

    metrics["ingestion_counter"].add(metric_count, {"type": "metrics"})
    metrics["storage_operations_counter"].add(1, {"operation": "store_metrics", "count": metric_count})
    return {"status": "ok"}
