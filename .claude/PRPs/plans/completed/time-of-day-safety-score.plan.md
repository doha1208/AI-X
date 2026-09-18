# Plan: 시간대 반영 안전점수 (Time-of-Day-Aware Safety Score)

## Summary
현재 `safety_score`는 CCTV 40%/보안등 20%/범죄역수 40% 고정 가중치로 계산되어 동 단위로 정적이다. 이 계획은 주간/야간 두 시간대에 서로 다른 가중치를 적용해, `/safety/route` 요청 시 전달된(또는 서버 현재) 시각에 따라 안전 가중 경로 탐색과 응답 점수가 달라지도록 만든다. 동 테이블에 저장된 `safety_score` 컬럼(거주지 추천용, 시간대 무관)은 건드리지 않고, 경로 계산 시점에만 순수 함수로 재계산한다.

## User Story
As a 낯선 동네를 밤에 혼자 걷는 사용자, I want 지금이 밤이라는 것을 반영한 안전 경로를 추천받고, so that 낮 기준으로 계산된 부정확한 안전도에 속지 않을 수 있다.

## Problem → Solution
[모든 시간대에 동일한 안전점수로 경로 계산] → [주간/야간에 따라 가중치가 달라지고, 그 결과가 경로 탐색 비용과 응답에 반영됨]

## Metadata
- **Complexity**: Medium
- **Source PRD**: `.claude/PRPs/prds/realtime-safe-navigation.prd.md`
- **PRD Phase**: Phase 1 — 시간대 반영 안전점수
- **Estimated Files**: 6 (2 new, 4 modified)

---

## UX Design

### Before
```
┌─────────────────────────────────────────────┐
│ 사용자가 출발/도착지 입력                     │
│ → 안전점수는 항상 낮/밤 구분 없이 동일         │
│ → 야간에도 "낮 기준 안전한 길"이 나올 수 있음   │
└─────────────────────────────────────────────┘
```

### After
```
┌─────────────────────────────────────────────┐
│ 사용자가 출발/도착지 입력 (선택: 시각 지정)    │
│ → 서버가 현재 시각(또는 지정 시각)의 주/야간   │
│   구간을 판정                                 │
│ → 야간이면 보안등 비중을 높이고 CCTV 비중을    │
│   낮춘 점수로 경로/응답이 계산됨               │
└─────────────────────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| `POST /safety/route` 요청 바디 | `start_lat/start_lng/end_lat/end_lng`만 | 위 필드 + 선택적 `at`(ISO8601, 생략 시 서버 현재 KST 시각) | 데모/테스트에서 야간을 강제로 시뮬레이션할 수 있게 함 |
| `POST /safety/route` 응답 | `safety_score`, `zones_passed[].safety_score`가 항상 day 가중치 | 요청 시각의 period(day/night)로 재계산된 점수 | 프론트는 이번 Phase에서 변경 없음(백엔드만) |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `backend/app/services/safety_score.py` | 1-33 | 정규화/가중합 로직 원본 — 이 계획이 확장하는 정확한 대상 |
| P0 | `backend/app/services/safe_route.py` | 195-280 | `_nearest_zone_score`, `_assign_edge_costs`, `find_safe_routes` — 정적 `zone.safety_score` 속성을 읽는 지점들, 전부 score_map 조회로 바꿔야 함 |
| P0 | `backend/app/api/safety.py` | 1-138 | `route_safety` 엔드포인트, `_point_sample_score`, `_zones_passed` — 폴백 경로와 응답 직렬화도 같은 score_map을 써야 day/night 표시가 일관됨 |
| P1 | `backend/app/schemas/safety.py` | 1-43 | `RouteRequest`/`RouteResponse` 스키마 컨벤션(Pydantic BaseModel, 필드명 snake_case) |
| P1 | `backend/app/models/safety_zone.py` | 1-19 | `SafetyZone` ORM 필드명(dong_code, cctv_count, streetlight_count, crime_count) — 재계산에 쓸 원본 raw count |
| P2 | `backend/tests/test_safety.py` | 1-70 | 기존 테스트 컨벤션(모듈 레벨 setup, sqlite 임시 DB, TestClient) |
| P2 | `backend/app/services/geo.py` | 1-9 | 순수 함수 스타일(타입힌트, 부작용 없음) — 새 유틸도 같은 스타일 유지 |

## External Documentation

No external research needed — 시간대 판정은 표준 라이브러리(`datetime`)만으로 충분하다.

**GOTCHA (Windows 환경)**: `zoneinfo.ZoneInfo("Asia/Seoul")`은 Windows에 IANA tz 데이터베이스가 기본 내장되어 있지 않아 `tzdata` 패키지 없이는 `ZoneInfoNotFoundError`가 날 수 있다(`requirements.txt`에 `tzdata` 없음, 개발 환경이 Windows). 한국은 서머타임이 없으므로 `timezone(timedelta(hours=9))` 고정 오프셋으로 KST를 표현하는 게 정확하면서도 의존성 추가가 필요 없다 — 이 방식을 쓴다.

---

## Patterns to Mirror

### PURE_FUNCTION_STYLE
// SOURCE: backend/app/services/geo.py:4-8
```python
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))
```
새 유틸(`period_for`)도 부작용 없는 순수 함수, 모듈 최상위, 타입힌트 필수.

### NORMALIZE_AND_WEIGHT
// SOURCE: backend/app/services/safety_score.py:1-32
```python
def _normalize(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 50.0
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100))


def compute_safety_scores(records: list[dict]) -> list[dict]:
    ...
    for record in records:
        cctv_score = _normalize(record["cctv_count"], c_lo, c_hi)
        light_score = _normalize(record["streetlight_count"], l_lo, l_hi)
        crime_score = 100 - _normalize(record["crime_count"], r_lo, r_hi)
        record["safety_score"] = round(cctv_score * 0.4 + light_score * 0.2 + crime_score * 0.4, 1)
    return records
```
고정된 `0.4/0.2/0.4`를 period별 가중치 테이블 조회로 바꾼다. 함수 시그니처는 하위호환 유지(`period` 기본값 `"day"` → 기존 호출부(`scripts/ingest_public_data.py:198`)는 코드 변경 없이 그대로 day 가중치로 동작).

### PONYTAIL_MVP_COMMENT
// SOURCE: backend/app/services/safety_score.py:14-15
```python
    ponytail: 방범시설(CCTV 40% + 보안등 20%) : 범죄 역수(40%) 가중치는
    임시 MVP 값. 실제 체감 안전도와 맞춰보며 조정 필요.
```
새 night 가중치도 동일 스타일의 ponytail 주석으로 "MVP 값, 조정 필요" 명시.

### EDGE_COST_LOOKUP
// SOURCE: backend/app/services/safe_route.py:195-211
```python
def _nearest_zone_score(lat: float, lng: float, zones: list[SafetyZone]) -> float:
    nearest = min(zones, key=lambda z: haversine_km(lat, lng, z.lat, z.lng))
    return nearest.safety_score


def _edge_cost(length_m: float, safety_score: float) -> float:
    multiplier = 1 + (100 - safety_score) / 100 * SAFETY_PENALTY_FACTOR
    return length_m * multiplier


def _assign_edge_costs(graph: nx.MultiDiGraph, zones: list[SafetyZone]) -> None:
    for u, v, data in graph.edges(data=True):
        mid_lat = (graph.nodes[u]["y"] + graph.nodes[v]["y"]) / 2
        mid_lng = (graph.nodes[u]["x"] + graph.nodes[v]["x"]) / 2
        score = _nearest_zone_score(mid_lat, mid_lng, zones)
        data["zone_score"] = score
        data["safety_cost"] = _edge_cost(data.get("length", 0.0), score)
```
`_nearest_zone_score`가 `nearest.safety_score`(정적 컬럼) 대신 `score_map[nearest.dong_code]`(period로 재계산된 값)를 읽도록 바꾼다. `_edge_cost`는 그대로(순수하게 숫자만 받음).

### FASTAPI_ROUTE_PATTERN
// SOURCE: backend/app/api/safety.py:71-91
```python
@router.post("/route", response_model=RouteResponse)
async def route_safety(payload: RouteRequest, db: Session = Depends(get_db)):
    zones = db.query(SafetyZone).all()
    safe_routes = await asyncio.to_thread(
        find_safe_routes,
        payload.start_lat, payload.start_lng, payload.end_lat, payload.end_lng,
        zones,
    )
```
`find_safe_routes` 호출에 `period=` 키워드 인자를 추가로 넘긴다(`asyncio.to_thread`의 위치/키워드 인자 전달 방식 그대로 사용).

### TEST_STRUCTURE
// SOURCE: backend/tests/test_safety.py:1-14, 61-69
```python
import os
if os.path.exists("test_safety.db"):
    os.remove("test_safety.db")
os.environ["DATABASE_URL"] = "sqlite:///./test_safety.db"
from fastapi.testclient import TestClient  # noqa: E402
...
client = TestClient(app)

def test_route_safety_returns_score():
    res = client.post(
        "/safety/route",
        json={"start_lat": 37.50, "start_lng": 127.00, "end_lat": 37.51, "end_lng": 127.01},
    )
    assert res.status_code == 200
```
통합 테스트는 이 파일에 이어서 추가(같은 `client`, 같은 setup_module 픽스처 재사용). 순수 로직 단위 테스트(`compute_safety_scores`, `period_for`)는 DB/앱이 필요 없으므로 새 파일 `tests/test_safety_score.py`, `tests/test_time_period.py`에 독립적으로 작성.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `backend/app/services/time_period.py` | CREATE | 시각 → day/night 판정 순수 함수. 한국 표준시 고정 오프셋(+9), 22:00~06:00을 night로 정의 |
| `backend/app/services/safety_score.py` | UPDATE | `compute_safety_scores`가 `period` 인자를 받아 day/night 가중치 테이블에서 조회하도록 확장. `SafetyZone` ORM 목록을 위한 `compute_zone_period_scores` 추가 |
| `backend/app/services/safe_route.py` | UPDATE | `find_safe_routes`/`_assign_edge_costs`/`_nearest_zone_score`가 정적 `zone.safety_score` 대신 `score_map`(period 반영)을 사용하도록 변경, `period` 파라미터 스레딩 |
| `backend/app/api/safety.py` | UPDATE | `route_safety`가 `payload.at`에서 period를 판정해 `find_safe_routes`와 폴백 경로(`_point_sample_score`, `_zones_passed`)에 동일한 score_map을 전달 |
| `backend/app/schemas/safety.py` | UPDATE | `RouteRequest`에 선택적 `at: datetime \| None = None` 필드 추가 |
| `backend/tests/test_safety_score.py` | CREATE | `compute_safety_scores`/`compute_zone_period_scores`의 day vs night 가중치 차이를 증명하는 단위 테스트 |
| `backend/tests/test_time_period.py` | CREATE | `period_for`의 경계값(22:00, 06:00 등) 단위 테스트 |
| `backend/tests/test_safety.py` | UPDATE | `POST /safety/route`에 `at`을 야간 시각으로 넘겼을 때 응답이 일관되게 처리되는지 확인하는 통합 테스트 1개 추가 |

## NOT Building

- 새벽 등 3단계 이상 시간대 세분화 — PRD Open Question, 이번 Phase는 day/night 2단계 MVP
- 범죄 발생 지점/야간 순찰 범위/도움 요청 장소 반영 — PRD Phase 3/4의 범위, 데이터 확보 전이라 이번 Phase에서 제외
- 실시간 위치 갱신/폴링 API — PRD Phase 2의 범위
- `residence-recommend`(거주지 추천) 엔드포인트의 시간대 반영 — 거주지 추천은 "어디 살지"를 묻는 것으로 시간대와 무관하다는 판단, day 가중치(현재 동작)를 그대로 유지
- 프론트엔드 UI 변경(시간대 선택 토글 등) — 이번 Phase는 백엔드 전용, 프론트는 이후 Phase(5. 지도 시각화)에서 다룸

---

## Step-by-Step Tasks

### Task 1: `period_for` 유틸리티 작성
- **ACTION**: `backend/app/services/time_period.py` 생성
- **IMPLEMENT**:
  ```python
  from datetime import datetime, time, timedelta, timezone
  from typing import Literal

  Period = Literal["day", "night"]

  # 한국은 서머타임이 없어 IANA tzdata 없이도(Windows 포함) 정확한 고정 오프셋.
  KST = timezone(timedelta(hours=9))

  NIGHT_START = time(22, 0)
  NIGHT_END = time(6, 0)


  def period_for(at: datetime | None = None) -> Period:
      """KST 기준 22:00~06:00을 야간(night)으로 판정한다.

      ponytail: 주/야간 2단계 MVP — 필요해지면 새벽 등으로 세분화.
      """
      moment = at if at is not None else datetime.now(KST)
      if moment.tzinfo is None:
          moment = moment.replace(tzinfo=KST)
      local_time = moment.astimezone(KST).time()
      is_night = local_time >= NIGHT_START or local_time < NIGHT_END
      return "night" if is_night else "day"
  ```
- **MIRROR**: PURE_FUNCTION_STYLE (`geo.py`) — 부작용 없는 모듈 최상위 함수, 완전한 타입힌트
- **IMPORTS**: 표준 라이브러리만(`datetime`, `typing`) — 신규 외부 의존성 없음
- **GOTCHA**: `zoneinfo.ZoneInfo("Asia/Seoul")`을 쓰지 말 것 — Windows에 `tzdata` 패키지가 없으면 런타임에 `ZoneInfoNotFoundError`. 고정 오프셋으로 충분(한국 무-서머타임)
- **VALIDATE**: `python -c "from app.services.time_period import period_for; from datetime import datetime, timezone, timedelta; print(period_for(datetime(2026,1,1,23,0,tzinfo=timezone(timedelta(hours=9)))))"` → `night` 출력

### Task 2: `safety_score.py`에 period 가중치 추가
- **ACTION**: `compute_safety_scores`를 period-aware로 확장, ORM 목록용 헬퍼 추가
- **IMPLEMENT**:
  ```python
  from typing import Literal

  Period = Literal["day", "night"]

  # (cctv_weight, streetlight_weight, crime_weight) — 합 1.0.
  # ponytail: MVP 값 — night는 CCTV(사후 확인용)보다 보안등(즉시 시야 확보)
  # 비중을 높임. 실제 체감 안전도와 맞춰보며 조정 필요.
  _PERIOD_WEIGHTS: dict[Period, tuple[float, float, float]] = {
      "day": (0.4, 0.2, 0.4),
      "night": (0.25, 0.35, 0.4),
  }


  def compute_safety_scores(records: list[dict], period: Period = "day") -> list[dict]:
      """... (기존 docstring 유지, period 설명 한 줄 추가)"""
      if not records:
          return records

      cctv_vals = [r["cctv_count"] for r in records]
      light_vals = [r["streetlight_count"] for r in records]
      crime_vals = [r["crime_count"] for r in records]
      c_lo, c_hi = min(cctv_vals), max(cctv_vals)
      l_lo, l_hi = min(light_vals), max(light_vals)
      r_lo, r_hi = min(crime_vals), max(crime_vals)
      w_cctv, w_light, w_crime = _PERIOD_WEIGHTS[period]

      for record in records:
          cctv_score = _normalize(record["cctv_count"], c_lo, c_hi)
          light_score = _normalize(record["streetlight_count"], l_lo, l_hi)
          crime_score = 100 - _normalize(record["crime_count"], r_lo, r_hi)
          record["safety_score"] = round(cctv_score * w_cctv + light_score * w_light + crime_score * w_crime, 1)
      return records


  def compute_zone_period_scores(zones: list, period: Period = "day") -> dict[str, float]:
      """SafetyZone ORM 목록을 dong_code -> period-가중 안전점수로 변환한다.

      저장된 zone.safety_score 컬럼(day 기준, 거주지 추천용)은 건드리지 않는
      순수 조회용 재계산 — 원본 원시 카운트(cctv/streetlight/crime)만 읽는다.
      """
      if not zones:
          return {}
      records = [
          {
              "dong_code": z.dong_code,
              "cctv_count": z.cctv_count,
              "streetlight_count": z.streetlight_count,
              "crime_count": z.crime_count,
          }
          for z in zones
      ]
      scored = compute_safety_scores(records, period=period)
      return {r["dong_code"]: r["safety_score"] for r in scored}
  ```
- **MIRROR**: NORMALIZE_AND_WEIGHT, PONYTAIL_MVP_COMMENT
- **IMPORTS**: `typing.Literal` 추가. `SafetyZone` 타입은 순환 임포트 위험 회피를 위해 타입힌트를 `list`(구체 타입 생략)로 둔다(YAGNI, mypy 설정도 없음)
- **GOTCHA**: `compute_safety_scores`의 시그니처를 바꾸되 `period` 기본값을 `"day"`로 둬서 `scripts/ingest_public_data.py:198`의 기존 호출(`compute_safety_scores(records)`)이 무수정으로 동일하게 동작해야 함 — 하위호환 필수
- **VALIDATE**: `pytest backend/tests/test_safety_score.py -v` (Task 6에서 작성할 테스트)

### Task 3: `safe_route.py`가 score_map을 쓰도록 변경
- **ACTION**: `_nearest_zone_score`, `_assign_edge_costs`, `find_safe_routes`에 `score_map` 스레딩
- **IMPLEMENT**:
  ```python
  from app.services.safety_score import Period, compute_zone_period_scores

  def _nearest_zone_score(lat: float, lng: float, zones: list[SafetyZone], score_map: dict[str, float]) -> float:
      nearest = min(zones, key=lambda z: haversine_km(lat, lng, z.lat, z.lng))
      return score_map[nearest.dong_code]

  def _assign_edge_costs(graph: nx.MultiDiGraph, zones: list[SafetyZone], score_map: dict[str, float]) -> None:
      for u, v, data in graph.edges(data=True):
          mid_lat = (graph.nodes[u]["y"] + graph.nodes[v]["y"]) / 2
          mid_lng = (graph.nodes[u]["x"] + graph.nodes[v]["x"]) / 2
          score = _nearest_zone_score(mid_lat, mid_lng, zones, score_map)
          data["zone_score"] = score
          data["safety_cost"] = _edge_cost(data.get("length", 0.0), score)

  def find_safe_routes(
      start_lat: float, start_lng: float, end_lat: float, end_lng: float,
      zones: list[SafetyZone], k: int = K_ALTERNATIVES, period: Period = "day",
  ) -> list[dict] | None:
      if not zones:
          return None
      score_map = compute_zone_period_scores(zones, period)
      bbox = _route_bbox(start_lat, start_lng, end_lat, end_lng)
      graph = _get_graph(bbox)
      if graph is None or graph.number_of_nodes() == 0:
          return None
      try:
          orig = _nearest_node(graph, start_lat, start_lng)
          dest = _nearest_node(graph, end_lat, end_lng)
          _assign_edge_costs(graph, zones, score_map)
          ...  # 나머지 동일
  ```
- **MIRROR**: EDGE_COST_LOOKUP
- **IMPORTS**: `from app.services.safety_score import Period, compute_zone_period_scores`
- **GOTCHA**: `_nearest_zone_score`가 `score_map[nearest.dong_code]`로 바뀌면서 `zones`에 없는 dong_code가 들어오면 `KeyError` — 하지만 `score_map`은 항상 같은 `zones` 리스트로 만들어지므로 발생 불가능(둘 다 같은 원본에서 파생)
- **VALIDATE**: `pytest backend/tests/test_safety.py -v` (기존 `test_route_safety_returns_score` 통과 유지 확인 — 회귀 없음)

### Task 4: `RouteRequest`에 선택적 `at` 필드 추가
- **ACTION**: `backend/app/schemas/safety.py`의 `RouteRequest`에 필드 추가
- **IMPLEMENT**:
  ```python
  from datetime import datetime

  class RouteRequest(BaseModel):
      start_lat: float
      start_lng: float
      end_lat: float
      end_lng: float
      at: datetime | None = None  # 생략 시 서버 현재 KST 시각 기준으로 주/야간 판정
  ```
- **MIRROR**: 기존 필드 스타일(snake_case, 타입힌트, 클래스 상단에 몰아서 선언)
- **IMPORTS**: `from datetime import datetime`
- **GOTCHA**: Pydantic이 ISO8601 문자열을 자동으로 `datetime`으로 파싱함 — 프론트/테스트에서 별도 파싱 불필요. 타임존 없는 문자열이 오면 naive datetime이 되므로 `period_for`가 KST로 간주하고 처리(Task 1의 `moment.replace(tzinfo=KST)` 분기가 커버)
- **VALIDATE**: 스키마만 변경 — `pytest backend/tests/test_safety.py -v`로 기존 테스트(=`at` 미포함 요청)가 여전히 통과하는지 확인

### Task 5: `api/safety.py`의 `route_safety`/폴백 경로에 period 반영
- **ACTION**: 엔드포인트가 `payload.at`에서 period를 판정하고, `find_safe_routes` 및 폴백(tmap/straight_line) 경로 모두 같은 `score_map`을 쓰도록 변경
- **IMPLEMENT**:
  ```python
  from app.services.safety_score import compute_zone_period_scores
  from app.services.time_period import period_for

  def _point_sample_score(points: list[Point], zones: list[SafetyZone], score_map: dict[str, float]) -> float:
      scores = [
          score_map[min(zones, key=lambda z: haversine_km(lat, lng, z.lat, z.lng)).dong_code]
          for lat, lng in points
      ]
      return sum(scores) / len(scores) if scores else 0.0

  @router.post("/route", response_model=RouteResponse)
  async def route_safety(payload: RouteRequest, db: Session = Depends(get_db)):
      zones = db.query(SafetyZone).all()
      period = period_for(payload.at)
      score_map = compute_zone_period_scores(zones, period)

      safe_routes = await asyncio.to_thread(
          find_safe_routes,
          payload.start_lat, payload.start_lng, payload.end_lat, payload.end_lng,
          zones, K_ALTERNATIVES, period,
      )

      candidates: list[dict]
      if safe_routes:
          mode: RouteMode = "safety_weighted"
          candidates = safe_routes
      else:
          tmap_points = await get_pedestrian_route(...)  # 기존 동일
          sample_points = tmap_points or [...]  # 기존 동일
          candidates = [{
              "points": sample_points,
              "score": _point_sample_score(sample_points, zones, score_map),
              "distance_m": _path_distance_m(sample_points),
          }]

      best = candidates[0]
      passed_zones = _zones_passed(best["points"], zones)
      passed = [
          SafetyZoneOut(
              dong_code=z.dong_code, dong_name=z.dong_name, lat=z.lat, lng=z.lng,
              safety_score=score_map[z.dong_code],
          )
          for z in passed_zones
      ]
      alternatives = [...]  # 기존 동일 (candidates[c]["score"]는 이미 score_map 기반이므로 그대로)
      return RouteResponse(
          safety_score=best["score"], zones_passed=passed,
          route_points=[...], mode=mode, alternatives=alternatives,
      )
  ```
- **MIRROR**: FASTAPI_ROUTE_PATTERN
- **IMPORTS**: `from app.services.safety_score import compute_zone_period_scores`, `from app.services.time_period import period_for`
- **GOTCHA**: `K_ALTERNATIVES`를 위치 인자로 넘기지 말고 `period=period` 키워드 인자로 넘겨서 `k`는 기본값을 쓰게 하는 게 안전(위치 인자 순서 실수 방지): `find_safe_routes(..., zones, period=period)`
- **VALIDATE**: `pytest backend/tests/test_safety.py -v` 전체 통과

### Task 6: 단위 테스트 — `compute_safety_scores`/`compute_zone_period_scores`
- **ACTION**: `backend/tests/test_safety_score.py` 생성
- **IMPLEMENT**:
  ```python
  from app.services.safety_score import compute_safety_scores

  def test_night_weights_favor_streetlight_over_cctv():
      # cctv-강세 동 vs streetlight-강세 동: day는 A가 우세, night는 B가 우세해야 함
      records_a = [
          {"dong_code": "A", "cctv_count": 100, "streetlight_count": 0, "crime_count": 0},
          {"dong_code": "B", "cctv_count": 0, "streetlight_count": 100, "crime_count": 0},
      ]
      day = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores([dict(r) for r in records_a], period="day")}
      night = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores([dict(r) for r in records_a], period="night")}

      assert day["A"] > day["B"]
      assert night["B"] > night["A"]

  def test_default_period_matches_existing_day_weights():
      records = [{"dong_code": "X", "cctv_count": 40, "streetlight_count": 80, "crime_count": 2}]
      default = compute_safety_scores([dict(r) for r in records])
      explicit_day = compute_safety_scores([dict(r) for r in records], period="day")
      assert default[0]["safety_score"] == explicit_day[0]["safety_score"]
  ```
- **MIRROR**: TEST_STRUCTURE — 순수 함수 테스트라 DB/TestClient 불필요, plain `def test_...()`
- **IMPORTS**: `from app.services.safety_score import compute_safety_scores`
- **GOTCHA**: `compute_safety_scores`가 입력 dict를 in-place 변형하므로, 같은 리스트를 day/night 두 번 계산에 재사용하면 안 됨 — 매번 `[dict(r) for r in records]`로 얕은 복사해서 넘길 것
- **VALIDATE**: `cd backend && pytest tests/test_safety_score.py -v` → 2 passed

### Task 7: 단위 테스트 — `period_for` 경계값
- **ACTION**: `backend/tests/test_time_period.py` 생성
- **IMPLEMENT**:
  ```python
  from datetime import datetime

  from app.services.time_period import KST, period_for

  def test_late_night_is_night():
      assert period_for(datetime(2026, 1, 1, 23, 0, tzinfo=KST)) == "night"

  def test_early_morning_is_night():
      assert period_for(datetime(2026, 1, 1, 5, 59, tzinfo=KST)) == "night"

  def test_boundary_6am_is_day():
      assert period_for(datetime(2026, 1, 1, 6, 0, tzinfo=KST)) == "day"

  def test_noon_is_day():
      assert period_for(datetime(2026, 1, 1, 12, 0, tzinfo=KST)) == "day"

  def test_naive_datetime_assumed_kst():
      assert period_for(datetime(2026, 1, 1, 23, 0)) == "night"
  ```
- **MIRROR**: TEST_STRUCTURE (plain function tests, no fixtures needed)
- **IMPORTS**: `from app.services.time_period import KST, period_for`
- **GOTCHA**: 없음 — 순수 함수라 결정적
- **VALIDATE**: `cd backend && pytest tests/test_time_period.py -v` → 5 passed

### Task 8: 통합 테스트 — `/safety/route`가 `at`을 받아들임
- **ACTION**: `backend/tests/test_safety.py`에 테스트 1개 추가
- **IMPLEMENT**:
  ```python
  def test_route_safety_accepts_night_timestamp():
      res = client.post(
          "/safety/route",
          json={
              "start_lat": 37.50, "start_lng": 127.00,
              "end_lat": 37.51, "end_lng": 127.01,
              "at": "2026-01-01T23:30:00+09:00",
          },
      )
      assert res.status_code == 200
      body = res.json()
      assert "safety_score" in body
      assert len(body["zones_passed"]) >= 1
  ```
- **MIRROR**: TEST_STRUCTURE — `test_route_safety_returns_score`와 동일 클라이언트/DB 픽스처 재사용, 같은 파일 하단에 추가
- **IMPORTS**: 추가 임포트 불필요(같은 파일 상단 것 재사용)
- **GOTCHA**: 이 테스트는 "에러 없이 받아들여지고 응답 형태가 유지되는지"만 검증 — TEST1/TEST2 픽스처는 극단값이라 day/night 점수가 우연히 같을 수 있음(Task 6에서 가중치 차이 자체는 이미 별도로 증명했으므로 여기선 중복 안 함)
- **VALIDATE**: `cd backend && pytest tests/test_safety.py -v` → 4 passed (기존 3개 + 신규 1개)

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `test_night_weights_favor_streetlight_over_cctv` | cctv-강세 동 A, streetlight-강세 동 B | day: A>B, night: B>A | 가중치 실제 반영 증명 |
| `test_default_period_matches_existing_day_weights` | period 인자 생략 | period="day"와 동일 결과 | 하위호환 |
| `test_late_night_is_night` / `test_early_morning_is_night` / `test_boundary_6am_is_day` | 22:00, 05:59, 06:00 | night/night/day | 경계값 |
| `test_naive_datetime_assumed_kst` | tzinfo 없는 datetime | KST로 간주되어 판정 | naive datetime 처리 |
| `test_route_safety_accepts_night_timestamp` | `at="2026-01-01T23:30:00+09:00"` | 200, 기존 응답 형태 유지 | 통합/회귀 |

### Edge Cases Checklist
- [x] 빈 zones 목록 — `compute_zone_period_scores([])`가 `{}` 반환
- [x] tzinfo 없는 `at` — naive datetime, KST로 간주
- [x] period 인자 생략(하위호환) — 기존 `ingest_public_data.py` 호출부 무수정 동작
- [ ] 최대 크기 입력 — 해당 없음(서울시 전체 동 개수 고정, 기존과 동일 규모)
- [ ] 동시 접속 — Phase 2(실시간 재경로) 범위, 이번 Phase 제외
- [ ] 네트워크 실패 — 해당 없음(순수 계산, 외부 호출 없음)
- [ ] 권한 거부 — 해당 없음(인증 불필요 엔드포인트, 기존과 동일)

---

## Validation Commands

### Static Analysis
```bash
cd backend && python -m compileall -q app
```
EXPECT: 출력 없음(구문 오류 없음) — 이 프로젝트에는 mypy/ruff 설정이 없어 컴파일 체크로 대체

### Unit Tests
```bash
cd backend && pytest tests/test_safety_score.py tests/test_time_period.py -v
```
EXPECT: 7 passed

### Full Test Suite
```bash
cd backend && pytest -v
```
EXPECT: 전체 통과, 회귀 없음(기존 `test_auth.py`, `test_safety.py` 포함)

### Manual Validation
- [ ] `uvicorn app.main:app --reload` 로 서버 기동
- [ ] `curl -X POST http://localhost:8000/safety/route -H "Content-Type: application/json" -d '{"start_lat":37.50,"start_lng":127.00,"end_lat":37.51,"end_lng":127.01,"at":"2026-01-01T12:00:00+09:00"}'` (day) 와 `"at":"2026-01-01T23:00:00+09:00"` (night) 응답의 `zones_passed[].safety_score` 값이 달라지는지 실제 서울 데이터로 확인

---

## Acceptance Criteria
- [ ] All tasks completed
- [ ] All validation commands pass
- [ ] Tests written and passing
- [ ] No type errors (compileall 통과)
- [ ] No lint errors (해당 없음 — 린터 미설정)
- [ ] Matches UX design (요청에 `at` 필드 추가, 응답 형태 불변)

## Completion Checklist
- [ ] Code follows discovered patterns
- [ ] Error handling matches codebase style
- [ ] Logging follows codebase conventions
- [ ] Tests follow test patterns
- [ ] No hardcoded values (가중치는 `_PERIOD_WEIGHTS` 테이블로 명시)
- [ ] Documentation updated — PRD phase 상태 업데이트(아래 Notes 참고)
- [ ] No unnecessary scope additions
- [ ] Self-contained — no questions needed during implementation

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 실서울 데이터에서 day/night 가중치 차이가 체감상 미미할 수 있음(대부분 동이 cctv/streetlight가 비례해서 분포) | M | L | MVP 가중치는 ponytail 주석으로 조정 지점 명시, 실측 후 값만 바꾸면 됨(구조 변경 불필요) |
| `at` 없이 서버 실행 중 실제 자정 넘어가는 순간 캐시된 score_map을 재사용하면 stale할 수 있음 | L | L | 이번 Phase는 요청마다 재계산(캐시 없음)이라 해당 없음 — 캐싱은 도입하지 않음 |
| `zoneinfo` 대신 고정 오프셋을 쓰는 결정이 추후 해외 확장 시 틀릴 수 있음 | L | L | 현재 스코프가 한국(서울) 한정이라 수용 가능한 트레이드오프, 확장 시 재검토 |

## Notes
- 구현 완료 후 `.claude/PRPs/prds/realtime-safe-navigation.prd.md`의 Phase 1 행을 `status: complete`, `PRP Plan: .claude/PRPs/plans/time-of-day-safety-score.plan.md`로 갱신할 것.
- Phase 2(실시간 재경로)는 이 Phase가 만든 `period`/`score_map` 계산 경로를 그대로 재사용할 수 있음 — 폴링 엔드포인트도 동일하게 `payload.at` 대신 매 폴링 요청의 "현재 시각"을 넘기면 됨.
