from datetime import UTC, datetime
import hashlib
import json

import pytest
from shapely.geometry import Polygon, mapping

from app.services import zone_environment_summaries as zones
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_sources import FacilitySource, build_environment_index
from app.services.time_period import KST
from test_walk_environment_samples import index, point


def boundary():
    return mapping(Polygon([(lng, lat) for lat, lng in [point(-500, -500), point(500, -500), point(500, 500), point(-500, 500)]]))


def test_boundary_mapping_preserves_raw_geometry_and_reports_missing_codes(tmp_path):
    geometry = boundary()
    raw = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {
        "adm_cd2": "A", "adm_nm": "A", "sggnm": "test"}, "geometry": geometry}]}).encode()
    (tmp_path / "boundary.json").write_bytes(raw)
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"sources": [{"collection_evidence": {"boundary_evidence": {
        "original_file": "boundary.json", "original_sha256": hashlib.sha256(raw).hexdigest()}}}]}))
    result = zones.load_assessment_boundaries(manifest, {"A", "B"})
    assert result.boundaries == {"A": geometry}
    assert result.missing_codes == ["B"] and result.version
    (tmp_path / "boundary.json").write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="boundary.*hash"):
        zones.load_assessment_boundaries(manifest, {"A"})


def test_weekday_summaries_keep_store_schedule_and_missing_boundaries_separate():
    road_index = index([(1, 2, point(0, 0), point(0, 100), {})])
    shop = FacilitySource("shop", "open_store", "https://data.go.kr", "2026-11-01", "2026-11-04", "a" * 64,
        coverage_geometry=boundary(), completeness="verified_complete", points=[point(0, 50)],
        opening_hours_evidence="official", opening_hours={"2": [[1320, 1440]]})
    bell = FacilitySource("bell", "bell", "https://data.go.kr", "2026-11-01", "2026-11-04", "b" * 64,
        coverage_geometry=boundary(), completeness="verified_complete")
    result = zones.build_zone_environment_summaries(road_index, {"A": boundary()}, {"A", "B"},
        policy=EnvironmentPolicy(), indexes=build_environment_index([shop, bell]), at=datetime(2026, 11, 4, tzinfo=KST))
    assert len(result) == 28
    assert result[("A", 2, "night")]["score"] == pytest.approx(50)
    assert result[("A", 5, "night")]["score"] == 0
    assert result[("A", 2, "night")]["sampled_length_m"] == pytest.approx(100)
    assert result[("B", 2, "night")]["unavailable_reason"] == "boundary_missing"
    assert "observations" not in result[("A", 2, "night")]


def test_empty_walk_scope_is_unavailable_instead_of_zero():
    result = zones.build_zone_environment_summaries(index([]), {"A": boundary()}, {"A"},
        policy=EnvironmentPolicy(), indexes=build_environment_index([]), at=datetime(2026, 11, 4, tzinfo=KST))
    assert result[("A", 2, "day")]["score"] is None
    assert result[("A", 2, "day")]["unavailable_reason"] == "no_walk_samples"


def test_weekday_template_uses_kst_calendar_for_utc_input():
    result = zones.build_zone_environment_summaries(index([]), {"A": boundary()}, {"A"},
        policy=EnvironmentPolicy(), indexes=build_environment_index([]), at=datetime(2026, 11, 3, 16, tzinfo=UTC))
    reference = datetime.fromisoformat(result[("A", 2, "night")]["reference_at"])
    assert reference.weekday() == 2 and reference.day == 4 and reference.hour == 23


@pytest.mark.parametrize("coordinates", [
    [[(300, 500), (700, 500)], [(2300, 500), (2700, 500)]],
    [[(100, 500), (700, 500)], [(2300, 500), (2700, 500)]],
    [[(300, 500), (700, 500)], [(2300, 500), (2950, 500)]],
    [[(300, 500), (700, 500)], [(800, 500), (2200, 500)]],
])
def test_scope_coverage_matches_union_buffer_for_disconnected_roads(coordinates):
    from shapely.geometry import MultiLineString, MultiPolygon, box
    from app.services.route_environment_sources import EnvironmentIndex
    area = MultiPolygon([box(0, 0, 1000, 1000), box(2000, 0, 3000, 1000)])
    roads = MultiLineString(coordinates)
    policy = EnvironmentPolicy()
    expected = area.covers(roads.buffer(policy.radius("bell")))
    indexes = EnvironmentIndex(coverage_by_factor={"bell": area})
    assert ("bell" in zones._common_scope_factors(roads, indexes=indexes, policy=policy, period="day")) == expected


def test_scope_coverage_does_not_union_all_road_buffers(monkeypatch):
    from shapely.geometry import MultiLineString, MultiPolygon, box
    from app.services.route_environment_sources import EnvironmentIndex
    area = MultiPolygon([box(0, 0, 1000, 1000), box(2000, 0, 3000, 1000)])
    roads = MultiLineString([[(300, 500), (700, 500)], [(2300, 500), (2700, 500)]])
    def reject_union(*args, **kwargs):
        raise AssertionError("full-road buffer union is not needed to prove coverage")
    monkeypatch.setattr(MultiLineString, "buffer", reject_union)
    indexes = EnvironmentIndex(coverage_by_factor={"bell": area})
    assert zones._common_scope_factors(roads, indexes=indexes, policy=EnvironmentPolicy(), period="day") == {"bell"}


@pytest.mark.parametrize("coverage_radius,expected", [(60, frozenset()), (61, frozenset({"cctv"}))])
@pytest.mark.parametrize("scope", ["area", "route"])
def test_short_clipped_road_uses_exact_coverage_for_common_factors(coverage_radius, expected, scope):
    from math import cos, radians
    from shapely.geometry import LineString
    from shapely.ops import transform
    from app.services.facility_assessment import AssessmentSample, assess_facility_samples
    from app.services.route_environment_sources import eligible_factors

    lat, lng = 37.5, 127
    sx, sy = 111320 * cos(radians(37.5)), 111320
    x, y = lng * sx, lat * sy
    line = LineString([(x - .01, y), (x + .01, y)])
    # Rounded cap chords fall just inside the exact radius. Clipping can leave
    # this tiny residual; neither area/zone nor group routes may claim coverage.
    geometry = mapping(transform(lambda x, y: (x / sx, y / sy), line.buffer(coverage_radius).buffer(.000001)))
    source = FacilitySource("cctv", "cctv", "https://data.go.kr/test", "2026-11-01", "2026-11-04", "a" * 64,
        coverage_geometry=geometry, completeness="verified_complete", purpose="crime_prevention")
    indexes = build_environment_index([source])
    policy = EnvironmentPolicy()
    route = [(lat, (x - .01) / sx), (lat, (x + .01) / sx)]
    common = (zones._common_scope_factors(line, indexes=indexes, policy=policy, period="day") if scope == "area"
              else eligible_factors(indexes, [route], "day", policy)[0])
    assert common == expected
    result = assess_facility_samples([AssessmentSample("tiny", (lat, lng), .02)], scope="area",
        at=datetime(2026, 11, 5, 12, tzinfo=KST), policy=policy, indexes=indexes, common_factors=common)
    assert result.reference_score == (0 if expected else None)
    assert eligible_factors(indexes, [route], "day", policy)[0] == expected
