import json

import pytest

from app.services.route_environment_inputs import prepare_environment_inputs
from app.services.route_environment_sources import load_environment_sources


def raw_files(root):
    root.mkdir()
    (root / "facility_points.json").write_text(json.dumps({"cctv": [[37.5, 127], [37.5, 127]], "lights": [[37.5, 127]], "lights_geocoded": [[37.501, 127]]}))
    (root / "store_points.json").write_text(json.dumps({"stores": [[37.5, 127]], "convenience": [[37.5, 127], [37.501, 127]]}))
    (root / "bell_points.json").write_text(json.dumps([[37.5, 127]]))


def test_connects_existing_files_without_inventing_provenance(tmp_path):
    raw = tmp_path / "raw"
    raw_files(raw)
    prepared = prepare_environment_inputs(raw, tmp_path / "absent-catalog.json", tmp_path / "prepared")
    sources = load_environment_sources(prepared.manifest_path)
    assert {s.factor for s in sources} == {"cctv", "lighting", "open_store", "bell"}
    assert all(s.completeness == "partial" and not s.eligible() for s in sources)
    assert all(s.observed_at == "" and s.retrieved_at == "" for s in sources)
    assert next(s for s in sources if s.factor == "cctv").points == [(37.5, 127)]
    assert len(next(s for s in sources if s.factor == "open_store").points) == 2
    assert next(s for s in sources if s.factor == "bell").points == [(37.5, 127)]
    again = prepare_environment_inputs(raw, tmp_path / "absent-catalog.json", tmp_path / "prepared")
    assert again.snapshot_id == prepared.snapshot_id
    assert again.manifest_path.stat().st_mtime_ns == prepared.manifest_path.stat().st_mtime_ns


def test_does_not_publish_partial_coordinates_as_complete(tmp_path):
    raw = tmp_path / "raw"
    raw_files(raw)
    (raw / "bell_points.json").write_text('[[37.5,127],[999,127]]')
    result = prepare_environment_inputs(raw, tmp_path / "catalog.json", tmp_path / "prepared")
    bell = next(d for d in result.diagnostics if d.source_id == "local-bell")
    assert bell.record_count == 2 and bell.valid_record_count == 1
    assert "invalid_coordinates" in bell.reason_codes
    assert bell.completeness == "partial"


def test_preserves_previous_snapshot_when_a_raw_file_is_corrupt(tmp_path):
    raw = tmp_path / "raw"
    raw_files(raw)
    result = prepare_environment_inputs(raw, tmp_path / "catalog.json", tmp_path / "prepared")
    original = result.manifest_path.read_bytes()
    (raw / "bell_points.json").write_text('{broken')
    with pytest.raises(ValueError):
        prepare_environment_inputs(raw, tmp_path / "catalog.json", tmp_path / "prepared")
    assert result.manifest_path.read_bytes() == original


def test_rejects_estimated_catalog_data(tmp_path):
    raw = tmp_path / "raw"
    raw_files(raw)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"sources": {"local-bell": {"estimated": True}}}))
    with pytest.raises(ValueError, match="estimated"):
        prepare_environment_inputs(raw, catalog, tmp_path / "prepared")


def test_optional_source_that_was_never_present_does_not_block_repeat_builds(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "facility_points.json").write_text('{"cctv":[[37.5,127]],"lights":[]}')
    (raw / "bell_points.json").write_text('[[37.5,127]]')
    output = tmp_path / "prepared"
    prepare_environment_inputs(raw, tmp_path / "catalog.json", output)
    second = prepare_environment_inputs(raw, tmp_path / "catalog.json", output)
    assert any(d.factor == "open_store" and d.reason_codes == ["source_missing"] for d in second.diagnostics)
    from app.services import safe_route
    from app.core.config import settings
    from test_route_artifact_builder import _tiny_walk_graph, _zones
    monkeypatch.setattr(settings, "route_environment_sources_path", str(second.manifest_path))
    monkeypatch.setattr(safe_route, "_load_local_graph", _tiny_walk_graph)
    monkeypatch.setattr(safe_route, "route_input_data_version", lambda *a, **k: "fixture")
    artifact = safe_route.build_route_artifact(_zones(), version="partial", region="gyeonggi")
    assert artifact.environment_index.sources


def test_source_preparation_has_a_shared_writer_lock(tmp_path):
    from app.services.route_build_state import builder_lock
    raw = tmp_path / "raw"
    raw_files(raw)
    output = tmp_path / "prepared"
    with builder_lock(output) as acquired:
        assert acquired
        with pytest.raises(RuntimeError, match="source_preparation_already_running"):
            prepare_environment_inputs(raw, tmp_path / "catalog.json", output)
