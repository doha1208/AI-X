from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ScoringProfileRecord(Base):
    __tablename__ = "scoring_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weights_json: Mapped[str] = mapped_column(Text, nullable=False)
    unknown_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)


class ScoreBuildRecord(Base):
    __tablename__ = "score_builds"
    __table_args__ = (Index("uq_route_pending_input", "profile_id", "input_fingerprint", "region", "target_schema", unique=True,
                           sqlite_where=text("status IN ('queued', 'building') AND input_fingerprint IS NOT NULL")),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    artifact_version: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    input_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str] = mapped_column(String, nullable=False, default="gyeonggi")
    target_schema: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    reason: Mapped[str] = mapped_column(String, nullable=False, default="profile_apply")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
