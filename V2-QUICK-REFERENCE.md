# V2 API Migration - Quick Reference

**Status:** 🔴 Planning Phase  
**Goal:** Make v2 frontend API compatible with existing UI

---

## The Problem

UI expects v1 GET endpoints → v2 has POST endpoints → UI gets 404 errors

```
UI: GET /api/stats → Frontend: 404 ❌
UI: GET /api/traces?limit=50 → Frontend: 404 ❌  
UI: GET /api/spans?service=X → Frontend: 404 ❌
```

---

## The Solution

**Add GET wrapper endpoints** that translate to v2's POST endpoints

```python
# Frontend gains this:
@router.get("/api/stats")
async def get_stats(...):
    return {
        "trace_count": await storage.count_traces(),
        "span_count": await storage.count_spans(),
        # ...
    }

@router.get("/api/traces")
async def get_traces_simple(limit: int = 50, ...):
    # Convert to POST request internally
    search_req = TraceSearchRequest(
        time_range=TimeRange(start_time=..., end_time=...),
        pagination=PaginationRequest(limit=limit)
    )
    result = await search_traces(search_req, storage)
    return result.traces  # Return array, not wrapped object
```

---

## What Needs to Be Done

### 6 New GET Endpoints Needed

1. **GET /api/stats** - System statistics (NEW)
2. **GET /api/spans** - Recent spans (NEW)
3. **GET /api/traces** - Wrap `POST /api/traces/search`
4. **GET /api/logs** - Wrap `POST /api/logs/search`
5. **GET /api/metrics** - Wrap `POST /api/metrics/search`
6. **GET /api/service-map** - Wrap `POST /api/service-map`

### 1 JavaScript Change

- `apps/ollyscale-ui/src/modules/api.js` line ~220:
  - Change: `/api/service-catalog` → `/api/services`

---

## File Locations

### Backend (Python)

```
apps/frontend/
├── app/
│   ├── routers/
│   │   └── query.py          ← Add 6 GET endpoints here
│   ├── services/
│   │   └── storage.py        ← Add count_*() methods
│   └── models.py             ← Add Span model (if missing)
```

### Frontend (JavaScript)

```
apps/ollyscale-ui/
└── src/
    └── modules/
        └── api.js            ← Change service-catalog → services (line ~220)
```

---

## Quick Start Commands

### 1. Edit Backend

```bash
# Open the main query router
code apps/frontend/app/routers/query.py

# Add GET endpoints following the pattern in V2-API-MIGRATION-PLAN.md
```

### 2. Test Endpoints

```bash
# Build and deploy
cd charts
./build-and-push-local.sh v2.x.x-api-compat

# Update ArgoCD
cd ../.kind
terraform apply -replace='kubectl_manifest.observability_applications["observability/ollyscale.yaml"]' -auto-approve

# Test each endpoint
curl http://ollyscale.test/api/stats
curl http://ollyscale.test/api/traces?limit=10
curl http://ollyscale.test/api/spans?limit=20
curl http://ollyscale.test/api/logs?limit=50
curl http://ollyscale.test/api/metrics
curl http://ollyscale.test/api/service-map
```

### 3. Check OpenAPI Docs

```bash
# View in browser
open http://ollyscale.test/docs

# Or check JSON
curl http://ollyscale.test/openapi.json | jq '.paths | keys'
```

### 4. Verify UI

```bash
# Open UI
open http://ollyscale.test

# Check browser console for errors
# All tabs should load data without 404s
```

---

## Code Templates

### GET Endpoint Wrapper Pattern

```python
@router.get(
    "/api/RESOURCE",
    summary="Get recent RESOURCE (simple)",
    tags=["query"]
)
async def get_RESOURCE_simple(
    limit: int = Query(default=100, le=1000),
    # Add filters as query params
    storage: Storage = Depends(get_storage),
):
    """Simple GET interface for UI compatibility."""
    now_ns = time.time_ns()

    # Convert to POST request
    search_req = RESOURCESearchRequest(
        time_range=TimeRange(
            start_time=now_ns - (30 * 60 * 10**9),  # Last 30 min
            end_time=now_ns
        ),
        pagination=PaginationRequest(limit=limit)
    )

    # Call POST handler
    result = await search_RESOURCE(search_req, storage)

    # Return array only (v1 format)
    return result.RESOURCE
```

### Storage Count Method Pattern

```python
async def count_RESOURCE(self) -> int:
    """Count total RESOURCE."""
    result = await self.db.fetch_one(
        "SELECT COUNT(*) FROM RESOURCE_table"
    )
    return result[0] if result else 0
```

---

## Testing Checklist

### Backend Tests

- [ ] `curl http://ollyscale.test/api/stats` returns JSON
- [ ] `curl http://ollyscale.test/api/traces?limit=10` returns array
- [ ] `curl http://ollyscale.test/api/spans?service=X` filters correctly
- [ ] `curl http://ollyscale.test/api/logs?trace_id=X` filters correctly
- [ ] OpenAPI docs show all GET endpoints

### UI Tests

- [ ] Stats tab loads without errors
- [ ] Traces tab displays traces
- [ ] Spans tab shows spans
- [ ] Logs tab displays logs
- [ ] Metrics tab shows metrics
- [ ] Service Map renders graph
- [ ] Service Catalog shows services
- [ ] Browser console has no 404 errors
- [ ] Auto-refresh (5s) works

---

## Common Issues

### Issue: "Method Not Allowed" Error

**Symptom:** `{"detail":"Method Not Allowed"}`

**Cause:** Endpoint exists but only accepts POST

**Fix:** Add GET wrapper endpoint

---

### Issue: "Not Found" Error

**Symptom:** `{"detail":"Not Found"}`

**Cause:** Endpoint doesn't exist at all

**Fix:** Create the endpoint

---

### Issue: Empty Response

**Symptom:** `[]` or `{"services": []}`

**Cause:** No data in database

**Fix:** Deploy demo apps to generate telemetry:

```bash
cd k8s-demo
./02-deploy.sh
```

---

### Issue: 500 Internal Server Error

**Symptom:** `{"detail":"Internal server error"}`

**Cause:** Backend code error (SQL query, missing method, etc.)

**Fix:** Check logs:

```bash
kubectl logs -n ollyscale deployment/ollyscale-frontend -f
```

---

## Documentation Links

- 📋 **[V2-API-MIGRATION-PLAN.md](./V2-API-MIGRATION-PLAN.md)** - Full implementation plan
- 📊 **[V2-MIGRATION-TRACKING.md](./V2-MIGRATION-TRACKING.md)** - Progress tracker
- 🔀 **[V2-API-COMPARISON.md](./V2-API-COMPARISON.md)** - V1 vs V2 comparison

---

## Next Steps

1. ✅ Review migration plan
2. ⏳ **Start implementing GET endpoints** (Sprint 1)
3. Test with curl
4. Deploy to cluster
5. Verify UI works
6. Move to Sprint 2

---

**Questions?** Check the detailed plan or ask in the chat.

**Last Updated:** January 23, 2026
