from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.admin_scoring import router as admin_scoring_router
from app.api.route_history import router as route_history_router
from app.api.safety import router as safety_router
from app.core.config import settings, validate_runtime_settings
from app.db.session import Base, engine
from app.db.schema import ensure_database_schema
from app.models import safety_zone, scoring_profile, user  # noqa: F401 (register models before create_all)
from app.services.safe_route import route_artifact_runtime
from app.observability import configure_observability, metrics_response
from app.services.route_builder_supervisor import start_builder_supervisor
from app.services.route_build_state import public_builder_status

Base.metadata.create_all(bind=engine)
ensure_database_schema(engine)

configure_observability()
app = FastAPI(title="안심 거주지 · 귀갓길 추천 플랫폼")


@app.on_event("startup")
def load_route_artifact() -> None:
    """완성된 최신 경로 산출물을 읽는다. 부재·손상 시 API 폴백은 계속 동작한다."""

    validate_runtime_settings(settings)
    app.state.builder_supervisor = start_builder_supervisor()
    route_artifact_runtime.load(Path(settings.route_artifact_dir))


@app.on_event("shutdown")
def stop_route_builder() -> None:
    supervisor = getattr(app.state, "builder_supervisor", None)
    if supervisor is not None:
        supervisor.close()

# CORS_ALLOW_ORIGINS(.env)로 배포/터널 환경마다 허용 origin을 바꾼다.
# 인증 쿠키를 보내므로 허용 origin은 반드시 구체적인 목록이어야 한다.
cors_origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_scoring_router)
app.include_router(route_history_router)
app.include_router(safety_router)


@app.get("/health")
def health():
    return {"status": "ok", "route_artifact": route_artifact_runtime.status(),
            "route_builder": public_builder_status(Path(settings.route_artifact_dir))}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()
