"""적재된 안전 데이터와 로컬 OSM 도로망으로 경로 산출물을 게시한다.

사용법:
    backend/.venv/Scripts/python.exe scripts/build_route_artifacts.py
    backend/.venv/Scripts/python.exe scripts/build_route_artifacts.py --region seoul-gyeonggi

공공데이터 적재가 성공한 뒤 실행한다. 산출물 생성에 실패하면 기존 current 매니페스트는
그대로 유지되므로, API 워커는 직전에 검증된 산출물을 계속 사용한다.
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.safety_zone import SafetyZone, scoped_zones_query
from app.services.route_artifact import publish_artifact
from app.services.safe_route import build_route_artifact


def _default_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_and_publish_route_artifact(
    *, zones: list[SafetyZone], directory: Path, version: str, region: str
) -> Path:
    """주어진 안전구역 데이터로 산출물을 만들고, 성공했을 때만 최신 버전으로 게시한다."""

    artifact = build_route_artifact(zones, version=version, region=region)
    return publish_artifact(artifact, directory)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and publish a safe-route artifact")
    parser.add_argument("--version", default=_default_version())
    parser.add_argument("--region", default="seoul-gyeonggi")
    parser.add_argument("--directory", type=Path, default=Path(settings.route_artifact_dir))
    args = parser.parse_args()

    db = SessionLocal()
    try:
        zones = scoped_zones_query(db).all()
    finally:
        db.close()
    if not zones:
        raise RuntimeError("Safety zones are required before building route artifacts")

    artifact_dir = build_and_publish_route_artifact(
        zones=zones,
        directory=args.directory,
        version=args.version,
        region=args.region,
    )
    print(f"Published route artifact {args.version} to {artifact_dir}")


if __name__ == "__main__":
    main()
