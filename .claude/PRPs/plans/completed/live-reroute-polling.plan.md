# Plan: 실시간 재경로 API/폴링 (Live Re-route Polling)

## Summary
사용자가 "실시간 안내"를 켜면 브라우저 Geolocation `watchPosition`으로 현재 위치를 계속 추적하고, 마지막 재계산 지점에서 50m 이상 이동했을 때(최소 5초 간격) 기존 `POST /safety/route`를 현재 위치→목적지로 다시 호출해 지도의 경로를 갱신한다. Phase 1에서 서버가 `at` 생략 시 이미 "현재 시각"을 기본값으로 쓰도록 만들어뒀으므로, 이 Phase는 백엔드 변경 없이 프론트엔드만으로 완성된다.

## User Story
As a 낯선 동네를 걸어서 이동 중인 사용자, I want 이동하는 동안 경로가 자동으로 갱신되길, so that 최초 조회 시점 이후 상황이 바뀌어도(예: 시간대가 바뀌거나 경로를 벗어나도) 계속 안전한 길로 안내받을 수 있다.

## Problem → Solution
[출발/도착지를 입력해 한 번만 경로를 조회 — 이후 이동해도 경로가 고정됨] → [실시간 안내 모드를 켜면 이동 중 위치가 일정 거리 이상 바뀔 때마다 경로가 자동으로 재계산됨]

## Metadata
- **Complexity**: Small
- **Source PRD**: `.claude/PRPs/prds/realtime-safe-navigation.prd.md`
- **PRD Phase**: Phase 2 — 실시간 재경로 API/폴링
- **Estimated Files**: 3 (1 new, 2 modified) — 백엔드 변경 없음

---

## UX Design

### Before
```
┌───────────────────────────────────────────┐
│ 출발지/도착지 입력 → "안전도 조회" 클릭     │
│ → 경로 한 번 표시                          │
│ → 사용자가 실제로 이동해도 경로는 그대로   │
└───────────────────────────────────────────┘
```

### After
```
┌───────────────────────────────────────────┐
│ 경로 조회 후 "실시간 안내 시작" 클릭        │
│ → 지도에 "● 실시간 안내 중" 배지 표시       │
│ → 50m 이상 이동할 때마다 경로가 자동 갱신   │
│ → 목적지 30m 이내 도달 시 자동으로 안내 종료│
│ → "중지" 버튼으로 언제든 수동 종료 가능     │
└───────────────────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| 경로 결과 카드(`page.tsx` 526-563 부근) | `routeModeHint` 아래 바로 `resultSummary` | 그 사이에 "실시간 안내 시작" 버튼 또는 "● 실시간 안내 중" 배지 + "중지" 버튼 추가 | 경로가 있을 때(`route`가 non-null)만 노출 |
| `SafetyMap` | `myLocation`이 최초 1회 위치로 고정 | `watchPosition`이 `myLocation`을 계속 갱신 → 지도의 내 위치 점이 실시간으로 움직임 | `SafetyMap.tsx`는 이미 `myLocation` prop 변화에 반응하므로 컴포넌트 자체는 무수정 |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `frontend/src/app/page.tsx` | 41-91 (state), 202-217 (`handleRouteSearch`), 526-563 (경로 결과 카드) | 새 내비게이션 상태/버튼을 끼워 넣을 정확한 위치와 기존 상태 관리 스타일 |
| P0 | `frontend/src/lib/api.ts` | 13-18 (`RouteResult`), 57-72 (`routeSafety`) | 재사용할 기존 함수 — 시그니처 변경 없이 그대로 반복 호출 |
| P0 | `backend/app/schemas/safety.py` | 20-25 (`RouteRequest.at`) | `at` 생략 시 서버가 자동으로 "현재 시각"을 쓴다는 것을 확인 — 프론트가 매 재조회마다 `at`을 넘길 필요가 없는 근거 |
| P1 | `frontend/src/components/SafetyMap.tsx` | 12-21 (Props), 164-169 (최초 1회 자동 center), 180-197 (내 위치 점 렌더링) | `myLocation`이 바뀔 때마다 오버레이만 갱신되고 지도 시점은 건드리지 않는다는 것 확인 — 이 컴포넌트는 무수정 |
| P1 | `backend/app/services/geo.py` | 1-9 (`haversine_km`) | 프론트에 포팅할 정확한 하버사인 공식 |
| P2 | `frontend/src/app/page.tsx` | 169-190 (키보드/외부클릭 cleanup effect 패턴) | `useEffect` cleanup 관례 — geolocation watch 해제에 동일 패턴 적용 |
| P2 | `frontend/src/app/page.module.css` | 569-583 (`.primaryButton`), 585-599 (`.resultSummary`) | 새 버튼/배지가 따를 사이징·색상 토큰(`--brand`, `--brand-dark`, `--warning`, `--safe`, `--radius-sm` — `globals.css:6-23`에 정의됨) |

## External Documentation

No external research needed — `navigator.geolocation.watchPosition`/`clearWatch`는 표준 브라우저 API이고 거리 임계값 로직은 이미 백엔드에 있는 하버사인 공식을 그대로 포팅한다.

**GOTCHA**: `watchPosition`은 HTTPS(또는 `localhost`) 컨텍스트에서만 동작한다 — 로컬 개발(`localhost:3000`)은 문제없지만, 배포 시 HTTP로 열면 브라우저가 위치 API 자체를 거부한다.

---

## Patterns to Mirror

### PURE_GEO_FUNCTION
// SOURCE: backend/app/services/geo.py:4-8
```python
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))
```
같은 공식을 TS로 포팅(단위만 km→m). 두 런타임(Python/TS)이라 임포트 공유는 불가능 — 의도적 중복.

### EXISTING_REQUEST_STATE_PATTERN
// SOURCE: frontend/src/app/page.tsx:202-217
```tsx
async function handleRouteSearch(e: React.FormEvent<HTMLFormElement>) {
  e.preventDefault();
  const [start, end] = await Promise.all([resolveField("start"), resolveField("end")]);
  if (!start || !end) {
    setError("출발지/도착지 주소를 찾을 수 없어요. 정확한 주소를 입력하거나 지도에서 선택해주세요");
    return;
  }
  try {
    const result = await routeSafety(start.lat, start.lng, end.lat, end.lng);
    setNearby([]);
    setRoute(result);
    setError(null);
  } catch (err) {
    setError(err instanceof Error ? err.message : "경로 조회 실패");
  }
}
```
재계산 호출도 같은 `routeSafety(...)` → `setRoute(...)` 패턴을 따른다. 단, 실시간 재계산 실패는 배너로 사용자를 방해하지 않고 조용히 다음 위치 갱신에서 재시도한다(아래 Task 2 GOTCHA).

### EFFECT_CLEANUP_PATTERN
// SOURCE: frontend/src/app/page.tsx:169-178
```tsx
useEffect(() => {
  if (!mapFullscreen && !contextMenu) return;
  function handleKeyDown(e: KeyboardEvent) {
    if (e.key !== "Escape") return;
    setMapFullscreen(false);
    setContextMenu(null);
  }
  window.addEventListener("keydown", handleKeyDown);
  return () => window.removeEventListener("keydown", handleKeyDown);
}, [mapFullscreen, contextMenu]);
```
`watchPosition`도 동일하게 구독/해제 쌍을 갖춘 effect로 관리(마운트 해제 시 `clearWatch` 보장).

### GEOLOCATION_ERROR_PATTERN
// SOURCE: frontend/src/app/page.tsx:59-74
```tsx
function requestMyLocation() {
  if (!navigator.geolocation) {
    setLocationDenied(true);
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      setMyLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      setLocationDenied(false);
    },
    (err) => {
      console.warn("[geolocation] failed:", err.message);
      setLocationDenied(true);
    }
  );
}
```
`watchPosition` 호출도 같은 존재 체크(`!navigator.geolocation`)와 `console.warn` 로깅 스타일을 따른다.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `frontend/src/lib/geo.ts` | CREATE | `haversineMeters` 순수 함수 — 이동 거리/도착 판정에 사용 |
| `frontend/src/app/page.tsx` | UPDATE | 내비게이션 상태(`navigating`), `watchPosition` 구독/해제, 재계산 트리거 로직, 토글 버튼 UI |
| `frontend/src/app/page.module.css` | UPDATE | 토글 버튼(`.navStartButton`/`.navStopButton`)과 실시간 배지(`.liveBadge`/`.liveDot`) 스타일 |

## NOT Building

- **백엔드 변경** — `/safety/route`가 이미 임의의 start/end와 (생략 시) 서버 "현재 시각"을 지원하므로(Phase 1 산출물) 그대로 재사용. 새 엔드포인트를 만들지 않는다(Decisions Log 참고).
- **WebSocket/SSE 실시간 스트림** — 도보 이동 속도엔 폴링(위치 갱신 이벤트 기반 조건부 재호출)으로 충분하다는 PRD Decision Log를 따름.
- **백그라운드 위치 추적** — 브라우저 탭이 열려 있는 동안만 동작. 탭을 닫거나 화면이 꺼지면 추적도 멈춘다(PRD Phase 2 NOT Building과 동일).
- **자동화된 프론트엔드 테스트 인프라 신규 설치(vitest/jest 등)** — 이 프로젝트엔 현재 프론트엔드 테스트 러너가 전혀 없다(`package.json`에 test 스크립트/테스트 라이브러리 없음 확인됨). 한 Phase 안에서 테스트 하네스 전체를 새로 까는 것은 스코프 초과이므로, 이번 Phase는 수동 브라우저 검증으로 대체하고 후속 과제로 Risks에 기록한다.
- **위치 표시 정확도 개선(예: 방향 화살표, 속도 기반 보간)** — 이번 Phase는 "재계산이 실제로 일어난다"는 핵심 기능만 다룬다.

---

## Step-by-Step Tasks

### Task 1: `haversineMeters` 유틸리티 작성
- **ACTION**: `frontend/src/lib/geo.ts` 생성
- **IMPLEMENT**:
  ```ts
  import type { LatLng } from "./kakao";

  const EARTH_RADIUS_M = 6371000;

  export function haversineMeters(a: LatLng, b: LatLng): number {
    const toRad = (deg: number) => (deg * Math.PI) / 180;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const lat1 = toRad(a.lat);
    const lat2 = toRad(b.lat);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
    return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
  }
  ```
- **MIRROR**: PURE_GEO_FUNCTION (`geo.py`) — 동일 공식, km 대신 m 단위
- **IMPORTS**: `import type { LatLng } from "./kakao"` — 기존 타입 재사용, 새 타입 정의 없음
- **GOTCHA**: 프로젝트에 자동 테스트 러너가 없어(YAGNI에 따라 이번 Phase에서 새로 설치하지 않음) 브라우저 콘솔에서 수동으로 한 번 검산할 것(위도 0.001도 차이 ≈ 111m)
- **VALIDATE**: `npm run build`(TypeScript 컴파일 확인) — 브라우저 콘솔에서 `haversineMeters({lat:37.5,lng:127},{lat:37.501,lng:127})`가 약 111을 반환하는지 수동 확인

### Task 2: 내비게이션 상태 + `watchPosition` 로직 추가
- **ACTION**: `frontend/src/app/page.tsx`에 실시간 안내 모드 추가
- **IMPLEMENT**:
  ```tsx
  import { haversineMeters } from "@/lib/geo";
  // ...

  const REROUTE_DISTANCE_M = 50;
  const REROUTE_MIN_INTERVAL_MS = 5000;
  const ARRIVAL_RADIUS_M = 30;

  export default function Dashboard() {
    // ...기존 상태 아래에 추가...
    const [navigating, setNavigating] = useState(false);
    const destinationRef = useRef<LatLng | null>(null);
    const watchIdRef = useRef<number | null>(null);
    const lastRouteFetchRef = useRef<{ origin: LatLng; at: number } | null>(null);
    const isRefetchingRef = useRef(false);

    function stopNavigation() {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
      setNavigating(false);
    }

    async function handlePositionUpdate(pos: GeolocationPosition) {
      const here: LatLng = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      setMyLocation(here);
      const destination = destinationRef.current;
      if (!destination) return;

      if (haversineMeters(here, destination) <= ARRIVAL_RADIUS_M) {
        stopNavigation();
        return;
      }

      const last = lastRouteFetchRef.current;
      const movedEnough = !last || haversineMeters(here, last.origin) >= REROUTE_DISTANCE_M;
      const enoughTimePassed = !last || Date.now() - last.at >= REROUTE_MIN_INTERVAL_MS;
      if (!movedEnough || !enoughTimePassed || isRefetchingRef.current) return;

      isRefetchingRef.current = true;
      try {
        const result = await routeSafety(here.lat, here.lng, destination.lat, destination.lng);
        setRoute(result);
        lastRouteFetchRef.current = { origin: here, at: Date.now() };
      } catch (err) {
        console.warn("[live-route] recompute failed:", err instanceof Error ? err.message : err);
        // 재계산 실패는 배너로 방해하지 않는다 — 기존 경로를 유지하고 다음 위치 갱신에서 재시도.
      } finally {
        isRefetchingRef.current = false;
      }
    }

    function startNavigation() {
      if (!route || !navigator.geolocation) return;
      const end = route.route_points[route.route_points.length - 1];
      destinationRef.current = { lat: end.lat, lng: end.lng };
      lastRouteFetchRef.current = myLocation ? { origin: myLocation, at: Date.now() } : null;
      setNavigating(true);
      watchIdRef.current = navigator.geolocation.watchPosition(
        handlePositionUpdate,
        (err) => {
          console.warn("[geolocation] watch failed:", err.message);
          setError("실시간 위치를 가져오지 못했어요. 위치 권한을 확인해주세요");
          stopNavigation();
        },
        { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
      );
    }

    useEffect(() => {
      return () => {
        if (watchIdRef.current !== null) navigator.geolocation.clearWatch(watchIdRef.current);
      };
    }, []);

    // ...JSX의 경로 결과 카드 안, routeModeHint 다음, resultSummary 앞에 삽입...
    {route && (
      <div className={styles.navToggleRow}>
        {navigating ? (
          <>
            <span className={styles.liveBadge}>
              <span className={styles.liveDot} /> 실시간 안내 중
            </span>
            <button type="button" className={styles.navStopButton} onClick={stopNavigation}>
              중지
            </button>
          </>
        ) : (
          <button type="button" className={styles.navStartButton} onClick={startNavigation}>
            실시간 안내 시작
          </button>
        )}
      </div>
    )}
  }
  ```
- **MIRROR**: EXISTING_REQUEST_STATE_PATTERN, EFFECT_CLEANUP_PATTERN, GEOLOCATION_ERROR_PATTERN
- **IMPORTS**: `import { haversineMeters } from "@/lib/geo";` (`LatLng`는 이미 `@/lib/kakao`에서 임포트되어 있음)
- **GOTCHA**:
  - `route`가 바뀌면(새로 경로를 검색하면) 이전 `navigating` 세션은 자동으로 멈추지 않는다 — 사용자가 새 경로를 조회하면서 동시에 실시간 안내 중이면 목적지가 옛날 값(`destinationRef`)으로 남는 버그가 될 수 있다. `handleRouteSearch`(202-217) 끝에 `stopNavigation()`을 호출해 새 검색 시 기존 내비게이션을 정리한다(추가 1줄).
  - 재계산 실패(네트워크 오류 등)를 배너로 띄우면 실시간 안내 중 화면이 계속 깜빡여 방해된다 — 콘솔 경고만 남기고 조용히 다음 위치 갱신을 기다린다(Plan Notes 참고).
  - `isRefetchingRef`로 겹치는 요청을 막지 않으면 느린 응답 중 GPS가 또 갱신될 때 중복 요청이 쌓일 수 있다.
- **VALIDATE**: `npm run build`(타입 오류 0건) — Manual Validation 섹션의 브라우저 시나리오로 실제 동작 확인

### Task 3: 토글 버튼/배지 스타일 추가
- **ACTION**: `frontend/src/app/page.module.css`에 클래스 추가
- **IMPLEMENT**:
  ```css
  .navToggleRow {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin: -2px 0 10px;
  }

  .navStartButton {
    height: 34px;
    padding: 0 14px;
    border: none;
    border-radius: var(--radius-sm);
    background: var(--brand);
    color: #fff;
    font-size: 12.5px;
    font-weight: 700;
    cursor: pointer;
  }

  .navStartButton:hover {
    background: var(--brand-dark);
  }

  .navStopButton {
    height: 34px;
    padding: 0 14px;
    border: 1px solid var(--warning);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--warning);
    font-size: 12.5px;
    font-weight: 700;
    cursor: pointer;
  }

  .liveBadge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--brand-dark);
  }

  .liveDot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--safe);
    box-shadow: 0 0 0 3px rgba(46, 125, 50, 0.2);
  }
  ```
- **MIRROR**: `.primaryButton`(569-583), `.resultSummary`(585-599) — 동일 토큰(`--brand`, `--brand-dark`, `--warning`, `--safe`, `--radius-sm`; `globals.css:6-23`에 정의됨 확인됨) 재사용, 동일 사이징 관례
- **IMPORTS**: 없음(CSS 모듈)
- **GOTCHA**: 없음 — 기존에 정의된 CSS 변수만 사용(신규 토큰 추가 없음)
- **VALIDATE**: `npm run build` 성공 + Manual Validation에서 육안 확인

---

## Testing Strategy

### Unit Tests
이 프로젝트엔 프론트엔드 테스트 러너가 없다(NOT Building 참고). `haversineMeters`는 백엔드에서 이미 검증된 공식을 그대로 포팅한 것이라 Task 1의 VALIDATE(수동 콘솔 검산)로 대체한다.

### Edge Cases Checklist
- [x] `navigator.geolocation`이 없는 브라우저 — `startNavigation`이 조기 반환(`!navigator.geolocation`)
- [x] 목적지 도착(30m 이내) — `stopNavigation()` 자동 호출
- [x] 재계산 API 실패 — 조용히 무시하고 기존 경로 유지, 다음 위치 갱신에서 재시도
- [x] 짧은 시간 안에 큰 거리 점프(GPS 노이즈) — `REROUTE_MIN_INTERVAL_MS` 5초 디바운스로 완화
- [x] 새 경로 검색 중 기존 내비게이션이 켜져 있던 경우 — `handleRouteSearch`에 `stopNavigation()` 추가로 정리
- [ ] 동시 접속/다중 탭 — 해당 없음(클라이언트 로컬 상태)
- [ ] 권한 거부 — `watchPosition` 에러 콜백에서 배너 표시 + 자동 중지로 커버(엣지케이스 목록에 포함됨, 별도 항목 아님)

---

## Validation Commands

### Static Analysis
```bash
cd frontend && npm run build
```
EXPECT: TypeScript 컴파일 및 Next.js 프로덕션 빌드 성공(0 오류) — Phase 시작 전 `/build-fix` 세션에서 이미 baseline이 초록불임을 확인함

### Unit Tests
N/A — 프론트엔드 테스트 러너 없음(Testing Strategy 참고)

### Full Test Suite
```bash
cd backend && python -m pytest -v
```
EXPECT: 기존 14개 전부 통과, 회귀 없음(이 Phase는 백엔드를 건드리지 않으므로 통과가 자명해야 함 — 그래도 확인)

### Manual Validation
- [ ] `cd frontend && npm run dev`로 개발 서버 기동, 로그인 후 대시보드 진입
- [ ] 출발지/도착지 입력해 "안전도 조회" — 경로가 지도에 표시되는지 확인
- [ ] "실시간 안내 시작" 클릭 — "● 실시간 안내 중" 배지가 뜨는지 확인
- [ ] Chrome DevTools → Sensors 탭에서 위치를 수동으로 50m 이상 옮겨보고, 경로가 실제로 재계산되어 지도가 갱신되는지 확인(네트워크 탭에서 `/safety/route` 재호출 확인)
- [ ] 위치를 목적지 30m 이내로 옮겨서 "실시간 안내 중" 배지가 자동으로 사라지는지 확인
- [ ] "중지" 버튼으로 수동 종료가 되는지 확인
- [ ] 실시간 안내 중 새로운 출발지/도착지로 다시 검색했을 때 이전 안내가 정리되는지 확인

---

## Acceptance Criteria
- [ ] All tasks completed
- [ ] All validation commands pass
- [ ] Tests written and passing — N/A(테스트 러너 없음, Testing Strategy에 명시)
- [ ] No type errors (`npm run build` 통과)
- [ ] No lint errors (`npm run lint` — 이 리포는 특별한 커스텀 규칙 없이 `eslint-config-next` 기본값 사용)
- [ ] Matches UX design

## Completion Checklist
- [ ] Code follows discovered patterns
- [ ] Error handling matches codebase style(배너 vs 콘솔 경고 구분 유지)
- [ ] Logging follows codebase conventions(`console.warn("[영역] 메시지:", ...)` 형식)
- [ ] Tests follow test patterns — N/A
- [ ] No hardcoded values(임계값은 모듈 최상위 상수로 명시)
- [ ] Documentation updated — PRD phase 상태 업데이트(Notes 참고)
- [ ] No unnecessary scope additions
- [ ] Self-contained — no questions needed during implementation

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 프론트엔드에 자동 테스트가 전혀 없어 이 로직의 회귀를 기계적으로 잡을 수 없음 | H | M | 이번 Phase는 수동 검증으로 진행. 발표 전 vitest+jsdom 도입을 후속 과제로 남김(테스트 하네스 신설은 별도 작업 단위) |
| GPS 정확도가 낮은 실내/건물 밀집 지역에서 위치가 튀어 불필요한 재계산이 반복될 수 있음 | M | L | `REROUTE_MIN_INTERVAL_MS`(5초) 디바운스로 1차 완화. 체감상 여전히 심하면 이동 평균/저역통과 필터 추가를 후속 과제로 |
| 모바일 브라우저에서 탭이 백그라운드로 가면 `watchPosition` 콜백 빈도가 OS에 의해 크게 줄거나 멈출 수 있음(NOT Building에 이미 명시된 제약) | M | L | 알려진 제약으로 문서화, 이번 Phase 범위 밖 |

## Notes
- 구현 완료 후 `.claude/PRPs/prds/realtime-safe-navigation.prd.md`의 Phase 2 행을 `status: complete`로 갱신하고 `PRP Plan` 컬럼에 `.claude/PRPs/plans/completed/live-reroute-polling.plan.md`를 채울 것.
- 이 Phase는 백엔드를 전혀 수정하지 않는다 — Phase 1이 `at` 생략 시 서버 현재 시각을 기본값으로 쓰도록 만들어둔 덕분에, 재계산 호출이 자동으로 최신 시간대(day/night) 가중치를 반영한다.
- Phase 3(점 단위 안전 데이터 조사)·Phase 5(지도 시각화)는 이 Phase와 독립적으로 진행 가능.
