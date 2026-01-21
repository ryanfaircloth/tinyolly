"""
Pydantic v2 models for OpenTelemetry (OTEL) trace/span/log/metric ingestion.
Covers minimal OTLP JSON payloads for v2 API.
"""

from typing import Any

from pydantic import BaseModel


class OTLPAttribute(BaseModel):
    key: str
    value: Any


class OTLPEvent(BaseModel):
    name: str
    time_unix_nano: int
    attributes: list[OTLPAttribute] | None = None


class OTLPLink(BaseModel):
    trace_id: str
    span_id: str
    attributes: list[OTLPAttribute] | None = None


class OTLPSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: int
    start_time_unix_nano: int
    end_time_unix_nano: int
    attributes: list[OTLPAttribute] | None = None
    events: list[OTLPEvent] | None = None
    links: list[OTLPLink] | None = None
    status_code: int | None = None
    status_message: str | None = None


class OTLPResource(BaseModel):
    attributes: list[OTLPAttribute] | None = None


class OTLPResourceSpans(BaseModel):
    resource: OTLPResource
    spans: list[OTLPSpan]


class OTLPTraceRequest(BaseModel):
    resource_spans: list[OTLPResourceSpans]


# Minimal log/metric models for future expansion
class OTLPLogRecord(BaseModel):
    time_unix_nano: int
    severity_number: int
    severity_text: str | None = None
    body: Any
    attributes: list[OTLPAttribute] | None = None


class OTLPResourceLogs(BaseModel):
    resource: OTLPResource
    logs: list[OTLPLogRecord]


class OTLPLogRequest(BaseModel):
    resource_logs: list[OTLPResourceLogs]


class OTLPMetric(BaseModel):
    name: str
    description: str | None = None
    unit: str | None = None
    data_points: list[Any]
    attributes: list[OTLPAttribute] | None = None


class OTLPResourceMetrics(BaseModel):
    resource: OTLPResource
    metrics: list[OTLPMetric]


class OTLPMetricRequest(BaseModel):
    resource_metrics: list[OTLPResourceMetrics]
