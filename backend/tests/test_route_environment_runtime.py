import networkx as nx
import numpy as np

from app.services.safe_route import RouteArtifactRuntime
from app.services.route_artifact import RouteArtifact, publish_artifact, load_current_artifact
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_sources import EnvironmentIndex
from app.services.time_period import KST
from datetime import datetime


def artifact():
    graph = nx.DiGraph()
    graph.add_node(1, y=37.5, x=127)
    graph.add_node(2, y=37.501, x=127)
    graph.add_edge(1, 2, length=111, edge_score=20, safety_cost=1000)
    return RouteArtifact("env", "gyeonggi", {"day": graph, "night": graph.copy()}, [1, 2],
                         np.array([(37.5,127*np.cos(np.radians(37.5))), (37.501,127*np.cos(np.radians(37.5)))]),
                         schema_version=3, environment_graph=graph.copy(), environment_index=EnvironmentIndex(), environment_model_version="facility-access-v1",
                         environment_policy_fingerprint=EnvironmentPolicy().fingerprint())


def test_new_artifact_roundtrip_keeps_environment_snapshot(tmp_path):
    publish_artifact(artifact(), tmp_path)
    loaded = load_current_artifact(tmp_path)
    assert loaded.environment_model_version == "facility-access-v1"
    assert loaded.environment_index is not None


def test_environment_candidates_do_not_need_dong_scores_or_legacy_cost():
    runtime = RouteArtifactRuntime()
    value = artifact()
    del value.graph_by_period["day"][1][2]["safety_cost"]
    runtime.install(value)
    found = runtime.find_environment_candidates((37.5,127), (37.501,127), at=datetime(2026,11,4,12,tzinfo=KST), policy=EnvironmentPolicy())
    assert found[0].points == [(37.5,127),(37.501,127)]


def test_legacy_artifact_cannot_silently_become_environment_model():
    runtime = RouteArtifactRuntime()
    from dataclasses import replace
    runtime.install(replace(artifact(), schema_version=2, environment_model_version=None))
    assert runtime.find_environment_candidates((37.5,127), (37.501,127), at=datetime(2026,11,4,12,tzinfo=KST), policy=EnvironmentPolicy()) is None


def test_incompatible_prepared_policy_is_not_silently_used():
    runtime = RouteArtifactRuntime()
    from dataclasses import replace
    runtime.install(replace(artifact(), environment_policy_fingerprint="old-radii"))
    assert runtime.environment_snapshot() is None


def test_environment_graph_parallel_reduction_is_independent_of_legacy_safety():
    from app.services.safe_route import _build_environment_graph
    graph = nx.MultiDiGraph()
    graph.add_node(1,y=37.5,x=127)
    graph.add_node(2,y=37.501,x=127)
    graph.add_edge(1,2,length=100,highway="residential",lit="no",safety_cost=600,edge_score=0)
    graph.add_edge(1,2,length=120,highway="pedestrian",lit="yes",safety_cost=120,edge_score=100)
    prepared = _build_environment_graph(graph)
    assert prepared[1][2]["length"] == 100
    assert "safety_cost" not in prepared[1][2]
    assert "edge_score" not in prepared[1][2]


def test_atomic_publication_with_identical_timestamp_still_reloads_version(tmp_path):
    import os
    from dataclasses import replace
    publish_artifact(artifact(), tmp_path)
    runtime = RouteArtifactRuntime()
    assert runtime.load(tmp_path)
    path = tmp_path / "current.json"
    original = path.stat()
    publish_artifact(replace(artifact(),version="env2"),tmp_path)
    os.utime(path,ns=(original.st_atime_ns,original.st_mtime_ns))
    assert runtime.reload_if_changed(tmp_path,now=0) is True
    assert runtime.status()["version"] == "env2"
