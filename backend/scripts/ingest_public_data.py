"""공공데이터(범죄/CCTV/가로등)를 안전 지수로 변환해 DB에 적재.

ponytail: 지금은 app/data/sample_zones.json의 합성 데이터를 사용.
실제 공공데이터포털 API 키 발급 후 fetch 함수만 교체하면 됨.
"""
import json
from pathlib import Path

from app.db.session import Base, SessionLocal, engine
from app.models.safety_zone import SafetyZone
from app.services.safety_score import compute_safety_score

SAMPLE_DATA_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "sample_zones.json"


def ingest():
    Base.metadata.create_all(bind=engine)
    zones = json.loads(SAMPLE_DATA_PATH.read_text(encoding="utf-8"))

    db = SessionLocal()
    try:
        for z in zones:
            score = compute_safety_score(
                z["cctv_count"], z["streetlight_count"], z["crime_count"]
            )
            existing = (
                db.query(SafetyZone).filter(SafetyZone.dong_code == z["dong_code"]).first()
            )
            if existing:
                for key, value in z.items():
                    setattr(existing, key, value)
                existing.safety_score = score
            else:
                db.add(SafetyZone(**z, safety_score=score))
        db.commit()
        print(f"Ingested {len(zones)} safety zones.")
    finally:
        db.close()


if __name__ == "__main__":
    ingest()
