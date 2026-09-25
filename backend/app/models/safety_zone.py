from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import settings
from app.db.session import Base


class SafetyZone(Base):
    __tablename__ = "safety_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dong_code: Mapped[str] = mapped_column(String, unique=True, index=True)
    dong_name: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    cctv_count: Mapped[int] = mapped_column(Integer, default=0)
    streetlight_count: Mapped[int] = mapped_column(Integer, default=0)
    # False면 이 동이 속한 시·군·구가 보안등 데이터를 사실상 못 올린 곳 — 개수를 0으로 믿지 않고 점수에서 "모름"으로 본다.
    lights_known: Mapped[bool] = mapped_column(Boolean, default=True)
    crime_count: Mapped[int] = mapped_column(Integer, default=0)
    # 시·군·구 범죄 건수 ÷ 주민등록 인구 × 1만. None은 해당 지역의 범죄율을 알 수 없다는 뜻이다.
    crime_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 동 중심에서 가장 가까운 경찰서/파출소까지의 거리(m). None은 시설 데이터를 알 수 없다는 뜻이다.
    police_dist_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    store_count: Mapped[int] = mapped_column(Integer, default=0)
    # 동 중심에서 가장 가까운 안전비상벨까지의 거리(m). None은 비상벨 데이터를 알 수 없다는 뜻이다.
    bell_dist_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_score: Mapped[float] = mapped_column(Float, default=0.0)


def scoped_zones_query(db: Session):
    """settings.region_scope_prefix가 설정돼 있으면 그 dong_code 접두사만 걸러서 반환한다.

    데이터를 지우지 않고 조회만 좁히는 방식 — 발표 시연처럼 특정 지역만 보여줄 때
    .env의 REGION_SCOPE_PREFIX만 바꾸면 되고, 값을 비우면 원래대로 전체가 나온다.
    """
    query = db.query(SafetyZone)
    if settings.region_scope_prefix:
        query = query.filter(SafetyZone.dong_code.startswith(settings.region_scope_prefix))
    return query
