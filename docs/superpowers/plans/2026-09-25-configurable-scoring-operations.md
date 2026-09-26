# Configurable Scoring Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a newly built, validated score-profile artifact as the only source for residence and route scores, with an administrator workflow and a separate periodic builder process.

**Architecture:** FastAPI records immutable profile drafts and build jobs; a single builder claims jobs, creates a versioned route artifact, and changes the `current.json` pointer only after validation. The API runtime reads that pointer and uses its day/night score maps for all served scores. A Next.js administrator page manages drafts and build status through admin-only APIs, while Docker Compose runs the API and builder against shared database and artifact volumes.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2 / SQLite, Pydantic v2, NetworkX artifact pickles, pytest, Next.js 16.3, React 19, TypeScript, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-25-phase1-configurable-scoring-design.md`

## Global Constraints

- Read `DEVELOPMENT.md` before every code, configuration, or data-pipeline change; do not inspect Claude-specific files.
- Do not run mutable Git commands. Leave each task ready for user review without staging, committing, switching branches, or pushing.
- Keep HTTP routers limited to validation and response composition; put artifact/build domain work in services or batch scripts.
- Never create OSM graphs, re-score every graph edge, or download public data during an HTTP request.
- The artifact manifest is the serving source of truth; absent or invalid artifacts retain the existing DB-score, computed-score, Tmap, and straight-line fallback behavior.
- Profile weights are non-negative, use exactly the supported six factors, and each day/night weight total is exactly `1.0`; `unknown_score` remains in `[0, 100]`.
- A rollback uses `POST /admin/scoring-profiles/{profile_id}/apply` to make a fresh artifact from the selected prior profile and the current safety-zone data. It never repoints to an old artifact.
- `GET /admin/scoring-profiles/builds` and `GET /admin/scoring-profiles/builds/{build_id}` require the same administrator authorization as all other scoring-profile endpoints.
- The builder checks queued work frequently and checks the scoped zone-data fingerprint every 1,800 seconds. It only queues a periodic rebuild when the active profile or data fingerprint differs from the current validated artifact.

## Review Focus

- A builder exception after a prior artifact exists must leave both that `current.json` and the prior active profile unchanged; Task 3 adds this regression test.
- A valid artifact that lacks a requested zone score must not yield a `KeyError` or partial mixed response; Task 4 falls back to the existing calculation for the whole request.
- A process interruption after pointer publication but before the DB status commit must recover the matching `building` job without publishing a second artifact; Task 5 adds that recovery test.
- An ordinary logged-in member must receive `403` from every build-status or apply endpoint and see no editable administrator controls; Tasks 2 and 7 cover both layers.
- A periodic check with an unchanged data fingerprint and active profile must not queue duplicate jobs; Task 5 counts queued records before and after the check.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `backend/app/models/scoring_profile.py` | Persist profile versions and build lifecycle timestamps/result metadata. |
| `backend/app/schemas/scoring_profile.py` | Validate profile input and expose typed profile/build API contracts. |
| `backend/app/services/scoring_profile_store.py` | Convert DB records, create drafts/jobs, query jobs, atomically claim jobs, and reconcile a published artifact. |
| `backend/app/api/admin_scoring.py` | Compose administrator-only profile and build-status responses. |
| `backend/scripts/build_route_artifacts.py` | Build one artifact, claim/process queued jobs, and perform DB/manifest recovery. |
| `backend/scripts/artifact_builder_worker.py` | Poll queued jobs and run the 30-minute active-artifact freshness check. |
| `backend/app/services/route_artifact.py` | Validate the persisted artifact/manifest score maps. |
| `backend/app/services/safe_route.py` | Return immutable score maps from the loaded artifact runtime. |
| `backend/app/api/safety.py` | Select a complete artifact score map or the existing fallback calculation for residence and route responses. |
| `backend/app/core/config.py` | Configure builder polling and data-fingerprint check intervals. |
| `backend/tests/test_admin_scoring.py` | Cover admin build-status authorization and API response contracts. |
| `backend/tests/test_build_route_artifacts_script.py` | Cover job claiming, success, failure preservation, reconciliation, and data-freshness queuing. |
| `backend/tests/test_route_artifact.py` | Reject artifacts with malformed score maps. |
| `backend/tests/test_safety.py` | Prove residence, passed zones, and Tmap/straight-line scores use artifact maps and retain fallbacks. |
| `backend/Dockerfile`, `backend/.dockerignore`, `docker-compose.yml` | Build the API/builder image and declare shared persistent DB/artifact volumes. |
| `frontend/src/lib/api.ts` | Define scoring-profile/build types and authorized API client functions. |
| `frontend/src/app/admin/scoring/page.tsx` | Render and protect the administrator score policy workflow. |
| `frontend/src/app/admin/scoring/page.module.css` | Style the isolated administrator screen. |
| `frontend/src/app/page.tsx` | Show an administrator navigation link only after an authorized profile query succeeds. |
| `DEVELOPMENT.md` | Document the completed scoring operations, admin API, worker, and fallback guarantees. |

### Task 1: Expand the persistent build contract

**Files:**
- Modify: `backend/app/models/scoring_profile.py`
- Modify: `backend/app/schemas/scoring_profile.py`
- Modify: `backend/app/services/scoring_profile_store.py`
- Test: `backend/tests/test_admin_scoring.py`

**Interfaces:**
- Produces `ScoreBuildOut(id: int, profile_id: int, profile_version: str, status: Literal["queued", "building", "succeeded", "failed"], artifact_version: str | None, error_code: str | None, created_at: datetime, started_at: datetime | None, finished_at: datetime | None)`.
- Produces `list_builds(db: Session, limit: int = 20) -> list[ScoreBuildOut]` and `get_build(db: Session, build_id: int) -> ScoreBuildOut | None` for Task 2.
- Produces `queue_profile_build(db: Session, profile_id: int) -> ScoreBuildOut | None`, which always creates a new job for an existing profile, including an active historical profile selected for rollback.

- [ ] **Step 1: Write failing API-contract tests for complete build data**

```python
def test_admin_can_read_a_queued_build_with_lifecycle_fields(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    token = _access_token("admin@example.com")
    draft = client.post("/admin/scoring-profiles", headers=_auth(token), json=VALID_PROFILE).json()
    queued = client.post(f"/admin/scoring-profiles/{draft['id']}/apply", headers=_auth(token))

    assert queued.status_code == 202
    assert queued.json() == {
        "id": queued.json()["id"], "profile_id": draft["id"], "profile_version": "pilot-v1",
        "status": "queued", "artifact_version": None, "error_code": None,
        "created_at": queued.json()["created_at"], "started_at": None, "finished_at": None,
    }
```

- [ ] **Step 2: Run the focused test to verify the current abbreviated schema fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py::test_admin_can_read_a_queued_build_with_lifecycle_fields -v`

Expected: FAIL because the current `ScoreBuildOut` does not expose profile version or lifecycle timestamps.

- [ ] **Step 3: Add lifecycle fields and one record-to-schema conversion path**

```python
class ScoreBuildRecord(Base):
    # existing id/profile_id/status/artifact_version/error_code fields
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

def _build_to_output(build: ScoreBuildRecord, profile: ScoringProfileRecord) -> ScoreBuildOut:
    return ScoreBuildOut(
        id=build.id, profile_id=build.profile_id, profile_version=profile.version,
        status=build.status, artifact_version=build.artifact_version,
        error_code=build.error_code, created_at=build.created_at,
        started_at=build.started_at, finished_at=build.finished_at,
    )
```

Use `datetime.now(UTC)` when transitioning to `building` and then to either terminal state. Build profile data with a joined query or an explicit `db.get`; do not expose stored `weights_json` through the build status response.

- [ ] **Step 4: Add store queries and preserve one-job-per-apply semantics**

```python
def list_builds(db: Session, limit: int = 20) -> list[ScoreBuildOut]:
    rows = db.query(ScoreBuildRecord, ScoringProfileRecord).join(
        ScoringProfileRecord, ScoringProfileRecord.id == ScoreBuildRecord.profile_id
    ).order_by(ScoreBuildRecord.id.desc()).limit(limit).all()
    return [_build_to_output(build, profile) for build, profile in rows]
```

Keep `queue_profile_build` as an insert for every existing `profile_id`, set only `status="queued"`, commit, refresh, and return the shared converter output.

- [ ] **Step 5: Run the focused contract and existing profile tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py backend/tests/test_scoring_profile.py -v`

Expected: PASS. Leave changes unstaged and uncommitted under the repository rules.

### Task 2: Expose authorized build-status APIs

**Files:**
- Modify: `backend/app/api/admin_scoring.py`
- Modify: `backend/tests/test_admin_scoring.py`

**Interfaces:**
- Consumes Task 1 `get_build` and `list_builds`.
- Produces `GET /admin/scoring-profiles/builds` and `GET /admin/scoring-profiles/builds/{build_id}` with `ScoreBuildOut` responses.
- Keeps `POST /admin/scoring-profiles/{profile_id}/apply` as the sole application and rollback request endpoint.

- [ ] **Step 1: Write failing authorization and lookup tests**

```python
def test_non_admin_cannot_read_build_status(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    token = _access_token("member@example.com")
    assert client.get("/admin/scoring-profiles/builds", headers=_auth(token)).status_code == 403

def test_admin_reads_build_list_and_missing_build_is_404(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    token = _access_token("admin@example.com")
    assert client.get("/admin/scoring-profiles/builds", headers=_auth(token)).json() == []
    assert client.get("/admin/scoring-profiles/builds/999", headers=_auth(token)).status_code == 404
```

- [ ] **Step 2: Run the two tests to verify the routes do not yet exist**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py -k "build_status or build_list" -v`

Expected: FAIL with 404 or mismatched response.

- [ ] **Step 3: Add narrowly scoped admin router handlers**

```python
@router.get("/builds", response_model=list[ScoreBuildOut])
def read_builds(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[ScoreBuildOut]:
    return list_builds(db)

@router.get("/builds/{build_id}", response_model=ScoreBuildOut)
def read_build(build_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> ScoreBuildOut:
    build = get_build(db, build_id)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="빌드 작업을 찾을 수 없습니다")
    return build
```

Keep all profile mutations in `scoring_profile_store.py`; the router only calls the service and translates a missing resource to HTTP 404.

- [ ] **Step 4: Run the entire admin API test module**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py -v`

Expected: PASS, including existing anonymous 401, member 403, draft, and queued-build checks.

- [ ] **Step 5: Record the review checkpoint without a Git mutation**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py -v`

Expected: PASS. Do not stage or commit.

### Task 3: Make queued builds safe, terminal, and profile-activating only after publish

**Files:**
- Modify: `backend/scripts/build_route_artifacts.py`
- Modify: `backend/app/services/scoring_profile_store.py`
- Modify: `backend/tests/test_build_route_artifacts_script.py`

**Interfaces:**
- Consumes Task 1 lifecycle fields and the existing `build_and_publish_route_artifact(..., profile: ScoringProfile)`.
- Produces `process_next_queued_build(*, directory: Path, region: str) -> bool`; `True` means it claimed and terminally handled exactly one job.
- Produces `claim_next_queued_build(db: Session) -> tuple[ScoreBuildRecord, ScoringProfileRecord | None] | None` for the worker in Task 5; a `None` profile denotes a terminal `profile_missing` job.

- [ ] **Step 1: Write success and failure-preservation tests against a temporary SQLite session**

```python
def test_queued_build_success_publishes_then_activates_profile(monkeypatch, tmp_path):
    # Seed an existing current artifact, one active profile, and one queued replacement profile.
    monkeypatch.setattr(script, "build_and_publish_route_artifact", lambda **kw: publish_artifact(_artifact(kw["version"]), tmp_path))
    assert script.process_next_queued_build(directory=tmp_path, region="seoul-gyeonggi") is True
    assert load_current_artifact(tmp_path).profile_version == "candidate-v1"
    assert _build_status() == "succeeded"
    assert _profile_status("candidate-v1") == "active"
    assert _profile_status("current-v1") == "draft"

def test_failed_queued_build_keeps_existing_current_artifact_and_active_profile(monkeypatch, tmp_path):
    publish_artifact(_artifact("stable-artifact"), tmp_path)
    monkeypatch.setattr(script, "build_and_publish_route_artifact", lambda **_: (_ for _ in ()).throw(RuntimeError("graph unavailable")))
    assert script.process_next_queued_build(directory=tmp_path, region="seoul-gyeonggi") is True
    assert load_current_artifact(tmp_path).version == "stable-artifact"
    assert _build_status() == "failed"
    assert _profile_status("current-v1") == "active"
```

Create local helper functions in this test module that seed `ScoringProfileRecord`, `ScoreBuildRecord`, and `SafetyZone` through the patched `script.SessionLocal`; do not depend on the process-wide test DB.

- [ ] **Step 2: Run the builder tests to verify the lifecycle and preservation guarantees fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_build_route_artifacts_script.py -v`

Expected: FAIL because the script currently omits lifecycle timestamps and does not exercise a full old/current preservation scenario.

- [ ] **Step 3: Atomically claim a single queued record before doing expensive work**

```python
def claim_next_queued_build(db: Session) -> tuple[ScoreBuildRecord, ScoringProfileRecord | None] | None:
    build = db.query(ScoreBuildRecord).filter_by(status="queued").order_by(ScoreBuildRecord.id).first()
    if build is None:
        return None
    build.status = "building"
    build.started_at = datetime.now(UTC)
    profile = db.get(ScoringProfileRecord, build.profile_id)
    if profile is None:
        build.status, build.error_code, build.finished_at = "failed", "profile_missing", datetime.now(UTC)
        db.commit()
        return build, None
    db.commit()
    return build, profile
```

Make `process_next_queued_build` return `True` for a `(build, None)` result and skip graph work, while a `None` result means the queue was empty and returns `False`. Commit a valid claim before invoking graph construction. Configure exactly one builder container in Task 6, so SQLite does not need multi-worker queue locking semantics.

- [ ] **Step 4: Complete each job only after artifact publication succeeds**

```python
try:
    build_and_publish_route_artifact(..., profile=profile)
except Exception:
    build.status, build.error_code, build.finished_at = "failed", "build_failed", datetime.now(UTC)
    db.commit()
    return True

build.status, build.artifact_version, build.finished_at = "succeeded", version, datetime.now(UTC)
db.query(ScoringProfileRecord).filter_by(status="active").update({"status": "draft"})
profile_record.status = "active"
db.commit()
return True
```

Keep the existing `publish_artifact` call as the only place that changes `current.json`; do not write or delete an existing artifact on any exception path.

- [ ] **Step 5: Run focused build and artifact tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_build_route_artifacts_script.py backend/tests/test_route_artifact.py -v`

Expected: PASS, including pointer preservation after the forced builder exception.

### Task 4: Serve only complete artifact score maps and retain existing fallbacks

**Files:**
- Modify: `backend/app/services/route_artifact.py`
- Modify: `backend/app/services/safe_route.py`
- Modify: `backend/app/api/safety.py`
- Modify: `backend/tests/test_route_artifact.py`
- Modify: `backend/tests/test_safe_route_artifact_runtime.py`
- Modify: `backend/tests/test_safety.py`

**Interfaces:**
- Produces `RouteArtifactRuntime.score_map(period: Period) -> dict[str, float] | None`, returning a defensive copy only for a validated loaded artifact.
- Produces `artifact_score_map_for_zones(period: Period, zones: list[SafetyZone]) -> dict[str, float] | None` in `safety.py`; it returns `None` unless every scoped zone has a finite score.
- `residence_recommend` and `route_safety` use this helper before the existing DB ordering or `compute_zone_period_scores` fallback.

- [ ] **Step 1: Add failing API tests for day map ordering and time-specific fallback scores**

```python
def test_residence_recommend_uses_loaded_artifact_day_scores(monkeypatch):
    monkeypatch.setattr(safety_api.route_artifact_runtime, "score_map", lambda period: {"TEST1": 12.0, "TEST2": 98.0})
    body = client.get("/safety/residence-recommend", params={"limit": 2}).json()
    assert [(zone["dong_code"], zone["safety_score"]) for zone in body] == [("TEST2", 98.0), ("TEST1", 12.0)]

def test_tmap_fallback_uses_artifact_night_scores(monkeypatch):
    monkeypatch.setattr(safety_api, "find_safe_routes", lambda *args, **kwargs: None)
    monkeypatch.setattr(safety_api, "get_pedestrian_route", _tmap_points)
    monkeypatch.setattr(safety_api.route_artifact_runtime, "score_map", lambda period: {"TEST1": 11.0, "TEST2": 89.0})
    body = client.post("/safety/route", json={**ROUTE, "at": "2026-01-01T23:30:00+09:00"}).json()
    assert body["zones_passed"][0]["safety_score"] == 11.0
```

Also add a partial-map test asserting an incomplete `{"TEST1": 80.0}` map invokes `compute_zone_period_scores` once and returns a complete response.

- [ ] **Step 2: Run the focused safety tests to verify current behavior is incomplete**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety.py -k "artifact or fallback" -v`

Expected: FAIL until the test helpers and whole-map validation are added.

- [ ] **Step 3: Validate maps at the artifact boundary and select one map for each whole response**

```python
def _valid_score_map(scores: object) -> bool:
    return isinstance(scores, dict) and all(
        isinstance(code, str) and code and isinstance(score, (int, float)) and math.isfinite(score)
        for code, score in scores.items()
    )

def artifact_score_map_for_zones(period: Period, zones: list[SafetyZone]) -> dict[str, float] | None:
    scores = route_artifact_runtime.score_map(period)
    if scores is None or any(zone.dong_code not in scores for zone in zones):
        return None
    return scores
```

Require both `day` and `night` maps to pass `_valid_score_map` in `_validate_artifact`. Use `scores = artifact_score_map_for_zones(...)` followed by an explicit `if scores is None`, never `runtime.score_map(period) or ...`, so an invalid or incomplete map cannot silently mix artifact and live scores.

- [ ] **Step 4: Apply the selected map to all three response sites**

```python
scores = artifact_score_map_for_zones("day", zones)
if scores is not None:
    return [SafetyZoneOut(..., safety_score=scores[zone.dong_code]) for zone in sorted(...)]

score_map = artifact_score_map_for_zones(period, zones)
if score_map is None:
    score_map = compute_zone_period_scores(zones, period)
```

Use `score_map` for residence `safety_score`, `_point_sample_score` in Tmap/straight-line mode, and every `zones_passed` element. Preserve the existing route mode selection and Tmap invocation behavior.

- [ ] **Step 5: Run safety and artifact regression tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_route_artifact.py backend/tests/test_safe_route_artifact_runtime.py backend/tests/test_safety.py -v`

Expected: PASS, including corrupt/partial-map fallback coverage.

### Task 5: Recover published work and operate the builder on two schedules

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/scoring_profile_store.py`
- Modify: `backend/scripts/build_route_artifacts.py`
- Create: `backend/scripts/artifact_builder_worker.py`
- Modify: `backend/tests/test_build_route_artifacts_script.py`

**Interfaces:**
- Produces `reconcile_published_build(db: Session, directory: Path) -> bool`, which repairs a matching `building` build after an already-valid manifest was published.
- Produces `queue_rebuild_if_active_artifact_is_stale(db: Session, directory: Path) -> bool`, which creates one queued job only when an active profile exists and its profile version or current scoped data fingerprint differs from the valid current artifact.
- Produces `run_worker(*, directory: Path, region: str, poll_seconds: int, refresh_seconds: int) -> None` for Compose.

- [ ] **Step 1: Write failing recovery and no-op freshness tests**

```python
def test_reconcile_marks_published_build_succeeded_after_interruption(tmp_path):
    # Seed a building job for profile "candidate-v1" and publish an artifact with that profile/version.
    assert script.reconcile_published_build(db, tmp_path) is True
    assert build.status == "succeeded"
    assert build.artifact_version == "published-v2"
    assert candidate.status == "active"

def test_unchanged_active_artifact_does_not_queue_periodic_rebuild(tmp_path):
    # Seed active profile and an artifact whose profile_version/data_version match current zones.
    assert script.queue_rebuild_if_active_artifact_is_stale(db, tmp_path) is False
    assert db.query(ScoreBuildRecord).count() == 0
```

Add a changed-zone-data test that changes `cctv_count`, expects `True`, and asserts one `queued` record; invoke it twice and assert the second call returns `False` because a queued/building job already exists for that profile.

- [ ] **Step 2: Run the builder test module to verify recovery and periodic work are absent**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_build_route_artifacts_script.py -v`

Expected: FAIL because neither recovery nor freshness scheduling functions exist.

- [ ] **Step 3: Reconcile only a valid current artifact with a matching interrupted job**

```python
def reconcile_published_build(db: Session, directory: Path) -> bool:
    artifact = load_current_artifact(directory)
    if artifact is None:
        return False
    build = db.query(ScoreBuildRecord).join(ScoringProfileRecord).filter(
        ScoreBuildRecord.status == "building",
        ScoringProfileRecord.version == artifact.profile_version,
    ).order_by(ScoreBuildRecord.id).first()
    if build is None:
        return False
    build.status, build.artifact_version, build.finished_at = "succeeded", artifact.version, datetime.now(UTC)
    # move active status to build.profile_id and commit once
    return True
```

Do not recover from an unreadable manifest, and do not create any artifact in this function.

- [ ] **Step 4: Compare active policy/data fingerprints and create at most one periodic job**

```python
def queue_rebuild_if_active_artifact_is_stale(db: Session, directory: Path) -> bool:
    active = _active_profile_record(db)
    if active is None:
        return False
    artifact = load_current_artifact(directory)
    zones = scoped_zones_query(db).all()
    stale = artifact is None or artifact.profile_version != active.version or artifact.data_version != _zone_data_version(zones)
    if not stale or _has_pending_build(db, active.id):
        return False
    db.add(ScoreBuildRecord(profile_id=active.id, status="queued"))
    db.commit()
    return True
```

Move `_zone_data_version` to a small shared service helper if importing it from `safe_route.py` would introduce a graph-loading dependency. The helper must hash the same deterministic zone fields used to build artifacts.

- [ ] **Step 5: Implement the worker loop and configuration defaults**

```python
def run_worker(*, directory: Path, region: str, poll_seconds: int, refresh_seconds: int) -> None:
    next_refresh = 0.0
    while True:
        process_next_queued_build(directory=directory, region=region)
        now = time.monotonic()
        if now >= next_refresh:
            with SessionLocal() as db:
                reconcile_published_build(db, directory)
                queue_rebuild_if_active_artifact_is_stale(db, directory)
            next_refresh = now + refresh_seconds
        time.sleep(poll_seconds)
```

Add `builder_poll_seconds: int = 10` and `builder_data_refresh_seconds: int = 1800` to `Settings`; expose CLI overrides in the worker only for test/development use. Keep the long-running loop out of `build_route_artifacts.py` so its one-shot script interface remains usable.

- [ ] **Step 6: Run recovery, worker helper, and builder tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_build_route_artifacts_script.py backend/tests/test_route_artifact_builder.py -v`

Expected: PASS, including interrupted-publish recovery and unchanged-data no-op checks.

### Task 6: Package the API and worker with shared persistent storage

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `docker-compose.yml`
- Modify: `.gitignore`
- Modify: `DEVELOPMENT.md`

**Interfaces:**
- Produces Compose service `api` running `uvicorn app.main:app` and service `artifact-builder` running `python scripts/artifact_builder_worker.py` from the same backend image.
- Produces named volumes `app_data` for SQLite and `route_artifacts` for `current.json`/versioned artifacts; both services mount both paths consistently.

- [ ] **Step 1: Add a Compose structure assertion document command**

```yaml
services:
  api:
    build: ./backend
    environment:
      DATABASE_URL: sqlite:////data/app.db
      ROUTE_ARTIFACT_DIR: /artifacts
    volumes: [app_data:/data, route_artifacts:/artifacts]
  artifact-builder:
    build: ./backend
    command: ["python", "scripts/artifact_builder_worker.py"]
    environment:
      DATABASE_URL: sqlite:////data/app.db
      ROUTE_ARTIFACT_DIR: /artifacts
    volumes: [app_data:/data, route_artifacts:/artifacts, ./backend/data/osm:/app/data/osm:ro]
volumes:
  app_data: {}
  route_artifacts: {}
```

- [ ] **Step 2: Run Compose validation to establish the file is not yet available**

Run: `docker compose -f docker-compose.yml config`

Expected: FAIL because the Compose file does not yet exist. If Docker is not installed in the workspace, record that exact environmental limitation and still validate YAML syntax with the project’s available tooling.

- [ ] **Step 3: Build a minimal reproducible backend image**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Exclude `.venv`, test databases, caches, local `.env`, and large local OSM source directories in `.dockerignore`. Document that production builder deployments must mount their trusted local OSM graph data at `/app/data/osm`, the path containing `seoul-gyeonggi-walk.osm`; do not copy untracked large graph files into the image.

- [ ] **Step 4: Add the API/builder service definitions and persistent volume policy**

Set `restart: unless-stopped` on both services, publish API port `8000:8000`, and keep exactly one `artifact-builder` replica. Do not expose the artifact volume to the frontend container or publish it as a host port.

- [ ] **Step 5: Validate Compose and update operation documentation**

Run: `docker compose -f docker-compose.yml config`

Expected: PASS with one API service, one builder service, and the two named volumes. Update `DEVELOPMENT.md` with the commands, shared-path values, worker intervals, and the invariant that only the builder writes `current.json`.

### Task 7: Build the protected administrator screen

**Files:**
- Read before editing: `frontend/AGENTS.md` and the relevant Next.js 16 routing/client-component guide under `frontend/node_modules/next/dist/docs/`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/admin/scoring/page.tsx`
- Create: `frontend/src/app/admin/scoring/page.module.css`

**Interfaces:**
- Consumes Task 2 endpoints through `listScoringProfiles(token)`, `createScoringProfile(token, draft)`, `applyScoringProfile(token, profileId)`, and `listScoreBuilds(token)`.
- Produces `ScoringProfile`, `ScoreBuild`, and `ScoringProfileDraft` TypeScript types mirroring the Pydantic contracts.
- Produces an `/admin/scoring` client route that redirects to `/` when its initial administrator-only request returns 401 or 403.

- [ ] **Step 1: Read the mandatory Next.js 16 documentation and define typed API calls**

```ts
export type ScoreBuild = {
  id: number; profile_id: number; profile_version: string;
  status: "queued" | "building" | "succeeded" | "failed";
  artifact_version: string | null; error_code: string | null;
  created_at: string; started_at: string | null; finished_at: string | null;
};

export function listScoreBuilds(token: string) {
  return request<ScoreBuild[]>("/admin/scoring-profiles/builds", { headers: authHeaders(token) });
}
```

Add a small `authHeaders(token)` helper inside `api.ts`; pass it to every admin request and preserve existing public API calls unchanged.

- [ ] **Step 2: Run lint to establish that the new route is absent**

Run: `npm run lint`

Working directory: `frontend`

Expected: PASS on the baseline; no administrator route is present yet. This supplies a clean comparison before adding UI code.

- [ ] **Step 3: Implement client-side authorization and draft validation**

```tsx
const [authorized, setAuthorized] = useState(false);
useEffect(() => {
  const token = getToken();
  if (!token) return router.replace("/login");
  Promise.all([listScoringProfiles(token), listScoreBuilds(token)])
    .then(([profiles, builds]) => { setProfiles(profiles); setBuilds(builds); setAuthorized(true); })
    .catch(() => router.replace("/"));
}, [router]);

const validPeriod = (period: Period) => Math.abs(sum(weights[period]) - 1) < 1e-9;
const canSave = validPeriod("day") && validPeriod("night") && unknownScore >= 0 && unknownScore <= 100;
```

Render version/name/description fields, six labeled factor inputs for each period, visibly formatted totals, the unknown-score input, a disabled save/apply path until valid, and a server-error region with `role="alert"`. Do not infer admin status from the JWT payload.

- [ ] **Step 4: Implement draft, apply, status polling, and rollback interactions**

```tsx
async function apply(profileId: number) {
  const build = await applyScoringProfile(requireToken(), profileId);
  setBuilds((previous) => [build, ...previous]);
}

useEffect(() => {
  if (!builds.some((build) => build.status === "queued" || build.status === "building")) return;
  const id = window.setInterval(() => listScoreBuilds(requireToken()).then(setBuilds).catch(setError), 5000);
  return () => window.clearInterval(id);
}, [builds]);
```

Label the historical profile action “현재 데이터로 다시 적용”; call `apply(profile.id)` rather than adding an endpoint that reuses an old artifact. Show safe Korean status labels and the safe `error_code`, never server tracebacks or artifact filesystem paths.

- [ ] **Step 5: Add dashboard access only after server authorization**

Use `listScoringProfiles(getToken())` in the logged-in dashboard effect solely to decide whether to show an `/admin/scoring` navigation link. Treat 401/403 as a normal non-admin result and do not show the link. The admin route’s own authorization check remains mandatory.

- [ ] **Step 6: Run frontend static verification**

Run: `npm run lint && npm run build`

Working directory: `frontend`

Expected: PASS. Check manually that an ordinary member is redirected from `/admin/scoring`, an administrator can save a valid draft, and invalid 0.99/1.01 totals keep the action disabled.

### Task 8: Connect the completed behavior to the project map and run the full verification matrix

**Files:**
- Modify: `DEVELOPMENT.md`
- Modify only if verification exposes an issue: the owning production file and its focused test file from Tasks 1–7.

**Interfaces:**
- Consumes all completed APIs, worker behavior, artifact runtime behavior, and frontend page from prior tasks.
- Produces an accurate `DEVELOPMENT.md` operational map and evidence that the feature meets the spec’s acceptance criteria.

- [ ] **Step 1: Update `DEVELOPMENT.md` in the existing responsibility and flow sections**

Document these exact points: profile/build tables and the four build states; build-status endpoints; artifact-map priority for residence and all route modes; current-data rollback; API/builder shared volumes; 10-second queue polling and 1,800-second fingerprint checks; and unchanged fallback behavior for absent/corrupt artifacts.

- [ ] **Step 2: Run the full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests -v`

Expected: PASS with no use of the developer’s normal database and no leftover `backend/tests/.test-suite.db` after pytest cleanup.

- [ ] **Step 3: Run the frontend lint and production build**

Run: `npm run lint && npm run build`

Working directory: `frontend`

Expected: PASS.

- [ ] **Step 4: Re-run the end-to-end regression scenarios as focused tests**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py backend/tests/test_build_route_artifacts_script.py backend/tests/test_safety.py backend/tests/test_route_artifact.py -v`

Expected: PASS, proving profile change → artifact publication → residence/route reflection, build failure preservation, damaged artifact fallback, and unauthorized-request blocking.

- [ ] **Step 5: Validate the deployment description and leave a review-ready checkpoint**

Run: `docker compose -f docker-compose.yml config`

Expected: PASS. Report the exact test/build/config outputs to the user, list all modified files, and leave every change unstaged and uncommitted.

## Plan Self-Review

- **Spec coverage:** Tasks 1–3 complete queued-to-terminal profile application; Task 4 connects the artifact maps with full-request fallbacks; Task 5 supplies crash recovery and the two required schedules; Task 6 supplies shared API/builder volumes; Task 7 supplies the administrator UI and both authorization layers; Task 8 verifies every requested failure and success path and updates `DEVELOPMENT.md`.
- **Placeholder scan:** The plan names concrete paths, interfaces, tests, commands, status values, endpoints, and volume paths. It contains no deferred implementation markers.
- **Type consistency:** `ScoreBuildOut` and TypeScript `ScoreBuild` use the same lifecycle field names. Both builder and API refer to `artifact_version`, `profile_version`, `error_code`, `started_at`, and `finished_at`. The periodic helper and worker names are defined before their Compose command is introduced.
- **Review focus coverage:** Build preservation is exercised in Task 3; partial score maps in Task 4; interrupted publication recovery and unchanged-data no-op in Task 5; member authorization in Task 2 and screen gating in Task 7.
