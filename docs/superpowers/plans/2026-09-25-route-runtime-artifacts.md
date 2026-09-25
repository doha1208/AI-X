# 경로 런타임 산출물 구현 계획

> **에이전트 작업자용:** 이 계획을 구현할 때는 `superpowers:executing-plans`를 사용해 작업 단위별로 진행한다. 단계는 체크박스로 추적한다.

**목표:** 데이터 갱신 시 안전 가중 경로 그래프를 버전 산출물로 만들고, API 요청은 로드된 산출물에서만 경로를 찾도록 전환한다.

**구조:** 배치 작업은 신뢰 가능한 로컬 OSM 그래프와 안전 데이터를 낮·밤용 불변 그래프로 변환해 원자적으로 게시한다. 런타임은 최신 매니페스트를 읽고, 노드 스냅·최단 경로 탐색·버전 기반 결과 캐시만 수행한다. Tmap은 명시적인 비교 요청 또는 안전 경로 실패 때만 사용한다.

**기술 스택:** Python 3, FastAPI, SQLAlchemy, NetworkX, SciPy KD-tree, pytest, Next.js 16, TypeScript.

**명세:** `docs/superpowers/specs/2026-09-25-route-runtime-artifacts-design.md`

## 전역 제약

- 초기 산출물은 서울·경기 데이터를 대상으로 하며, 지역별 산출물 확장을 막는 전역 상수는 만들지 않는다.
- 사용자 입력과 외부 파일을 pickle로 읽지 않는다. pickle은 애플리케이션이 기록한 산출물 디렉터리의 파일만 읽는다.
- HTTP 요청에서 OSM 다운로드, 간선 전체 재점수화, 산출물 생성 작업을 수행하지 않는다.
- 낮·밤 그래프와 기존 `safety_weighted → tmap → straight_line` 폴백 순서를 유지한다.
- 새 데이터 버전이 게시되면 이전 버전의 결과 캐시는 사용하지 않는다.
- 이 작업공간의 규칙상 에이전트는 Git 스테이징·커밋을 수행하지 않는다. 각 작업 뒤의 검증 결과와 권장 커밋 메시지를 사용자에게 제공한다.

## 검토 중점

- 부분 작성·손상·잘못된 스키마의 매니페스트가 최신 산출물로 채택되지 않고, 기존에 로드한 산출물로 계속 응답해야 한다.
- 산출물이 없는 개발 환경에서도 경로 API는 500 오류가 아니라 기존 Tmap·직선 폴백 응답을 반환해야 한다.
- 같은 도로 노드 쌍이라도 낮과 밤, 또는 산출물 버전이 다르면 결과 캐시를 공유하면 안 된다.
- 사용자 직접 검색은 비교선을 계속 받고, 위치 추적 재경로는 Tmap 비교 요청을 보내지 않아야 한다.
- 데이터 적재가 실패하거나 경로 산출물 생성이 실패한 경우 `current` 매니페스트가 바뀌면 안 된다.

---

### 작업 1: 경로 산출물 형식과 원자적 게시

**파일:**

- 생성: `backend/app/services/route_artifact.py`
- 생성: `backend/tests/test_route_artifact.py`
- 수정: `backend/app/core/config.py`

**인터페이스:**

- 생성: `RouteArtifact(version: str, region: str, graph_by_period: dict[Period, nx.DiGraph], node_ids: list[int], node_points: np.ndarray)`
- 생성: `publish_artifact(artifact: RouteArtifact, directory: Path) -> Path`
- 생성: `load_current_artifact(directory: Path) -> RouteArtifact | None`
- 생성: 설정 `route_artifact_dir: str = "data/route_artifacts"`

- [x] **1단계: 실패하는 산출물 게시·로드 테스트를 작성한다.**

```python
def test_publish_then_load_current_artifact(tmp_path):
    artifact = _artifact(version="v1")

    publish_artifact(artifact, tmp_path)

    loaded = load_current_artifact(tmp_path)
    assert loaded is not None
    assert loaded.version == "v1"
    assert loaded.graph_by_period["day"].has_edge(1, 2)


def test_corrupt_current_artifact_is_rejected(tmp_path):
    (tmp_path / "current.json").write_text('{"version":"missing"}', encoding="utf-8")

    assert load_current_artifact(tmp_path) is None
```

- [x] **2단계: 테스트가 실패하는지 확인한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_route_artifact.py -v`  
기대 결과: `ModuleNotFoundError: No module named 'app.services.route_artifact'`.

- [x] **3단계: 최소 산출물 모델·매니페스트·원자적 게시를 구현한다.**

```python
@dataclass(frozen=True)
class RouteArtifact:
    version: str
    region: str
    graph_by_period: dict[Period, nx.DiGraph]
    node_ids: list[int]
    node_points: np.ndarray


def publish_artifact(artifact: RouteArtifact, directory: Path) -> Path:
    version_dir = directory / artifact.version
    temp_dir = directory / f".{artifact.version}.tmp"
    # temp_dir에 pickle과 JSON 메타데이터를 모두 쓴 뒤 version_dir로 교체한다.
    # 마지막에 current.json.tmp를 current.json으로 replace한다.


def load_current_artifact(directory: Path) -> RouteArtifact | None:
    # current.json과 version 디렉터리의 메타데이터 버전·스키마를 대조한다.
    # 오류는 경고 로그 후 None으로 바꿔 런타임 폴백을 허용한다.
```

`current.json`에는 `schema_version`, `version`, `region`, `artifact_file`, `sha256`만 기록한다. 산출물 파일의 SHA-256을 로드 전에 대조한다. 임시 파일과 임시 디렉터리는 어떤 매니페스트에서도 참조하지 않는다.

- [x] **4단계: 설정을 추가하고 산출물 테스트를 통과시킨다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_route_artifact.py -v`  
기대 결과: 2개 이상 PASS.

- [x] **5단계: 기존 그래프 캐시 회귀 테스트를 실행한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safe_route_graph_cache.py -v`  
기대 결과: PASS.

권장 사용자 커밋 메시지: `feat: add versioned route artifact storage`

### 작업 2: 데이터 갱신 후 경로 산출물을 만드는 배치 명령

**파일:**

- 생성: `backend/scripts/build_route_artifacts.py`
- 수정: `backend/app/services/safe_route.py`
- 생성: `backend/tests/test_route_artifact_builder.py`

**인터페이스:**

- 생성: `build_route_artifact(zones: list[SafetyZone], version: str, region: str) -> RouteArtifact`
- 생성: `build_and_publish_route_artifact(version: str | None = None) -> Path`
- 사용: `route_artifact.publish_artifact()`

- [x] **1단계: 작은 그래프에서 낮·밤 그래프를 모두 포함하는 산출물 생성 실패 테스트를 작성한다.**

```python
def test_build_route_artifact_precomputes_both_periods(monkeypatch, zones):
    monkeypatch.setattr(sr, "_load_local_graph", lambda: _tiny_walk_graph())
    monkeypatch.setattr(sr, "_facility_index", lambda: None)

    artifact = sr.build_route_artifact(zones, version="20260925T010203Z", region="seoul-gyeonggi")

    assert set(artifact.graph_by_period) == {"day", "night"}
    assert artifact.node_ids == [1, 2]
    assert artifact.graph_by_period["night"][1][2]["safety_cost"] > 0
```

- [x] **2단계: 테스트가 실패하는지 확인한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_route_artifact_builder.py -v`  
기대 결과: `AttributeError: module 'app.services.safe_route' has no attribute 'build_route_artifact'`.

- [x] **3단계: 기존 안전 점수화 로직을 재사용하는 생성 함수를 구현한다.**

```python
def build_route_artifact(zones, version: str, region: str) -> RouteArtifact:
    graph = _load_local_graph()
    if graph is None or graph.number_of_nodes() == 0:
        raise RuntimeError("Local walking graph is required to build route artifacts")
    zone_index = _build_zone_index(zones)
    graph_by_period = {
        period: _build_scored_graph(
            graph, zones, compute_zone_period_scores(zones, period), zone_index, period, _facility_index()
        )
        for period in ("day", "night")
    }
    node_ids = list(graph.nodes)
    node_points = np.array([(graph.nodes[n]["y"], graph.nodes[n]["x"] * _LNG_SCALE) for n in node_ids])
    return RouteArtifact(version, region, graph_by_period, node_ids, node_points)
```

배치 스크립트는 DB의 `scoped_zones_query(db).all()`을 읽고 UTC 기반 버전을 생성한 뒤 `publish_artifact`를 호출한다. 산출물 생성 실패는 명확한 비영(0이 아닌) 종료 코드로 끝내며 기존 `current.json`을 변경하지 않는다. `ingest_public_data.py`는 이 단계에서 자동 실행하지 않는다. 운영 스케줄러가 적재 성공 후 이 명령을 순서대로 호출한다.

- [x] **4단계: 생성기 테스트를 통과시키고, 기존 점수·시설 테스트를 실행한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_route_artifact_builder.py backend/tests/test_safety_score.py backend/tests/test_facility_density.py -v`  
기대 결과: PASS.

권장 사용자 커밋 메시지: `feat: build route artifacts from refreshed safety data`

### 작업 3: 런타임 산출물 로드와 안전 경로 탐색 전환

**파일:**

- 수정: `backend/app/services/safe_route.py`
- 수정: `backend/app/main.py`
- 생성: `backend/tests/test_safe_route_artifact_runtime.py`
- 수정: `backend/tests/test_safety.py`

**인터페이스:**

- 생성: `RouteArtifactRuntime.load(directory: Path) -> bool`
- 생성: `RouteArtifactRuntime.find_routes(start_lat: float, start_lng: float, end_lat: float, end_lng: float, period: Period, k: int) -> list[dict] | None`
- 생성: 테스트 전용 `RouteArtifactRuntime.install(artifact: RouteArtifact) -> None` 및 `RouteArtifactRuntime.clear() -> None`
- 변경: `find_safe_routes(...)`는 로드된 산출물만 질의하며 OSM·Overpass를 요청하지 않는다.

- [x] **1단계: 산출물만 사용하고, 산출물이 없으면 None을 반환하는 실패 테스트를 작성한다.**

```python
def test_find_safe_routes_queries_loaded_artifact(monkeypatch, artifact):
    sr.install_route_artifact_for_test(artifact)
    monkeypatch.setattr(sr, "_get_graph", lambda *_: pytest.fail("HTTP-time graph loading is forbidden"))

    routes = sr.find_safe_routes(37.5, 127.0, 37.501, 127.001, [], period="day")

    assert routes is not None
    assert routes[0]["points"] == [(37.5, 127.0), (37.501, 127.001)]


def test_missing_artifact_returns_none_without_graph_fetch(monkeypatch):
    sr.clear_route_artifact_for_test()
    monkeypatch.setattr(sr, "_get_graph", lambda *_: pytest.fail("must not fetch graph"))

    assert sr.find_safe_routes(37.5, 127.0, 37.501, 127.001, [], period="day") is None
```

- [x] **2단계: 테스트가 실패하는지 확인한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safe_route_artifact_runtime.py -v`  
기대 결과: 테스트 도우미와 런타임 함수가 없어 실패.

- [x] **3단계: 원자적으로 교체 가능한 런타임 보관소를 구현한다.**

```python
class RouteArtifactRuntime:
    def __init__(self) -> None:
        self._artifact: RouteArtifact | None = None
        self._tree: cKDTree | None = None
        self._lock = threading.Lock()

    def load(self, directory: Path) -> bool:
        artifact = load_current_artifact(directory)
        if artifact is None:
            return False
        tree = cKDTree(artifact.node_points)
        with self._lock:
            self._artifact, self._tree = artifact, tree
        return True
```

`main.py`의 startup 훅은 `warm_cache()` 대신 최신 산출물을 로드한다. 기동 실패는 API 전체를 중단시키지 않는다. `find_safe_routes()`는 Runtime의 그래프·KD-tree만 사용하고, 산출물이 없거나 경로가 없으면 `None`을 반환해 API가 기존 폴백을 적용하게 한다. 기존 `_get_graph()`·`warm_cache()`는 배치 생성에 필요하지 않으면 제거하고, 관련 레거시 캐시 테스트도 산출물 테스트로 교체한다.

- [x] **4단계: 런타임·API 폴백 테스트를 통과시킨다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safe_route_artifact_runtime.py backend/tests/test_safety.py -v`  
기대 결과: PASS. 산출물이 없는 테스트 DB에서도 `/safety/route`는 200과 기존 응답 필드를 반환.

- [x] **5단계: 안전 경로 관련 회귀 테스트를 실행한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safe_route_road_tags.py backend/tests/test_safe_route_perf.py -v`  
기대 결과: PASS 또는 산출물 구조에 맞춘 명시적 갱신 후 PASS.

권장 사용자 커밋 메시지: `feat: route requests use prebuilt artifacts`

### 작업 4: 버전 기반 경로 결과 캐시와 산출물 재로드

**파일:**

- 수정: `backend/app/services/safe_route.py`
- 수정: `backend/app/core/config.py`
- 수정: `backend/tests/test_safe_route_artifact_runtime.py`

**인터페이스:**

- 생성: 설정 `route_result_cache_size: int = 2048`
- 생성: 설정 `route_artifact_reload_seconds: int = 60`
- 생성: `RouteArtifactRuntime.reload_if_changed(directory: Path, now: float) -> bool`
- 생성: `RouteArtifactRuntime.find_routes(...)` 내부 LRU 키 `(artifact.version, period, origin_node, destination_node, alternatives)`.

- [x] **1단계: 버전·낮밤·노드 쌍을 분리하는 캐시 실패 테스트를 작성한다.**

```python
def test_result_cache_is_invalidated_when_artifact_version_changes(runtime, artifact_v1, artifact_v2):
    runtime.install(artifact_v1)
    runtime.find_routes(37.5, 127.0, 37.501, 127.001, "day", 1)
    runtime.install(artifact_v2)

    routes = runtime.find_routes(37.5, 127.0, 37.501, 127.001, "day", 1)

    assert routes[0]["score"] == artifact_v2.graph_by_period["day"][1][2]["edge_score"]
```

- [x] **2단계: 테스트가 실패하는지 확인한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safe_route_artifact_runtime.py::test_result_cache_is_invalidated_when_artifact_version_changes -v`  
기대 결과: 새 산출물을 설치해도 이전 결과가 재사용되어 실패.

- [x] **3단계: 제한된 LRU와 매니페스트 재확인을 구현한다.**

`OrderedDict`로 크기가 `route_result_cache_size`를 넘으면 가장 오래된 항목을 제거한다. 새 산출물을 성공적으로 설치할 때에만 캐시 전체를 비운다. 매니페스트의 수정 시각을 `route_artifact_reload_seconds`마다 확인하고, 로드 실패면 현재 산출물과 캐시를 유지한다. 요청 처리 중에는 전체 파일을 다시 읽지 않는다.

- [x] **4단계: 캐시·재로드 테스트를 통과시킨다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safe_route_artifact_runtime.py -v`  
기대 결과: 버전 변경, 손상된 새 매니페스트, 낮밤 분리, LRU 상한 테스트가 모두 PASS.

권장 사용자 커밋 메시지: `feat: cache routes by artifact version and nodes`

### 작업 5: 선택적 Tmap 비교와 실시간 재경로 최적화

**파일:**

- 수정: `backend/app/schemas/safety.py`
- 수정: `backend/app/api/safety.py`
- 수정: `backend/app/services/tmap.py`
- 수정: `backend/tests/test_safety.py`
- 수정: `frontend/src/lib/api.ts`
- 수정: `frontend/src/app/page.tsx`

**인터페이스:**

- 추가: `RouteRequest.include_comparison: bool = True`
- 변경: `routeSafety(startLat, startLng, endLat, endLng, options?: { includeComparison?: boolean })`
- 추가: 설정 `tmap_route_cache_seconds: int = 300`과 `get_pedestrian_route()`의 제한된 in-memory 캐시 키 `(start_lat, start_lng, end_lat, end_lng)`

- [x] **1단계: 비교 비활성 요청이 Tmap을 호출하지 않는 실패 API 테스트를 작성한다.**

```python
def test_route_without_comparison_skips_tmap(monkeypatch):
    monkeypatch.setattr(safety_api, "find_safe_routes", lambda *args, **kwargs: [_route()])
    called = False

    async def tmap(*args):
        nonlocal called
        called = True
        return [(37.5, 127.0), (37.51, 127.01)]

    monkeypatch.setattr(safety_api, "get_pedestrian_route", tmap)
    res = client.post("/safety/route", json={**_payload(), "include_comparison": False})

    assert res.status_code == 200
    assert called is False
    assert res.json()["shortest_route_points"] is None
```

- [x] **2단계: 테스트가 실패하는지 확인한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety.py::test_route_without_comparison_skips_tmap -v`  
기대 결과: 현재 라우터가 Tmap을 무조건 병렬 호출하므로 실패.

- [x] **3단계: 비교 플래그와 조건부 외부 호출을 구현한다.**

`include_comparison=True`이면 안전 경로와 Tmap을 병렬 실행해 기존 직접 검색 지연을 유지한다. `False`이면 안전 경로만 실행하고, 안전 경로가 없을 때에만 Tmap을 호출한다. 프런트의 직접 주소 검색은 `{ includeComparison: true }`, `handlePositionUpdate()`는 `{ includeComparison: false }`를 전달한다. Tmap 서비스는 동일한 반올림 좌표 쌍의 성공 결과만 짧은 TTL 동안 캐시하며, 실패 결과는 캐시하지 않는다.

- [x] **4단계: 프런트 요청 호출 지점을 바꾸고 정적 검증한다.**

```ts
const result = await routeSafety(start.lat, start.lng, end.lat, end.lng, { includeComparison: true });

const result = await routeSafety(here.lat, here.lng, destination.lat, destination.lng, {
  includeComparison: false,
});
```

현재 프런트엔드에는 테스트 실행기가 없으므로 Vitest나 Testing Library를 이 변경만을 위해 추가하지 않는다. `routeSafety()`가 선택지를 JSON 본문에 넣도록 구현하고, 백엔드 통합 테스트로 `include_comparison=false`의 외부 호출 생략을 보장한다. TypeScript 호출부는 다음 단계의 lint와 production build로 검증한다.

- [x] **5단계: API·프런트 검증을 통과시킨다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety.py -v`  
실행: `npm run lint` 및 `npm run build` (작업 디렉터리 `frontend`)  
기대 결과: PASS.

권장 사용자 커밋 메시지: `perf: skip comparison routing during live reroutes`

### 작업 6: 운영 문서·상태 표시·전체 회귀 검증

**파일:**

- 수정: `backend/app/main.py`
- 수정: `backend/tests/test_safety.py`
- 수정: `DEVELOPMENT.md`

**인터페이스:**

- 변경: `GET /health` 응답에 `route_artifact: {"available": bool, "version": str | null}`를 추가한다.

- [x] **1단계: 산출물 가용 상태를 노출하는 실패 테스트를 작성한다.**

```python
def test_health_reports_loaded_route_artifact(monkeypatch):
    monkeypatch.setattr(route_runtime, "status", lambda: {"available": True, "version": "v1"})

    res = client.get("/health")

    assert res.json()["route_artifact"] == {"available": True, "version": "v1"}
```

- [x] **2단계: 테스트가 실패하는지 확인한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety.py::test_health_reports_loaded_route_artifact -v`  
기대 결과: `route_artifact` 키가 없어 실패.

- [x] **3단계: 건강 상태와 운영 절차를 구현·문서화한다.**

`/health`는 내부 파일 경로·예외·좌표를 노출하지 않는다. `DEVELOPMENT.md`에는 “공공데이터 적재 성공 후 `build_route_artifacts.py` 실행, `current` 매니페스트를 원자적으로 교체, API 워커가 새 버전을 로드” 절차와 산출물 부재 시 Tmap/직선 폴백을 추가한다.

- [x] **4단계: 전체 관련 회귀 테스트와 정적 검증을 실행한다.**

실행: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_safety.py backend/tests/test_safe_route_artifact_runtime.py backend/tests/test_route_artifact.py backend/tests/test_route_artifact_builder.py backend/tests/test_safe_route_road_tags.py backend/tests/test_safe_route_perf.py backend/tests/test_facility_density.py -v`  
실행: `npm run lint` 및 `npm run build` (작업 디렉터리 `frontend`)  
기대 결과: 모두 PASS.

권장 사용자 커밋 메시지: `docs: document route artifact operations`
