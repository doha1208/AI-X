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
