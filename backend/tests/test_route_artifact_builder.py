import networkx as nx

from app.models.safety_zone import SafetyZone
from app.services import safe_route as sr
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
    monkeypatch.setattr(sr, "_facility_index", lambda: None)

    artifact = sr.build_route_artifact(_zones(), version="v1", region="seoul-gyeonggi")

    assert set(artifact.graph_by_period) == {"day", "night"}
    assert artifact.node_ids == [1, 2]
    assert artifact.node_points.tolist() == [[37.5, 100.75587421698687], [37.501, 100.75666757032717]]
    assert artifact.graph_by_period["day"][1][2]["safety_cost"] > 0
    assert artifact.graph_by_period["night"][1][2]["safety_cost"] > 0
    assert artifact.profile_version == DEFAULT_SCORING_PROFILE.version
    assert set(artifact.score_by_period) == {"day", "night"}
    assert artifact.score_by_period["day"]["TEST1"] == 50.0
