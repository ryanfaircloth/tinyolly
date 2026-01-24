# API Comparison: V1 (Redis) vs V2 (PostgreSQL)

**Last Updated:** January 23, 2026

---

## Overview

| Aspect | V1 API (Redis) | V2 API (PostgreSQL) |
|--------|----------------|---------------------|
| **Storage** | Redis (ephemeral, 30min TTL) | PostgreSQL (persistent) |
| **Query Style** | GET with query params | POST with request bodies |
| **Response Format** | OpenTelemetry-native JSON | OpenTelemetry-aligned schemas |
| **Pagination** | Simple `?limit=X` | Cursor-based pagination |
| **Filtering** | Query params (`?service=X`) | Filter arrays in POST body |
| **Time Range** | Implicit (last 30min) | Explicit TimeRange in POST |
| **Location** | `apps/ollyscale/` | `apps/frontend/` |

---

## Endpoint Comparison

### 1. System Statistics

#### V1 (Redis)
```http
GET /api/stats
```

**Response:**
```json
{
  "trace_count": 1523,
  "span_count": 8945,
  "log_count": 15234,
  "metric_count": 234,
  "service_count": 12,
  "uptime_seconds": 3600,
  "redis_memory_mb": 45.2
}
```

#### V2 (PostgreSQL)
```http
❌ MISSING - Needs implementation
```

**Proposed Response:**
```json
{
  "trace_count": 1523,
  "span_count": 8945,
  "log_count": 15234,
  "metric_count": 234,
  "service_count": 12,
  "oldest_data": 1706011200000000000,
  "newest_data": 1706097600000000000
}
```

---

### 2. Traces

#### V1 (Redis)
```http
GET /api/traces?limit=50
```

**Response:**
```json
[
  {
    "trace_id": "abc123...",
    "root_service": "frontend",
    "root_operation": "GET /api/users",
    "start_time": 1706097600000000000,
    "duration_ns": 45000000,
    "span_count": 12,
    "error": false
  }
]
```

#### V2 (PostgreSQL)
```http
POST /api/traces/search

Body:
{
  "time_range": {
    "start_time": 1706011200000000000,
    "end_time": 1706097600000000000
  },
  "pagination": {
    "limit": 50
  }
}
```

**Response:**
```json
{
  "traces": [
    {
      "trace_id": "abc123...",
      "root_span_id": "def456...",
      "service_name": "frontend",
      "operation_name": "GET /api/users",
      "start_time_unix_nano": 1706097600000000000,
      "end_time_unix_nano": 1706097645000000000,
      "duration_ns": 45000000,
      "span_count": 12,
      "status_code": 0,
      "attributes": {}
    }
  ],
  "pagination": {
    "has_more": false,
    "next_cursor": null,
    "total_count": 1523
  }
}
```

**❌ INCOMPATIBLE** - Need GET wrapper

---

### 3. Single Trace Detail

#### V1 (Redis)
```http
GET /api/traces/{trace_id}
```

**Response:**
```json
{
  "trace_id": "abc123...",
  "spans": [
    {
      "span_id": "def456...",
      "trace_id": "abc123...",
      "parent_span_id": null,
      "name": "GET /api/users",
      "kind": 2,
      "startTimeUnixNano": "1706097600000000000",
      "endTimeUnixNano": "1706097645000000000",
      "attributes": {...},
      "status": {...}
    }
  ],
  "span_count": 12
}
```

#### V2 (PostgreSQL)
```http
GET /api/traces/{trace_id}
```

**Response:**
```json
{
  "trace_id": "abc123...",
  "spans": [...],
  "metadata": {
    "span_count": 12,
    "duration_ns": 45000000
  }
}
```

**✅ COMPATIBLE** - Minor response format differences (acceptable)

---

### 4. Spans

#### V1 (Redis)
```http
GET /api/spans?limit=100&service=frontend
```

**Response:**
```json
[
  {
    "span_id": "def456...",
    "trace_id": "abc123...",
    "parent_span_id": null,
    "service_name": "frontend",
    "name": "GET /api/users",
    "kind": 2,
    "startTimeUnixNano": "1706097600000000000",
    "endTimeUnixNano": "1706097645000000000",
    "duration_ns": 45000000,
    "attributes": {...}
  }
]
```

#### V2 (PostgreSQL)
```http
❌ MISSING - No spans endpoint exists
```

**Proposed:**
```http
POST /api/spans/search

Body:
{
  "time_range": {...},
  "filters": [
    {"field": "service.name", "operator": "eq", "value": "frontend"}
  ],
  "pagination": {"limit": 100}
}
```

**❌ INCOMPATIBLE** - Need GET wrapper + POST endpoint

---

### 5. Logs

#### V1 (Redis)
```http
GET /api/logs?limit=100&trace_id=abc123
```

**Response:**
```json
[
  {
    "log_id": "xyz789...",
    "trace_id": "abc123...",
    "span_id": "def456...",
    "time_unix_nano": "1706097600000000000",
    "severity_number": 9,
    "severity_text": "INFO",
    "body": "User logged in",
    "attributes": {...}
  }
]
```

#### V2 (PostgreSQL)
```http
POST /api/logs/search

Body:
{
  "time_range": {...},
  "filters": [
    {"field": "trace_id", "operator": "eq", "value": "abc123"}
  ],
  "pagination": {"limit": 100}
}
```

**Response:**
```json
{
  "logs": [
    {
      "time_unix_nano": 1706097600000000000,
      "observed_time_unix_nano": 1706097600000000000,
      "severity_number": 9,
      "severity_text": "INFO",
      "body": "User logged in",
      "attributes": [...],
      "trace_id": "abc123...",
      "span_id": "def456...",
      "resource": {...},
      "scope": {...}
    }
  ],
  "pagination": {
    "has_more": false,
    "next_cursor": null
  }
}
```

**❌ INCOMPATIBLE** - Need GET wrapper

---

### 6. Metrics

#### V1 (Redis)
```http
GET /api/metrics
```

**Response:**
```json
[
  {
    "name": "http.server.duration",
    "type": "histogram",
    "unit": "ms",
    "description": "HTTP server request duration",
    "data_points": [
      {
        "attributes": {"service.name": "frontend"},
        "time_unix_nano": "1706097600000000000",
        "count": 1523,
        "sum": 45000,
        "buckets": [...]
      }
    ]
  }
]
```

#### V2 (PostgreSQL)
```http
POST /api/metrics/search

Body:
{
  "time_range": {...},
  "pagination": {"limit": 100}
}
```

**Response:**
```json
{
  "metrics": [
    {
      "name": "http.server.duration",
      "description": "HTTP server request duration",
      "unit": "ms",
      "metric_type": "histogram",
      "data_points": [...],
      "resource": {...},
      "scope": {...}
    }
  ],
  "pagination": {
    "has_more": false
  }
}
```

**❌ INCOMPATIBLE** - Need GET wrapper

---

### 7. Service Map

#### V1 (Redis)
```http
GET /api/service-map?limit=500
```

**Response:**
```json
{
  "nodes": [
    {
      "id": "frontend",
      "name": "frontend",
      "type": "service",
      "request_count": 1523,
      "error_rate": 0.05
    }
  ],
  "edges": [
    {
      "source": "frontend",
      "target": "backend",
      "call_count": 1450,
      "error_count": 12
    }
  ]
}
```

#### V2 (PostgreSQL)
```http
POST /api/service-map

Body:
{
  "start_time": 1706011200000000000,
  "end_time": 1706097600000000000
}
```

**Response:**
```json
{
  "nodes": [
    {
      "id": "frontend",
      "name": "frontend",
      "type": "service",
      "attributes": {}
    }
  ],
  "edges": [
    {
      "source": "frontend",
      "target": "backend",
      "call_count": 1450,
      "error_count": 12,
      "avg_duration_ms": 31.2
    }
  ],
  "time_range": {
    "start_time": 1706011200000000000,
    "end_time": 1706097600000000000
  }
}
```

**❌ INCOMPATIBLE** - Need GET wrapper

---

### 8. Service Catalog

#### V1 (Redis)
```http
GET /api/service-catalog
```

**Response:**
```json
[
  {
    "service_name": "frontend",
    "request_count": 1523,
    "error_count": 76,
    "error_rate": 5.0,
    "p50_latency_ms": 25.3,
    "p95_latency_ms": 89.7,
    "p99_latency_ms": 145.2
  }
]
```

#### V2 (PostgreSQL)
```http
GET /api/services?start_time=X&end_time=Y
```

**Response:**
```json
{
  "services": [
    {
      "name": "frontend",
      "request_count": 1523,
      "error_count": 76,
      "error_rate": 5.0,
      "p50_latency_ms": 25.3,
      "p95_latency_ms": 89.7,
      "first_seen": 1706011200000000000,
      "last_seen": 1706097600000000000,
      "namespace": "default",
      "version": "v1.2.3"
    }
  ],
  "total_count": 12
}
```

**✅ MOSTLY COMPATIBLE** - Just rename in JS: `/api/service-catalog` → `/api/services`

---

## Key Differences Summary

### Query Style

| Feature | V1 | V2 |
|---------|----|----|
| **Method** | GET | POST |
| **Filters** | Query params (`?service=X`) | Filter array in body |
| **Time Range** | Implicit (last 30min) | Explicit `TimeRange` object |
| **Pagination** | Simple `?limit=X` | Cursor-based |
| **Complexity** | Simple, URL-based | Advanced, structured |

### Response Structure

| Feature | V1 | V2 |
|---------|----|----|
| **Traces** | Array of objects | `{traces: [...], pagination: {...}}` |
| **Logs** | Array of objects | `{logs: [...], pagination: {...}}` |
| **Metrics** | Array of objects | `{metrics: [...], pagination: {...}}` |
| **Services** | Array of objects | `{services: [...], total_count: N}` |
| **Service Map** | `{nodes: [...], edges: [...]}` | `{nodes: [...], edges: [...], time_range: {...}}` |

---

## Migration Strategy

### Phase 1: Backward Compatibility GET Endpoints

Add GET wrappers that convert query params → POST request internally:

```python
@router.get("/api/traces")
async def get_traces_simple(
    limit: int = 50,
    storage: Storage = Depends(get_storage)
):
    # Convert to POST request
    now_ns = time.time_ns()
    search_req = TraceSearchRequest(
        time_range=TimeRange(
            start_time=now_ns - (30 * 60 * 10**9),  # Last 30 min
            end_time=now_ns
        ),
        pagination=PaginationRequest(limit=limit)
    )
    
    # Call POST handler internally
    result = await search_traces(search_req, storage)
    
    # Return just the traces array (v1 format)
    return result.traces
```

### Phase 2: Update JavaScript (Optional)

Update UI to use POST endpoints directly for advanced features:

```javascript
// Advanced trace search
const response = await fetch('/api/traces/search', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    time_range: {
      start_time: startTime,
      end_time: endTime
    },
    filters: [
      {field: 'service.name', operator: 'eq', value: 'frontend'},
      {field: 'http.status_code', operator: 'gte', value: 500}
    ],
    pagination: {limit: 100}
  })
});
```

---

## Advantages of V2 API

1. **Structured Queries** - Filter arrays allow complex queries
2. **Pagination** - Cursor-based pagination for large datasets
3. **Explicit Time Ranges** - No ambiguity about query window
4. **OpenAPI Schemas** - Full request/response validation
5. **Persistent Storage** - PostgreSQL allows advanced analytics

---

## Advantages of V1 API

1. **Simple URLs** - Easy to test with curl
2. **Browser-friendly** - Can share URLs with query params
3. **Cacheable** - GET requests can be cached by browsers
4. **Familiar** - Standard REST patterns

---

## Conclusion

**Hybrid Approach (Recommended):**
- Keep v2 POST endpoints for advanced queries
- Add v1-compatible GET wrappers for simple queries
- UI works immediately with minimal changes
- Future: Gradually migrate UI to use POST endpoints

**Files to Create/Modify:**
1. `apps/frontend/app/routers/query.py` - Add GET wrappers
2. `apps/ollyscale-ui/src/modules/api.js` - Update service-catalog call
3. `apps/frontend/app/services/storage.py` - Add count/stats methods

---

**See Also:**
- [V2-API-MIGRATION-PLAN.md](./V2-API-MIGRATION-PLAN.md) - Detailed implementation plan
- [V2-MIGRATION-TRACKING.md](./V2-MIGRATION-TRACKING.md) - Progress tracking
