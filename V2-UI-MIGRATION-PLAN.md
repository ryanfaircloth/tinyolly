# V2 UI Migration Plan - Migrate to POST-Based API

**Status:** 🟡 **IN PROGRESS**  
**Goal:** Update JavaScript UI to use v2's improved POST-based search API

---

## Overview

The v2 API uses **POST-based search endpoints** with structured request bodies (TimeRange, Filters, Pagination). This is superior to the old GET-based API because:

1. **Structured queries** - Complex filters without URL encoding issues
2. **Better pagination** - Cursor-based for large datasets
3. **Explicit time ranges** - No ambiguity about query windows
4. **Type safety** - Full request/response validation via Pydantic
5. **Future-proof** - Easier to add new filter types

---

## Current UI vs V2 API Mapping

| UI Function | Current Call | V2 Endpoint | Status |
|-------------|--------------|-------------|---------|
| `loadStats()` | `GET /api/stats` | ❌ Not needed - remove | **REMOVE** |
| `loadTraces()` | `GET /api/traces?limit=50` | `POST /api/traces/search` | **UPDATE** |
| `fetchTraceDetail()` | `GET /api/traces/{id}` | `GET /api/traces/{id}` | ✅ Compatible |
| `loadSpans()` | `GET /api/spans?service=X` | `POST /api/traces/search` (extract spans) | **UPDATE** |
| `loadLogs()` | `GET /api/logs?trace_id=X` | `POST /api/logs/search` | **UPDATE** |
| `loadMetrics()` | `GET /api/metrics` | `POST /api/metrics/search` | **UPDATE** |
| `loadServiceMap()` | `GET /api/service-map` | `POST /api/service-map` | **UPDATE** |
| `loadServiceCatalog()` | `GET /api/service-catalog` | `GET /api/services` | **RENAME** |

---

## Implementation Plan

### Step 1: Create API Helper Functions

**File:** `apps/ollyscale-ui/src/modules/api.js`

Add helper functions for building POST requests:

```javascript
/**
 * Build a TimeRange for the last N minutes
 */
function buildTimeRange(minutes = 30) {
    const now = Date.now() * 1000000; // Convert to nanoseconds
    const start = now - (minutes * 60 * 1000000000);
    return {
        start_time: start,
        end_time: now
    };
}

/**
 * Build a search request with time range and optional filters
 */
function buildSearchRequest(filters = [], limit = 100, cursor = null) {
    return {
        time_range: buildTimeRange(),
        filters: filters.length > 0 ? filters : null,
        pagination: {
            limit: limit,
            cursor: cursor
        }
    };
}

/**
 * POST request helper
 */
async function postJSON(url, body) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
}
```

---

### Step 2: Update Trace Loading

**Before:**

```javascript
export async function loadTraces() {
    try {
        const response = await fetch('/api/traces?limit=50');
        let traces = await response.json();
        traces = traces.filter(filterOllyScaleTrace);
        renderTraces(traces);
    } catch (error) {
        console.error('Error loading traces:', error);
        document.getElementById('traces-container').innerHTML = renderErrorState('Error loading traces');
    }
}
```

**After:**

```javascript
export async function loadTraces() {
    try {
        const requestBody = buildSearchRequest([], 50);
        const result = await postJSON('/api/traces/search', requestBody);

        // V2 returns {traces: [...], pagination: {...}}
        let traces = result.traces || [];
        traces = traces.filter(filterOllyScaleTrace);

        renderTraces(traces);
    } catch (error) {
        console.error('Error loading traces:', error);
        document.getElementById('traces-container').innerHTML = renderErrorState('Error loading traces');
    }
}
```

---

### Step 3: Update Span Loading

**Before:**

```javascript
export async function loadSpans(serviceName = null) {
    const container = document.getElementById('spans-container');
    container.innerHTML = renderLoadingState('Loading spans...');

    try {
        let url = '/api/spans?limit=50';
        if (serviceName) {
            url += `&service=${encodeURIComponent(serviceName)}`;
        }
        const response = await fetch(url);
        let spans = await response.json();
        spans = spans.filter(filterOllyScaleData);
        renderSpans(spans);
    } catch (error) {
        console.error('Error loading spans:', error);
        container.innerHTML = renderErrorState('Error loading spans: ' + error.message);
    }
}
```

**After:**

```javascript
export async function loadSpans(serviceName = null) {
    const container = document.getElementById('spans-container');
    container.innerHTML = renderLoadingState('Loading spans...');

    try {
        // Build filters
        const filters = [];
        if (serviceName) {
            filters.push({
                field: 'service.name',
                operator: 'eq',
                value: serviceName
            });
        }

        // Search traces and extract spans
        const requestBody = buildSearchRequest(filters, 100); // Get more traces to extract spans
        const result = await postJSON('/api/traces/search', requestBody);

        // Extract spans from traces
        const allSpans = [];
        for (const trace of (result.traces || [])) {
            if (trace.spans && Array.isArray(trace.spans)) {
                allSpans.push(...trace.spans);
            }
        }

        // Filter and limit
        const spans = allSpans.filter(filterOllyScaleData).slice(0, 50);
        renderSpans(spans);
    } catch (error) {
        console.error('Error loading spans:', error);
        container.innerHTML = renderErrorState('Error loading spans: ' + error.message);
    }
}
```

---

### Step 4: Update Log Loading

**Before:**

```javascript
export async function loadLogs(filterTraceId = null) {
    try {
        let url = '/api/logs?limit=100';
        if (filterTraceId) {
            url += `&trace_id=${filterTraceId}`;
        } else {
            const input = document.getElementById('trace-id-filter');
            if (input && input.value) {
                url += `&trace_id=${input.value.trim()}`;
            }
        }
        const response = await fetch(url);
        let logs = await response.json();
        logs = logs.filter(filterOllyScaleData);
        renderLogs(logs, 'logs-container');
    } catch (error) {
        console.error('Error loading logs:', error);
        document.getElementById('logs-container').innerHTML = renderErrorState('Error loading logs');
    }
}
```

**After:**

```javascript
export async function loadLogs(filterTraceId = null) {
    try {
        // Get trace ID from parameter or input field
        let traceId = filterTraceId;
        if (!traceId) {
            const input = document.getElementById('trace-id-filter');
            if (input && input.value) {
                traceId = input.value.trim();
            }
        }

        // Build filters
        const filters = [];
        if (traceId) {
            filters.push({
                field: 'trace_id',
                operator: 'eq',
                value: traceId
            });
        }

        const requestBody = buildSearchRequest(filters, 100);
        const result = await postJSON('/api/logs/search', requestBody);

        // V2 returns {logs: [...], pagination: {...}}
        let logs = result.logs || [];
        logs = logs.filter(filterOllyScaleData);

        renderLogs(logs, 'logs-container');
    } catch (error) {
        console.error('Error loading logs:', error);
        document.getElementById('logs-container').innerHTML = renderErrorState('Error loading logs');
    }
}
```

---

### Step 5: Update Metrics Loading

**Before:**

```javascript
export async function loadMetrics() {
    const metricsTab = document.getElementById('metrics-content');
    if (!metricsTab || !metricsTab.classList.contains('active')) {
        return;
    }

    try {
        const response = await fetch('/api/metrics');
        let metrics = await response.json();
        metrics = metrics.filter(filterollyScaleMetric);
        renderMetrics(metrics);
    } catch (error) {
        console.error('Error loading metrics:', error);
    }
}
```

**After:**

```javascript
export async function loadMetrics() {
    const metricsTab = document.getElementById('metrics-content');
    if (!metricsTab || !metricsTab.classList.contains('active')) {
        return;
    }

    try {
        const requestBody = buildSearchRequest([], 100);
        const result = await postJSON('/api/metrics/search', requestBody);

        // V2 returns {metrics: [...], pagination: {...}}
        let metrics = result.metrics || [];
        metrics = metrics.filter(filterollyScaleMetric);

        renderMetrics(metrics);
    } catch (error) {
        console.error('Error loading metrics:', error);
    }
}
```

---

### Step 6: Update Service Map Loading

**Before:**

```javascript
export async function loadServiceMap() {
    const loadingEl = document.getElementById('map-loading');
    if (loadingEl) loadingEl.style.display = 'flex';

    try {
        const response = await fetch('/api/service-map?limit=500');
        let graph = await response.json();

        // Filter logic...
        renderServiceMap(graph);
    } catch (error) {
        console.error('Error loading service map:', error);
        if (loadingEl) loadingEl.style.display = 'none';
    }
}
```

**After:**

```javascript
export async function loadServiceMap() {
    const loadingEl = document.getElementById('map-loading');
    if (loadingEl) loadingEl.style.display = 'flex';

    try {
        const timeRange = buildTimeRange(30); // Last 30 minutes
        const result = await postJSON('/api/service-map', timeRange);

        // V2 returns {nodes: [...], edges: [...], time_range: {...}}
        let graph = {
            nodes: result.nodes || [],
            edges: result.edges || []
        };

        // Filter ollyScale services if needed
        if (shouldHideOllyScale()) {
            const ollyscaleServices = ['ollyscale-ui', 'ollyscale-otlp-receiver', 'ollyscale-opamp-server'];

            graph.edges = graph.edges.filter(edge =>
                !ollyscaleServices.includes(edge.source) &&
                !ollyscaleServices.includes(edge.target)
            );

            const connectedNodes = new Set();
            graph.edges.forEach(edge => {
                connectedNodes.add(edge.source);
                connectedNodes.add(edge.target);
            });

            graph.nodes = graph.nodes.filter(node =>
                !ollyscaleServices.includes(node.id) &&
                connectedNodes.has(node.id)
            );
        }

        renderServiceMap(graph);
    } catch (error) {
        console.error('Error loading service map:', error);
        if (loadingEl) loadingEl.style.display = 'none';
    }
}
```

---

### Step 7: Update Service Catalog Loading

**Before:**

```javascript
export async function loadServiceCatalog() {
    try {
        const response = await fetch('/api/service-catalog');
        let services = await response.json();
        services = services.filter(filterOllyScaleData);
        renderServiceCatalog(services);
    } catch (error) {
        console.error('Error loading service catalog:', error);
        document.getElementById('catalog-container').innerHTML = renderErrorState('Error loading service catalog');
    }
}
```

**After:**

```javascript
export async function loadServiceCatalog() {
    try {
        // V2 uses /api/services (GET endpoint that already exists)
        const response = await fetch('/api/services');
        const result = await response.json();

        // V2 returns {services: [...], total_count: N}
        let services = result.services || [];
        services = services.filter(filterOllyScaleData);

        renderServiceCatalog(services);
    } catch (error) {
        console.error('Error loading service catalog:', error);
        document.getElementById('catalog-container').innerHTML = renderErrorState('Error loading service catalog');
    }
}
```

---

### Step 8: Remove/Update Stats Loading

**Option A: Remove stats entirely** (stats tab may not be needed)

**Option B: Calculate from other endpoints**

```javascript
export async function loadStats() {
    try {
        // Get services to count
        const servicesResp = await fetch('/api/services');
        const servicesData = await servicesResp.json();

        // Build stats from available data
        const stats = {
            service_count: servicesData.total_count || 0,
            // Other counts could be estimated from pagination metadata
            trace_count: 'N/A',
            span_count: 'N/A',
            log_count: 'N/A',
            metric_count: 'N/A'
        };

        renderStats(stats);
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}
```

---

## Testing Checklist

### Manual Testing

- [ ] Traces tab loads and displays traces
- [ ] Clicking a trace shows trace detail
- [ ] Spans tab loads spans
- [ ] Service filter works in spans tab
- [ ] Logs tab loads logs
- [ ] Trace ID filter works in logs tab
- [ ] Metrics tab displays metrics
- [ ] Service Map renders correctly
- [ ] Service Catalog shows services with RED metrics
- [ ] Stats page works (or is removed)
- [ ] Auto-refresh (5s interval) works without errors
- [ ] Browser console shows no errors
- [ ] Network tab shows successful POST requests

### Browser DevTools Verification

```javascript
// Check requests in Network tab:
// POST /api/traces/search - Status 200
// POST /api/logs/search - Status 200
// POST /api/metrics/search - Status 200
// POST /api/service-map - Status 200
// GET /api/services - Status 200
```

---

## Rollback Plan

If issues occur:

1. **Revert JavaScript changes:**

   ```bash
   git checkout apps/ollyscale-ui/src/modules/api.js
   ```

2. **Rebuild UI:**

   ```bash
   make deploy
   ```

3. **Verify old UI works** with v1 backend if needed

---

## Benefits of This Approach

1. **Better API design** - Structured requests, proper pagination
2. **Type safety** - Pydantic validation on backend
3. **Flexibility** - Easy to add complex filters later
4. **Performance** - Cursor-based pagination for large datasets
5. **Consistency** - All search endpoints use same pattern
6. **Future-proof** - Modern REST API patterns

---

## Next Steps

1. **Implement helper functions** (buildTimeRange, buildSearchRequest, postJSON)
2. **Update each load function** one at a time
3. **Test after each change** to catch issues early
4. **Deploy and verify** UI works correctly
5. **Remove unused code** (stats endpoint if not needed)

---

**Last Updated:** January 23, 2026
