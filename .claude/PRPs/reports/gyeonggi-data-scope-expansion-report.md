# Implementation Report: 경기도 데이터 수집 범위 확장 (조사 + 코드 준비)

## Summary
데이터 수집 스크립트 3곳(CCTV 필터, 범죄 컬럼, 보안등 API 호출)과 격자 빌더의 지역 범위를 서울에서 경기도까지 확장했다. 핵심 발견은 보안등 API가 `instt_code` 없이도 전국 데이터를 페이지네이션으로 반환한다는 것(실측 확인) — 원래 PRD가 걱정했던 "경기도 기관코드 조사"라는 리스크 자체가 사라져 `SEOUL_GU_INSTT_CODES` 상수를 완전히 삭제했다.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Small | Small — 예상대로 |
| Confidence | 9/10 | 계획과 정확히 일치, 편차 없음 |
| Files Changed | 2 | 2 |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | CCTV 필터를 경기도까지 확장 | 완료 | |
| 2 | 범죄 통계 컬럼을 경기도까지 확장 | 완료 | 56개 지역(서울 25 + 경기 31) 확인 |
| 3 | 보안등 수집을 전국 페이지네이션으로 재작성 | 완료 | `SEOUL_GU_INSTT_CODES` 완전 삭제 |
| 4 | 격자 빌더 범위를 경기도까지 확장 | 완료 | BBOX + region 필터 |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | Pass | `python -m compileall -q scripts` — 오류 없음 |
| Unit Tests | Pass | `load_crime_by_gu()` 직접 호출 → 56개 지역, 고양시/강남구 모두 포함 확인 |
| Full Test Suite | Pass | `python -m pytest -q` — 기존 15/15 전부 통과, 회귀 없음(이 계획은 `app/`을 건드리지 않음) |
| Edge Cases | Pass | `SEOUL_GU_INSTT_CODES` 참조 완전 제거(grep 확인), BBOX 값 확인 |

## Files Changed

| File | Action | Lines |
|---|---|---|
| `backend/scripts/ingest_public_data.py` | UPDATED | +26 / -13 |
| `backend/scripts/build_dong_grid.py` | UPDATED | +3 / -1 |

## Deviations from Plan

None — 계획과 정확히 일치하게 구현됨.

## Issues Encountered

None — 계획대로 순조롭게 진행됨. 계획 수립 단계에서 이미 보안등 API를 실측 테스트해뒀던 덕분에 구현 자체는 매끄러웠다.

## Tests Written

계획에 명시된 대로 `backend/scripts/`는 기존에도 pytest 대상이 아니었고(외부 API/파일 의존 배치 스크립트), 이번에도 새 테스트 하네스를 만들지 않았다. `load_crime_by_gu()`를 직접 호출해 결과를 검증하는 수동 검증으로 대체(계획의 Testing Strategy에 명시된 대로).

## Next Steps
- [ ] Code review via `/code-review`
- [ ] PRD Phase 3(재지오코딩 배치, 약 3.9시간 예상) 진행 여부 확인 — 장시간 배치라 사용자 승인 필요
- [ ] Create PR via `/prp-pr`
