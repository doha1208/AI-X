# Phase 1 — 구성 가능한 안전점수·산출물 운영 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자가 코드 재배포 없이 안전점수 정책을 바꾸고, 검증된 데이터·정책 버전이 거주지 추천과 경로 탐색에 함께 적용되게 한다.

**Architecture:** 점수 계산은 명시적인 `ScoringProfile`을 받고, 데이터·프로필 조합으로 만든 버전 산출물이 행정동 점수 맵과 낮·밤 경로 그래프를 함께 보유한다. 관리자는 초안을 저장하고 적용을 요청하며, 별도 빌더가 검증된 산출물의 `current.json`을 원자적으로 게시한 경우에만 서비스가 새 버전을 읽는다.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLAlchemy, SQLite/PostgreSQL, NetworkX, pytest, Next.js 16.3.5, React 19, TypeScript, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-25-phase1-configurable-scoring-design.md`

## Global Constraints

- API 요청은 OSM 다운로드, 전 구간 재점수화, 산출물 생성을 하지 않는다.
- 점수 프로필은 여섯 지원 요인의 낮·밤 가중치와 누락 데이터 중립 점수만 바꾼다. 새 요인과 임의 수식은 코드 변경이다.
- 각 시간대 가중치는 0 이상이고 합계는 정확히 1.0이어야 한다.
- 관리자 API는 프런트 표시 여부와 무관하게 서버에서 허용 이메일과 유효한 access token을 확인한다.
- 빌드·외부 데이터·산출물 오류 시 마지막 정상 산출물 또는 기존 `tmap → straight_line` 폴백을 유지한다.
- 산출물은 신뢰 가능한 영속 디렉터리에만 기록·pickle 로드하며, `current.json`은 완성·검증 뒤에만 교체한다.
- 프런트 변경 전 `frontend/AGENTS.md` 및 `frontend/node_modules/next/dist/docs/`의 관련 Next.js 16 문서를 읽는다.
- 작업자는 Git 스테이징·커밋·푸시를 절대 실행하지 않는다. 각 작업의 마지막 단계는 사용자의 수동 커밋 검토 지점이다.

## Review Focus

- 기존 DB의 `0`이 실제 관측값인지 미수집 값인지 혼동되지 않아야 한다. Task 1에서 `None`과 기존 보안등 `lights_known` 플래그 회귀 테스트를 추가한다.
- 가중치 합계의 부동소수점 오차가 유효한 1.0 입력을 거절하거나 1.0이 아닌 입력을 통과시키면 안 된다. Task 2에서 `math.isclose` 허용 오차 테스트를 추가한다.
- 일반 사용자 또는 토큰 없는 요청이 관리자 설정을 변경하면 안 된다. Task 3에서 401/403 통합 테스트를 추가한다.
- 빌드 실패·손상 매니페스트가 현재 서비스 결과를 바꾸면 안 된다. Task 4에서 기존 산출물 유지 테스트를 추가한다.
- API가 새 산출물 경로 그래프와 DB의 오래된 `safety_score`를 섞으면 안 된다. Task 5에서 하나의 산출물 점수 맵으로 추천·통과 구역·경로 비용을 검증한다.

---

## File Structure

| 경로 | 책임 |
| --- | --- |
| `backend/app/services/scoring_profile.py` | 지원 요인, 기본 프로필, 프로필 값 검증, 점수 계산용 불변 타입 |
| `backend/app/services/safety_score.py` | 전달받은 프로필과 `None` 보존 원시값으로 행정동 점수 계산 |
| `backend/app/models/scoring_profile.py` | 프로필 초안·상태와 빌드 요청 이력 SQLAlchemy 모델 |
| `backend/app/schemas/scoring_profile.py` | 관리자 API의 입력·출력 Pydantic 모델 |
| `backend/app/services/scoring_profile_store.py` | 초안 저장, 적용 요청, 현재 프로필 조회를 DB 모델 밖으로 분리 |
| `backend/app/api/admin_scoring.py` | 관리자 전용 프로필 API |
| `backend/app/services/route_artifact.py` | 프로필·데이터 버전과 낮·밤 점수 맵을 포함한 산출물 검증·원자적 게시 |
| `backend/app/services/safe_route.py` | 후보 프로필로 그래프를 만들고, 런타임 산출물 점수 맵을 조회 |
| `backend/scripts/build_route_artifacts.py` | 특정 초안/활성 프로필과 현재 DB 스냅샷으로 산출물을 빌드 |
| `backend/scripts/refresh_and_build.py` | 30분 수집 작업에서 데이터 fingerprint가 바뀔 때만 빌드를 요청 |
| `frontend/src/app/admin/scoring/page.tsx` | 관리자 점수 프로필 편집·적용·되돌리기 화면 |
| `frontend/src/lib/api.ts` | 관리자 프로필 API 타입과 호출 함수 |
| `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | API·빌더·프런트 및 공유 산출물 볼륨의 데모 배포 |

### Task 1: 누락 데이터의 중립 처리

**Files:**
- Modify: `backend/app/models/safety_zone.py`
- Modify: `backend/app/services/safety_score.py`
- Modify: `backend/scripts/ingest_public_data.py`
- Modify: `backend/tests/test_safety_score.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Produces: missing values preserved through `compute_safety_scores(records: list[dict], period: Period = "day") -> list[dict]` and `compute_zone_period_scores(zones: list[SafetyZone], period: Period = "day") -> dict[str, float]`.
- Produces: nullable `crime_rate`, `police_dist_m`, `bell_dist_m` fields; no caller may convert a missing value to `0`.

- [ ] **Step 1: Add failing neutral-value tests.**

```python
def test_unknown_crime_police_and_bell_are_neutral_not_zero():
    rows = [
        {"dong_code": "KNOWN", "crime_rate": 50, "police_dist_m": 300, "bell_dist_m": 100},
        {"dong_code": "UNKNOWN", "crime_rate": None, "police_dist_m": None, "bell_dist_m": None},
        {"dong_code": "RISKY", "crime_rate": 200, "police_dist_m": 3000, "bell_dist_m": 1200},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(rows)}
    assert scores["RISKY"] < scores["UNKNOWN"] < scores["KNOWN"]
```

Add a second test proving `None` rows do not change known rows' min/max normalization, mirroring the existing streetlight test.

- [ ] **Step 2: Run the focused test to confirm failure.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety_score.py -k unknown -v`

Expected: FAIL because `compute_zone_period_scores()` uses `z.crime_rate or 0` and equivalent coercions.

- [ ] **Step 3: Make raw missingness explicit.**

Change the three numeric ORM columns to `Mapped[float | None]` with `nullable=True`. In ingestion, assign `None` when a source or nearest-point lookup is unavailable; retain numeric `0` only when the source explicitly reports a real zero. Update `ensure_new_columns()` to add new databases with nullable `FLOAT` columns and do not rewrite historical zeros automatically. Task 2, not this task, adds the optional profile argument.

```python
def _factor_value(record: dict, factor: str) -> float | None:
    if factor == "streetlight_count" and record.get("lights_known") is False:
        return None
    value = record.get(factor)
    return value if value is not None else None
```

Build `compute_zone_period_scores()` records with `z.crime_rate`, `z.police_dist_m`, and `z.bell_dist_m` directly, never `or 0`.

- [ ] **Step 4: Run focused and existing score tests.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety_score.py backend/tests/test_crime_rate.py backend/tests/test_poi_factors.py -v`

Expected: PASS. The existing one-record compatibility test remains in range 0–100.

- [ ] **Step 5: User commit checkpoint.**

Do not run Git commands. Report the test output and suggest: `fix: treat missing safety factors as neutral`.

### Task 2: 기본값 호환 점수 프로필과 계산 서비스

**Files:**
- Create: `backend/app/services/scoring_profile.py`
- Modify: `backend/app/services/safety_score.py`
- Modify: `backend/tests/test_safety_score.py`
- Create: `backend/tests/test_scoring_profile.py`

**Interfaces:**
- Produces: `FACTOR_NAMES: tuple[str, ...]`
- Produces: `@dataclass(frozen=True) class ScoringProfile(version: str, weights: dict[Period, dict[str, float]], unknown_score: float)`
- Produces: `validate_profile(profile: ScoringProfile) -> None`, raising `ValueError` with a user-safe Korean message.
- Produces: `DEFAULT_SCORING_PROFILE`, equal to the current day/night weight policy and `unknown_score=50.0`.

- [ ] **Step 1: Write failing profile validation and compatibility tests.**

```python
def test_default_profile_keeps_current_day_and_night_ordering():
    profile = DEFAULT_SCORING_PROFILE
    assert profile.weights["day"]["cctv_count"] > profile.weights["day"]["streetlight_count"]
    assert profile.weights["night"]["streetlight_count"] > profile.weights["night"]["cctv_count"]

def test_profile_rejects_weight_sum_other_than_one():
    invalid = replace(DEFAULT_SCORING_PROFILE, weights={**DEFAULT_SCORING_PROFILE.weights,
        "day": {**DEFAULT_SCORING_PROFILE.weights["day"], "cctv_count": 0.26}})
    with pytest.raises(ValueError, match="합계"):
        validate_profile(invalid)
```

Also test negative weights, an unknown factor, and `unknown_score` outside 0–100.

- [ ] **Step 2: Run to confirm the module does not exist.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scoring_profile.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the immutable profile and thread it through scoring.**

Use `math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9)` and require the exact `FACTOR_NAMES` set for each period. Replace module-level `_PERIOD_WEIGHTS`/`UNKNOWN_SCORE` reads with `profile.weights[period]` and `profile.unknown_score`; use `DEFAULT_SCORING_PROFILE` if the optional argument is absent. Do not alter the output rounding or lower-is-safer factors.

- [ ] **Step 4: Run profile and score regression tests.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scoring_profile.py backend/tests/test_safety_score.py -v`

Expected: PASS; previously known default results and day/night ordering remain unchanged.

- [ ] **Step 5: User commit checkpoint.**

Do not run Git commands. Suggest: `refactor: make safety scoring policy configurable`.

### Task 3: 관리자 권한과 프로필 초안 API

**Files:**
- Create: `backend/app/models/scoring_profile.py`
- Create: `backend/app/schemas/scoring_profile.py`
- Create: `backend/app/services/scoring_profile_store.py`
- Create: `backend/app/api/admin_scoring.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_admin_scoring.py`

**Interfaces:**
- Produces: settings `admin_emails: str = ""`, parsed case-insensitively into a set.
- Produces: `require_admin(current_user: User = Depends(get_current_user)) -> User`, returning 403 for an authenticated non-admin.
- Produces: `POST /admin/scoring-profiles`, `GET /admin/scoring-profiles`, `GET /admin/scoring-profiles/active`.
- Produces: immutable `ScoringProfileRecord` rows with `id`, `version`, `name`, `description`, `weights_json`, `unknown_score`, `status`, `created_at`, `created_by`.

- [ ] **Step 1: Add API authorization and draft tests.**

```python
def test_anonymous_user_cannot_read_profiles(client):
    assert client.get("/admin/scoring-profiles").status_code == 401

def test_non_admin_cannot_create_profile(client, user_token):
    response = client.post("/admin/scoring-profiles", headers={"Authorization": f"Bearer {user_token}"}, json=VALID_PROFILE)
    assert response.status_code == 403

def test_admin_can_save_a_valid_draft(client, admin_token):
    response = client.post("/admin/scoring-profiles", headers={"Authorization": f"Bearer {admin_token}"}, json=VALID_PROFILE)
    assert response.status_code == 201
    assert response.json()["status"] == "draft"
```

Set `ADMIN_EMAILS=admin@example.com` before app imports in this test module, and create matching users through the existing signup helper.

- [ ] **Step 2: Run the new API tests to confirm failure.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py -v`

Expected: FAIL because no admin router or dependency exists.

- [ ] **Step 3: Implement persistence, server-side authorization, and validation.**

Store weights as canonical JSON using the exact `ScoringProfile` validator from Task 2. Set new records to `draft`; never issue SQL update statements for their policy payload. `create_all` test registration must import `scoring_profile`; production migration is an Alembic revision, not an ad-hoc `ALTER TABLE`. Add the router in `main.py`. Never put admin status only in JWT claims; query the authenticated email and check the parsed server allow-list on each protected request.

- [ ] **Step 4: Run authorization, schema, and existing auth tests.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py backend/tests/test_auth.py -v`

Expected: PASS; invalid weight payloads return 422 and leave no draft row.

- [ ] **Step 5: User commit checkpoint.**

Do not run Git commands. Suggest: `feat: add protected scoring profile drafts`.

### Task 4: 프로필·데이터 버전 산출물과 안전한 적용 요청

**Files:**
- Modify: `backend/app/models/scoring_profile.py`
- Modify: `backend/app/schemas/scoring_profile.py`
- Modify: `backend/app/services/scoring_profile_store.py`
- Modify: `backend/app/api/admin_scoring.py`
- Modify: `backend/app/services/route_artifact.py`
- Modify: `backend/app/services/safe_route.py`
- Modify: `backend/scripts/build_route_artifacts.py`
- Create: `backend/tests/test_scoring_profile_apply.py`
- Modify: `backend/tests/test_route_artifact.py`
- Modify: `backend/tests/test_route_artifact_builder.py`

**Interfaces:**
- Produces: `ScoreBuildRecord(profile_id: int, status: Literal["queued", "building", "succeeded", "failed"], data_version: str | None, artifact_version: str | None, error_code: str | None)`.
- Produces: `POST /admin/scoring-profiles/{profile_id}/apply` returning 202 and a build id.
- Produces: `build_and_publish_route_artifact(zones, directory, version, region, profile) -> Path`.
- Extends: `RouteArtifact` with `profile_version: str`, `data_version: str`, and `score_by_period: dict[Period, dict[str, float]]`; increment artifact schema version.

- [ ] **Step 1: Add failing atomic-application tests.**

```python
def test_failed_candidate_build_does_not_replace_current_artifact(tmp_path, monkeypatch, profile, zones):
    publish_artifact(_artifact(version="old", profile_version="p-old"), tmp_path)
    monkeypatch.setattr(sr, "_load_local_graph", lambda: None)
    with pytest.raises(RuntimeError):
        build_and_publish_route_artifact(zones=zones, directory=tmp_path, version="candidate", region="test", profile=profile)
    assert load_current_artifact(tmp_path).version == "old"

def test_published_artifact_contains_profile_data_and_both_score_maps(tmp_path, profile, zones):
    build_and_publish_route_artifact(zones=zones, directory=tmp_path, version="v2", region="test", profile=profile)
    artifact = load_current_artifact(tmp_path)
    assert artifact.profile_version == profile.version
    assert set(artifact.score_by_period) == {"day", "night"}
```

- [ ] **Step 2: Run the targeted tests to confirm failure.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scoring_profile_apply.py backend/tests/test_route_artifact.py -v`

Expected: FAIL because the artifact has no profile/data/score-map fields and apply endpoint does not exist.

- [ ] **Step 3: Implement candidate build and publication.**

Create a deterministic `data_version` SHA-256 from sorted raw zone fields (`dong_code`, coordinates, six inputs, known flags). Build day/night score maps once with the candidate profile, pass those maps into `_build_scored_graph`, and store them in the artifact. Extend metadata and manifest validation for the new required fields; reject old schema artifacts safely. The builder must write a candidate version fully, verify it by `load_current_artifact`-equivalent validation before pointer replacement, then atomically replace `current.json`.

`apply` only creates a queued `ScoreBuildRecord`; it does not calculate in the HTTP process. The builder script claims one queued record, marks it `building`, publishes only on success, and writes a safe failure code (`missing_local_graph`, `invalid_profile`, or `build_failed`) otherwise. The current manifest is the activation authority; a startup reconciliation updates a profile/build row that was published before a process interruption.

- [ ] **Step 4: Run builder, artifact, and application regressions.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_scoring_profile_apply.py backend/tests/test_route_artifact.py backend/tests/test_route_artifact_builder.py backend/tests/test_safe_route_artifact_runtime.py -v`

Expected: PASS; a failed candidate does not alter `current.json`, while a successful candidate exposes its profile and data versions.

- [ ] **Step 5: User commit checkpoint.**

Do not run Git commands. Suggest: `feat: publish route artifacts from scoring profiles`.

### Task 5: 산출물 점수 맵으로 거주지·경로 응답 통일

**Files:**
- Modify: `backend/app/services/safe_route.py`
- Modify: `backend/app/api/safety.py`
- Modify: `backend/app/schemas/safety.py`
- Modify: `backend/tests/test_safe_route_artifact_runtime.py`
- Modify: `backend/tests/test_safety.py`

**Interfaces:**
- Produces: `RouteArtifactRuntime.score_map(period: Period) -> dict[str, float] | None`.
- Produces: `RouteArtifactRuntime.status() -> dict[str, bool | str | None]` including `profile_version` and `data_version` when available.
- Changes: `/safety/residence-recommend` and `/safety/zones` map `SafetyZone` rows to `SafetyZoneOut` using the active day score map; `/safety/route` uses the active period score map for passed zones and fallback sampling.

- [ ] **Step 1: Add failing same-version response tests.**

```python
def test_recommendation_uses_loaded_artifact_day_scores(client, artifact, monkeypatch):
    install_artifact_with_scores(artifact, {"A": 90.0, "B": 10.0})
    seed_zones(client, safety_scores={"A": 0.0, "B": 100.0})
    response = client.get("/safety/residence-recommend")
    assert [row["dong_code"] for row in response.json()] == ["A", "B"]

def test_route_passed_zone_uses_artifact_night_score(client, artifact, monkeypatch):
    install_artifact_with_scores(artifact, {"A": 22.0}, period="night")
    response = client.post("/safety/route", json={**PAYLOAD, "at": "2026-09-25T23:00:00+09:00"})
    assert response.json()["zones_passed"][0]["safety_score"] == 22.0
```

- [ ] **Step 2: Run to confirm failure.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety.py backend/tests/test_safe_route_artifact_runtime.py -v`

Expected: FAIL because recommendations order by the stale `SafetyZone.safety_score` column and routes recompute with defaults.

- [ ] **Step 3: Use the active artifact as the score source.**

Add a lock-protected copy-returning runtime method for score maps. For recommendation and nearby-zone endpoints, fetch the scoped zones, build `SafetyZoneOut` with the active map, sort recommendations in Python by mapped day score, and omit only zones absent from a valid map. When no artifact is loaded, retain existing DB score behavior for recommendation and the default profile computation for route/Tmap/straight-line fallback. Do not expose the map or raw profile through public endpoints.

- [ ] **Step 4: Run API and routing regressions.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety.py backend/tests/test_safe_route_artifact_runtime.py backend/tests/test_safe_route_perf.py -v`

Expected: PASS; the active artifact's profile version is the only score source whenever it is available.

- [ ] **Step 5: User commit checkpoint.**

Do not run Git commands. Suggest: `fix: keep route and residence scores on one artifact version`.

### Task 6: 관리자 점수 설정 화면

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/app/admin/scoring/page.tsx`
- Create: `frontend/src/app/admin/scoring/page.module.css`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/components/icons.tsx` only if an existing icon cannot express the link
- Modify: `DEVELOPMENT.md`

**Interfaces:**
- Produces: `getActiveScoringProfile()`, `listScoringProfiles()`, `createScoringProfile(input)`, `applyScoringProfile(id)`, and `getScoreBuild(id)` in `api.ts`.
- Produces: `/admin/scoring` page with editable `weights.day`, `weights.night`, `unknown_score`, draft save, apply status, history, and rollback action.

- [ ] **Step 1: Read frontend constraints and write the initial failing/static checks.**

Read `frontend/AGENTS.md` and the relevant app-router/client-component documentation in `frontend/node_modules/next/dist/docs/`. Add TypeScript fixtures or a lightweight pure helper test only if the repository already has a runner; do not introduce Vitest solely for this page. Define a pure `weightTotal(weights: Record<Factor, number>): number` export and check invalid totals in the component before calling the API.

- [ ] **Step 2: Confirm the page is absent and backend contracts are green.**

Run: `Test-Path frontend/src/app/admin/scoring/page.tsx`

Expected: `False`.

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_admin_scoring.py backend/tests/test_scoring_profile_apply.py -v`

Expected: PASS.

- [ ] **Step 3: Implement the protected administrator workflow.**

Use the existing bearer-token helpers in `frontend/src/lib/auth.ts`. On 401 redirect to `/login`; on 403 render a short “관리자 권한이 필요합니다” state without exposing profile data. Render the six day/night numeric inputs, per-period running totals, a 0–100 neutral-score input, and disable “적용” unless client validation passes. Saving creates a new draft; applying polls the build-status endpoint at a bounded interval until `succeeded` or `failed`. The history list's rollback button creates an apply request for the selected prior profile; it must not overwrite history in the browser.

Add a discrete “점수 설정” link only for the client-side page entry point; the backend remains authoritative. Update `DEVELOPMENT.md` with the profile/artifact workflow and the admin screen's responsibility.

- [ ] **Step 4: Run frontend static checks and production build.**

Run (workdir `frontend`): `npm run lint`

Expected: PASS.

Run (workdir `frontend`): `npm run build`

Expected: PASS.

- [ ] **Step 5: User commit checkpoint.**

Do not run Git commands. Suggest: `feat: add scoring policy administration screen`.

### Task 7: 컨테이너 운영과 30분 데이터 확인

**Files:**
- Create: `backend/scripts/refresh_and_build.py`
- Create: `backend/scripts/worker_loop.py`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `backend/.dockerignore`
- Create: `frontend/.dockerignore`
- Modify: `DEVELOPMENT.md`
- Create: `backend/tests/test_refresh_and_build.py`

**Interfaces:**
- Produces: `refresh_and_queue_if_changed() -> bool`, returning `True` only when the raw-zone fingerprint differs from the current artifact's `data_version` and a build is queued.
- Produces: `worker_loop.py` that runs the refresh/check command once, then waits 1800 seconds; it exits non-zero only for unrecoverable configuration errors.
- Produces: Compose services `api`, `builder`, and `frontend`; `api` and `builder` mount the same named `route_artifacts` volume.

- [ ] **Step 1: Add data-fingerprint and no-op tests.**

```python
def test_identical_zone_snapshot_does_not_queue_a_build(monkeypatch, zones):
    monkeypatch.setattr(worker, "load_current_data_version", lambda: worker.fingerprint_zones(zones))
    assert worker.refresh_and_queue_if_changed(zones=zones) is False

def test_changed_zone_snapshot_queues_one_build(monkeypatch, zones):
    monkeypatch.setattr(worker, "load_current_data_version", lambda: "old")
    queued = []
    monkeypatch.setattr(worker, "queue_active_profile_build", lambda data_version: queued.append(data_version))
    assert worker.refresh_and_queue_if_changed(zones=zones) is True
    assert len(queued) == 1
```

- [ ] **Step 2: Run to confirm failure.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_refresh_and_build.py -v`

Expected: FAIL because the worker module does not exist.

- [ ] **Step 3: Implement bounded worker operation and Compose wiring.**

`refresh_and_build.py` calls the existing derived-factor refresh function, reads a single stable DB snapshot after commit, computes the same canonical fingerprint as Task 4, and queues the active profile only when it differs from the current artifact. It must log a safe reason and return without queueing when external data refresh fails. `worker_loop.py` uses `time.sleep(1800)` only between completed attempts; it never holds a DB transaction while sleeping.

Compose passes `DATABASE_URL`, `ADMIN_EMAILS`, API keys, and `ROUTE_ARTIFACT_DIR=/data/route_artifacts` from an untracked environment file. The API and builder mount `route_artifacts:/data/route_artifacts`; no key, token, or host volume path is written into the image. The builder service runs the loop, while API runs Uvicorn. Document start, status check, manual one-shot builder execution, and the “no valid artifact → Tmap/straight line” behavior in `DEVELOPMENT.md`.

- [ ] **Step 4: Run backend tests and validate the compose configuration.**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_refresh_and_build.py backend/tests/test_scoring_profile_apply.py backend/tests/test_safe_route_artifact_runtime.py -v`

Expected: PASS.

Run: `docker compose config`

Expected: exit code 0; the rendered `api` and `builder` services both reference `route_artifacts` and secrets remain environment substitutions.

- [ ] **Step 5: User commit checkpoint.**

Do not run Git commands. Suggest: `chore: run scoring artifact refreshes in a builder container`.

## Final Verification

- [ ] Run the full backend suite: `backend/.venv/Scripts/python.exe -m pytest backend/tests -v`.
- [ ] Run frontend checks in `frontend`: `npm run lint` then `npm run build`.
- [ ] With Compose started using non-secret test values, verify `/health` reports the current artifact availability and version without an internal path.
- [ ] Verify a normal user receives 403 from every `/admin/scoring-profiles*` endpoint and an allow-listed user can create a valid draft.
- [ ] Verify an invalid profile, a missing local OSM graph, and a corrupted new manifest leave the previously loaded route and residence results unchanged.
- [ ] Give the user a concise change summary, exact verification output, and the seven suggested commit messages. Do not run Git commands.
