import networkx as nx

from app.models.safety_zone import SafetyZone
from app.services import safe_route as sr
from app.services.facility_density import build_facility_index
from app.services.scoring_profile import DEFAULT_SCORING_PROFILE


def _tiny_walk_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node(1, y=37.5, x=127.0)
    graph.add_node(2, y=37.501, x=127.001)
    graph.add_edge(1, 2, length=140.0, highway="residential")
    return graph


def _zones() -> list[SafetyZone]:
    return [
        SafetyZone(
            dong_code="TEST1",
            dong_name="테스트동",
            lat=37.5,
            lng=127.0,
            cctv_count=10,
            streetlight_count=10,
            crime_rate=1.0,
            police_dist_m=100.0,
            bell_dist_m=100.0,
            store_count=10,
            safety_score=50.0,
        )
    ]


def test_build_route_artifact_precomputes_day_and_night_graphs(monkeypatch):
    monkeypatch.setattr(sr, "_load_local_graph", _tiny_walk_graph)
    monkeypatch.setattr(sr, "load_facility_index", lambda: None)

    artifact = sr.build_route_artifact(_zones(), version="v1", region="seoul-gyeonggi")

    assert set(artifact.graph_by_period) == {"day", "night"}
    assert artifact.node_ids == [1, 2]
    assert artifact.node_points.tolist() == [[37.5, 100.75587421698687], [37.501, 100.75666757032717]]
    assert artifact.graph_by_period["day"][1][2]["safety_cost"] > 0
    assert artifact.graph_by_period["night"][1][2]["safety_cost"] > 0
    assert artifact.profile_version == DEFAULT_SCORING_PROFILE.version
    assert set(artifact.score_by_period) == {"day", "night"}
    assert artifact.score_by_period["day"]["TEST1"] == 50.0
    assert artifact.data_version == sr.route_input_data_version(_zones())


def test_route_input_data_version_changes_when_facility_points_change(tmp_path):
    facility_points = tmp_path / "facility_points.json"
    facility_points.write_text('{"cctv": []}', encoding="utf-8")

    first = sr.route_input_data_version(_zones(), facility_points_path=facility_points)
    facility_points.write_text('{"cctv": [[37.5, 127.0]]}', encoding="utf-8")
    second = sr.route_input_data_version(_zones(), facility_points_path=facility_points)

    assert first != second


def test_build_route_artifact_reloads_facility_index_for_each_build(monkeypatch):
    monkeypatch.setattr(sr, "_load_local_graph", _tiny_walk_graph)
    indexes = iter(
        [
            build_facility_index(cctv=[], lights=[]),
            build_facility_index(cctv=[(37.5005, 127.0005)], lights=[]),
        ]
    )
    calls = 0

    def load_current_facilities():
        nonlocal calls
        calls += 1
        return next(indexes)

    monkeypatch.setattr(sr, "load_facility_index", load_current_facilities)

    sr.build_route_artifact(_zones(), version="v1", region="seoul-gyeonggi")
    sr.build_route_artifact(_zones(), version="v2", region="seoul-gyeonggi")

    assert calls == 2
