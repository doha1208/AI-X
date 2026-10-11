"""대기 중인 점수 프로필 적용과 주기적 산출물 freshness 확인을 실행한다."""

import argparse
import time
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal
from scripts.build_route_artifacts import (
    process_next_queued_build,
    queue_rebuild_if_active_artifact_is_stale,
    reconcile_published_build,
)


def run_worker(
    *, directory: Path, region: str, poll_seconds: int, refresh_seconds: int
) -> None:
    next_refresh = 0.0
    while True:
        process_next_queued_build(directory=directory, region=region)
        now = time.monotonic()
        if now >= next_refresh:
            db = SessionLocal()
            try:
                reconcile_published_build(db, directory)
                queue_rebuild_if_active_artifact_is_stale(db, directory)
            finally:
                db.close()
            next_refresh = now + refresh_seconds
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process score-profile artifact builds")
    parser.add_argument("--directory", type=Path, default=Path(settings.route_artifact_dir))
    parser.add_argument("--region", default="seoul-gyeonggi")
    parser.add_argument("--poll-seconds", type=int, default=settings.builder_poll_seconds)
    parser.add_argument(
        "--refresh-seconds", type=int, default=settings.builder_data_refresh_seconds
    )
    args = parser.parse_args()
    run_worker(
        directory=args.directory,
        region=args.region,
        poll_seconds=args.poll_seconds,
        refresh_seconds=args.refresh_seconds,
    )


if __name__ == "__main__":
    main()
