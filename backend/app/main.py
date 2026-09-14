from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.safety import router as safety_router
from app.db.session import Base, engine
from app.models import safety_zone, user  # noqa: F401 (register models before create_all)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="안심 거주지 · 귀갓길 추천 플랫폼")

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
