# 경기도 전역 커버리지 확장

## Problem Statement

안심 귀갓길 서비스는 현재 안전구역 데이터(CCTV/보안등/범죄)와 보행자 도로망이 전부 서울 시계(37.42~37.70N, 126.76~127.18E)로 하드코딩돼 있다. 서울 밖 좌표로 조회하면 안전 가중 경로 탐색 자체가 동작하지 않고 Tmap 순수 최단경로로 조용히 강등되며, 더 나쁘게는 서울 경계에 있는 엉뚱한 동의 안전점수가 마치 정답인 것처럼 표시될 수 있다. 개발자 본인이 테스트하려는 지역조차 서울 밖이라 실제 사용 시나리오로 검증이 안 되는 상태다.

## Evidence

- 개발자 본인이 있는 지역이 서울 밖이라 직접 테스트가 안 됨(이번 대화에서 확인된 동기).
- 코드 조사로 CCTV 원본 CSV(전국CCTV표준데이터)에 경기도 주소 prefix가 이미 14종 존재, 범죄 통계 CSV(경찰청 발생지역별 통계)에 경기도 컬럼이 이미 31개 존재 — 원본 데이터는 전국 단위이고 서울만 필터링해서 버리고 있었다는 것을 직접 확인.
- 보행자 도로망 원본(`south-korea-latest.osm.pbf`, 287MB, 전국)이 이미 로컬에 있음 — 재다운로드 불필요.

## Proposed Solution

서울만 필터링하던 지점들(CCTV 주소 필터, 범죄 컬럼 슬라이스, 보안등 기관코드 목록, 역지오코딩 지역 필터+bbox, OSM 추출 bbox)을 경기도까지 포함하도록 확장한다. 보안등 기관코드는 `code.go.kr`(행정표준코드관리시스템) 또는 공공데이터포털 "경기도_행정기관 코드"(15127365) 데이터셋에서 확보한다.

## Key Hypothesis

우리는 안전구역 데이터와 도로망을 경기도까지 확장하면 개발자 본인 지역을 포함한 실사용 시나리오로 서비스를 검증할 수 있을 것이라 믿는다.
우리는 경기도 내 임의 주소로 조회했을 때 서울과 동일한 품질(`mode: safety_weighted`, 실제 그 지역 안전구역 기반 점수)로 응답하면 맞다는 것을 알게 될 것이다.

## What We're NOT Building

- 경기도 외 다른 광역시/도(인천, 강원 등) — 이번 스코프는 경기도까지만.
- 프론트엔드 동 경계 폴리곤(GeoJSON) 신규 제작 — 경기도용 폴리곤 데이터가 없으면 기존 원(circle) 폴백으로 표시(이미 구현된 폴백 경로, 추가 작업 불필요). 있으면 좋지만 이번 스코프의 필수 조건은 아님.
- 서버 인프라 스케일업(더 큰 인스턴스로 이전 등) — 지금 개발 머신에서 감당 가능한 수준으로 진행, 실제 배포 환경 최적화는 범위 밖.

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|---------------|
| 경기도 좌표 안전 가중 경로 성공률 | 서울과 동일하게 `mode: safety_weighted`로 응답 | 개발자 본인 지역 좌표로 `/safety/route` 호출해 mode 확인 |
| 경기도 안전구역 데이터 존재 | DB에 경기도 시/군/구 동 단위 안전점수 레코드 존재 | `SafetyZone` 테이블에서 경기도 위경도 범위 레코드 카운트 확인 |
| 응답 속도 회귀 없음 | 캐시 적중 시 서울과 마찬가지로 1초 내외 | 그래프 확대 후 `/safety/route` 반복 호출 타이밍 재측정 |

## Open Questions

- [x] ~~보안등 API 경기도 기관코드의 정확한 목록/개수~~ — 실측 결과 불필요한 것으로 확인. `instt_code` 없이 전국 페이지네이션 가능(`totalCount: 1857668`), 기관코드 자체가 필요 없어짐(계획 파일 참고)
- [ ] 확대된 도로망 그래프의 실제 메모리 사용량(RAM) — 개발 머신에서 감당 가능한지 실측 필요
- [ ] 재지오코딩 배치(격자점 역지오코딩)가 실제로 몇 시간 걸리는지 — 경기도 면적 기준 격자점 개수부터 계산 필요

## Recommended Next Step

기술 스파이크: (1) 경기도 행정기관 코드 데이터셋 다운로드해 보안등 API 호출 가능 여부 확인, (2) 확장된 bbox로 격자점 개수를 계산해 재지오코딩 소요 시간 추정, (3) 확장된 OSM 추출을 시험 삼아 한 번 돌려 그래프 크기/로딩 시간/메모리 실측.

---

## Users & Context

**Primary User**
- **Who**: 이번 스코프에서는 개발자 본인(테스트 목적) — 이후 실사용자는 기존 PRD와 동일(낯선 동네를 이동하는 사람), 다만 서울이 아닌 경기도 거주/방문자까지 확장
- **Current behavior**: 서울 밖에서는 앱을 켜도 최단경로만 나오거나 엉뚱한 안전점수를 봄
- **Trigger**: 개발자가 자기 동네에서 직접 테스트해보고 싶을 때
- **Success state**: 경기도 어디서든 서울과 동일한 품질의 안전 가중 경로/거주지 추천을 받음

**Job to Be Done**
When 서울이 아닌 경기도 지역에서 서비스를 테스트/사용할 때, I want to 서울과 동일한 안전 가중 경로 추천을 받고 싶다, so I can 실제 내 동네에서 이 서비스가 제대로 작동하는지 확인할 수 있다.

**Non-Users**
경기도 외 다른 지역(인천, 강원 등) 사용자는 이번 스코프 대상이 아님.

---

## Solution Detail

### Core Capabilities (MoSCoW)

| Priority | Capability | Rationale |
|----------|------------|-----------|
| Must | CCTV 데이터 경기도까지 필터 확장 | 원본에 이미 있음, 필터 한 줄 수정으로 해결되는 가장 쉬운 항목 |
| Must | 범죄 통계 경기도 컬럼 파싱 확장 | 원본에 이미 있음, 컬럼 매핑만 추가 |
| Must | 보안등 API 경기도 기관코드 추가 | 공공데이터포털/code.go.kr에서 조회 가능한 것으로 확인됨 |
| Must | 좌표→행정동 역지오코딩 범위 확장(필터+bbox) | 안전구역 데이터를 동 단위로 만드는 데 필수 |
| Must | 보행자 도로망 OSM 추출 bbox 확장 | 이미 있는 전국 PBF에서 재추출만 하면 됨 |
| Should | 확장된 그래프에 대한 성능 재검증 | 이미 만든 KD-tree/period 캐싱이 커진 그래프에도 잘 버티는지 확인 |
| Could | 경기도 동 경계 GeoJSON(지도 폴리곤 시각화) | 없어도 원 폴백으로 동작, 있으면 시각적으로 더 좋음 |
| Won't | 경기도 외 지역, 인프라 스케일업 | Not Building 참고 |

### MVP Scope

CCTV/범죄/보안등 데이터 확장 + 역지오코딩 범위 확장 + OSM 재추출. 이 넷이 있어야 경기도 좌표로 서울과 동일한 품질의 응답이 나온다.

### User Flow

기존 PRD(`realtime-safe-navigation.prd.md`)의 User Flow와 동일 — 다만 입력 좌표 범위가 서울 시계 밖(경기도)이어도 같은 품질로 동작해야 한다는 점만 다르다.

---

## Technical Approach

**Feasibility**: MEDIUM — 코드 변경 자체는 필터/bbox 확장 위주라 작지만, 오프라인 데이터 준비 단계(재지오코딩 배치, 기관코드 확보, OSM 재추출)가 시간이 걸리고 실측 전까지는 정확한 소요 시간을 모른다.

**Architecture Notes**
- `backend/scripts/ingest_public_data.py:37` `SEOUL_GU_INSTT_CODES` — 경기도 시/군 기관코드 목록을 추가로 정의해야 함(값은 아직 미확보, Open Questions 참고)
- `backend/scripts/ingest_public_data.py:82-92` `load_crime_by_gu` — `header[2:27]`(서울 25개 컬럼)만 읽는 슬라이스를 경기도 31개 컬럼까지 포함하도록 확장
- `backend/scripts/ingest_public_data.py:95-115` `count_cctv_by_dong` — `addr.startswith("서울")` 필터에 `"경기"` 추가
- `backend/scripts/build_dong_grid.py:24-25,49-50` `BBOX`, `region_1depth_name == "서울특별시"` — bbox 확장 + `"경기도"` 허용 추가. 격자점이 늘어나는 만큼 Kakao API 호출 횟수(`REQUEST_DELAY_SEC=0.15`)도 비례해서 늘어 배치 시간이 길어짐
- `backend/scripts/extract_seoul_walk_network.py`(및 `app/services/safe_route.py`의 `LOCAL_WALK_NETWORK_BBOX`) — 같은 확장된 bbox로 재추출 필요. 이미 있는 `south-korea-latest.osm.pbf`에서 추출하므로 재다운로드는 불필요
- `frontend/public/data/seoul-dong-boundaries.geojson` — 경기도용 폴리곤 없으면 `SafetyMap.tsx`가 이미 원(circle)으로 폴백하므로 당장 안 막힘(Could 항목)

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| 확장된 그래프(노드/간선 5~10배) 로딩에 필요한 RAM이 개발 머신 한계를 넘을 수 있음 | M | 재추출 직후 먼저 로딩 테스트로 메모리/시간 실측, 필요시 경기도를 서울 인접 시부터 단계적으로 확장하는 것으로 축소 |
| 재지오코딩 배치가 예상보다 훨씬 오래 걸릴 수 있음(면적 5배 이상, API 호출 간격 고정) | M | 먼저 격자점 개수를 계산해 예상 소요 시간을 확인한 뒤 실행(Recommended Next Step 1) |
| 보안등 기관코드가 서울처럼 깔끔한 규칙(3000000+i*10000)이 아닐 수 있음 | M | code.go.kr 기관코드 조회 페이지 또는 "경기도_행정기관 코드" 데이터셋을 직접 받아 정확한 코드 리스트 확보 |
| OneDrive 실시간 동기화가 큰 파일(재추출된 OSM XML 등) 처리 속도를 더 떨어뜨릴 수 있음(이전 세션에서 관찰된 패턴) | L | 작업 중에는 OneDrive 동기화 일시정지를 고려, 또는 시간 여유를 두고 진행 |

---

## Implementation Phases

<!--
  STATUS: pending | in-progress | complete
  PARALLEL: phases that can run concurrently (e.g., "with 3" or "-")
  DEPENDS: phases that must complete first (e.g., "1, 2" or "-")
  PRP: link to generated plan file once created
-->

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 1 | 경기도 기관코드/범위 조사 | 보안등 기관코드 확보, 격자점 개수 계산, bbox 확정 | complete | - | - | `.claude/PRPs/plans/completed/gyeonggi-data-scope-expansion.plan.md` |
| 2 | CCTV/범죄 데이터 확장 | 필터·컬럼 슬라이스를 경기도까지 확장 | complete | with 1 | - | `.claude/PRPs/plans/completed/gyeonggi-data-scope-expansion.plan.md` |
| 3 | 역지오코딩 배치 재실행 | 확장된 bbox로 `build_dong_grid.py` 재실행(수 시간) | complete | - | 1 | - |
| 4 | 보안등 데이터 수집 + DB 재적재 | 전국 페이지네이션(기관코드 불필요)으로 수집, `ingest_public_data.py` 전체 재실행 | complete | - | 1, 2, 3 | - |
| 5 | OSM 도로망 재추출 + 성능 재검증 | 확장 bbox로 재추출, 로딩/응답 속도 실측 | complete | - | 1 | - |
| 6 | 경기도 동 경계 GeoJSON(선택) | 지도 폴리곤 시각화용 데이터 확보 | pending | with 2-5 | - | - |

### Phase Details

**Phase 1: 경기도 기관코드/범위 조사**
- **Goal**: 이후 단계가 막히지 않도록 필요한 외부 정보를 전부 확보
- **Scope**: code.go.kr/data.go.kr에서 경기도 시/군 기관코드 확보, 확장 bbox 확정, 격자점 개수 계산
- **Success signal**: 보안등 API를 실제로 경기도 기관코드로 호출해봐서 정상 응답 확인

**Phase 2: CCTV/범죄 데이터 확장**
- **Goal**: 이미 갖고 있는 원본에서 경기도 데이터를 더 이상 버리지 않게 함
- **Scope**: `count_cctv_by_dong`, `load_crime_by_gu` 확장
- **Success signal**: 경기도 CCTV/범죄 카운트가 딕셔너리에 채워짐(수동 확인)

**Phase 3: 역지오코딩 배치 재실행**
- **Goal**: 경기도 좌표를 실제 행정동으로 매핑할 수 있게 함
- **Scope**: `build_dong_grid.py`의 bbox/필터 확장 후 재실행
- **Success signal**: `dong_grid.json`에 경기도 격자점들이 포함됨

**Phase 4: 보안등 데이터 수집 + DB 재적재**
- **Goal**: 경기도 안전구역 레코드를 실제로 DB에 채움
- **Scope**: `SEOUL_GU_INSTT_CODES`를 경기도까지 확장한 목록으로 교체(또는 병행), `ingest_public_data.py` 전체 재실행
- **Success signal**: `SafetyZone` 테이블에 경기도 위경도 범위 레코드 존재

**Phase 5: OSM 도로망 재추출 + 성능 재검증**
- **Goal**: 경기도 좌표에서도 `safety_weighted` 모드가 나오게 함, 응답 속도 회귀 없음을 확인
- **Scope**: 확장 bbox로 `extract_seoul_walk_network.py`(또는 이름 개정) 재실행, `LOCAL_WALK_NETWORK_BBOX` 갱신, 로딩/응답 시간 실측
- **Success signal**: 개발자 본인 지역 좌표로 조회 시 `mode: safety_weighted`, 응답 1초 내외(캐시 적중 시)

**Phase 6: 경기도 동 경계 GeoJSON(선택)**
- **Goal**: 지도에서 경기도 동도 실제 폴리곤으로 보이게 함(현재는 원 폴백)
- **Scope**: 경기도 행정동 경계 데이터 소싱 및 프론트 반영
- **Success signal**: 경기도 동이 원이 아니라 실제 경계 모양으로 표시됨

### Parallelism Notes

Phase 2(CCTV/범죄)는 순수 코드 수정이라 Phase 1(조사)과 동시에 진행 가능. Phase 6(GeoJSON)은 나머지 파이프라인과 독립적이라 아무 때나 병행 가능. Phase 3·4·5는 서로 실질적 의존관계가 있어(범위 확정 → 지오코딩 → 데이터 적재 → 도로망) 순차 진행이 자연스럽다.

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| 확장 범위 | 경기도 전체 | 서울 인접 시부터 단계적 확장 | 사용자가 전체를 원함, 원본 데이터가 이미 전국 단위라 필터만 넓히면 되는 구조라 단계적으로 할 이유가 적음(단, 성능/시간 리스크는 감수) |
| 경기도 동 경계 폴리곤 | 이번 스코프에서 필수 아님(Could) | 필수로 포함 | 원 폴백이 이미 있어 기능적으로 막히지 않음, 있으면 좋지만 없어도 서비스 가능 |

---

## Research Summary

**Market Context**
해당 없음 — 이번 확장은 신규 기능이 아니라 기존 기능의 지리적 커버리지 확대라 시장 조사 대상이 아님.

**Technical Context**
CCTV/범죄 원본 데이터는 이미 전국 단위이고 서울만 필터링해서 버리고 있었다(코드로 직접 확인). 보행자 도로망 원본(PBF)도 전국 단위로 이미 로컬에 있음. 진짜 새로 필요한 건 (1) 경기도 보안등 기관코드(code.go.kr/데이터포털에서 확보 가능함을 확인), (2) 역지오코딩 배치 재실행(시간 소요), (3) 확대된 그래프에 대한 성능 재검증뿐이다.

---

*Generated: 2026-09-18*
*Status: DRAFT - needs validation*
