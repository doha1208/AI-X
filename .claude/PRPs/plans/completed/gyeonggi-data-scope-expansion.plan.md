# Plan: 경기도 데이터 수집 범위 확장 (조사 + 코드 준비)

## Summary
PRD Phase 1(조사)을 실행하며 핵심 리스크였던 "보안등 기관코드를 어떻게 구하나"가 실제로는 불필요하다는 걸 실측으로 확인했다 — `tn_pubr_public_scrty_lmp_api`가 `instt_code` 없이도 전국 데이터를 페이지네이션으로 반환한다(실측 `totalCount: 1857668`). 이 발견 덕분에 이 계획은 기관코드 목록을 구하는 대신, 수집 스크립트 3곳(CCTV 필터/범죄 컬럼/보안등 API 호출 방식)과 격자 빌더의 지역 범위를 서울+경기도로 넓히는 순수 코드 작업이 된다. PRD Phase 2(CCTV/범죄 확장)도 같은 파일을 건드리는 코드 작업이라 이 계획에 함께 포함한다.

## User Story
As a 개발자(테스트 목적), I want 데이터 수집 스크립트가 경기도 좌표까지 처리하길, so that 재지오코딩/재적재 배치(다음 단계)를 돌렸을 때 실제로 경기도 안전구역 데이터가 채워진다.

## Problem → Solution
[CCTV/범죄 필터가 서울만 인정, 보안등은 서울 25개 구 기관코드만 순회, 격자 빌더도 서울 bbox+서울특별시 필터만 인정] → [CCTV/범죄는 경기도도 인정, 보안등은 기관코드 없이 전국을 페이지네이션하며 격자 bbox가 자동으로 범위를 거름, 격자 빌더 bbox+지역필터가 경기도까지 확장]

## Metadata
- **Complexity**: Small
- **Source PRD**: `.claude/PRPs/prds/gyeonggi-do-expansion.prd.md`
- **PRD Phase**: Phase 1(경기도 기관코드/범위 조사) — 조사 결과가 코드 변경으로 직결되어 Phase 2(CCTV/범죄 데이터 확장)까지 함께 완료
- **Estimated Files**: 2 (둘 다 UPDATE, 신규 파일 없음)

---

## UX Design

N/A — 내부 데이터 수집 스크립트 변경, 사용자가 보는 UI 변화 없음. (이 계획 이후 PRD Phase 3~5에서 실제 데이터가 채워지면 그때 비로소 경기도 조회가 가능해진다.)

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `backend/scripts/ingest_public_data.py` | 37, 81-92, 95-113, 116-152 | 이번에 고칠 정확한 함수들 — `SEOUL_GU_INSTT_CODES`, `load_crime_by_gu`, `count_cctv_by_dong`, `fetch_security_lights` |
| P0 | `backend/scripts/build_dong_grid.py` | 24-25, 42-58 | BBOX 상수와 `reverse_geocode`의 `region_1depth_name == "서울특별시"` 필터 — 둘 다 확장 대상 |
| P1 | `backend/scripts/ingest_public_data.py` | 60-78 | `snap_to_dong` — bbox 밖 좌표를 자동으로 None 반환한다는 것을 확인(보안등 재작성이 안전한 근거) |
| P2 | `backend/app/services/safe_route.py` | 19-20 | `LOCAL_WALK_NETWORK_BBOX` — **이번 계획에서 건드리지 않음**(NOT Building 참고), 위치만 알아두기 |

## External Documentation

**보안등 표준데이터 API(`tn_pubr_public_scrty_lmp_api`) 실측 결과** (2026-09-18, 실제 `.env`의 `SECURITY_LIGHT_API_KEY`로 호출):
```
KEY_INSIGHT: instt_code 파라미터 없이 호출해도 resultCode=00(정상)이고 전국 데이터가 페이지네이션됨(totalCount=1857668)
APPLIES_TO: fetch_security_lights() 재작성 — 기관코드 순회 루프를 통째로 제거 가능
GOTCHA: totalCount가 186만 건이라 numOfRows=1000 기준 약 1858페이지 — 이 호출 자체만으로도 수 분 소요(재지오코딩 배치와는 별개)
```

**경기도 5대 범죄 컬럼 실측** (동일 CSV, `csv.reader`로 헤더 직접 파싱):
```
KEY_INSIGHT: header[78:109](31개, 고양시~양평군)가 경기도 28시 3군 전체와 정확히 대응
APPLIES_TO: load_crime_by_gu() 컬럼 슬라이스 확장
GOTCHA: 접두어가 서울은 "서울 "(한 칸), 경기도는 "경기도 "(전체 명칭)로 달라 문자열 치환을 두 가지 다 해줘야 함
```

**경기도 대략적 위경도 범위** (웹 검색, 근사치):
```
KEY_INSIGHT: 위도 약 36.9~38.3N(평택~연천), 경도 약 126.3~127.9E — 정확한 행정경계가 아니라 여유를 둔 사각형
APPLIES_TO: build_dong_grid.py의 BBOX 상수
GOTCHA: 이 bbox는 격자/역지오코딩용 "여유 있는 사각형"일 뿐 — OSM 도로망 재추출(PRD Phase 5)은 이 계획에 포함되지 않으므로 LOCAL_WALK_NETWORK_BBOX와는 아직 안 맞아도 된다(고의적 불일치, 아래 GOTCHA 참고)
```

---

## Patterns to Mirror

### DICT_COMPREHENSION_MERGE
// SOURCE: backend/scripts/ingest_public_data.py:81-92 (수정 전 원본)
```python
def load_crime_by_gu() -> dict:
    with CRIME_CSV.open(encoding="cp949", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    seoul_gu_cols = header[2:27]
    totals = [0] * 25
    for row in rows:
        if row[1] in FIVE_MAJOR_CRIME_SUBCATS:
            for i in range(25):
                totals[i] += int(row[2 + i])
    return {gu.replace("서울 ", ""): total for gu, total in zip(seoul_gu_cols, totals)}
```
같은 CSV 파싱 스타일(cp949, `csv.reader`, 헤더 슬라이스)을 유지하되 컬럼 범위를 두 구간으로 확장한다.

### PAGINATED_API_LOOP
// SOURCE: backend/scripts/ingest_public_data.py:116-152 (수정 전 원본, `fetch_security_lights` 내부 while 루프)
```python
while True:
    params = {..., "pageNo": str(page), "numOfRows": "1000", "type": "json", "instt_code": instt_code}
    url = "..." + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as resp:
        body = json.loads(resp.read())
    payload = body.get("body") or {}
    items = (payload.get("items") or {}).get("item")
    if not items:
        break
    ...
    total_count = payload.get("totalCount", 0)
    if page * 1000 >= total_count:
        break
    page += 1
    time.sleep(0.1)
```
페이지네이션 루프 자체는 그대로 재사용 — 바깥의 `for instt_code in SEOUL_GU_INSTT_CODES:` 루프만 제거하고 이 while 루프를 한 번만 돈다.

### BBOX_FILTER
// SOURCE: backend/scripts/ingest_public_data.py:60-63 (`snap_to_dong`, 변경 없음)
```python
def snap_to_dong(lat: float, lng: float, step: float, cells: dict, bbox) -> dict | None:
    west, south, east, north = bbox
    if not (west - step <= lng <= east + step and south - step <= lat <= north + step):
        return None
```
이 함수가 이미 bbox 밖 좌표를 걸러주므로, CCTV/보안등 쪽에서 지역명으로 미리 걸러내는 건 성능 최적화일 뿐 정확성엔 필수가 아니다 — 이 사실이 보안등 재작성의 안전성 근거.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `backend/scripts/ingest_public_data.py` | UPDATE | CCTV 필터 확장, 범죄 컬럼 확장, 보안등 API를 전국 페이지네이션으로 재작성(기관코드 목록 삭제) |
| `backend/scripts/build_dong_grid.py` | UPDATE | BBOX를 서울+경기도로 확장, 역지오코딩 지역 필터에 "경기도" 추가 |

## NOT Building

- **OSM 도로망 재추출 / `LOCAL_WALK_NETWORK_BBOX` 갱신** — PRD Phase 5. 이 두 bbox(격자용 vs 도로망용)를 지금 동시에 안 맞추는 건 의도적 — 도로망 파일을 실제로 재추출하기 전에 `LOCAL_WALK_NETWORK_BBOX`만 넓히면, 커버 안 되는 지역 요청도 "로컬 그래프가 있다"고 착각해 엉뚱하게 처리될 수 있음(위험한 절반짜리 상태).
- **재지오코딩 배치 실행, `ingest_public_data.py` 전체 실행** — PRD Phase 3·4. 이 계획은 코드만 준비하고, 실제로 몇 시간짜리 배치를 돌리는 건 별도 단계(아래 Manual Validation 참고, 실행 자체는 이 plan의 범위 밖).
- **경기도 동 경계 GeoJSON** — PRD Phase 6(선택), 완전히 독립적인 작업.
- **보안등 API 호출 재시도(retry) 로직 추가** — 기존 코드에도 없던 것이라 이번에 새로 넣지 않음(스코프 확장 아님, YAGNI).

---

## Step-by-Step Tasks

### Task 1: CCTV 필터를 경기도까지 확장
- **ACTION**: `backend/scripts/ingest_public_data.py`의 `count_cctv_by_dong` 수정
- **IMPLEMENT**:
  ```python
  addr = row.get("소재지도로명주소") or row.get("소재지지번주소") or ""
  if not addr.startswith(("서울", "경기")):
      continue
  ```
- **MIRROR**: 기존 `if not addr.startswith("서울"):` 한 줄을 튜플 prefix 체크로만 바꿈 — 나머지 로직 무수정
- **IMPORTS**: 없음
- **GOTCHA**: CCTV 원본 CSV의 경기도 주소 prefix는 실측으로 `"경기"`로 시작함 확인됨(`"경기도"` 풀네임이 아닌 축약형도 섞여 있을 수 있어 `"경기"`만 체크 — `"경기도"`로 하면 일부 행이 누락될 위험)
- **VALIDATE**: `python -c "from scripts.ingest_public_data import count_cctv_by_dong; print('import ok')"` (backend 디렉터리에서 실행)

### Task 2: 범죄 통계 컬럼을 경기도까지 확장
- **ACTION**: `load_crime_by_gu` 재작성
- **IMPLEMENT**:
  ```python
  def load_crime_by_gu() -> dict:
      """구/시/군 이름 -> 5대 범죄 합계. 서울 25개 구(컬럼 2:27) +
      경기도 31개 시/군(컬럼 78:109, 실측 확인)을 합쳐서 반환한다."""
      with CRIME_CSV.open(encoding="cp949", newline="") as f:
          reader = csv.reader(f)
          header = next(reader)
          rows = list(reader)

      col_indices = list(range(2, 27)) + list(range(78, 109))
      region_cols = [header[i] for i in col_indices]
      totals = [0] * len(col_indices)
      for row in rows:
          if row[1] in FIVE_MAJOR_CRIME_SUBCATS:
              for i, col_idx in enumerate(col_indices):
                  totals[i] += int(row[col_idx])

      result: dict[str, int] = {}
      for name, total in zip(region_cols, totals):
          result[name.replace("서울 ", "").replace("경기도 ", "")] = total
      return result
  ```
- **MIRROR**: DICT_COMPREHENSION_MERGE — 같은 파싱 스타일, 컬럼 인덱스만 두 구간으로 확장
- **IMPORTS**: 없음
- **GOTCHA**: 접두어가 서울은 `"서울 "`(한 칸 공백), 경기도는 `"경기도 "`(전체 명칭 + 공백)로 다름 — 하나만 `.replace()`하면 다른 쪽 접두어가 그대로 남아 나중에 동 이름 매칭이 깨짐. 반드시 둘 다 replace할 것(위 코드에 이미 반영)
- **VALIDATE**: `python -c "from scripts.ingest_public_data import load_crime_by_gu; d = load_crime_by_gu(); print(len(d), '고양시' in d, '강남구' in d)"` → `56 True True` 나와야 함(25+31=56개 지역)

### Task 3: 보안등 수집을 전국 페이지네이션으로 재작성
- **ACTION**: `fetch_security_lights` 재작성, `SEOUL_GU_INSTT_CODES` 상수 삭제
- **IMPLEMENT**:
  ```python
  def fetch_security_lights(step: float, cells: dict, bbox) -> dict:
      """보안등 표준데이터 API는 instt_code 없이도 전국 데이터를 페이지네이션으로
      받을 수 있다(실측 확인, totalCount~186만 건). 기관코드를 미리 조사해둘
      필요 없이 snap_to_dong의 bbox 체크가 서울+경기 밖 지점은 자동으로 걸러준다.

      ponytail: 전국 페이지를 순서대로 다 훑는 단순한 방식 — 기관코드/지역별로
      쪼개 병렬 호출하면 더 빠르겠지만, 이 스크립트는 가끔 한 번 돌리는 배치라
      단순함이 낫다.
      """
      key = load_env_value("SECURITY_LIGHT_API_KEY")
      counts: dict[str, int] = {}
      page = 1
      while True:
          params = {
              "serviceKey": key,
              "pageNo": str(page),
              "numOfRows": "1000",
              "type": "json",
          }
          url = "https://api.data.go.kr/openapi/tn_pubr_public_scrty_lmp_api?" + urllib.parse.urlencode(params)
          with urllib.request.urlopen(url, timeout=20) as resp:
              body = json.loads(resp.read())
          payload = body.get("body") or {}
          items = (payload.get("items") or {}).get("item")
          if not items:
              break
          if isinstance(items, dict):
              items = [items]
          for item in items:
              try:
                  lat = float(item["latitude"])
                  lng = float(item["longitude"])
              except (KeyError, ValueError, TypeError):
                  continue
              cell = snap_to_dong(lat, lng, step, cells, bbox)
              if cell:
                  counts[cell["dong_code"]] = counts.get(cell["dong_code"], 0) + 1
          total_count = payload.get("totalCount", 0)
          if page * 1000 >= total_count:
              break
          page += 1
          time.sleep(0.1)
      return counts
  ```
  그리고 파일 상단의 `SEOUL_GU_INSTT_CODES = [str(3000000 + i * 10000) for i in range(25)]` 줄을 삭제(더 이상 참조하는 곳이 없음).
- **MIRROR**: PAGINATED_API_LOOP — while 루프 내부는 그대로, 바깥 `for instt_code in ...` 루프만 제거
- **IMPORTS**: 없음(기존 `urllib.parse`, `urllib.request`, `json`, `time` 그대로 사용)
- **GOTCHA**: 전국 186만 건을 1000건씩 페이지네이션하면 약 1858번 호출 — `time.sleep(0.1)`까지 합치면 이 함수 하나만 최소 3~9분 걸림(네트워크 상태에 따라 변동). 재지오코딩 배치(수 시간)와는 별개의 시간이니 전체 `ingest()` 실행 시간 추정에 합산해야 함
- **VALIDATE**: `grep -n "SEOUL_GU_INSTT_CODES" scripts/ingest_public_data.py`가 빈 결과여야 함(참조 완전 제거 확인). 실제 API 호출 검증은 Manual Validation 참고(비용/시간이 드는 실호출이라 자동 실행 안 함)

### Task 4: 격자 빌더 범위를 경기도까지 확장
- **ACTION**: `backend/scripts/build_dong_grid.py`의 `BBOX`와 `reverse_geocode` 지역 필터 수정
- **IMPLEMENT**:
  ```python
  BBOX = (126.30, 36.85, 127.90, 38.30)  # west, south, east, north — 서울+경기도 전역(근사치)
  # ponytail: extract_seoul_walk_network.py의 BBOX와는 아직 다름(고의적) —
  # PRD Phase 5에서 도로망을 재추출하기 전까진 두 bbox를 맞추지 않는다.
  ```
  그리고 `reverse_geocode` 안의 필터:
  ```python
  if doc.get("region_type") == "H" and doc.get("region_1depth_name") in ("서울특별시", "경기도"):
  ```
- **MIRROR**: 기존 상수/조건문 스타일 그대로, 값만 확장
- **IMPORTS**: 없음
- **GOTCHA**: 이 파일 24행의 기존 주석 `# west, south, east, north (extract_seoul_walk_network.py와 동일)`는 확장 후 더 이상 사실이 아니므로 반드시 함께 고칠 것(위 IMPLEMENT에 이미 새 주석 반영) — 안 고치면 다음 사람이 "두 bbox가 같아야 하는데 왜 다르지"라고 혼란스러워함
- **VALIDATE**: `python -c "from scripts.build_dong_grid import BBOX; print(BBOX)"` → `(126.3, 36.85, 127.9, 38.3)` 출력 확인

---

## Testing Strategy

### Unit Tests
`backend/scripts/`는 현재 pytest 대상이 아니다(기존에도 `scripts/` 전용 테스트 없음 — 실제 외부 API/파일에 의존하는 배치 스크립트라 이 프로젝트의 기존 관례상 포맷). 이번에도 새 테스트 하네스를 만들지 않고, 각 Task의 VALIDATE(순수 로직은 직접 호출해 결과 확인, 외부 호출은 스킵)로 대체한다.

### Edge Cases Checklist
- [x] 서울/경기 접두어가 둘 다 있을 때 올바르게 분리되는지 — Task 2 VALIDATE로 확인(56개 지역, 서울/경기 둘 다 존재)
- [x] `SEOUL_GU_INSTT_CODES` 참조가 완전히 제거됐는지 — Task 3 VALIDATE
- [x] bbox 밖 좌표가 여전히 걸러지는지 — `snap_to_dong`은 무수정이라 기존 동작 그대로 유지됨(회귀 없음)
- [ ] 실제 보안등 API 페이지네이션 186만 건 완주 — 비용/시간이 커서 이 계획에서 실행 안 함(Manual Validation 참고)
- [ ] 재지오코딩 배치 실제 실행 — PRD Phase 3 범위, 이 계획 밖

---

## Validation Commands

### Static Analysis
```bash
cd backend && python -m compileall -q scripts
```
EXPECT: 출력 없음(구문 오류 없음)

### Unit Tests
```bash
cd backend && python -c "from scripts.ingest_public_data import load_crime_by_gu; d = load_crime_by_gu(); assert len(d) == 56; assert '고양시' in d and '강남구' in d; print('OK')"
```
EXPECT: `OK` 출력

### Full Test Suite
```bash
cd backend && python -m pytest -q
```
EXPECT: 기존 15개 전부 통과(이 계획은 `app/` 쪽을 건드리지 않으므로 회귀 없음이 자명해야 함 — 그래도 확인)

### Manual Validation
- [ ] `grep -n "SEOUL_GU_INSTT_CODES" backend/scripts/ingest_public_data.py` — 빈 결과 확인(완전 삭제)
- [ ] (선택, 비용 발생) 실제 `fetch_security_lights()`를 격자 없이 소규모로 호출해 `resultCode: 00`과 실제 위경도 값이 오는지 확인 — 전체 배치는 PRD Phase 4에서
- [ ] PRD Phase 3(재지오코딩 배치) 실행 전, 새 BBOX 기준 격자점 개수부터 계산: `(1.60/0.005) * (1.45/0.005) ≈ 92,800개`, `REQUEST_DELAY_SEC=0.15s` 기준 **약 3.9시간** 예상 — 실행 여부/타이밍은 사용자 승인 필요(장시간 배치이자 Kakao API 호출량이 커서 이 계획에서 자동 실행하지 않음)

---

## Acceptance Criteria
- [ ] All tasks completed
- [ ] All validation commands pass
- [ ] Tests written and passing — 기존 15개 회귀 없음 확인(신규 테스트는 Testing Strategy 사유로 생략)
- [ ] No type errors (compileall 통과)
- [ ] No lint errors (해당 없음 — 린터 미설정, Phase 1 계획과 동일 판단)
- [ ] Matches UX design — N/A(내부 변경)

## Completion Checklist
- [ ] Code follows discovered patterns
- [ ] Error handling matches codebase style(기존과 동일 — 명시적 에러 핸들링 없이 실패 시 예외 전파, 배치 스크립트 관례 유지)
- [ ] Logging follows codebase conventions — 해당 없음(이 스크립트들은 print/예외 기반, 기존 관례 유지)
- [ ] No hardcoded values(BBOX는 상수로 명시, 매직넘버 없음)
- [ ] Documentation updated — PRD phase 상태 업데이트(Notes 참고)
- [ ] No unnecessary scope additions — OSM 재추출/실제 배치 실행은 의도적으로 이 계획 밖
- [ ] Self-contained — no questions needed during implementation

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 경기도 bbox(126.30~127.90, 36.85~38.30)가 근사치라 실제 행정구역과 살짝 어긋날 수 있음 | M | L | `snap_to_dong`이 bbox 밖은 자동으로 걸러주므로 너무 좁지만 않으면 안전 — 실제 재지오코딩 결과에서 경기도 시/군이 다 나오는지로 사후 검증 가능 |
| 보안등 API 186만 건 페이지네이션 중간에 네트워크 오류로 끊길 수 있음(재시도 로직 없음, 기존과 동일) | M | M | 기존에도 없던 리스크라 이번에 새로 만드는 건 아님 — 실행 전 재시도 로직 추가를 원하면 별도 작업으로 분리 |
| CCTV 주소 `"경기"` prefix 필터가 "경기도"가 아닌 다른 시작 문자열(예: 도로명 변경 등)을 놓칠 가능성 | L | L | 실측으로 14개 서로 다른 "경기" 시작 prefix를 확인했으므로 현재 데이터 기준으로는 충분 |

## Notes
- 구현 완료 후 `.claude/PRPs/prds/gyeonggi-do-expansion.prd.md`의 Phase 1과 Phase 2 행을 모두 `status: complete`로 갱신할 것(이 계획이 둘 다 커버함), `PRP Plan` 컬럼에 `.claude/PRPs/plans/completed/gyeonggi-data-scope-expansion.plan.md`를 채울 것.
- 다음 PRD Phase(3: 역지오코딩 배치 재실행)는 이 계획이 완료된 뒤, 사용자가 실제로 몇 시간짜리 배치 실행을 승인했을 때 진행한다 — 별도 계획으로 다룰 것을 권장(실행 자체가 크고 되돌리기 번거로운 작업이라).
