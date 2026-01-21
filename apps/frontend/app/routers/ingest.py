"""Ingestion endpoints for OTLP data."""

from fastapi import APIRouter, status

from app.models.api import LogIngestRequest, MetricIngestRequest, TraceIngestRequest

router = APIRouter()


@router.post("/traces", status_code=status.HTTP_202_ACCEPTED)
async def ingest_traces(request: TraceIngestRequest):
    """Ingest OTLP traces."""
    # TODO: Implement trace storage
    return {"status": "accepted", "count": len(request.resource_spans)}


@router.post("/logs", status_code=status.HTTP_202_ACCEPTED)
async def ingest_logs(request: LogIngestRequest):
    """Ingest OTLP logs."""
    # TODO: Implement log storage
    return {"status": "accepted", "count": len(request.resource_logs)}


@router.post("/metrics", status_code=status.HTTP_202_ACCEPTED)
async def ingest_metrics(request: MetricIngestRequest):
    """Ingest OTLP metrics."""
    # TODO: Implement metric storage
    return {"status": "accepted", "count": len(request.resource_metrics)}
