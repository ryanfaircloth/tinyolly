# Storage Interface Mismatch - Fix Plan

## Problem Analysis

### Current State

#### Interface Definition (`app/storage/interface.py`)

```python
async def store_traces(self, resource_spans: list[dict[str, Any]]) -> int
async def store_logs(self, resource_logs: list[dict[str, Any]]) -> int
```

**Expected:** List of resource_spans/resource_logs directly

#### ORM Implementation (`app/storage/postgres_orm.py`)

```python
async def store_traces(self, data: dict) -> int:
    resource_spans = data.get("resource_spans", data.get("resourceSpans", []))
```

**Actual:** Expects dict wrapper with "resource_spans" key
**MISMATCH:** Signature doesn't match interface

#### Receiver Usage (`receiver/server.py`)

```python
resource_spans = _convert_to_dict(request).get("resource_spans", [])
count = await storage.store_traces(resource_spans)  # Passes list
```

**Reality:** Passes list directly, following interface contract

#### Test Usage (`tests/test_postgres_orm.py`)

```python
otlp_data = {"resource_spans": [...]}
count = await storage.store_traces(otlp_data)  # Passes dict
```

**WRONG:** Tests pass dict, not matching interface or real usage

### Root Cause

1. **ORM implementation was copied from old postgres.py** which expected wrapped dict
2. **Tests were written against wrong signature** - they test dict input instead of list
3. **No integration test** between receiver and storage layer
4. **Type hints not enforced** - no mypy/pyright catching the mismatch

## Consequences

- Receiver fails at runtime with `'list' object has no attribute 'get'`
- Tests pass but don't validate real usage
- 0 spans stored in database despite receiver running

---

## Fix Plan

### Phase 1: Fix Implementation Signatures

**Goal:** Make ORM implementation match interface contract

#### Task 1.1: Fix `store_traces()` signature

- **File:** `apps/frontend/app/storage/postgres_orm.py`
- **Change:** `async def store_traces(self, data: dict)` → `async def store_traces(self, resource_spans: list[dict])`
- **Logic:** Remove `data.get("resource_spans")` wrapper extraction
- **Expected:** Method accepts list directly, iterates over resource_spans

#### Task 1.2: Fix `store_logs()` signature

- **File:** `apps/frontend/app/storage/postgres_orm.py`
- **Change:** `async def store_logs(self, data: dict)` → `async def store_logs(self, resource_logs: list[dict])`
- **Logic:** Remove `data.get("resource_logs")` wrapper extraction
- **Expected:** Method accepts list directly, iterates over resource_logs

#### Task 1.3: Fix `store_metrics()` signature

- **File:** `apps/frontend/app/storage/postgres_orm.py`
- **Current:** `async def store_metrics(self, data: dict)`
- **Check interface:** What does interface say?
- **Fix:** Match interface signature

---

### Phase 2: Fix Tests

**Goal:** Tests must validate actual receiver usage patterns

#### Task 2.1: Fix `test_store_traces_with_scope_spans()`

- **File:** `apps/frontend/tests/test_postgres_orm.py`
- **Current:** Passes `{"resource_spans": [...]}`
- **Fix:** Pass `[{resource_span_dict}]` directly
- **Expected:** Test validates that list input works

#### Task 2.2: Fix `test_store_logs_with_scope_logs()`

- **File:** `apps/frontend/tests/test_postgres_orm.py`
- **Current:** Passes `{"resource_logs": [...]}`
- **Fix:** Pass `[{resource_log_dict}]` directly
- **Expected:** Test validates that list input works

#### Task 2.3: Add integration test

- **File:** `apps/frontend/tests/test_receiver_storage_integration.py` (NEW)
- **Purpose:** Test receiver → storage flow end-to-end
- **Content:**

  ```python
  @pytest.mark.asyncio
  async def test_receiver_stores_traces():
      """Verify receiver can convert protobuf and store via ORM."""
      # 1. Create protobuf ExportTraceServiceRequest
      # 2. Convert to dict (simulate _convert_to_dict)
      # 3. Extract resource_spans list
      # 4. Call storage.store_traces(resource_spans)
      # 5. Assert count > 0
  ```

#### Task 2.4: Add type checking validation

- **File:** `apps/frontend/pyproject.toml` or CI config
- **Tool:** Run `mypy` or `pyright` on storage layer
- **Expected:** Type checker catches signature mismatches
- **Command:** `mypy apps/frontend/app/storage/ --strict`

---

### Phase 3: Validate Fix

**Goal:** Confirm data flows correctly from receiver to database

#### Task 3.1: Run unit tests

```bash
cd apps/frontend
poetry run pytest tests/test_postgres_orm.py -v
```

**Expected:** All tests pass with corrected signatures

#### Task 3.2: Run integration tests (if added)

```bash
poetry run pytest tests/test_receiver_storage_integration.py -v
```

**Expected:** Receiver → storage flow works

#### Task 3.3: Deploy and verify

```bash
make deploy
```

**Wait for receiver pod restart**

#### Task 3.4: Check receiver logs

```bash
kubectl logs -n ollyscale -l app.kubernetes.io/component=otlp-receiver --tail=50
```

**Expected:** "Stored N spans" messages, no errors

#### Task 3.5: Check database

```bash
kubectl exec -it -n ollyscale ollyscale-db-1 -- psql -U postgres -d ollyscale \
  -c "SELECT COUNT(*) FROM spans_fact;"
```

**Expected:** Count > 0

---

## Detailed Implementation Changes

### Change 1: `postgres_orm.py` - `store_traces()`

**Before:**

```python
async def store_traces(self, data: dict) -> int:
    """Store OTLP traces using SQLModel ORM.

    Args:
        data: OTLP JSON trace data with resource_spans

    Returns:
        Number of spans stored
    """
    resource_spans = data.get("resource_spans", data.get("resourceSpans", []))
    if not resource_spans:
        return 0

    logging.info(f"store_traces called with {len(resource_spans)} resource_spans")

    spans_to_insert = []

    async with AsyncSession(self.engine) as session:
        for resource_span in resource_spans:
            # ... rest of code
```

**After:**

```python
async def store_traces(self, resource_spans: list[dict]) -> int:
    """Store OTLP traces using SQLModel ORM.

    Args:
        resource_spans: List of OTLP ResourceSpans (matches interface)

    Returns:
        Number of spans stored
    """
    if not resource_spans:
        return 0

    logging.info(f"store_traces called with {len(resource_spans)} resource_spans")

    spans_to_insert = []

    async with AsyncSession(self.engine) as session:
        for resource_span in resource_spans:
            # ... rest of code unchanged
```

**Changes:**

- Remove parameter `data: dict`
- Add parameter `resource_spans: list[dict]`
- Remove line: `resource_spans = data.get("resource_spans", ...)`
- Rest of logic unchanged

---

### Change 2: `postgres_orm.py` - `store_logs()`

**Before:**

```python
async def store_logs(self, data: dict) -> int:
    """Store OTLP logs using SQLModel ORM."""
    resource_logs = data.get("resource_logs", data.get("resourceLogs", []))
    if not resource_logs:
        return 0

    logs_to_insert = []

    async with AsyncSession(self.engine) as session:
        for resource_log in resource_logs:
            # ... rest of code
```

**After:**

```python
async def store_logs(self, resource_logs: list[dict]) -> int:
    """Store OTLP logs using SQLModel ORM.

    Args:
        resource_logs: List of OTLP ResourceLogs (matches interface)

    Returns:
        Number of log records stored
    """
    if not resource_logs:
        return 0

    logs_to_insert = []

    async with AsyncSession(self.engine) as session:
        for resource_log in resource_logs:
            # ... rest of code unchanged
```

**Changes:**

- Remove parameter `data: dict`
- Add parameter `resource_logs: list[dict]`
- Remove line: `resource_logs = data.get("resource_logs", ...)`
- Rest of logic unchanged

---

### Change 3: `test_postgres_orm.py` - Tests

**Before:**

```python
@pytest.mark.asyncio
async def test_store_traces_with_scope_spans():
    storage = PostgresStorage("postgresql+asyncpg://localhost/test")

    # WRONG: Passing wrapped dict
    otlp_data = {
        "resource_spans": [
            {
                "resource": {...},
                "scope_spans": [...]
            }
        ]
    }

    try:
        count = await storage.store_traces(otlp_data)
        assert count == 1
    except Exception as e:
        assert "scopeSpans" not in str(e)
```

**After:**

```python
@pytest.mark.asyncio
async def test_store_traces_with_scope_spans():
    storage = PostgresStorage("postgresql+asyncpg://localhost/test")

    # CORRECT: Passing list directly (matches receiver usage)
    resource_spans = [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "test-service"}},
                ]
            },
            "scope_spans": [
                {
                    "scope": {"name": "test-scope"},
                    "spans": [
                        {
                            "traceId": "AAAAAAAAAAAAAAAAAAAAAA==",
                            "spanId": "AAAAAAAAAAA=",
                            "name": "test-span",
                            "kind": 2,
                            "startTimeUnixNano": "1000000",
                            "endTimeUnixNano": "2000000",
                            "attributes": [],
                        }
                    ],
                }
            ],
        }
    ]

    try:
        count = await storage.store_traces(resource_spans)
        assert count == 1
    except Exception as e:
        # Expected to fail on DB connection, but not on signature/parsing
        assert "'list' object has no attribute 'get'" not in str(e)
        assert "scopeSpans" not in str(e)
```

---

## Validation Criteria

### Unit Tests Pass

- [ ] `test_store_traces_with_scope_spans()` passes
- [ ] `test_store_logs_with_scope_logs()` passes
- [ ] No signature mismatch errors
- [ ] Type hints validate correctly

### Integration Test Pass (if added)

- [ ] Receiver can convert protobuf to dict
- [ ] Storage can accept list from receiver
- [ ] End-to-end flow works

### Runtime Validation

- [ ] Receiver starts without errors
- [ ] Receiver logs show "Stored N spans"
- [ ] No `'list' object has no attribute 'get'` errors
- [ ] Database contains spans (COUNT > 0)
- [ ] Service dimensions populated
- [ ] Operation dimensions populated
- [ ] Resource dimensions populated

---

## Rollback Plan

If fix fails:

1. `git revert HEAD`
2. Restore previous commit: `44541d5`
3. Re-analyze problem with more thorough testing

---

## Lessons Learned

### What Went Wrong

1. **Copied implementation without checking interface** - postgres_orm.py copied from old postgres.py
2. **Tests written against implementation, not interface** - validated wrong contract
3. **No integration testing** - unit tests didn't catch receiver usage pattern
4. **No type checking in CI** - would have caught signature mismatch
5. **Assumed tests were correct** - trusted green checkmarks without validating test quality

### Preventive Measures

1. **Always check interface first** before implementing
2. **Write tests from caller's perspective** - simulate real usage
3. **Add integration tests** for cross-module contracts
4. **Enable strict type checking** - mypy/pyright in pre-commit
5. **Review test quality** - do tests validate real usage or just make code coverage green?

---

## Next Steps After Fix

Once data is storing correctly:

1. Implement query methods (`search_traces`, `search_logs`, `get_services`)
2. Update FastAPI routes to use ORM storage
3. Add UI integration
4. Performance testing with real load
5. Add metrics storage implementation
