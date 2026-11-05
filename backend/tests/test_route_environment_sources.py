import hashlib
import json

import pytest

from app.services.route_environment_sources import load_environment_sources


def descriptor(tmp_path, **kwargs):
    points = tmp_path / "points.json"
    points.write_text(json.dumps([[37.5, 127.0]]))
    record = dict(source_id="cctv", factor="cctv", source_url="https://data.go.kr/test",
                  observed_at="2026-06-30", retrieved_at="2026-11-04", sha256=hashlib.sha256(points.read_bytes()).hexdigest(),
                  points_file="points.json", completeness="partial", coordinate_crs="EPSG:4326", purpose="crime_prevention")
    record.update(kwargs)
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"schema_version": 1, "sources": [record]}))
    return manifest, points


def test_loads_verified_file_without_promoting_completeness(tmp_path):
    manifest, _ = descriptor(tmp_path)
    loaded = load_environment_sources(manifest)
    assert loaded[0].points == [(37.5, 127.0)]
    assert loaded[0].completeness == "partial"


@pytest.mark.parametrize("change", [{"estimated": True}, {"factor": "police_count"}, {"coordinate_crs": "EPSG:5179"}, {"points_file": "../outside.json"}])
def test_rejects_estimates_aggregate_counts_and_unsafe_inputs(tmp_path, change):
    manifest, _ = descriptor(tmp_path, **change)
    assert load_environment_sources(manifest) == []


def test_changed_file_cannot_keep_verified_status(tmp_path):
    manifest, points = descriptor(tmp_path)
    points.write_text("[]")
    assert load_environment_sources(manifest) == []


def test_verified_collection_requires_original_evidence_and_complete_processing(tmp_path):
    from test_route_public_sources import AREA, csv_bytes, row
    from scripts.collect_route_public_sources import publish_collection
    records = publish_collection(csv_bytes([row()]), factor="cctv", agencies={"4060000": ("파주시", AREA)}, directory=tmp_path)
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"schema_version": 1, "sources": records}), encoding="utf-8")
    loaded = load_environment_sources(manifest)
    assert loaded[0].eligible()
    assert loaded[0].completeness == "verified_collection"
    loaded[0].collection_evidence["coordinate_missing"] = 1
    assert not loaded[0].eligible()


def test_original_receipt_cannot_be_reused_for_changed_or_missing_original(tmp_path):
    from test_route_public_sources import AREA, csv_bytes, row
    from scripts.collect_route_public_sources import publish_collection
    records = publish_collection(csv_bytes([row()]), factor="cctv", agencies={"4060000": ("파주시", AREA)}, directory=tmp_path)
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"schema_version": 1, "sources": records}), encoding="utf-8")
    (tmp_path / records[0]["collection_evidence"]["original_file"]).write_bytes(b"changed")
    assert load_environment_sources(manifest) == []


def test_changed_raw_lighting_page_invalidates_collection_evidence(tmp_path):
    from test_route_public_sources import AREA
    from scripts.collect_route_public_sources import publish_collection, archive_response
    item = {"insttCode": "4060000", "latitude": "37.5", "longitude": "127", "referenceDate": "2026-07-01"}
    page = archive_response(json.dumps({"body": {"totalCount": 1, "items": {"item": [item]}}}).encode(), tmp_path,
                            page_no=1, public_url="https://api.data.go.kr/test", retrieved_at="2026-11-04")
    records = publish_collection(json.dumps([item]).encode(), factor="lighting", agencies={"4060000": ("파주시", AREA)}, directory=tmp_path, response_pages=[page])
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"schema_version": 1, "sources": records}), encoding="utf-8")
    assert load_environment_sources(manifest)[0].eligible()
    (tmp_path / page["file"]).write_bytes(b"changed")
    assert load_environment_sources(manifest) == []
