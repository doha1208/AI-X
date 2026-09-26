import json

import networkx as nx
import numpy as np

from app.core.config import settings
from app.services import safe_route as sr
from app.services.route_artifact import RouteArtifact, publish_artifact


def _artifact(version: str = "v1", score: float = 70.0) -> RouteArtifact:
    graph = nx.DiGraph()
    graph.add_node(1, y=37.5, x=127.0)
    graph.add_node(2, y=37.501, x=127.001)
    graph.add_edge(1, 2, length=140.0, edge_score=score, safety_cost=210.0)
    return RouteArtifact(
        version=version,
        region="seoul-gyeonggi",
        graph_by_period={"day": graph, "night": graph.copy()},
        node_ids=[1, 2],
        node_points=np.array([(37.5, 100.75587421698687), (37.501, 100.75666757032717)]),
    )


def test_runtime_finds_route_in_loaded_artifact_without_graph_fetch(monkeypatch):
    runtime = sr.RouteArtifactRuntime()
    runtime.install(_artifact())
    monkeypatch.setattr(sr, "_get_graph", lambda *_: (_ for _ in ()).throw(AssertionError("must not fetch graph")))

    routes = runtime.find_routes(37.5, 127.0, 37.501, 127.001, period="day", k=1)

    assert routes == [{"points": [(37.5, 127.0), (37.501, 127.001)], "score": 70.0, "distance_m": 140.0}]


def test_find_safe_routes_returns_none_without_a_loaded_artifact(monkeypatch):
    monkeypatch.setattr(sr, "route_artifact_runtime", sr.RouteArtifactRuntime())
    monkeypatch.setattr(sr, "_get_graph", lambda *_: (_ for _ in ()).throw(AssertionError("must not fetch graph")))

    assert sr.find_safe_routes(37.5, 127.0, 37.501, 127.001, [], period="day") is None


def test_runtime_loads_the_current_published_artifact(tmp_path):
    publish_artifact(_artifact(), tmp_path)
    runtime = sr.RouteArtifactRuntime()

    assert runtime.load(tmp_path) is True
    assert runtime.find_routes(37.5, 127.0, 37.501, 127.001, period="night", k=1) is not None


def test_result_cache_is_discarded_when_a_new_artifact_is_installed():
    runtime = sr.RouteArtifactRuntime(cache_size=2)
    first_artifact = _artifact(version="v1", score=70.0)
    runtime.install(first_artifact)

    first = runtime.find_routes(37.5, 127.0, 37.501, 127.001, period="day", k=1)
    first_artifact.graph_by_period["day"][1][2]["edge_score"] = 20.0
    cached = runtime.find_routes(37.5, 127.0, 37.501, 127.001, period="day", k=1)
    runtime.install(_artifact(version="v2", score=20.0))
    refreshed = runtime.find_routes(37.5, 127.0, 37.501, 127.001, period="day", k=1)

    assert first[0]["score"] == 70.0
    assert cached[0]["score"] == 70.0
    assert refreshed[0]["score"] == 20.0


def test_invalid_new_manifest_keeps_the_last_loaded_artifact(tmp_path):
    publish_artifact(_artifact(version="v1", score=70.0), tmp_path)
    runtime = sr.RouteArtifactRuntime()
    assert runtime.load(tmp_path) is True
    (tmp_path / "current.json").write_text(json.dumps({"version": "v2"}), encoding="utf-8")

    assert runtime.reload_if_changed(tmp_path, now=1000.0) is False
    routes = runtime.find_routes(37.5, 127.0, 37.501, 127.001, period="day", k=1)

    assert routes[0]["score"] == 70.0


def test_runtime_reloads_a_newly_published_artifact(tmp_path):
    publish_artifact(_artifact(version="v1", score=70.0), tmp_path)
    runtime = sr.RouteArtifactRuntime()
    assert runtime.load(tmp_path) is True
    publish_artifact(_artifact(version="v2", score=20.0), tmp_path)

    assert runtime.reload_if_changed(tmp_path, now=1000.0) is True
    routes = runtime.find_routes(37.5, 127.0, 37.501, 127.001, period="day", k=1)

    assert routes[0]["score"] == 20.0


def test_route_lookup_uses_a_newly_published_artifact_after_reload(monkeypatch, tmp_path):
    publish_artifact(_artifact(version="v1", score=70.0), tmp_path)
    runtime = sr.RouteArtifactRuntime()
    assert runtime.load(tmp_path) is True
    monkeypatch.setattr(sr, "route_artifact_runtime", runtime)
    monkeypatch.setattr(settings, "route_artifact_dir", str(tmp_path))
    publish_artifact(_artifact(version="v2", score=20.0), tmp_path)

    routes = sr.find_safe_routes(37.5, 127.0, 37.501, 127.001, [], period="day")

    assert routes[0]["score"] == 20.0
