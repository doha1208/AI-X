from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

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
    crime_count: Mapped[int] = mapped_column(Integer, default=0)
    safety_score: Mapped[float] = mapped_column(Float, default=0.0)
