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


def run_worker(*, directory: Path, region: str, poll_seconds: int, refresh_seconds: int) -> None:
    from dataclasses import asdict
    from datetime import UTC, datetime
    import logging
    import threading
    from app.models.scoring_profile import ScoreBuildRecord
    from app.services.route_build_state import builder_lock, update_builder_state, utc_now
    from app.services.route_environment_inputs import prepare_environment_inputs

    with builder_lock(directory) as acquired:
        if not acquired:
            return
        stop = threading.Event()
        def heartbeat():
            while not stop.is_set():
                update_builder_state(directory, last_worker_heartbeat_at=utc_now())
                stop.wait(5)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            update_builder_state(directory, status="starting")
            with SessionLocal() as db:
                reconcile_published_build(db, directory)
                # With the directory lock held, remaining building rows belong to an interrupted writer.
                db.query(ScoreBuildRecord).filter(ScoreBuildRecord.status == "building").update(
                    {"status": "failed", "error_code": "interrupted", "finished_at": datetime.now(UTC)})
                db.commit()
            next_refresh = 0.0
            while True:
                now = time.monotonic()
                try:
                    with SessionLocal() as db:
                        reconcile_published_build(db, directory)
                    if now >= next_refresh:
                        update_builder_state(directory, status="preparing")
                        prepared = prepare_environment_inputs(Path("data/osm"), Path(settings.route_source_catalog_path),
                                                              Path(settings.route_environment_sources_path).parent)
                        update_builder_state(directory, source_snapshot_id=prepared.snapshot_id,
                                             environment_inputs_ready=bool(prepared.diagnostics),
                                             source_counts={d.source_id:d.valid_record_count for d in prepared.diagnostics},
                                             source_diagnostics=[asdict(d) for d in prepared.diagnostics])
                        with SessionLocal() as db:
                            queue_rebuild_if_active_artifact_is_stale(db, directory, region=region)
                        update_builder_state(directory, last_checked_at=utc_now(), status="idle")
                        next_refresh = time.monotonic() + refresh_seconds
                    process_next_queued_build(directory=directory, region=region)
                except Exception as error:
                    logging.getLogger(__name__).exception("Artifact worker iteration failed")
                    reason = str(error) if isinstance(error, ValueError) and str(error) in (
                        "bootstrap_required", "profile_unresolved", "safety_zones_unavailable") else "input_preparation_failed"
                    update_builder_state(directory, status="failed", stale_reason=reason, last_checked_at=utc_now())
                    next_refresh = time.monotonic() + min(refresh_seconds, 60)
                time.sleep(max(1, poll_seconds))
        finally:
            stop.set()
            thread.join(timeout=6)
            update_builder_state(directory, status="stopped", last_worker_heartbeat_at=None)


def main() -> None:
    from app.db.session import Base, engine
    from app.db.schema import ensure_database_schema
    Base.metadata.create_all(bind=engine)
    ensure_database_schema(engine)
    parser = argparse.ArgumentParser(description="Process score-profile artifact builds")
    parser.add_argument("--directory", type=Path, default=Path(settings.route_artifact_dir))
    parser.add_argument("--region", default="gyeonggi")
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
