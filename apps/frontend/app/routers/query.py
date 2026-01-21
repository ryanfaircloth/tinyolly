"""Query endpoints for traces, logs, and metrics."""

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_storage
from app.models.api import (
    LogSearchRequest,
    LogSearchResponse,
    MetricSearchRequest,
    MetricSearchResponse,
    PaginationResponse,
    ServiceListResponse,
    ServiceMapResponse,
    TimeRange,
    TraceSearchRequest,
    TraceSearchResponse,
)
from app.storage import StorageBackend

router = APIRouter()


@router.post("/traces/search", response_model=TraceSearchResponse)
async def search_traces(request: TraceSearchRequest, storage: StorageBackend = Depends(get_storage)):
    """Search traces with filters and pagination."""
    traces, has_more, next_cursor = await storage.search_traces(
        time_range=request.time_range, filters=request.filters, pagination=request.pagination
    )

    return TraceSearchResponse(
        traces=traces,
        pagination=PaginationResponse(has_more=has_more, next_cursor=next_cursor, total_count=len(traces)),
    )


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, storage: StorageBackend = Depends(get_storage)):
    """Get trace by ID with all spans."""
    trace = await storage.get_trace_by_id(trace_id)

    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    return trace


@router.post("/logs/search", response_model=LogSearchResponse)
async def search_logs(request: LogSearchRequest, storage: StorageBackend = Depends(get_storage)):
    """Search logs with filters and pagination."""
    logs, has_more, next_cursor = await storage.search_logs(
        time_range=request.time_range, filters=request.filters, pagination=request.pagination
    )

    return LogSearchResponse(
        logs=logs,
        pagination=PaginationResponse(has_more=has_more, next_cursor=next_cursor, total_count=len(logs)),
    )


@router.post("/metrics/search", response_model=MetricSearchResponse)
async def search_metrics(request: MetricSearchRequest, storage: StorageBackend = Depends(get_storage)):
    """Search metrics with filters and pagination."""
    metrics, has_more, next_cursor = await storage.search_metrics(
        time_range=request.time_range,
        metric_names=request.metric_names,
        filters=request.filters,
        pagination=request.pagination,
    )

    return MetricSearchResponse(
        metrics=metrics,
        pagination=PaginationResponse(has_more=has_more, next_cursor=next_cursor, total_count=len(metrics)),
    )


@router.get("/services", response_model=ServiceListResponse)
async def list_services(
    start_time: int | None = None, end_time: int | None = None, storage: StorageBackend = Depends(get_storage)
):
    """List services with RED metrics for optional time range."""
    # Build time range if provided
    time_range = None
    if start_time and end_time:
        time_range = TimeRange(start_time=start_time, end_time=end_time)

    services = await storage.get_services(time_range=time_range)

    return ServiceListResponse(services=services, total_count=len(services))


@router.post("/service-map", response_model=ServiceMapResponse)
async def get_service_map(time_range: TimeRange, storage: StorageBackend = Depends(get_storage)):
    """Get service dependency map for time range."""
    nodes, edges = await storage.get_service_map(time_range=time_range)

    return ServiceMapResponse(nodes=nodes, edges=edges, time_range=time_range)
