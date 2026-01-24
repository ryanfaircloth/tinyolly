# V2 API Migration Plan

## Executive Summary

The v2 frontend (PostgreSQL-backed) uses **POST-based search endpoints** with structured request bodies, while the v1 API (Redis-backed) uses **GET endpoints** with query parameters. The JavaScript UI expects v1-style GET endpoints. We need to create a compatibility layer to bridge this gap.

## Current State Analysis

### V1 API (Redis - apps/ollyscale) - What UI Expects

```
GET  /api/stats                    → System statistics
GET  /api/traces?limit=50          → List of traces
GET  /api/traces/{trace_id}        → Single trace detail
GET  /api/spans?limit=50&service=X → List of spans
GET  /api/logs?limit=100&trace_id=X → List of logs
GET  /api/metrics                  → List of metrics
GET  /api/service-map?limit=500    → Service dependency graph
GET  /api/service-catalog          → Services with RED metrics
```

### V2 API (PostgreSQL - apps/frontend) - What Actually Exists

```
GET  /health/                      → Health check ✓
GET  /health/db                    → DB health ✓
POST /api/traces                   → Ingest traces (not query!)
POST /api/logs                     → Ingest logs (not query!)
POST /api/metrics                  → Ingest metrics (not query!)
POST /api/traces/search            → Search traces (requires POST body)
GET  /api/traces/{trace_id}        → Get single trace ✓
POST /api/logs/search              → Search logs (requires POST body)
POST /api/metrics/search           → Search metrics (requires POST body)
GET  /api/services?start_time=X    → List services ✓
POST /api/service-map              → Service map (requires POST body)
```

### Gap Analysis

| UI Expectation | V2 Implementation | Status | Action Required |
|----------------|-------------------|--------|-----------------|
| `GET /api/stats` | ❌ Missing | **MISSING** | Create new endpoint |
| `GET /api/traces?limit=50` | `POST /api/traces/search` | **INCOMPATIBLE** | Add GET wrapper |
| `GET /api/traces/{id}` | `GET /api/traces/{id}` | ✅ **COMPATIBLE** | None |
| `GET /api/spans?limit=50` | ❌ Missing | **MISSING** | Create new endpoint |
| `GET /api/logs?limit=100` | `POST /api/logs/search` | **INCOMPATIBLE** | Add GET wrapper |
| `GET /api/metrics` | `POST /api/metrics/search` | **INCOMPATIBLE** | Add GET wrapper |
| `GET /api/service-map?limit=500` | `POST /api/service-map` | **INCOMPATIBLE** | Add GET wrapper |
| `GET /api/service-catalog` | `GET /api/services` | ✅ **COMPATIBLE** | Update JS (rename) |

## Migration Strategy

### Option A: Backward Compatibility Layer (RECOMMENDED)

Create GET endpoint wrappers in v2 that translate query parameters to POST requests internally.

**Pros:**
- No UI changes required
- Gradual migration path
- Both APIs coexist

**Cons:**
- Code duplication
- Maintenance overhead

### Option B: Update JavaScript UI

Rewrite UI to use POST-based search endpoints.

**Pros:**
- Cleaner API design
- Better for complex filters

**Cons:**
- Breaks existing UI patterns
- More refactoring required
- Harder to debug

### Option C: Hybrid Approach (SELECTED)

1. **Add compatibility GET endpoints** for simple queries (stats, spans, etc.)
2. **Update JavaScript** to use new endpoint names where they make sense
3. **Keep POST endpoints** for advanced features

## Implementation Plan

### Phase 1: Create Missing Endpoints (Priority: CRITICAL)

#### 1.1 Add GET /api/stats Endpoint

**File:** `apps/frontend/app/routers/query.py`

```python
@router.get(
    "/api/stats",
    summary="Get system statistics",
    tags=["query"]
)
async def get_stats(storage: Storage = Depends(get_storage)):
    """Get overall system statistics (trace/log/metric counts, services, time range)."""
    # Query database for counts
    return {
        "trace_count": await storage.count_traces(),
        "span_count": await storage.count_spans(),
        "log_count": await storage.count_logs(),
        "metric_count": await storage.count_metrics(),
        "service_count": await storage.count_services(),
        "oldest_data": await storage.get_oldest_timestamp(),
        "newest_data": await storage.get_newest_timestamp(),
    }
```

**Dependencies:**
- Implement `count_*` methods in Storage class
- Add database queries for counts

---

#### 1.2 Add GET /api/spans Endpoint

**File:** `apps/frontend/app/routers/query.py`

```python
@router.get(
    "/api/spans",
    summary="Get recent spans",
    tags=["query"]
)
async def get_spans(
    limit: int = Query(default=50, le=1000),
    service: str | None = Query(default=None),
    storage: Storage = Depends(get_storage),
):
    """Get list of recent spans, optionally filtered by service name."""
    # Convert to internal search request
    now_ns = time.time_ns()
    search_req = SpanSearchRequest(
        time_range=TimeRange(
            start_time=now_ns - (30 * 60 * 10**9),  # Last 30 minutes
            end_time=now_ns
        ),
        filters=[Filter(field="service.name", operator="eq", value=service)] if service else [],
        pagination=PaginationRequest(limit=limit)
    )
    
    result = await storage.search_spans(search_req)
    return result.spans
```

**Dependencies:**
- Implement `search_spans()` method in Storage
- Add Span model and SpanSearchRequest schema
- Database query for spans table

---

### Phase 2: Add GET Wrapper Endpoints (Priority: HIGH)

#### 2.1 Wrap POST /api/traces/search with GET

**File:** `apps/frontend/app/routers/query.py`

```python
@router.get(
    "/api/traces",
    summary="Get recent traces (simple)",
    tags=["query"]
)
async def get_traces_simple(
    limit: int = Query(default=50, le=1000),
    service: str | None = Query(default=None),
    storage: Storage = Depends(get_storage),
):
    """Get recent traces - simple GET interface for UI compatibility."""
    now_ns = time.time_ns()
    
    # Build filters
    filters = []
    if service:
        filters.append(Filter(field="service.name", operator="eq", value=service))
    
    # Convert to search request
    search_req = TraceSearchRequest(
        time_range=TimeRange(
            start_time=now_ns - (30 * 60 * 10**9),  # Last 30 minutes
            end_time=now_ns
        ),
        filters=filters if filters else None,
        pagination=PaginationRequest(limit=limit)
    )
    
    # Use existing search logic
    result = await search_traces(search_req, storage)
    return result.traces
```

---

#### 2.2 Wrap POST /api/logs/search with GET

**File:** `apps/frontend/app/routers/query.py`

```python
@router.get(
    "/api/logs",
    summary="Get recent logs (simple)",
    tags=["query"]
)
async def get_logs_simple(
    limit: int = Query(default=100, le=1000),
    trace_id: str | None = Query(default=None),
    storage: Storage = Depends(get_storage),
):
    """Get recent logs - simple GET interface for UI compatibility."""
    now_ns = time.time_ns()
    
    # Build filters
    filters = []
    if trace_id:
        filters.append(Filter(field="trace_id", operator="eq", value=trace_id))
    
    # Convert to search request
    search_req = LogSearchRequest(
        time_range=TimeRange(
            start_time=now_ns - (30 * 60 * 10**9),  # Last 30 minutes
            end_time=now_ns
        ),
        filters=filters if filters else None,
        pagination=PaginationRequest(limit=limit)
    )
    
    # Use existing search logic
    result = await search_logs(search_req, storage)
    return result.logs
```

---

#### 2.3 Wrap POST /api/metrics/search with GET

**File:** `apps/frontend/app/routers/query.py`

```python
@router.get(
    "/api/metrics",
    summary="Get recent metrics (simple)",
    tags=["query"]
)
async def get_metrics_simple(
    limit: int = Query(default=100, le=1000),
    metric_name: str | None = Query(default=None),
    storage: Storage = Depends(get_storage),
):
    """Get recent metrics - simple GET interface for UI compatibility."""
    now_ns = time.time_ns()
    
    # Convert to search request
    search_req = MetricSearchRequest(
        time_range=TimeRange(
            start_time=now_ns - (30 * 60 * 10**9),  # Last 30 minutes
            end_time=now_ns
        ),
        metric_names=[metric_name] if metric_name else None,
        pagination=PaginationRequest(limit=limit)
    )
    
    # Use existing search logic
    result = await search_metrics(search_req, storage)
    return result.metrics
```

---

#### 2.4 Wrap POST /api/service-map with GET

**File:** `apps/frontend/app/routers/query.py`

```python
@router.get(
    "/api/service-map",
    summary="Get service dependency map (simple)",
    tags=["query"]
)
async def get_service_map_simple(
    limit: int = Query(default=500, le=5000, description="Max traces to analyze"),
    storage: Storage = Depends(get_storage),
):
    """Get service dependency map - simple GET interface for UI compatibility."""
    now_ns = time.time_ns()
    
    # Convert to TimeRange request
    time_range = TimeRange(
        start_time=now_ns - (30 * 60 * 10**9),  # Last 30 minutes
        end_time=now_ns
    )
    
    # Use existing POST logic
    return await get_service_map(time_range, storage)
```

---

### Phase 3: Update JavaScript UI (Priority: MEDIUM)

#### 3.1 Update Service Catalog Call

**File:** `apps/ollyscale-ui/src/modules/api.js`

```javascript
// OLD:
const response = await fetch('/api/service-catalog');

// NEW:
const response = await fetch('/api/services');
```

**Line:** ~220 in api.js

---

### Phase 4: Testing Strategy

#### 4.1 Unit Tests

Create test file: `apps/frontend/tests/test_compat_endpoints.py`

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_stats(client: AsyncClient):
    response = await client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "trace_count" in data
    assert "service_count" in data

@pytest.mark.asyncio
async def test_get_traces_simple(client: AsyncClient):
    response = await client.get("/api/traces?limit=10")
    assert response.status_code == 200
    traces = response.json()
    assert isinstance(traces, list)
    assert len(traces) <= 10

@pytest.mark.asyncio
async def test_get_spans_with_filter(client: AsyncClient):
    response = await client.get("/api/spans?limit=20&service=frontend")
    assert response.status_code == 200
    spans = response.json()
    assert isinstance(spans, list)

@pytest.mark.asyncio
async def test_get_logs_with_trace_filter(client: AsyncClient):
    response = await client.get("/api/logs?trace_id=abc123")
    assert response.status_code == 200
    logs = response.json()
    assert isinstance(logs, list)
```

#### 4.2 Integration Tests

1. **Deploy v2 frontend**
2. **Test each endpoint** with curl:
   ```bash
   curl http://ollyscale.test/api/stats
   curl http://ollyscale.test/api/traces?limit=10
   curl http://ollyscale.test/api/spans?limit=20
   curl http://ollyscale.test/api/logs?limit=50
   curl http://ollyscale.test/api/metrics
   curl http://ollyscale.test/api/service-map
   curl http://ollyscale.test/api/services
   ```

3. **Verify UI loads data** - open browser DevTools and check for:
   - No 404 errors in Network tab
   - Data populates in each tab (Traces, Logs, Metrics, etc.)
   - Service Map renders correctly
   - Service Catalog shows services

---

## Database Schema Requirements

### New Tables/Queries Needed

#### 1. Spans Table (if not exists)

```sql
CREATE TABLE IF NOT EXISTS spans (
    span_id VARCHAR(16) PRIMARY KEY,
    trace_id VARCHAR(32) NOT NULL,
    parent_span_id VARCHAR(16),
    name VARCHAR(255) NOT NULL,
    kind INTEGER,
    start_time_unix_nano BIGINT NOT NULL,
    end_time_unix_nano BIGINT NOT NULL,
    duration_ns BIGINT GENERATED ALWAYS AS (end_time_unix_nano - start_time_unix_nano) STORED,
    status_code INTEGER,
    status_message TEXT,
    attributes JSONB,
    events JSONB,
    links JSONB,
    resource JSONB,
    scope JSONB,
    service_name VARCHAR(255) GENERATED ALWAYS AS (resource->>'service.name') STORED,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_spans_trace_id ON spans(trace_id);
CREATE INDEX idx_spans_service_name ON spans(service_name);
CREATE INDEX idx_spans_start_time ON spans(start_time_unix_nano);
```

#### 2. System Stats Queries

```python
# In Storage class:

async def count_traces(self) -> int:
    """Count total traces."""
    result = await self.db.fetch_one("SELECT COUNT(DISTINCT trace_id) FROM spans")
    return result[0] if result else 0

async def count_spans(self) -> int:
    """Count total spans."""
    result = await self.db.fetch_one("SELECT COUNT(*) FROM spans")
    return result[0] if result else 0

async def count_logs(self) -> int:
    """Count total logs."""
    result = await self.db.fetch_one("SELECT COUNT(*) FROM logs")
    return result[0] if result else 0

async def count_metrics(self) -> int:
    """Count distinct metric names."""
    result = await self.db.fetch_one("SELECT COUNT(DISTINCT name) FROM metrics")
    return result[0] if result else 0

async def count_services(self) -> int:
    """Count distinct services."""
    result = await self.db.fetch_one("SELECT COUNT(DISTINCT service_name) FROM spans WHERE service_name IS NOT NULL")
    return result[0] if result else 0

async def get_oldest_timestamp(self) -> int:
    """Get oldest data timestamp in nanoseconds."""
    result = await self.db.fetch_one("SELECT MIN(start_time_unix_nano) FROM spans")
    return result[0] if result else 0

async def get_newest_timestamp(self) -> int:
    """Get newest data timestamp in nanoseconds."""
    result = await self.db.fetch_one("SELECT MAX(start_time_unix_nano) FROM spans")
    return result[0] if result else 0
```

---

## Implementation Order

### Sprint 1: Critical GET Endpoints (3-5 days)

**Files to modify:**
- `apps/frontend/app/routers/query.py` - Add GET wrapper endpoints
- `apps/frontend/app/services/storage.py` - Add count/stats methods
- `apps/frontend/app/models.py` - Add any missing models (Span, SpanSearchRequest, etc.)

**Deliverables:**
1. ✅ GET /api/stats
2. ✅ GET /api/spans?limit=X&service=Y
3. ✅ GET /api/traces?limit=X
4. ✅ GET /api/logs?limit=X&trace_id=Y
5. ✅ GET /api/metrics
6. ✅ GET /api/service-map?limit=X

**Testing:**
- Unit tests for each endpoint
- Manual curl tests
- OpenAPI docs verify endpoints exist

---

### Sprint 2: UI Updates (1-2 days)

**Files to modify:**
- `apps/ollyscale-ui/src/modules/api.js` - Update service-catalog call

**Deliverables:**
1. ✅ Change `/api/service-catalog` → `/api/services`

**Testing:**
- Browser DevTools shows no 404s
- All tabs load data correctly
- Service Map renders
- Service Catalog populates

---

### Sprint 3: Database Schema & Queries (2-3 days)

**Files to modify:**
- `apps/frontend/app/services/storage.py` - Add missing query methods
- `apps/frontend/alembic/versions/` - Add migration for spans table (if needed)

**Deliverables:**
1. ✅ Implement `count_*` methods
2. ✅ Implement `search_spans()` method
3. ✅ Add database indexes for performance
4. ✅ Ensure spans table exists with correct schema

**Testing:**
- Database migrations run successfully
- Queries return data
- Performance benchmarks (queries < 100ms)

---

### Sprint 4: Integration Testing (1-2 days)

**Deliverables:**
1. ✅ End-to-end tests with demo apps
2. ✅ Load testing (simulate 1000+ spans/traces/logs)
3. ✅ UI verification in all tabs
4. ✅ Documentation updates

---

## Success Criteria

### Functional Requirements

- [ ] All UI tabs load without 404 errors
- [ ] Stats page shows system statistics
- [ ] Traces tab displays recent traces
- [ ] Spans tab displays spans (filterable by service)
- [ ] Logs tab displays logs (filterable by trace_id)
- [ ] Metrics tab displays metrics
- [ ] Service Map renders dependency graph
- [ ] Service Catalog shows services with RED metrics

### Performance Requirements

- [ ] Endpoint response times < 200ms (p95)
- [ ] Database queries use indexes
- [ ] No N+1 query problems
- [ ] UI auto-refresh (5s interval) works smoothly

### Code Quality

- [ ] All endpoints have OpenAPI documentation
- [ ] Unit tests cover 80%+ of new code
- [ ] Pre-commit hooks pass
- [ ] No console errors in browser DevTools

---

## Rollback Plan

If v2 frontend has issues:

1. **Revert HTTPRoute** to point `/` to old ollyscale-ui:5002
2. **Keep PostgreSQL running** - data is preserved
3. **Debug v2 issues** in non-production environment
4. **Re-deploy when ready**

Command:
```bash
kubectl patch httproute ollyscale -n ollyscale --type=merge -p '
spec:
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: ollyscale-ui
      port: 5002
'
```

---

## Open Questions

1. **Response format differences**: Do v1 and v2 return identical JSON structures? May need response transformation.
2. **Pagination**: v1 uses `limit`, v2 uses `PaginationRequest` with cursors. Need to handle cursor→None for simple GET.
3. **Time ranges**: v1 uses "last 30 minutes" implicitly. v2 requires explicit TimeRange. Default to last 30min?
4. **Error handling**: v1 vs v2 error response formats may differ. Need consistent error responses.

---

## Next Steps

1. **Review this plan** with team
2. **Start Sprint 1** - Implement GET wrapper endpoints
3. **Test endpoints** with curl + OpenAPI docs
4. **Deploy to dev** cluster
5. **Verify UI** loads data correctly
6. **Iterate** based on findings

---

## Notes

- **Backward compatibility is key** - UI should work with minimal changes
- **Keep POST endpoints** - they're better for advanced features
- **GET wrappers** are a bridge, not permanent architecture
- **Future**: Migrate UI to use POST endpoints properly (optional)

