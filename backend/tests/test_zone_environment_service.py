from types import SimpleNamespace
from datetime import datetime

import pytest


def zone(code):
    return SimpleNamespace(dong_code=code, dong_name=f"{code}동", lat=37.5, lng=127)


def summary(basis_id, coverage, *, source="source-a", **overrides):
    used = sorted(coverage)
    return {
        "scope": "zone", "period": "day", "status": "degraded", "evaluation_basis": "multi_factor",
        "score": 100 * sum(coverage.values()) / len(coverage) if coverage else None,
        "reference_score": None, "reference_factor": None, "score_bounds": None,
        "sampled_length_m": 100, "used_factors": used, "factor_coverage": coverage,
        "factor_evaluation_ratio": {factor: 1 for factor in used}, "verified_distance_ratio": 1,
        "comparison_basis_id": basis_id, "source_versions": {"source": source},
        "model_version": "facility-access-v1", "policy_version": "environment-v1-draft",
        "assessed_at": "2026-11-05T01:00:00+09:00", "reference_at": "2026-11-05T12:00:00+09:00",
        "unavailable_reason": None, **overrides,
    }


def snapshot(rows, *, version="artifact-one", schema=4):
    return SimpleNamespace(artifact=SimpleNamespace(version=version, schema_version=schema,
        zone_facility_summaries=rows, boundary_diagnostics={"missing_codes": ["G"], "invalid_codes": ["H"]}))


def listing(rows, codes="ABCDEFGH", **options):
    from app.services.zone_environment_service import list_facility_zones
    return list_facility_zones(snapshot=snapshot(rows), zones=[zone(c) for c in codes],
                               period="day", weekday=3, **options)


def test_largest_comparable_group_only_gets_ranks_with_displayed_ties():
    rows = {(code, 3, "day"): summary(basis, values) for code, basis, values in [
        ("A", "bells", {"bell": .8, "cctv": .61}),
        ("B", "bells", {"bell": .8, "cctv": .62}),
        ("C", "other", {"lighting": .9, "cctv": .9}),
        ("D", "bells", {"bell": .6, "cctv": .6}),
    ]}
    rows["E", 3, "day"] = summary("single", {"bell": .8}, evaluation_basis="single_factor", score=None, reference_score=80, reference_factor="bell")
    rows["F", 3, "day"] = summary("partial", {}, evaluation_basis="partial_coverage", score_bounds={"lower": 10, "upper": 80})
    result = listing(rows)
    assert result.basis_id == "bells"
    assert [(z.dong_code, z.rank) for z in result.zones] == [
        ("A", 1), ("B", 1), ("D", 3), ("C", None), ("E", None), ("F", None), ("G", None), ("H", None)]
    assert result.zones[-2].assessment.unavailable_reason == "boundary_missing"
    assert result.zones[-1].assessment.unavailable_reason == "boundary_invalid"
    assert result.zones[4].assessment.reference_score == 80 and result.zones[5].assessment.score_bounds["lower"] == 10


def test_equal_group_sizes_choose_factor_names_and_stale_basis_returns_choices():
    from app.services.zone_environment_service import ComparisonBasisChanged
    rows = {
        ("A", 3, "day"): summary("b", {"bell": .5, "cctv": .5}),
        ("B", 3, "day"): summary("l", {"lighting": .99, "cctv": .99}),
        ("A", 4, "day"): summary("friday", {"bell": .8, "cctv": .8}),
    }
    assert listing(rows, "AB").basis_id == "b"
    assert listing(rows, "AB", basis_id="l").zones[0].dong_code == "B"
    with pytest.raises(ComparisonBasisChanged) as exc:
        listing(rows, "AB", basis_id="friday")
    assert {g.basis_id for g in exc.value.groups} == {"b", "l"}


def test_relative_percentile_uses_the_selected_groups_displayed_ties_and_includes_zero():
    scores = [0, *([10] * 17), 71, 71.2]
    codes = [f"A{i:02d}" for i in range(20)]
    rows = {(code, 3, "day"): summary("main", {"bell": .5, "cctv": .5}, score=score)
            for code, score in zip(codes, scores)}
    rows["B", 3, "day"] = summary("other", {"bell": .9, "lighting": .9})
    rows["C", 3, "day"] = summary("main", {"bell": .9}, evaluation_basis="single_factor", score=None)
    result = listing(rows, [*codes, "B", "C"], compare_codes=["A00", "A19"])
    by_code = {row.dong_code: row for row in result.zones}
    assert result.relative_method == "midrank-percentile-v1"
    assert result.groups[0].relative_status == "available"
    assert by_code["A00"].assessment.score == 0
    assert by_code["A00"].relative_percentile == 2.5
    assert by_code["A01"].relative_percentile == 47.5
    assert by_code["A18"].relative_percentile == by_code["A19"].relative_percentile == 95
    assert by_code["A18"].rank == by_code["A19"].rank == 1
    assert by_code["A18"].rank_tied and by_code["A19"].rank_tied
    assert by_code["B"].relative_percentile is by_code["C"].relative_percentile is None

    switched = listing(rows, [*codes, "B", "C"], basis_id="other")
    assert all(row.relative_percentile is None for row in switched.zones)
    assert next(group for group in switched.groups if group.basis_id == "other").relative_status == "insufficient_group"


@pytest.mark.parametrize(("count", "expected"), [(19, "insufficient_group"), (20, "no_variation")])
def test_relative_percentile_requires_enough_members_and_score_variation(count, expected):
    codes = [str(i) for i in range(count)]
    rows = {(code, 3, "day"): summary("main", {"bell": .5, "cctv": .5}) for code in codes}
    result = listing(rows, codes)
    assert result.groups[0].relative_status == expected
    assert all(row.relative_percentile is None for row in result.zones)


def test_comparison_recalculates_common_factors_and_keeps_noncomparable_evidence():
    rows = {
        ("A", 3, "day"): summary("a", {"bell": .8, "cctv": .2, "lighting": .9}),
        ("B", 3, "day"): summary("b", {"bell": .7, "cctv": .9}),
        ("C", 3, "day"): summary("c", {"bell": .3, "open_store": .7}),
        ("D", 3, "day"): summary("d", {"open_store": .5}, evaluation_basis="single_factor", score=None, reference_score=50),
    }
    same = listing(rows, "ABCD", compare_codes=["A", "B"]).comparison
    assert same.used_factors == ["bell", "cctv"]
    assert same.scores == pytest.approx({"A": 50, "B": 80})
    one = listing(rows, "ABCD", compare_codes=["A", "C"]).comparison
    assert one.evaluation_basis == "single_factor" and one.scores == pytest.approx({"A": 80, "C": 30})
    none = listing(rows, "ABCD", compare_codes=["A", "D"]).comparison
    assert none.evaluation_basis == "not_comparable" and none.scores == {}


def test_artifact_generation_and_source_hash_change_result_group_not_basis():
    from app.services.zone_environment_service import list_facility_zones
    def result(version, source):
        return list_facility_zones(snapshot=snapshot({("A", 3, "day"): summary("same", {"bell": .6, "cctv": .6}, source=source)}, version=version),
                                   zones=[zone("A")], period="day", weekday=3)
    a, b, c = result("v1", "a"), result("v2", "a"), result("v2", "b")
    assert a.basis_id == b.basis_id == c.basis_id == "same"
    assert len({x.groups[0].result_group_id for x in (a, b, c)}) == 3


def test_schema3_keeps_all_zones_without_substituting_regional_score():
    from app.services.zone_environment_service import list_facility_zones
    result = list_facility_zones(snapshot=snapshot({}, schema=3), zones=[zone("A")], period="day", weekday=3)
    assert result.status == "pending"
    assert result.basis_id is None and result.groups == []
    assert result.zones[0].rank is None and result.zones[0].assessment.score is None


def test_facility_api_provides_basis_conflict_and_zone_details(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import safety
    from app.db.session import SessionLocal
    from app.main import app
    from app.models.safety_zone import SafetyZone
    from app.services.time_period import KST

    codes = ["4111100001", "4111100002"]
    with SessionLocal() as db:
        db.add_all([SafetyZone(dong_code=code, dong_name=f"동네{i}", lat=37.5, lng=127, safety_score=50)
                    for i, code in enumerate(codes)])
        db.commit()
    weekday = datetime.now(KST).weekday()
    rows = {(code, weekday, period): summary("group-" + period, {"bell": .4, "cctv": .6}, period=period)
            for period in ("day", "night") for code in codes}
    monkeypatch.setattr(safety.route_artifact_runtime, "reload_if_changed", lambda *a, **k: False)
    monkeypatch.setattr(safety.route_artifact_runtime, "environment_snapshot", lambda: snapshot(rows))
    client = TestClient(app)
    res = client.get("/safety/facility-zones", params={"period": "day"})
    assert res.status_code == 200 and len(res.json()["zones"]) == 2
    assert res.json()["relative_method"] == "midrank-percentile-v1"
    assert res.json()["groups"][0]["relative_status"] == "insufficient_group"
    assert res.json()["zones"][0]["relative_percentile"] is None
    conflict = client.get("/safety/facility-zones", params={"period": "day", "basis_id": "old"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["groups"][0]["basis_id"] == "group-day"
    compare = client.get("/safety/facility-zones", params=[("period", "day"), *[("dong_codes", code) for code in codes]]).json()
    assert compare["comparison"]["scores"] == {code: 50.0 for code in codes}
    detail = client.get(f"/safety/zones/{codes[0]}").json()
    assert detail["facility_environment"]["day"]["basis_id"] == "group-day"
    assert detail["facility_environment"]["night"]["basis_id"] == "group-night"
