# V2 API Migration - Progress Tracking

**Status:** 🔴 **IN PROGRESS** - Phase 1 (Critical GET Endpoints)  
**Started:** January 23, 2026  
**Target Completion:** TBD

---

## Quick Summary

The v2 frontend uses POST-based search endpoints while the UI expects v1-style GET endpoints. We're implementing GET wrapper endpoints for backward compatibility while keeping the improved POST endpoints for advanced features.

**See detailed plan:** [V2-API-MIGRATION-PLAN.md](./V2-API-MIGRATION-PLAN.md)

---

## Current Blocker

**UI cannot load data** - Frontend returns 404 for expected GET endpoints like `/api/stats`, `/api/spans`, etc.

---

## Sprint 1: Critical GET Endpoints ⏳ IN PROGRESS

**Goal:** Implement GET wrapper endpoints so UI can load data

### Tasks

- [ ] **GET /api/stats** - System statistics (trace/log/metric counts)
  - [ ] Add endpoint to `apps/frontend/app/routers/query.py`
  - [ ] Implement `count_*()` methods in Storage
  - [ ] Test with curl

- [ ] **GET /api/spans** - Recent spans with optional service filter
  - [ ] Add endpoint to `apps/frontend/app/routers/query.py`
  - [ ] Implement `search_spans()` in Storage
  - [ ] Add Span model if missing
  - [ ] Test with `?service=X` filter

- [ ] **GET /api/traces** - Recent traces wrapper
  - [ ] Add GET endpoint wrapping `POST /api/traces/search`
  - [ ] Convert query params → TimeRange + filters
  - [ ] Test with `?limit=50`

- [ ] **GET /api/logs** - Recent logs wrapper
  - [ ] Add GET endpoint wrapping `POST /api/logs/search`
  - [ ] Support `?trace_id=X` filter
  - [ ] Test with and without trace_id

- [ ] **GET /api/metrics** - Recent metrics wrapper
  - [ ] Add GET endpoint wrapping `POST /api/metrics/search`
  - [ ] Support `?metric_name=X` filter
  - [ ] Test with metric filter

- [ ] **GET /api/service-map** - Service map wrapper
  - [ ] Add GET endpoint wrapping `POST /api/service-map`
  - [ ] Convert `?limit=X` → TimeRange
  - [ ] Test with `?limit=500`

### Testing Sprint 1

- [ ] All endpoints return 200 OK
- [ ] OpenAPI docs list all GET endpoints
- [ ] Curl tests successful for each endpoint
- [ ] No 500 errors in frontend logs

---

## Sprint 2: UI Updates ⏸️ PENDING

**Goal:** Update JavaScript to use correct endpoint names

### Tasks

- [ ] **Update service-catalog call** in `apps/ollyscale-ui/src/modules/api.js`
  - [ ] Change `/api/service-catalog` → `/api/services`
  - [ ] Test Service Catalog tab loads

### Testing Sprint 2

- [ ] Browser DevTools shows no 404 errors
- [ ] All UI tabs populate with data
- [ ] Service Map renders correctly
- [ ] Service Catalog displays services

---

## Sprint 3: Database Schema ⏸️ PENDING

**Goal:** Ensure database has required tables and queries

### Tasks

- [ ] **Verify spans table exists** with correct schema
  - [ ] Check if migration needed
  - [ ] Add indexes for performance

- [ ] **Implement Storage methods**
  - [ ] `count_traces()` - Count distinct trace IDs
  - [ ] `count_spans()` - Count total spans
  - [ ] `count_logs()` - Count total logs
  - [ ] `count_metrics()` - Count distinct metric names
  - [ ] `count_services()` - Count distinct services
  - [ ] `get_oldest_timestamp()` - Min timestamp
  - [ ] `get_newest_timestamp()` - Max timestamp
  - [ ] `search_spans()` - Query spans with filters

### Testing Sprint 3

- [ ] All queries return data
- [ ] Migrations run without errors
- [ ] Query performance < 100ms (p95)
- [ ] Indexes are used (check EXPLAIN)

---

## Sprint 4: Integration Testing ⏸️ PENDING

**Goal:** End-to-end verification

### Tasks

- [ ] Deploy demo apps to generate telemetry
- [ ] Verify each UI tab loads data
- [ ] Load test (1000+ spans/traces/logs)
- [ ] Performance benchmarking
- [ ] Update documentation

### Testing Sprint 4

- [ ] Stats tab shows counts
- [ ] Traces tab displays traces
- [ ] Spans tab shows spans (with service filter)
- [ ] Logs tab shows logs (with trace filter)
- [ ] Metrics tab displays metrics
- [ ] Service Map renders graph
- [ ] Service Catalog shows RED metrics
- [ ] Auto-refresh (5s) works smoothly

---

## Blockers & Issues

### Active Blockers

1. **Frontend returns 404 for GET /api/stats**
   - **Impact:** UI cannot load stats page
   - **Resolution:** Implement GET /api/stats endpoint (Sprint 1)

2. **Frontend returns 404 for GET /api/spans**
   - **Impact:** Spans tab shows no data
   - **Resolution:** Implement GET /api/spans endpoint (Sprint 1)

### Resolved Issues

✅ **Health check 307 redirects** - Fixed by using `/health/` with trailing slash  
✅ **Gateway API routing** - HTTPRoute correctly configured  
✅ **Services exist** - ollyscale-frontend and ollyscale-webui services working

---

## Open Questions

- [ ] Do v1 and v2 return identical JSON structures for traces/spans/logs?
- [ ] Should we transform response format for compatibility?
- [ ] What's the default time range for queries? (Assume last 30 minutes?)
- [ ] How to handle pagination cursors in GET endpoints? (Set cursor=None?)

---

## Next Steps

1. ✅ Create detailed migration plan → [V2-API-MIGRATION-PLAN.md](./V2-API-MIGRATION-PLAN.md)
2. ⏳ **START Sprint 1** - Implement GET wrapper endpoints
3. Test endpoints with curl + OpenAPI docs
4. Deploy to cluster
5. Verify UI loads data
6. Move to Sprint 2 (UI updates)

---

## Commands Reference

### Testing Endpoints

```bash
# Stats
curl http://ollyscale.test/api/stats

# Traces
curl http://ollyscale.test/api/traces?limit=10

# Spans
curl http://ollyscale.test/api/spans?limit=20
curl http://ollyscale.test/api/spans?limit=20&service=frontend

# Logs
curl http://ollyscale.test/api/logs?limit=50
curl http://ollyscale.test/api/logs?trace_id=abc123

# Metrics
curl http://ollyscale.test/api/metrics

# Service Map
curl http://ollyscale.test/api/service-map?limit=500

# Services (Service Catalog)
curl http://ollyscale.test/api/services
```

### Deploy Changes

```bash
cd charts
./build-and-push-local.sh v2.x.x-api-compat

cd ../.kind
terraform apply -replace='kubectl_manifest.observability_applications["observability/ollyscale.yaml"]' -auto-approve

# Wait for deployment
sleep 20 && kubectl get po -n ollyscale

# Check logs
kubectl logs -n ollyscale deployment/ollyscale-frontend -f
```

### Clear Data

```bash
# Clear PostgreSQL data (if needed)
kubectl exec -n ollyscale ollyscale-pg-cluster-1 -- psql -U app -d ollyscale -c "TRUNCATE TABLE spans, logs, metrics, traces CASCADE;"
```

---

## Success Metrics

### Phase 1 Success (Sprint 1)

- [ ] All 6 GET endpoints return 200 OK
- [ ] OpenAPI docs include new endpoints
- [ ] Zero 404 errors in logs

### Phase 2 Success (Sprint 2)

- [ ] UI tabs load without errors
- [ ] Browser DevTools shows no 404s

### Phase 3 Success (Sprint 3)

- [ ] Database queries < 100ms
- [ ] All Storage methods implemented

### Phase 4 Success (Sprint 4)

- [ ] End-to-end tests pass
- [ ] UI auto-refresh works
- [ ] Documentation updated

---

**Last Updated:** January 23, 2026  
**Next Review:** After Sprint 1 completion
