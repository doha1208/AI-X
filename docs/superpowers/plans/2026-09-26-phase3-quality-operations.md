# Phase 3 품질·운영성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 3 regression checks deterministic, validate the production `/api` path, and expose privacy-safe route telemetry.

**Architecture:** Keep fast, hermetic backend and frontend tests in the pull-request workflow; run the public-domain smoke check separately after deployment. Centralize route telemetry in a FastAPI observability module, then let the API router, Tmap service, and artifact runtime report only fixed, non-identifying outcomes.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy/SQLite, pytest, `prometheus-client`, Next.js 16.3, React 19, TypeScript, Vitest, React Testing Library, Node 22, GitHub Actions, Caddy, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-26-phase3-quality-operations-design.md`

## Global Constraints

- Preserve existing API schemas, safety-score formulas, route-selection behavior, cookie protocol, and Tmap/straight-line fallbacks.
- Tests must not create, delete, or open a database inside the repository; use pytest-provided temporary directories and mocks for OSM/Tmap.
- Never record coordinates, addresses, email/user identifiers, IPs, cookie/header/request-body content, exception strings, or API keys in route logs or metric labels.
- `route_duration_seconds{outcome}`, `route_requests_total{mode,fallback_reason}`, `tmap_failures_total{reason}`, and `route_result_cache_total{result}` have only the enum label values defined by the spec.
- `/metrics` stays reachable only through host loopback; public `/api/metrics` returns 404 while `/api/health` remains public.
- Production smoke calls only a configured HTTPS `SMOKE_BASE_URL` plus `/api/...`; it must never create users or print credentials.
- Do not create, amend, stage, switch, merge, rebase, push, pull, fetch, or otherwise alter Git state. Do not modify `README.md` or Claude-specific files.
- Update `DEVELOPMENT.md` with the completed Phase 3 test, smoke, and observability operation.

## Review Focus

- A test process launched from any working directory must never delete a checked-in or developer SQLite database; its database path must be under pytest's temporary root.
- A Tmap HTTP/JSON failure must still yield the existing route fallback while incrementing exactly one bounded failure reason and leaking neither status text nor API keys.
- A late response for a superseded route must not replace the newest route's bell markers, including when the original request ignores cancellation.
- A production smoke run must fail closed for missing secrets, non-HTTPS URLs, direct port 8000 access, missing secure/HttpOnly session cookies, empty zone data, or an invalid route response.
- A public request to `/api/metrics` must not expose telemetry, while host-local `/metrics` remains scrapeable and all documented metrics can be emitted safely.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `backend/tests/conftest.py` | Create an isolated session DB in pytest temp storage and reset mutable service state per test. |
| `backend/tests/test_test_environment.py` | Prove the test DB is temporary and repository-local DB names are never used. |
| `backend/app/observability.py` | JSON logging setup, bounded route telemetry helpers, Prometheus registry/response helpers. |
| `backend/app/main.py` | Configure observability and register the internal `/metrics` endpoint. |
| `backend/app/api/safety.py` | Time and classify each route request without changing response schemas. |
| `backend/app/services/tmap.py` | Classify and count external Tmap HTTP/JSON failures without exposing details. |
| `backend/app/services/safe_route.py` | Count artifact route-result cache hit/miss. |
| `backend/tests/test_observability.py` | Verify enum-only telemetry, no sensitive output, cache metrics, and `/metrics` payload. |
| `frontend/src/lib/useRouteBells.ts` | Own cancellation/latest-response protection for route bell state. |
| `frontend/src/lib/useRouteBells.test.tsx` | Prove only the latest route request updates bell markers. |
| `frontend/src/lib/api.test.ts` | Verify same-origin `/api` and one-shot access-token refresh behavior. |
| `frontend/vitest.config.ts`, `frontend/src/test/setup.ts` | Configure jsdom, aliases, and testing-library cleanup. |
| `frontend/package.json`, `frontend/package-lock.json` | Add test dependencies and `test` script. |
| `.github/workflows/quality.yml` | Run isolated backend and frontend checks on PR/default-branch changes. |
| `scripts/production-smoke.mjs` | Make HTTPS `/api` smoke calls with a minimal in-memory cookie jar. |
| `.github/workflows/production-smoke.yml` | Run the smoke script manually and daily with GitHub Environment settings. |
| `Caddyfile`, `docker-compose.yml` | Prevent public metrics proxying and bind API port to loopback. |
| `DEVELOPMENT.md` | Describe Phase 3 completion and required CI/smoke/metrics operation. |

### Task 1: Isolate backend tests and lock in existing core regression coverage

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_test_environment.py`
- Modify: `backend/tests/test_tmap.py`
- Modify: `backend/tests/test_safe_route_artifact_runtime.py`
- Modify: `backend/tests/test_safety.py`

**Interfaces:**
- Produces: `isolated_database` autouse fixture that leaves every test with a fresh schema and service-runtime state.
- Produces: `test_database_path` session fixture returning the exact temporary SQLite path for environmental assertions.
- Consumes: existing `SessionLocal`, `route_artifact_runtime`, `RouteRequestGate`, `tmap._route_cache`, and current small graph/Tmap test doubles.

- [ ] **Step 1: Write failing temporary-DB and reset-regression tests.**

Create `test_test_environment.py` with assertions that `test_database_path` exists below pytest's temp base, is not `backend/tests/.test-suite.db`, and a row created in one test is absent in the next test. Add a two-call Tmap cache test and a two-call artifact-runtime cache test that explicitly assert the second call is cached.

```python
def test_database_path_is_outside_the_repository(test_database_path: Path):
    assert test_database_path.exists()
    assert "backend/tests/.test-suite.db" not in test_database_path.as_posix()

def test_database_starts_empty_after_the_previous_test():
    assert SessionLocal().query(SafetyZone).count() == 0
```

- [ ] **Step 2: Run the focused tests and verify the environment test fails under the repository-local DB fixture.**

Run: `Set-Location backend; python -m pytest tests/test_test_environment.py tests/test_tmap.py tests/test_safe_route_artifact_runtime.py -v`  
Expected: FAIL because `test_database_path` and the required state-reset fixture do not yet exist.

- [ ] **Step 3: Replace the repository-local database setup with pytest temporary storage.**

In `conftest.py`, create the session DB path with `tmp_path_factory.mktemp("database") / "app.db"` before importing application modules, set `DATABASE_URL` from that path, and expose it through `test_database_path`. Remove all `Path(__file__).parent / ".test-suite.db"` deletion logic. Keep the autouse schema reset, dispose the engine at session finish, and reset Tmap cache, artifact runtime, route request gate, facility/graph caches, and monkeypatched settings to their default test-safe state around every test. Do not perform any filesystem cleanup outside pytest's generated temporary directory.

- [ ] **Step 4: Preserve and make explicit the four backend Phase 3 regressions.**

Keep/add tests in existing suites for: over-10 km `RouteRequest` rejection (`test_route_policy.py`), active-artifact version replacement yielding the new cached route score (`test_safe_route_artifact_runtime.py`), unknown source data receiving neutral score (`test_safety_score.py`/`test_crime_rate.py`), and Tmap HTTP failure returning the existing straight-line route response (`test_safety.py`). Each test must patch the relevant runtime dependency rather than perform network or OSM I/O.

- [ ] **Step 5: Run backend regression tests.**

Run: `Set-Location backend; python -m pytest tests -v`  
Expected: PASS; no `backend/tests/.test-suite.db` is created and no test calls Tmap or OSM over the network.

### Task 2: Add privacy-safe structured route telemetry and internal metrics

**Files:**
- Create: `backend/app/observability.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/safety.py`
- Modify: `backend/app/services/tmap.py`
- Modify: `backend/app/services/safe_route.py`
- Create: `backend/tests/test_observability.py`
- Modify: `backend/tests/test_safety.py`
- Modify: `backend/tests/test_tmap.py`

**Interfaces:**
- Produces: `configure_observability() -> None`, `record_route(...) -> None`, `record_tmap_failure(reason: Literal["http_error", "invalid_response"]) -> None`, `record_route_cache(result: Literal["hit", "miss"]) -> None`, and `metrics_response() -> Response` in `app.observability`.
- Consumes: API route outcome, `RouteArtifactRuntime.find_routes` cache branch, and Tmap HTTP/JSON parsing result.
- Produces: `GET /metrics` with Prometheus content type; it is intentionally not under the API router prefix.

- [ ] **Step 1: Write failing telemetry tests against an isolated Prometheus registry.**

`test_observability.py` must create a test registry through the module's explicit registry factory, emit one safe-route success, one `tmap` fallback, one `straight_line` fallback, cache hit/miss, and both Tmap failure reasons. Assert metric samples have only the exact enum labels below and that a sentinel coordinate, email, token, cookie value, and API key occur in neither rendered metrics nor captured JSON log.

```python
assert sample.labels == {"mode": "straight_line", "fallback_reason": "tmap_unavailable"}
assert "37.50000" not in rendered
assert "secret-token" not in rendered
```

Add route endpoint tests that assert a valid response increments `route_requests_total` once and an empty-zone 422 increments `route_duration_seconds{outcome="safety_zones_unavailable"}`. Add a Tmap test double that raises `httpx.HTTPError` and another that returns a body with no LineString, expecting `http_error` and `invalid_response` respectively.

- [ ] **Step 2: Run telemetry tests to verify they fail before the metrics implementation exists.**

Run: `Set-Location backend; python -m pytest tests/test_observability.py tests/test_safety.py tests/test_tmap.py -v`  
Expected: FAIL because `app.observability` and `/metrics` do not exist.

- [ ] **Step 3: Implement the observability module with finite labels and JSON logging.**

Add `prometheus-client` to `backend/requirements.txt`. In `app.observability`, construct the four collectors named in the spec from an injectable `CollectorRegistry`; validate every metric helper argument against fixed Python literal/constant sets before emitting. Implement a JSON formatter that emits only `event`, `status_code`, `duration_ms`, `mode`, `fallback_reason`, and a safe message; its API must not accept request objects, payloads, headers, cookies, coordinates, identifiers, or raw exceptions. Make repeated `configure_observability()` calls idempotent for tests.

- [ ] **Step 4: Instrument route, Tmap, cache, and metrics endpoint without changing public schemas.**

Call `configure_observability()` before FastAPI startup work in `main.py`, and add `@app.get("/metrics", include_in_schema=False)` returning `metrics_response()`. In `route_safety`, capture `time.perf_counter()` once, classify only the spec's fixed outcomes (`none`, `artifact_unavailable`, `safe_route_unavailable`, `tmap_unavailable`, `safety_zones_unavailable`), then record duration and request counters on success/known 422 paths. In `get_pedestrian_route`, count only HTTP exceptions as `http_error` and malformed/no-LineString successful bodies as `invalid_response`; preserve `None` fallback behavior. In `RouteArtifactRuntime.find_routes`, call `record_route_cache("hit")` only on the existing cache return and `record_route_cache("miss")` before computing a noncached lookup.

- [ ] **Step 5: Run targeted metrics and full backend tests.**

Run: `Set-Location backend; python -m pytest tests/test_observability.py tests/test_safety.py tests/test_tmap.py tests/test_safe_route_artifact_runtime.py -v`  
Expected: PASS; `/metrics` contains only finite labels and existing route response JSON remains unchanged.

Run: `Set-Location backend; python -m pytest tests -v`  
Expected: PASS.

### Task 3: Add frontend unit tests and isolate route-bell async state

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/lib/api.test.ts`
- Create: `frontend/src/lib/useRouteBells.ts`
- Create: `frontend/src/lib/useRouteBells.test.tsx`
- Modify: `frontend/src/app/page.tsx`

**Interfaces:**
- Produces: `useRouteBells(points: RoutePoint[] | undefined): Bell[]`, where `Bell` is `{ lat: number; lng: number }`.
- Consumes: existing `nearbyBells`, `haversineMeters`, `ROUTE_BELL_FETCH_LIMIT`, and `ROUTE_BELL_RADIUS_M` behavior currently in `page.tsx`.
- Produces: `npm run test` invoking Vitest once in CI.

- [ ] **Step 1: Add failing API-client and latest-route bell tests.**

In `api.test.ts`, reset modules and remove `NEXT_PUBLIC_API_BASE_URL`, mock `fetch`, call `nearbyZones`, and assert the request URL begins `/api/safety/zones`. Add a `me()` test with responses ordered as 401, CSRF 200, refresh 200, `me` 200 and assert exactly one refresh request includes `X-CSRF-Token`.

In `useRouteBells.test.tsx`, render the hook with route A, rerender it with route B before route A's deferred `nearbyBells` promise resolves, then resolve B and A in that order. Assert B's bells remain returned, and assert A received an aborted signal.

```tsx
expect(result.current).toEqual([{ lat: 37.51, lng: 127.01 }]);
expect(firstSignal.aborted).toBe(true);
```

- [ ] **Step 2: Run the new frontend tests and verify they fail before setup and hook implementation.**

Run: `Set-Location frontend; npm run test -- --run src/lib/api.test.ts src/lib/useRouteBells.test.tsx`  
Expected: FAIL because no test script/configuration or hook exists.

- [ ] **Step 3: Add the Vitest/jsdom test harness.**

Add Vitest, jsdom, `@testing-library/react`, and `@testing-library/jest-dom` as development dependencies, add `"test": "vitest"`, configure the `@/` alias from `tsconfig.json`, and load automatic testing-library cleanup plus jest-dom matchers from `src/test/setup.ts`. Preserve the existing `lint`, `build`, and Next.js configuration.

- [ ] **Step 4: Extract only the route-bell state boundary from the page.**

Move `bellsNearRoute` and its two route-bell constants from `page.tsx` to `useRouteBells.ts`. The hook owns an effect-scoped `AbortController` and monotonic request id; it clears bells only for the current non-abort failure. Replace the page's `bells` state, `bellsRequestRef`, and active-alternative bell effect with `const bells = useRouteBells(activeAlternative?.route_points)`. Do not alter normal nearby-search bells, geolocation reroute thresholds, route selection, or `SafetyMap` props.

- [ ] **Step 5: Run frontend regression and static checks.**

Run: `Set-Location frontend; npm run test -- --run`  
Expected: PASS.

Run: `Set-Location frontend; npm run lint; npx tsc --noEmit; npm run build`  
Expected: PASS.

### Task 4: Automate PR quality checks and production smoke checks

**Files:**
- Create: `.github/workflows/quality.yml`
- Create: `.github/workflows/production-smoke.yml`
- Create: `scripts/production-smoke.mjs`
- Create: `scripts/production-smoke.test.mjs`

**Interfaces:**
- Consumes: GitHub Environment variable `SMOKE_BASE_URL`, variables `SMOKE_START_LAT`, `SMOKE_START_LNG`, `SMOKE_END_LAT`, `SMOKE_END_LNG`, and secrets `SMOKE_USER_EMAIL`, `SMOKE_USER_PASSWORD`.
- Produces: zero exit code only after every configured HTTPS `/api` check succeeds; all other configuration/response errors produce a nonzero exit code without credential output.

- [ ] **Step 1: Write failing smoke-script tests with a local mocked fetch implementation.**

Export `validateSmokeConfig`, `CookieJar`, and `runSmoke` from `production-smoke.mjs`. In `production-smoke.test.mjs`, inject a fetch fake and assert config rejects `http:`, `localhost`, `:8000`, missing credentials, and paths containing `/api`; assert a successful sequence sends all calls to `${baseUrl}/api/...`, carries the CSRF header/cookies, requires `Secure` + `HttpOnly` session cookies, and rejects a 422 zones/route response.

- [ ] **Step 2: Run the smoke tests and verify they fail before the script exists.**

Run: `node --test scripts/production-smoke.test.mjs`  
Expected: FAIL because the smoke module is absent.

- [ ] **Step 3: Implement the no-dependency smoke script.**

Use `new URL` to validate an HTTPS origin-only `SMOKE_BASE_URL`. Implement `CookieJar` from `response.headers.getSetCookie()` (or a testable equivalent) without logging its values. `runSmoke` must log only stage names and perform health, CSRF, login, me, zones, and route in the exact spec order. Require `health.status === "ok"`, login `access_token`/`refresh_token` attributes `Secure` and `HttpOnly`, the configured user email from `/auth/me`, a nonempty zone array, and a route whose `mode` is one of the three specified values with finite `safety_score` and nonempty `route_points`.

- [ ] **Step 4: Add the two GitHub Actions workflows.**

`quality.yml` triggers on pull requests and pushes to the repository's default branch, grants read-only contents permission, installs Python 3.12/backend requirements, runs `python -m pytest tests -v` with `backend` as working directory, installs Node 22/frontend dependencies, then runs `npm run lint`, `npx tsc --noEmit`, and `npm run test -- --run` with `frontend` as working directory.

`production-smoke.yml` triggers with `workflow_dispatch` and a daily UTC cron. It targets a named GitHub Environment, grants read-only contents permission, uses Node 22, passes only the six named Environment inputs to the script, and runs `node scripts/production-smoke.mjs`. Do not add deployment, signup, database migration, or credential-echo steps.

- [ ] **Step 5: Run all local smoke tests and validate workflow syntax by inspection.**

Run: `node --test scripts/production-smoke.test.mjs`  
Expected: PASS.

Run: `Get-Content .github/workflows/quality.yml; Get-Content .github/workflows/production-smoke.yml`  
Expected: each workflow has only the intended triggers, read-only permission, and no deployment command or secret-printing command.

### Task 5: Restrict metrics network exposure and document Phase 3 operations

**Files:**
- Modify: `Caddyfile`
- Modify: `docker-compose.yml`
- Modify: `DEVELOPMENT.md`

**Interfaces:**
- Consumes: FastAPI's root `/metrics` endpoint on port 8000.
- Produces: public `/api/metrics` 404, host-local `http://127.0.0.1:8000/metrics`, and documented CI/smoke setup instructions.

- [ ] **Step 1: Add failing configuration assertions.**

Create focused text-level assertions in `backend/tests/test_observability.py` that load repository-root `Caddyfile` and `docker-compose.yml`: `/api/metrics` must be handled before `/api/*`, the metrics path must return 404, and the API service must bind exactly `127.0.0.1:8000:8000`. These checks deliberately prevent accidental public telemetry exposure.

- [ ] **Step 2: Run the configuration assertions to confirm the current deployment config is not yet compliant.**

Run: `Set-Location backend; python -m pytest tests/test_observability.py -k "deployment_config" -v`  
Expected: FAIL because current Caddy proxies all `/api/*` paths and Docker exposes port 8000 on all interfaces.

- [ ] **Step 3: Deny public metrics and bind the API to loopback.**

Add the explicit `/api/metrics` 404 Caddy handler before `handle_path /api/*`; leave all other `/api` routes unchanged. Replace Compose API port mapping with `127.0.0.1:8000:8000`, preserving API/builder volumes, environment, and restart policies. Do not expose a new port or change the frontend proxy target.

- [ ] **Step 4: Update the development guide.**

Mark Phase 3 complete only after its implementation tests pass. Add the responsibility of `backend/app/observability.py`, test commands for backend/frontend/smoke tests, GitHub Environment variable/secret names, smoke-account restrictions, public versus internal metrics paths, the four metric names/labels, and the privacy ban on location/token/user data. Preserve all prior Phase descriptions and do not create or edit README files.

- [ ] **Step 5: Run complete verification.**

Run: `Set-Location backend; python -m pytest tests -v`  
Expected: PASS.

Run: `Set-Location frontend; npm run lint; npx tsc --noEmit; npm run test -- --run; npm run build`  
Expected: PASS.

Run: `node --test scripts/production-smoke.test.mjs`  
Expected: PASS.

- [ ] **Step 6: Invoke `$code-change-verification` and report its evidence before declaring the implementation complete.**

Use the repository's required verification skill after all commands above pass. Report the exact verification commands and outcomes; do not claim completion if any check is unavailable or failing.
