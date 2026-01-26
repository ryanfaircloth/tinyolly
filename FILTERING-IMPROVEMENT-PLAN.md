# Filtering & UI Improvement Plan

## Issues to Address

### 1. Spans View Bug

**Error**: `can't access property "length", r is null`  
**Location**: `apps/ollyscale-ui/src/modules/api.js:123-124`  
**Root Cause**: `result.traces` can be null/undefined, but code accesses it without null check  
**Fix**: Add null check before iterating traces

### 2. Remove Generic Search Boxes

- Current UI has freeform text search boxes
- Need specific, structured filters instead
- Keep namespace dropdown (already implemented)

### 3. Add Structured Filters

#### For Logs

- **Log Level Dropdown**: Multi-select (TRACE, DEBUG, INFO, WARN, ERROR, FATAL)
  - Maps to OTel severity numbers: TRACE(1-4), DEBUG(5-8), INFO(9-12), WARN(13-16), ERROR(17-20), FATAL(21-24)
  - Default: All selected
- **Trace ID Filter**: Clickable links + manual input
  - Support NULL (valid for logs without traces)
- **Span ID Filter**: Clickable links + manual input  
  - Never NULL (skip if not present)

#### For Traces/Spans

- **HTTP Status Dropdown**: Multi-select (2xx, 4xx, 5xx, unknown)
  - Default: All selected
- **Trace ID Filter**: Clickable links + manual input
- **Span ID Filter**: Clickable links (spans only)

## Implementation Plan

### Phase 1: Backend Filter Support (DRY Approach)

**File**: `apps/frontend/app/storage/postgres_orm.py`

Add helper methods (similar to `_apply_namespace_filtering`):

```python
@staticmethod
def _apply_traceid_filter(stmt, fact_table, filters):
    """Apply trace_id filtering.

    Args:
        stmt: SQLAlchemy statement
        fact_table: Table model (LogsFact, SpansFact, TracesFact)
        filters: List of Filter objects

    Returns:
        Modified statement
    """
    trace_filters = [f for f in filters if f.field == "trace_id"]
    if not trace_filters:
        return stmt

    for f in trace_filters:
        if f.operator == "equals":
            if f.value == "" or f.value is None:
                # NULL trace_id (only valid for logs)
                stmt = stmt.where(fact_table.trace_id.is_(None))
            else:
                stmt = stmt.where(fact_table.trace_id == f.value)

    return stmt

@staticmethod
def _apply_spanid_filter(stmt, fact_table, filters):
    """Apply span_id filtering (never NULL)."""
    span_filters = [f for f in filters if f.field == "span_id"]
    if not span_filters:
        return stmt

    for f in span_filters:
        if f.operator == "equals" and f.value:
            stmt = stmt.where(fact_table.span_id == f.value)

    return stmt

@staticmethod
def _apply_log_level_filter(stmt, filters):
    """Apply log severity level filtering with IN operator.

    Supports both severity_text (TRACE, DEBUG, INFO, WARN, ERROR, FATAL)
    and severity_number ranges per OTel spec:
    - TRACE: 1-4
    - DEBUG: 5-8
    - INFO: 9-12
    - WARN: 13-16
    - ERROR: 17-20
    - FATAL: 21-24
    """
    from sqlalchemy import or_

    level_filters = [f for f in filters if f.field == "severity"]
    if not level_filters:
        return stmt

    for f in level_filters:
        if f.operator == "in" and f.value:
            # Map text levels to number ranges
            conditions = []
            for level_text in f.value:
                if level_text == "TRACE":
                    conditions.append(LogsFact.severity_number.between(1, 4))
                elif level_text == "DEBUG":
                    conditions.append(LogsFact.severity_number.between(5, 8))
                elif level_text == "INFO":
                    conditions.append(LogsFact.severity_number.between(9, 12))
                elif level_text == "WARN":
                    conditions.append(LogsFact.severity_number.between(13, 16))
                elif level_text == "ERROR":
                    conditions.append(LogsFact.severity_number.between(17, 20))
                elif level_text == "FATAL":
                    conditions.append(LogsFact.severity_number.between(21, 24))

            if conditions:
                stmt = stmt.where(or_(*conditions))

    return stmt

@staticmethod
def _apply_http_status_filter(stmt, filters):
    """Apply HTTP status code range filtering (2xx, 4xx, 5xx, unknown)."""
    from sqlalchemy import or_

    status_filters = [f for f in filters if f.field == "http_status"]
    if not status_filters:
        return stmt

    conditions = []
    for f in status_filters:
        if f.operator == "in" and f.value:
            for status_range in f.value:
                if status_range == "2xx":
                    conditions.append(SpansFact.http_status_code.between(200, 299))
                elif status_range == "4xx":
                    conditions.append(SpansFact.http_status_code.between(400, 499))
                elif status_range == "5xx":
                    conditions.append(SpansFact.http_status_code.between(500, 599))
                elif status_range == "unknown":
                    conditions.append(SpansFact.http_status_code.is_(None))

    if conditions:
        stmt = stmt.where(or_(*conditions))

    return stmt
```

**Update search methods**:

```python
async def search_logs(...):
    # ... existing code ...

    # Apply new filters
    stmt = self._apply_traceid_filter(stmt, LogsFact, filters)
    stmt = self._apply_spanid_filter(stmt, LogsFact, filters)
    stmt = self._apply_log_level_filter(stmt, filters)

    # ... rest of search ...

async def search_spans(...):  # NEW METHOD NEEDED
    # Similar to search_traces but returns individual spans
    stmt = self._apply_traceid_filter(stmt, SpansFact, filters)
    stmt = self._apply_spanid_filter(stmt, SpansFact, filters)
    stmt = self._apply_http_status_filter(stmt, filters)

async def search_traces(...):
    # Add namespace filtering (currently missing)
    stmt, namespace_filters = self._apply_namespace_filtering(stmt, filters)
    stmt = self._apply_traceid_filter(stmt, SpansFact, filters)  # Use SpansFact
    stmt = self._apply_http_status_filter(stmt, filters)
```

### Phase 2: API Endpoints

**File**: `apps/frontend/app/routers/query.py`

Add `/spans/search` endpoint:

```python
@router.post("/spans/search", response_model=SpanSearchResponse)
async def search_spans(request: SpanSearchRequest, storage: StorageBackend = Depends(get_storage)):
    """Search spans with filters and pagination."""
    try:
        spans, has_more, next_cursor = await storage.search_spans(
            time_range=request.time_range,
            filters=request.filters,
            pagination=request.pagination
        )

        return SpanSearchResponse(
            spans=spans,
            pagination=PaginationResponse(has_more=has_more, next_cursor=next_cursor, total_count=len(spans)),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search spans: {e!s}",
        ) from e
```

**File**: `apps/frontend/app/models/api.py`

Add new models:

```python
class SpanSearchRequest(BaseModel):
    time_range: TimeRange
    filters: list[Filter] | None = None
    pagination: Pagination | None = None

class SpanSearchResponse(BaseModel):
    spans: list[dict]
    pagination: PaginationResponse
```

### Phase 3: Frontend Components

**New Files**:

1. `apps/ollyscale-ui/src/modules/logLevelFilter.js`

```javascript
// Multi-select dropdown for log levels
// Default: all selected
// Levels: TRACE, DEBUG, INFO, WARN, ERROR, FATAL
// Maps to OTel severity numbers: TRACE(1-4), DEBUG(5-8), INFO(9-12), WARN(13-16), ERROR(17-20), FATAL(21-24)

export function createLogLevelFilter() {
    // Returns: { field: "severity", operator: "in", value: ["ERROR", "WARN"] }
}
```

1. `apps/ollyscale-ui/src/modules/httpStatusFilter.js`

```javascript
// Multi-select dropdown for HTTP status ranges
// Default: all selected
// Ranges: 2xx, 4xx, 5xx, unknown

export function createHttpStatusFilter() {
    // Returns: { field: "http_status", operator: "in", value: ["2xx", "4xx"] }
}
```

1. `apps/ollyscale-ui/src/modules/traceSpanFilter.js`

```javascript
// Input fields + clickable links for trace_id/span_id
// Makes trace/span IDs in results clickable

export function makeTraceIdClickable(traceId) {
    // Returns HTML: <a href="#" data-trace-id="...">traceId</a>
}

export function makeSpanIdClickable(spanId) {
    // Returns HTML: <a href="#" data-span-id="...">spanId</a>
}

export function attachFilterClickHandlers() {
    // Attaches click handlers to links
    // Calls loadLogs/loadSpans/loadTraces with filter
}
```

**Updated Files**:

1. `apps/ollyscale-ui/src/modules/api.js`
   - Fix spans null check bug
   - Add `searchSpans()` function (call `/api/spans/search`)
   - Update `loadLogs()`, `loadTraces()` to accept structured filters

2. `apps/ollyscale-ui/src/modules/logs.js`
   - Remove generic search box
   - Add log level dropdown
   - Make trace_id/span_id clickable

3. `apps/ollyscale-ui/src/modules/traces.js`
   - Remove generic search box
   - Add HTTP status dropdown
   - Make trace_id clickable

4. `apps/ollyscale-ui/src/index.html`
   - Update UI layout with new filter controls

### Phase 4: Unit Tests

**New Test Files**:

1. `apps/frontend/tests/test_traceid_spanid_filtering.py`

```python
@pytest.mark.asyncio
async def test_logs_filter_by_traceid():
    """Test logs can be filtered by trace_id"""

@pytest.mark.asyncio
async def test_logs_filter_by_null_traceid():
    """Test logs can be filtered by NULL trace_id"""

@pytest.mark.asyncio
async def test_spans_filter_by_spanid():
    """Test spans can be filtered by span_id"""

@pytest.mark.asyncio  
async def test_spanid_null_not_allowed():
    """Test NULL span_id filters are skipped"""
```

1. `apps/frontend/tests/test_log_level_filtering.py`

```python
@pytest.mark.asyncio
async def test_log_level_single(): (e.g., ERROR = 17-20)"""

@pytest.mark.asyncio
async def test_log_level_multiple():
    """Test filtering logs by multiple severity levels (IN operator)"""

@pytest.mark.asyncio
async def test_log_level_trace():
    """Test TRACE level maps to severity_number 1-4"""

@pytest.mark.asyncio
async def test_log_level_fatal():
    """Test FATAL level maps to severity_number 21-24
    """Test filtering logs by multiple severity levels (IN operator)"""
```

1. `apps/frontend/tests/test_http_status_filtering.py`

```python
@pytest.mark.asyncio
async def test_http_status_2xx():
    """Test filtering spans by 2xx status codes"""

@pytest.mark.asyncio
async def test_http_status_multiple_ranges():
    """Test filtering spans by multiple status ranges (2xx + 4xx)"""

@pytest.mark.asyncio
async def test_http_status_unknown():
    """Test filtering spans with NULL status code"""
```

### Phase 5: Deployment & Verification

**Steps**:

1. Run unit tests:

   ```bash
   cd apps/frontend
   poetry run pytest tests/test_traceid_spanid_filtering.py -v
   poetry run pytest tests/test_log_level_filtering.py -v
   poetry run pytest tests/test_http_status_filtering.py -v
   ```

2. Deploy:

   ```bash
   make deploy
   ```

3. Verify pods:

   ```bash
   kubectl get pods -n ollyscale
   kubectl logs -n ollyscale deployment/ollyscale-frontend -f
   ```

4. Test API with curl:

   ```bash
   # Test trace_id filter
   curl -X POST https://ollyscale.ollyscale.test:49443/api/logs/search \
     -H "Content-Type: application/json" \
     -d '{"time_range":{"start_time":0,"end_time":9999999999999},"filters":[{"field":"trace_id","operator":"equals","value":"abc123"}]}'

   # Test log level filter (ERROR = 17-20, WARN = 13-16)
   curl -X POST https://ollyscale.ollyscale.test:49443/api/logs/search \
     -H "Content-Type: application/json" \
     -d '{"time_range":{"start_time":0,"end_time":9999999999999},"filters":[{"field":"severity","operator":"in","value":["ERROR","WARN"]}]}'

   # Test TRACE level (severity_number 1-4)
   curl -X POST https://ollyscale.ollyscale.test:49443/api/logs/search \
     -H "Content-Type: application/json" \
     -d '{"time_range":{"start_time":0,"end_time":9999999999999},"filters":[{"field":"severity","operator":"in","value":["TRACE"]}]}'

   # Test HTTP status filter
   curl -X POST https://ollyscale.ollyscale.test:49443/api/spans/search \
     -H "Content-Type: application/json" \
     -d '{"time_range":{"start_time":0,"end_time":9999999999999},"filters":[{"field":"http_status","operator":"in","value":["4xx","5xx"]}]}'

   # Test NULL trace_id for logs
   curl -X POST https://ollyscale.ollyscale.test:49443/api/logs/search \
     -H "Content-Type: application/json" \
     -d '{"time_range":{"start_time":0,"end_time":9999999999999},"filters":[{"field":"trace_id","operator":"equals","value":null}]}'
   ```

## Database Schema Verification

**Check if columns exist**:

```sql, 'severity_number'
-- Check LogsFact
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'logs_fact'
AND column_name IN ('trace_id', 'span_id', 'severity_text');

-- Check SpansFact
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'spans_fact' TRACE, DEBUG, INFO, WARN, ERROR, FATAL - multi-select, default all)
- [ ] Log level filtering uses severity_number ranges per OTel spec
AND column_name IN ('trace_id', 'span_id', 'http_status_code');
```

## Success Criteria

- [ ] Spans view error fixed (null check added)
- [ ] Generic search boxes removed
- [ ] Log level dropdown working (multi-select, default all)
- [ ] HTTP status dropdown working (multi-select, default all)
- [ ] Trace ID clickable in all views
- [ ] Span ID clickable where relevant
- [ ] NULL trace_id filter works for logs
- [ ] NULL span_id filter never applied
- [ ] All unit tests pass
- [ ] Deployment successful
- [ ] API curl tests pass
- [ ] UI functional in browser

## Notes

- All filter helpers use `@staticmethod` for consistency
- DRY approach: one helper per filter type, reused across search methods
- NULL handling: trace_id can be NULL (logs), span_id cannot
- Frontend: Use structured filter objects, not freeform text
- Backend: Validate filter fields/operators before applying
