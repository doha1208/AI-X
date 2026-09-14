import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.safety import router as safety_router
from app.db.session import Base, SessionLocal, engine
from app.models import safety_zone, user  # noqa: F401 (register models before create_all)
from app.models.safety_zone import SafetyZone
from app.services.safe_route import warm_cache

Base.metadata.create_all(bind=engine)

app = FastAPI(title="안심 거주지 · 귀갓길 추천 플랫폼")


@app.on_event("startup")
def warm_safe_route_cache() -> None:
    """안전구역 커버 지역의 도로망을 백그라운드로 미리 받아둔다.

    ponytail: 사용자가 첫 검색을 누르기 전에 캐시가 준비되길 바라는 최선의
    노력(best-effort)일 뿐 — 실패해도 무시하고 실제 요청 시 재시도한다.
    """

    def _run() -> None:
        db = SessionLocal()
        try:
            warm_cache(db.query(SafetyZone).all())
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(safety_router)


@app.get("/health")
def health():
    return {"status": "ok"}
