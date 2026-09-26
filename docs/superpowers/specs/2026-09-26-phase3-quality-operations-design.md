# Phase 3 품질·운영성 설계

## 목표

기능 변경이 기존 안전 경로·인증·지도 동작을 손상시키지 않는지 결정적으로 검증하고, 공개 배포 환경에서 발생한 경로 폴백과 외부 연동 실패를 개인 위치나 인증 정보를 노출하지 않고 관찰한다.

## 범위와 성공 기준

Phase 3은 다음 네 가지 결과를 제공한다.

1. 백엔드 테스트는 수집 단계부터 운영 DB와 분리된 임시 SQLite DB를 사용하고, 테스트 간 DB·캐시·전역 런타임 상태가 서로 영향을 주지 않는다.
2. 자동 회귀 테스트는 API의 경로 범위 검증, 산출물/결과 캐시 갱신, 누락 데이터 중립 처리, `/api` 기본 프록시, access-token 갱신, 재경로 후 최신 비상벨 상태 반영을 검증한다.
3. 공개 도메인 스모크 테스트는 실제 Caddy `/api` 프록시를 통해 health, CSRF 로그인, 현재 사용자, 안전구역, 경로 API를 점검한다.
4. API는 경로 계산 시간, 폴백 사유, 외부 Tmap 실패, 경로 결과 캐시 hit/miss를 구조화 로그와 Prometheus 형식 메트릭으로 제공하며, 위치·주소·이메일·토큰·쿠키·요청 본문을 기록하지 않는다.

이 작업은 점수 공식, 경로 선택 알고리즘, 인증 프로토콜, 공개 API 응답 본문을 변경하지 않는다. 기존 Tmap 및 직선 폴백도 계속 동작해야 한다.

## 현 상태

- `backend/tests/conftest.py`는 테스트 수집 전에 `DATABASE_URL`을 설정하지만, 저장소 내부 `backend/tests/.test-suite.db`를 직접 삭제·생성한다.
- 테스트는 module-level `TestClient`, 서비스 전역 캐시, 전역 `route_artifact_runtime`, 전역 요청 제한기를 함께 사용한다. 병렬 또는 전체 조합 실행에서 상태가 남을 수 있다.
- 백엔드는 pytest 단위·통합 테스트가 이미 있고, Tmap 및 산출물 그래프를 monkeypatch한 패턴도 존재한다.
- 프런트는 `/api` 기본값과 요청 취소/최신 요청 보호 로직을 갖지만 자동화된 테스트 러너가 없다.
- 배포는 Caddy가 `/api/*`를 FastAPI로 프록시하고, 공개 도메인은 `ansimnavi.duckdns.org`이다. CI 워크플로는 없다.
- 현재 로그는 모듈별 텍스트 로그에 머물며, 경로 처리 결과와 캐시 효율을 집계하는 메트릭은 없다.

## 선택한 접근

### 계층형 검증

GitHub Actions를 두 워크플로로 분리한다.

- `quality.yml`은 pull request와 기본 브랜치 변경에서 실행한다. 임시 DB와 모의 외부 서비스만 사용하므로 빠르고 재현 가능하며, 배포를 수행하지 않는다.
- `production-smoke.yml`은 `workflow_dispatch`와 하루 한 번의 schedule로 실행한다. 실제 공개 도메인에 대해 외부 관점의 최소 사용자 흐름만 확인한다.

PR마다 별도 미리보기 배포와 전체 브라우저 E2E를 만드는 방식은 현재 인프라에 없는 배포·격리 체계가 필요하므로 이번 범위에서 제외한다.

### 백엔드 테스트 격리

pytest의 `tmp_path_factory`로 세션 전용 디렉터리와 SQLite 파일을 만든다. conftest가 애플리케이션 모듈보다 먼저 환경 변수를 설정하고, 세션 종료 시 engine을 dispose한 뒤 임시 경로를 pytest에 맡겨 정리한다. 저장소 경로의 DB 파일을 만들거나 삭제하지 않는다.

각 테스트는 기존 DB 테이블 초기화 fixture를 유지하되, 다음 상태도 일관되게 초기화한다.

- `app.services.tmap._route_cache`
- `route_artifact_runtime`의 산출물·결과 캐시
- `app.api.safety.route_request_gate`
- 테스트에서 변경하는 `settings` 값과 시설/그래프 캐시

테스트는 실제 OSM 파일, Tmap HTTP, 운영 DB, 배포 비밀값을 읽지 않는다. 안전 경로·Tmap·산출물 테스트는 현재처럼 작은 NetworkX 그래프와 httpx 대역을 사용한다.

### 프런트 회귀 검증

Vitest, jsdom, React Testing Library를 프런트 개발 의존성으로 추가한다. 기존 Next.js lint 및 타입 검사는 그대로 유지한다.

테스트 가능하고 화면 동작도 명확하게 하기 위해, `page.tsx` 안의 경로 주변 비상벨 비동기 상태 관리를 `frontend/src/lib/useRouteBells.ts` 훅으로 분리한다. 이 훅은 활성 경로를 입력으로 받고 자신이 만든 `AbortSignal`을 `nearbyBells`에 전달해 다음을 보장한다.

- 새 경로가 선택되면 이전 비상벨 요청을 취소한다.
- 취소되지 않은 이전 요청이 나중에 완료되어도 현재 마커 상태를 덮어쓰지 못한다.
- 최신 요청의 비상벨만 `SafetyMap`에 전달되는 상태가 된다.

프런트 테스트는 모의 `fetch`로 `NEXT_PUBLIC_API_BASE_URL` 미설정 시 `/api`가 사용되는지, access token이 401일 때 CSRF를 포함한 refresh를 한 번 시도하는지, 위 최신 요청 보장이 지켜지는지를 검증한다. 실제 Kakao SDK·브라우저 위치 권한·공개 네트워크는 테스트에 쓰지 않는다.

### 공개 배포 스모크

Node 내장 `fetch`만 사용하는 스크립트를 `scripts/` 아래에 둔다. 추가 HTTP 클라이언트 의존성은 추가하지 않는다. 스크립트는 cookie jar를 최소 구현해 다음 요청을 순서대로 수행한다.

1. `${SMOKE_BASE_URL}/api/health`가 200 및 `status: "ok"`인지 확인한다.
2. `${SMOKE_BASE_URL}/api/auth/csrf`에서 CSRF 쿠키와 본문 토큰을 받는다.
3. 전용 계정으로 `${SMOKE_BASE_URL}/api/auth/login`을 호출하고 `Secure`, `HttpOnly` access/refresh cookie를 확인한다.
4. 같은 cookie jar로 `/api/auth/me`가 해당 계정을 반환하는지 확인한다.
5. 사전 지정한 서울·경기 서비스 범위 좌표로 `/api/safety/zones`가 성공 응답을 주는지 확인한다.
6. 같은 범위 내 출발·도착점으로 `/api/safety/route`를 호출하고 `safety_weighted`, `tmap`, `straight_line` 중 하나의 모드, 경로 점수, 좌표 배열을 확인한다.

스모크는 반드시 `SMOKE_BASE_URL`의 HTTPS 도메인과 `/api` 경로만 사용한다. API 포트 8000, localhost, 컨테이너 이름을 호출하면 실패한다. 안전구역 데이터 부재 등으로 route가 의도된 422를 반환하면, 배포가 준비되지 않은 것으로 보고 워크플로를 실패시킨다.

workflow는 GitHub Environment의 다음 설정을 사용한다.

| 이름 | 유형 | 용도 |
| --- | --- | --- |
| `SMOKE_BASE_URL` | Variable | `https://ansimnavi.duckdns.org`처럼 공개 HTTPS 기본 URL |
| `SMOKE_USER_EMAIL` | Secret | 관리자 권한이 없는 전용 스모크 계정 이메일 |
| `SMOKE_USER_PASSWORD` | Secret | 전용 스모크 계정 비밀번호 |
| `SMOKE_START_LAT`, `SMOKE_START_LNG`, `SMOKE_END_LAT`, `SMOKE_END_LNG` | Variables | 현재 데이터가 보장하는 유효 경로 좌표 |

스모크 계정은 운영자가 한 번 생성하며, 관리자 이메일 목록에 넣지 않는다. 워크플로는 계정을 생성하지 않으므로 운영 DB에 계정 찌꺼기를 남기지 않는다. GitHub 로그에는 secret 값을 출력하지 않는다.

### 관측성

`backend/app/observability.py`가 애플리케이션 로그 포맷과 Prometheus collector를 한곳에서 소유한다. `configure_observability()`는 FastAPI 생성 전에 JSON 구조화 로그를 설정한다. 경로 요청 완료 시 다음의 비식별 필드만 기록한다.

- 이벤트 이름과 HTTP 결과
- 전체 경로 처리 시간(ms)
- 최종 경로 모드
- 안전 경로 산출물 부재·경로 없음·Tmap 실패처럼 정규화된 폴백 사유

Prometheus collector는 다음의 고정 이름과 label을 제공한다.

- `route_duration_seconds{outcome}` histogram. `outcome`은 `success`, `safety_zones_unavailable`만 허용한다.
- `route_requests_total{mode,fallback_reason}` counter. `mode`은 `safety_weighted`, `tmap`, `straight_line`, `failed`만 허용하고, `fallback_reason`은 `none`, `artifact_unavailable`, `safe_route_unavailable`, `tmap_unavailable`, `safety_zones_unavailable`만 허용한다.
- `tmap_failures_total{reason}` counter. `reason`은 `http_error`, `invalid_response`만 허용한다.
- `route_result_cache_total{result}` counter. `result`는 `hit`, `miss`만 허용한다.

메트릭 label은 유한한 열거값만 사용한다. 동 코드, 좌표, 주소, 사용자 ID·이메일, IP, 요청 경로의 동적 값, 예외 문자열은 label 또는 로그 필드로 사용하지 않는다. 인증 header, cookie, request body를 로깅하지 않는다.

Prometheus text endpoint는 `/metrics`로 FastAPI 내부에 제공한다. `Caddyfile`은 일반 `/api/*` handler보다 먼저 `/api/metrics`에 404를 반환한다. Docker Compose의 API 포트는 `127.0.0.1:8000:8000`으로 loopback에만 bind한다. 내부 수집기는 host loopback을 통해 `/metrics`를 scrape할 수 있고, 공개 사용자는 기존 `/api/health`만 볼 수 있다.

관측성 자체가 기존 route 응답을 바꾸지 않도록, 메트릭 기록 오류는 요청을 실패시키지 않는다. Tmap 실패는 정상 폴백으로 집계하고, 원본 HTTP 오류나 API key는 로그에 기록하지 않는다.

## 변경 경계

예상 변경 대상은 다음과 같다.

| 영역 | 책임 |
| --- | --- |
| `backend/tests/conftest.py` 및 관련 테스트 | 임시 DB·전역 상태 격리와 핵심 회귀 검증 |
| `backend/app/observability.py`, `main.py`, `api/safety.py` | 구조화 로그, metrics 등록, 경로 결과 계측 |
| `backend/app/services/tmap.py`, `safe_route.py` | 안전한 Tmap 실패·결과 캐시 계측 hook |
| `backend/requirements.txt` | Prometheus Python client |
| `frontend/package.json`, lockfile, 테스트 설정·테스트 파일 | Vitest/React 테스트 환경과 API·재경로 회귀 |
| `frontend/src/app/page.tsx` 및 분리 모듈 | 최신 경로의 비상벨 상태만 반영하는 테스트 가능한 경계 |
| `.github/workflows/`, `scripts/` | PR 품질 검증과 배포 스모크 자동화 |
| `docker-compose.yml`, `Caddyfile` | metrics 비공개 및 API loopback 노출 |
| `DEVELOPMENT.md` | 테스트·CI·스모크·관측성 운영 기준 |

`README.md`, 안전 점수 공식, OSM 수집 배치, 사용자 API 스키마는 이번 작업의 변경 대상이 아니다.

## 오류 처리와 검증

- 테스트 fixture 또는 collector 초기화 실패는 테스트를 조용히 통과시키지 않고 명확히 실패시킨다.
- PR 품질 워크플로에서 어느 하나의 backend/frontend 검증이 실패하면 워크플로를 실패시킨다.
- production smoke에서 설정 변수가 누락되거나, HTTPS·`/api` URL 제약을 지키지 않거나, cookie 속성·응답 형태가 기대와 다르면 실패한다.
- `/metrics`는 수집 실패가 사용자 경로 요청의 5xx를 만들지 않도록 best-effort로 기록한다.
- 관측성 테스트는 허용 목록에 없는 민감 문자열이 로그/metrics label에 나타나지 않음을 검증한다.

## 운영 절차

1. 운영자가 공개 HTTPS URL, 유효한 서비스 좌표, 권한 없는 스모크 계정을 준비한다.
2. GitHub Environment에 Variables와 Secrets를 저장한다.
3. PR 워크플로가 통과한 변경을 기존 방식으로 배포한다.
4. 배포 후 `production-smoke.yml`을 수동 실행하거나 예약 실행 결과를 확인한다.
5. 장애 시 구조화 로그의 이벤트·모드·폴백 사유와 내부 `/metrics`만 확인한다. 위치, 계정, 토큰을 수집하려고 로그 수준을 올리지 않는다.

## 비목표

- 자동 배포, 롤백, 알림 채널 연동
- PR별 미리보기 환경
- 실제 Kakao 지도 SDK를 구동하는 풀 브라우저 E2E
- 장기 메트릭 저장소, Grafana/Prometheus 서버 배포
- 운영 사용자 데이터를 만드는 스모크 계정 자동 가입·삭제
