# 안심 거주지 · 안심 귀갓길

서울·경기 동 단위 안전 지수와, 그 점수를 반영한 도보 귀갓길 안내.

- `backend/` — FastAPI + SQLite (Python 3.12)
- `frontend/` — Next.js 16 (Node 22)
- `Caddyfile` — 외부 공개용 HTTPS 프록시 (ansimnavi.duckdns.org)

## 처음 세팅

### 1. 코드 받기
```bash
git clone https://github.com/doha1208/AI-X.git
```

### 2. 데이터 파일 받기 (git에 없음 — 팀장에게 압축 파일로 받는다)
용량이 커서(수 GB) git에 올리지 않는다. 받은 파일을 아래 위치에 그대로 둔다.

| 위치 | 내용 |
|---|---|
| `backend/app.db` | 동별 안전 점수 DB |
| `backend/data/osm/*.json` | CCTV·보안등·상점·비상벨·사고다발 좌표 |
| `backend/data/route_artifacts/<버전>/` + `current.json` | 경로 계산용 그래프 (최신 버전 1개만 있으면 됨) |

경로 그래프를 직접 다시 만들 사람만 `backend/data/osm/*.osm`, `*.graph.pickle`(약 1.5GB)도 받는다.

### 3. 백엔드
```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
cp .env.example .env                               # 키 값은 팀 채팅으로 받는다 — 절대 커밋 금지
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

### 4. 프론트엔드
```bash
cd frontend
npm ci
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000, 카카오 키 입력
npm run dev                        # http://localhost:3000
```

## 같이 개발하는 순서

`main`에 직접 올리지 않는다. 기능마다 브랜치 → PR → 검사 통과 → 합치기.

```bash
git switch main && git pull                 # 1. 최신 main에서 시작
git switch -c feat/기능이름                  # 2. 내 브랜치 만들기
# ... 작업 ...
cd backend && .venv/Scripts/python -m pytest tests -q          # 3. 올리기 전에 로컬 검사
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run && npm run build
git push -u origin feat/기능이름             # 4. 올리고 GitHub에서 PR 만들기
```

5. PR에서 **Quality** 검사(백엔드 테스트·린트·타입·프론트 테스트·빌드)가 초록색이어야 합친다.
6. PR을 오래 두면 그사이 main이 바뀐다. 합치기 전에 `git pull origin main`으로 최신 main을 받아
   내 브랜치에서 충돌을 먼저 해결하고, 검사가 다시 통과하는지 본다.

### 지키면 충돌이 줄어드는 것
- 한 PR에는 한 가지 기능만. 작게 자주 합친다.
- 같은 파일을 동시에 크게 고칠 일이 생기면 미리 말한다 (특히 `SafetyMap.tsx`, `safe_route.py`).
- `app.db`, `data/`, `.env`, `node_modules`는 올리지 않는다 (`.gitignore`에 있음).
- 점수 계산 방식을 바꾸면 경로 그래프를 다시 만들어야 한다:
  `cd backend && PYTHONPATH=. .venv/Scripts/python scripts/build_route_artifacts.py`
  — 새로 만든 `data/route_artifacts/`는 팀에 다시 공유한다.
