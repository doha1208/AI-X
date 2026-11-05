# 시설 접근성 평가 확장 Implementation Plan

> **For agentic workers:** 승인 후 `superpowers:executing-plans`로 아래 작업을 순서대로 구현한다. 사용자 또는 적용 지침의 별도 명시 없이는 병렬 에이전트 구현을 시작하지 않는다. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 새 시설 접근성 계산을 집 리포트·주변 보행환경·실시간 안내·동네 시설 비교에 일관되게 적용한다.

**Architecture:** 시설 판정과 거리 가중 계산을 공통화하고 경로·반경·행정동의 공간 집계는 분리한다. 새 보행 색인·요일별 지역 집계는 기존 빌더가 생성하고 API는 스냅샷 하나를 조회한다. 지역 통계 점수는 별도 지표로 보존한다.

**Tech Stack:** FastAPI/Pydantic, Python/NumPy/SciPy/Shapely/NetworkX, 기존 산출물 빌더, Next.js/React/TypeScript, pytest/Vitest.

**Spec:** [시설 접근성 평가 확장 설계](facility-assessment-expansion-design-2026-11-04.md). 이 계획의 제안 수치는 해당 설계와 함께 검토한다.

## Global Constraints

- 경기도, KST 야간22:00~06:00, 표본20m, CCTV60m·보안등40m·영업 확인 상점50m·비상벨200m 유지.
- 종합 동일 비중, 단일 지표 참고, 부분 범위, 미상을 구분한다. 실제 작동·영업·유인 운영을 추정하지 않는다.
- 기존 경로5점·우회 제한은 유지하며 동네 순위·알림에는 재사용하지 않는다.
- HTTP 요청에서 전체 그래프 로드·다운로드·599개 동 재계산을 하지 않는다.
- 코드 수정 전 `DEVELOPMENT.md`와 해당 도메인 스킬을 읽고, 기능별 문서도 같은 단계에 갱신한다.
- README와 Claude 전용 파일은 변경하지 않는다. Git 변경은 해당 실행 시점의 사용자 명시 요청이 있을 때만 한다.
- 설계 문서 작성과 제품 구현을 구분한다. 각 단계의 현재 완료 여부는 아래 체크박스로 추적한다.

## Review Focus

1. 지도·리포트가 같은 경로를 가리키는데 구 점수 필드 또는 다른 대안의 점수를 보여주는 경우 → Task1.
2. 수동 야간이2000년 토요일이 되거나 KST 자정에 영업 요일이 바뀌는 경우 → Task2.
3. 양방향 도로 중복·범위 밖 끝점·경계 틈·빈 보행망이 잘못된 고득점으로 이어지는 경우 → Task3·4.
4. 상점 미확인·고득점 비상벨·이전 위치 응답 때문에 조명 안내가 빠지거나 잘못 경고하는 경우 → Task5.
5. 서로 다른 지표·요일·모델의 점수를 비교·순위·환경 변화 알림으로 섞는 경우 → Task6.

## Task 1: 집 리포트 밤 귀갓길의 새 평가 연결

**Files:** Modify `frontend/src/app/report/page.tsx`; Create `frontend/src/app/report/page.test.tsx`; Reuse `RouteEnvironmentSummary.tsx`, `routeGuidance.ts`.

**Interfaces:** Consumes existing `RouteResult.alternatives[0].environment_assessment` or `RouteResult.environment_assessment`; produces correct report rendering without a backend contract change.

- [x] 종합82·단일 비상벨68·부분20~80·미상 응답에서 옳은 표시와 상세가 나오는 실패 테스트를 작성한다. `safety_score=null`이어도 새 점수를 표시해야 한다.
- [x] `npm run test -- --run src/app/report/page.test.tsx`로 기존 표시 실패를 확인한다.
- [x] 첫 대안 평가와 같은 대안의 거리를 표시하고 공통 요약·상세를 재사용한다. 비교 거리 제목과 안내 문구를 설계1단계에 맞춘다.
- [x] 같은 테스트와 기존 경로/안내 테스트를 실행해 통과시킨다. 모바일 카드의 상세는 접힌 상태를 유지한다.
- [x] `DEVELOPMENT.md`에 리포트 연결을 갱신한다. 독립 검토 단위: `fix(report): 밤 귀갓길의 시설 평가 표시 연결`.

검증 기록(2026-11-04): 신규10개 중8개 RED→GREEN, 관련5개 파일33개 통과, 프런트 전체27개 파일123개 통과, ESLint·webpack 빌드 통과. 실제 권광로109번길12 리포트에서 수원시청역→집 시설22점·620m·일반 비교560m와390px 모바일의 접힌 상세를 확인했다. 커밋은 실행하지 않았다. Task2는 질문창 승인 대기이다.

## Task 2: 공통 평가 모듈과 KST 시각 계약

**Files:** Create `backend/app/services/facility_assessment.py`, `backend/tests/test_facility_assessment.py`; Modify `route_environment.py`, `route_environment_evidence.py`, 관련 테스트; Modify `frontend/src/lib/preferences.ts`, `frontend/src/lib/preferences.test.ts`.

**Interfaces:**
- `AssessmentSample(sample_id: str, point: tuple[float,float], weight: float)`.
- `observe_facilities(points, *, at, policy, indexes) -> list[FacilityObservation]`는 시설별 상태만 판정한다. 단일 좌표는 `LocalFacilityEvidence`로 반환하며 거리 집계와 스칼라 점수를 만들지 않는다.
- `assess_facility_samples(samples, *, scope, at, policy, indexes, common_factors) -> FacilityAssessment`.
- `FacilityAssessment`는 설계4.1의 거리 가중 필드를 소유한다. scope는route/area/zone이다.
- 기존 `evaluate_route_environment(...) -> EnvironmentAssessment` 및 경로 HTTP 필드는 유지한다.
- `routeTimeFor(mode, now?: Date)`는 KST 현재 날짜의 대표12시/23시 또는 auto의undefined를 반환한다.

- [x] 총100m에서 지표별80m·40m 접근이면 종합60점, 단일이면80점이라는 테스트를 작성한다. 자료 미상과 알려진0 및 부분 범위를 추가한다.
- [x] 같은 데이터로 추출 전 경로의 score·reference·bounds·공백·후보 순서가 보존되는 고정 fixture를 둔다. `pytest tests/test_facility_assessment.py tests/test_route_environment.py tests/test_route_environment_rank.py -q`로 확인한다.
- [x] `2026-11-03T15:10:00Z`가 KST11월4일인 사례와 수요일 시간표를 테스트한다. 대표 시각이2000-01-01이 아니어야 한다.
- [x] 공통 계산을 분리하고 경로 어댑터를 연결한다. 기존 함수 전체를 지점/면적 평가에 복사하지 않는다.
- [x] 관련 pytest와 `npm run test -- --run src/lib/preferences.test.ts src/lib/routeGuidance.test.ts`를 통과시킨다.
- [x] 독립 검토 단위: `refactor(scoring): 시설 접근성 판정 공통화 및 KST 평가 시각 정리`.

검증 기록(2026-11-04): 신규 공통 평가 테스트18개와 기존 경로/시간대 포함47개 통과, 프런트 관련29개 통과. 전체 백엔드323개·프런트124개 및 ESLint·webpack 빌드 통과. 기존6개 fixture의 전체 경로 응답·선택 결과가 정확히 일치했다. 백엔드 재시작 후 사용자 화성→수원 경로와6개 시12건의 점수·범위·공백·후보 수가 이전 실제 응답과 일치했다. 기존 schema3 산출물을 재사용했으며 커밋은 실행하지 않았다. Task3는질문창 승인 대기이다.

## Task 3: 공간 표본·행정동 자료와 schema4 산출물

**Files:** Create `backend/app/services/walk_environment_samples.py`, `backend/tests/test_walk_environment_samples.py`; Modify `backend/app/services/route_artifact.py`, `safe_route.py`, `route_artifact_validation.py`, `route_environment_inputs.py`, `scoring_profile_store.py`, `backend/scripts/build_route_artifacts.py`, `artifact_builder_worker.py` 및 대응 테스트; Modify `backend/scripts/build_gyeonggi_boundaries.py`의 원본/코드 재사용 경로가 필요한 부분.

**Interfaces:**
- `WalkEnvironmentIndex`: physical segment ID·형상·길이·공간 색인·보행망 버전.
- `load_walk_source_for_sampling(xml_path, *, cache_path)`는 모든 연결 성분을 보존하는 순차 XML 로더로 물리 색인을 반환한다. 기존 `_load_local_graph`와 축소된 `environment_graph`의 캐시를 재사용하지 않는다. 실측에서16.32GB를 사용한 NetworkX retain_all=True 로딩은 중단하고 노드/way 두 번 읽기로 대체했다.
- `sample_area_walks(index, *, lat, lng, radius_m, step_m) -> list[AssessmentSample]`.
- `sample_zone_walks(index, *, boundary, step_m) -> list[AssessmentSample]`.
- `RouteArtifact.schema_version=4`, `walk_environment_index`, `zone_facility_summaries`, `boundary_version`, `sampling_version` 추가. 런타임은3·4의 경로 계약을 허용한다.
- `safe_route.build_route_artifact(...,target_schema=4)`와 `scripts.build_route_artifacts.build_and_publish_route_artifact(...,target_schema)`가 작업 기록의target을 실제 산출물까지 전달한다. target3은 신규 색인 없이 기존 계약으로 생성한다.
- 지역 집계 키 `(dong_code, weekday, period)`와 비교 basis 메타데이터를 저장한다. 준비 상태는 경로/주변/지역별로 구분한다.

- [x] 역방향 중복100m→100m, 평행한 다른 형상은 각각 유지, 두 끝점이 범위 밖인 통과 선분은 포함, 분리된 도로를 연결하지 않음, 빈 도로는 미상이라는 공간 테스트를 먼저 작성한다.
- [x] 경계 절단·동 코드599개 대조·매칭 실패 목록·도 경계 주변 시설 반경을 테스트한다. 지도용 경계 틈을 자료 미상으로 전파하지 않는다.
- [x] schema3는 기존 경로만 사용 가능, schema4는 추가 기능 사용 가능, 잘못된4는 current를 바꾸지 않음, 요청 중 교체로 버전이 섞이지 않음을 테스트한다.
- [x] 색인·표본 생성과 요일별 낮/밤 지역 배치를 구현한다. fingerprint에 공통 계산·표본·경계·시각 정책 버전을 포함한다. schema3 고정 비교가 있는 load/reload/snapshot/validation/bootstrap/queue를3·4 호환으로 바꾸고 신규 큐의 target_schema를4로 한다. 기존 target3 대기 작업은 변경 없이 취소하지 않고 구 형식 빌드를 끝낸 뒤4 필요 여부를 다시 검사한다.
- [x] `pytest tests/test_walk_environment_samples.py tests/test_route_artifact.py tests/test_route_artifact_builder.py tests/test_route_artifact_validation.py tests/test_route_environment_runtime.py tests/test_build_route_artifacts_script.py -q`를 통과시킨다.
- [x] 대표 자료로 빌더1회 검증, warm300m p95≤1초·1000m≤2초 제안 목표와 peak memory를 측정해 기록한다. 별도 원본 재다운로드는 필요할 때만 한다.
- [x] 독립 검토 단위: `feat(artifacts): 주변·지역 시설 평가용 보행 색인과 집계 게시`.

중간 검증 기록(2026-11-04): 관련46개·전체 백엔드339개 통과(기존 경고8개). 실제 도로 색인537,086개·원본 경계599/599개 연결을 확인했다. 수원 대표 지점의 warm10회 p95는300m0.112초(381표본),1000m1.520초(4,613표본)이며 동별 빌더 동시 실행 상태에서 측정했다. 실제 schema4 생성·게시와 서버 전환 확인은 진행 중이다.

재개 검증 기록(2026-11-05): 이전 API·빌더 종료로 schema4는 미게시 상태였다. 전수 집계에서 확인한 전체 경계 거리 순회 병목을 원본 선분 STRtree의 정확한 최근접 거리 조회로 대체했다. 구멍/분리 영역·경계 허용오차·구 캐시 호환 테스트4개 RED→GREEN, 기존 고정 응답6개를 포함한 관련48개·전체343개 통과(기존 경고8개). 실제 수원 표본의 모든 지표 판정·점수는 기존과 일치했고, 개선 후 warm10회 p95는300m0.044초·1000m0.572초였다. 기존 물리 보행망 캐시를 재사용해 자동 빌더를 다시 시작했으며 게시 검증은 진행 중이다.

추가 병목 검증(2026-11-05): 동194에서 반복 확인된 전체 도로 버퍼 합치기를 동일 해상도의 개별 도로 버퍼 포함 검사로 대체했다. 기존 합집합 판정 비교4개 및 합치기 방지 회귀 테스트 RED→GREEN, 관련13개·최종 전체 백엔드348개 통과(기존 경고8개). 새 스냅샷은 이 구현의 지문으로 다시 생성한다.

Task3 최종 완료(2026-11-05): 자동 빌더 작업8이 schema4 `20261104T232522610231Z-default-v3`를 게시했고 API도 동일 버전을 로드했다. 물리 선분537,086개·599개 동·8,386개 요일/주야간 슬롯을 확인했으며 경계 누락·오류와 산출 실패 사유는0개다. 종합6,048개·단일616개·부분 범위1,722개를 구분하고 부분 범위를 종합 점수로 승격하지 않는다. 보행/경로 평가/주변/지역 준비 상태는 모두true이다.

최종 검증은 전체 백엔드348개, 사용자 화성→수원 경로+6개 시 주야간 총13건의 기존 점수·범위·거리·후보 일치 및 `git diff --check` 통과다. 최종 주변 성능은 원본 선분 절단·표본 생성·낮/밤 두 평가·현재 위치 근거까지 포함한 warm10회 p95:300m0.045초,1000m0.670초였다. 대표 수원 지점의 측정값이며 API 전체 지역의 보장은 아니다. 빌더 최대 메모리5.26GB, 게시 파일587,047,361bytes를 기록했다. 새 산출물 첫 로드를 포함한 사용자 요청16.63초, 같은 경로의 이후 요청0.298초,6개 시12건은0.016~0.074초였다. 서버26280·자동 빌더35344가 실행 중이며 커밋은 하지 않았다. Task4는 질문창 승인 대기다.

## Task 4: 주변·현재 위치 API와 집 주변 리포트 전환

**Files:** Create `backend/app/services/area_environment_service.py`, `backend/tests/test_area_environment_service.py`; Modify `spot_report.py`, `api/safety.py`, `schemas/safety.py`, `test_spot_report.py`; Modify `frontend/src/lib/api.ts`, `frontend/src/app/report/page.tsx` 및 테스트.

**Interfaces:**
- `assess_area_environment(*, snapshot, lat, lng, radius_m, at) -> AreaEnvironmentReport`는 대표 주간·야간 평가와 요청 at 기준의LocalFacilityEvidence를 생성한다.
- `GET /safety/spot?lat=&lng=&radius_m=&at=`에 `area_environment`, `local_environment`, `facility_observations`, `artifact_version`, `status`, `unavailable_reason` 추가.
- `spotReport(lat,lng,{at,...requestOptions}) -> Promise<SpotReport>`로 시각을 전달한다. 기존 `zone`은 보존한다.
- `nearest_havens` 결과에는 출처·자료 버전·영업/유인/작동 확인 상태를 포함하고, 인덱스 캐시는 자료 버전으로 교체한다.

- [x] 집 주변의 새로운 시설 점수가 옛 `edge_local_scores`를 호출하지 않는 테스트와 schema3/빈 보행망/알려진0/부분 자료 테스트를 작성한다.
- [x] 구 스칼라 필드는deprecated·null, 새 자료와 관측 수는 동일 snapshot, 상점 미확인은24시로 표시하지 않는 계약 테스트를 작성한다. 구 화면 호환 필드는 즉시 삭제하지 않는다.
- [x] 새 서비스와 API·타입을 연결하고, 리포트의 낮·밤 카드와 시설 수를 새 필드로 전환한다. 오류·대기·미상을 분리한다.
- [x] `pytest tests/test_area_environment_service.py tests/test_spot_report.py tests/test_safety.py -q`와 `npm run test -- --run src/app/report/page.test.tsx`를 통과시킨다.
- [x] 독립 검토 단위: `feat(report): 집 주변 보행 시설 접근성 평가 전환`.

Task4 완료(2026-11-05): 백엔드 관련36개·전체352개, 프런트 전체126개·최종 관련15개, ESLint·Next.js webpack 빌드 통과. 실제 수원 좌표300m·1km API는 기존 schema4 한 버전으로 평가·관측·비상벨/편의점 거점을 응답했다. UTC 요청을 KST 다음 날짜의12시·23시로 처리했고 구 점수3개는 null이다. 300m 평가 보행로 약6.57km, 낮42점·밤47점, CCTV9·보안등77·비상벨2·상점120개 관측을 확인했다. 390px 모바일 브라우저에서 실제 주변 API와 연결해 점수·시설 수·영업/유인 미확인·기본 접힘과 대표 시각을 검증했다(브라우저 인증과 외부 역 검색은 격리). 다른 검사 종료 후 같은 주소 warm HTTP 요청5회 중앙값300m0.177초,1km1.846초였다. 로컬 서버를 실행했고 운영 배포·커밋은 하지 않았다. Task5는 질문창 승인 대기다.

## Task 5: 실시간 시설 공백 안내

**Files:** Create `frontend/src/lib/facility_alerts.ts`, `frontend/src/lib/facility_alerts.test.ts`; Modify `useSafeHaven.ts`, `havens.ts`, `guideHandoff.ts`, `routeGuidance.ts`, `navigate/page.tsx`, 안내 컴포넌트와 대응 테스트; 필요 시 현재 폴리라인 평가용 backend service/API를 추가한다.

**Interfaces:**
- `FacilityAlertPolicy` 초기 제안: lookahead200m / trigger100m / clear60m / start proximity20m / cooldown180초.
- `deriveFacilityAlert({period,progressM,routeEvidence,localEnvironment,policy,previousState,nowMs}) -> {nextState,alert,announce}`는 순수 함수이다. `previousState`는 활성 공백ID·마지막 음성 시각을 보존한다. `alert`는없으면null이다.
- 전방 routeEvidence는 공통 평가 엔진으로 실제 선택 폴리라인을 평가한 진행 거리별 `{start_m,end_m,state}` 구간이다. 신규 `POST /safety/route-environment`는 기존과 같은 서비스 범위·요청 제한을 적용하고 폴리라인·선택적 현재 위치·시각을 받아 경로 형상을 변경하지 않는 최신 평가를 반환한다. 입력점 상한5000·총 길이 상한20km는 제안 정책으로 명시해 테스트한다.
- 응답은 `assessment`, `route_evidence`, `local_environment`, `havens`, `artifact_version`, `evaluated_at`, `valid_until`, `temporal_key`이다. route와point는 한 snapshot과시각을 사용한다. 실제 안내는 현재 KST로 평가하며 수동12시·23시 미리보기와 구별한다.
- `useSafeHaven(position,active,{routePoints,routeId}) -> LiveFacilityReport|null`로 확장하고 신규 API 응답을 사용한다. handoff와 `GuideOption`에 artifact/version/time 기준을 보존한다. 전방 근거 없음·버전 불일치·유효기간 만료 시 재평가한다. 최소15초 요청 제한 중 만료되면 자동 알림을 억제한다.

- [x] 높은 비상벨 점수+확인된 조명 공백, 조명 부재+상점 미상, 전체 미상, 인접 영업 시설, 주간 조건의 기대 안내를 테스트한다.
- [x] 99.9/100m 발동·59.9m 해제/60m 유지·180초 반복·공백 시작 거리·전방 창 이동에도 같은 공백ID 유지·이탈/재탐색 억제·요일 변경·늦게 도착한 응답·산출물 교체를 테스트한다. 정지 중 폐점/개점·자정 넘는 영업·22시/06시·기간 만료·스냅샷은 같고 영업 상태만 바뀐 경우를 포함한다.
- [x] 공백 순수 함수와 안내 상태를 구현하고 `here_score<40`·`LOW_SPOT_SCORE`를 소비 코드에서 제거한다. 자동 안내에서 미확인을 위험으로 승격하지 않는다.
- [x] 폴리라인 평가 API의 입력 검증·점 제한·서비스 범위·스냅샷 일치·평가 실패 시 기존 경로 보존을 pytest와 브라우저로 확인한다. 위치 요청40m·15초 제한을 유지한다.
- [x] `npm run test -- --run src/lib/facility_alerts.test.ts src/lib/havens.test.ts src/lib/guideHandoff.test.ts src/lib/routeGuidance.test.ts` 및 실제 안내 컴포넌트 테스트를 통과시킨다.
- [x] 독립 검토 단위: `feat(navigation): 확인된 시설 공백 기반 알림과 거점 안내 적용`.

Task5 완료(2026-11-05): 백엔드 전체366개(기존 경고8개), 프런트 전체141개·최종 관련30개, ESLint·webpack 빌드, diff 검사 통과. 실제 화성→수원 102점·3,889.62m 경로의 주·야간 평가에서 경로 재탐색 없이 동일 산출물의 위치·경로 구간을 확인했다. 390px 모바일 브라우저에서 높은 참고 점수95와 비상벨 인접이 있어도 보안등 공백만 안내하고, 같은 공백을 걸을 때 음성이 한 번이며 이탈 후 사라지는 것을 GPS·야간 응답 모의로 검증했다. 전체 검사에서 드러난 경찰 파일 캐시 문제는 동일 파일 크기·수정 시각에서도 내용이 달라지면 재색인하는 회귀 테스트로 고쳤다. 로컬 API·프런트엔드는 실행 중이고 Task6은 질문창 승인 대기다.

## Task 6: 거주지 시설 비교·지도·관심 동네

**Files:** Create `backend/app/services/zone_environment_service.py`, `backend/tests/test_zone_environment_service.py`; Modify `api/safety.py`, `schemas/safety.py`; Modify `frontend/src/lib/api.ts`, `watchedZones.ts`, `app/page.tsx`, `app/compare/page.tsx`, `components/SafetyMap.tsx`; Create/extend 각각의 `.test.ts(x)`.

**Interfaces:**
- `list_facility_zones(*,snapshot,period,weekday,basis_id=None) -> FacilityZoneResponse`는 현재 요일의 대표 시각 배치 결과만 읽는다.
- `GET /safety/facility-zones`와 동 상세의 `facility_environment.day/night`를 설계6단계대로 추가한다. 비교 의미의basis_id와 데이터 세대의result_group_id를 구분하고, 저장된 비교 기준이 유효하지 않으면409와선택 가능한집합을 반환한다.
- `DisplayMetric = regional_statistics | facility_access`; 지도에는 원본 `safety_score`를 덮어쓰지 않는 표시 metric·nullable value를 전달한다.
- 관심 동네 schema2에 metric·period·basis/model/policy/artifact/schedule 식별자를 보존한다. 구 저장값은 regional_statistics로 해석한다.

- [x] 다른 지표의80점과70점을 직접 순위로 섞지 않는 테스트, 가장 큰 비교 집합 선택, 동률 공동 순위, 요일 변경, 단일·부분·미상 표시를 작성한다.
- [x] 동일 두 동의 비교에서 공통 지표 재집계, 공통 지표 하나/없음, 경계 매칭 실패를 테스트한다.
- [x] API·지역 서비스와 홈의 평가 기준 전환을 구현한다. 전체 동 목록은 보존하고 비교 가능한 집합에만 순위를 붙인다.
- [x] 지도 색·툴팁·카드가 같은 기준을 사용하는지, 관심 동네 구 저장값·버전 변경이 환경 변화 경고를 만들지 않는지 테스트한다.
- [x] `pytest tests/test_zone_environment_service.py tests/test_safety.py tests/test_safety_score.py -q`; 프런트 홈·비교·지도·관심 동네 테스트를 통과시킨다.
- [x] 독립 검토 단위: `feat(residence): 지역 통계와 분리된 보행 시설 비교 제공`.

Task6 완료(2026-11-05): 백엔드 관련60개·전체372개, 프런트 전체152개, ESLint·webpack 빌드·diff 검사 통과. 동일 schema4의 실제 응답에서 낮·밤 각각599개 동을 유지했다. 낮 기본 집합398개·비교 집합1개, 밤 기본 집합249개·비교 집합4개이며 표시 점수 공동 순위를 확인했다. 서로 다른 야간 비교 집합의 실제 두 동은 공통 비상벨·CCTV만 재집계했고, 이전 기준은409와 선택지로 응답했다. 실제 API와 지도 SDK 모의 브라우저에서 카드·중립색·툴팁 동기화, 이전 툴팁 닫힘, 기준 재선택 및390px 비교 화면을 확인했다. 관심 동네 구 형식은 지역 통계로 읽고 저장 당시 시간대를 모르면 첫 조회에서만 기준값을 설정한다. Task7은 질문창 승인 대기다.

## Task 7: 설명·관리자 범위·구 계약 제거와 전체 검증

**Files:** Modify `frontend/src/app/data/page.tsx`, `me/page.tsx`, `admin/scoring/page.tsx`, 설명 테스트; Modify `backend/app/services/spot_report.py`, `schemas/safety.py`, frontend API 타입, `scripts/production-smoke.mjs`, `DEVELOPMENT.md`.

**Interfaces:** 지역 통계·시설 접근성·알림 정책의 이름/버전/기준 시각을 각 API와 화면에 동일하게 표시한다. 삭제 대상은 전환이 끝난 구 spot 점수 계산과 production 소비 경로이다. deprecated·null 필드는 구 화면 탭의 호환을 위해 유지한다.

- [x] 구 가점/감점 설명·미확인24시 단정·새 시설 지수를 제어하는 것처럼 보이는 통계 가중치 제목이 남지 않는 화면 테스트를 작성한다.
- [x] 지역 통계 프로필·시설 정책·알림 정책을 구분하고 정확한 자료 기준일/범위를 표시한다. 공원·유흥 등 원자료를 근거 없이 삭제하지 않고 새 지수 사용 여부를 설명한다.
- [x] 모든 구 spot 필드 소비자가 사라진 것을 검색으로 확인한 후 계산·함수 연결을 제거한다. 구 모델로 암묵 폴백하는 경로가 없어야 한다. API 호환용null 필드에는 구 점수 계산이 연결되지 않음을 테스트한다.
- [x] 전체 `pytest -q`, `npm run test -- --run`, `npm run lint`, `npm run build -- --webpack` 통과를 확인한다.
- [x] 사용자 제공 경로+6개 시의 낮/밤,300m/1000m, 자료 교체, 모바일 카드·음성 중복을 실제 API·브라우저로 확인하고 수치·근거·지연을 기록한다.
- [x] 운영 스모크의 경로 없음/보행 가능/시설 평가 가능 계약과 로컬 새 산출물 준비 상태를 검증한다. 운영 배포 후의 HTTPS 시험 계정 스모크는 배포 인계 항목으로 남긴다(이번 요청에서 운영 배포하지 않음).
- [x] 독립 검토 단위: `docs(ui): 시설 평가 설명 동기화 및 이전 점수 계약 정리`.

Task7 완료(2026-11-05): 백엔드377개·프런트157개·ESLint·webpack 빌드·스모크 계약4개·diff 검사 통과. 독립 전체 검토에서 확인한 짧은 절단 보행로의 근사 버퍼/정확한 거리 불일치와 실제 안내 시각 누락을 RED→GREEN으로 수정했다. 자동 빌더 작업9는673.652초 후새 schema4 `20261105T064133564191Z-default-v3`를 게시했고 API도 동일 버전으로 전환했다. 물리 선분537,086개·동599개·집계8,386개, 경계 오류/누락0개다. 사용자 경로+6개 시 주야간13건 기존 평가/대안 일치, 사용자 별도 야간 및 실시간 주야간, 주변24건, 동별/지도/409/390px 안내·음성 억제까지 확인했다. 보류 지적은 없고 Git 변경·운영 배포는 하지 않았다. 상세 판단·검증 한계는 [최종 검증 기록](facility-assessment-expansion-verification-2026-11-05.md)에 보존한다.

추가 커밋 요청(2026-11-05): 위 기록은 구현 검증 완료 시점이다. 이후 사용자 요청과 Git 금지 규칙의 명시적 예외 승인에 따라 Task1→7 순서의 커밋으로 정리했다. 공통 파일은 커밋별로 분리해 검사했고 설계·계획·최종 검증 문서를 포함했다. 푸시·운영 배포는 수행하지 않았다.

## 순서와 중단 지점

Task1은 기존 API만 사용하므로 가장 먼저 독립 적용할 수 있다. Task2→3은 공통 기반이며, Task4→5→6은 API와 자료 계약 의존성 때문에 순서대로 구현한다. Task4/5는구 알림 스칼라 제거와 새 알림 소비자 전환이 연결되므로 같은 배포 단위다. 설명은 각 단계에서 갱신하고 Task7에서 전체 일관성을 확인한다.

각 단계는 실패 테스트 확인→구현→해당 검증→문서 갱신→변경 검토 순서로 끝낸다. 커밋은 사용자 요청이 있는 경우 위 검토 단위대로 분리한다. 한 단계가 실패하면 그 단계의 소비 기능 확장을 중단하고 이전 정상 경로·산출물은 보존한다.
