import json

import networkx as nx
import numpy as np

from app.services.route_artifact import RouteArtifact, load_current_artifact, publish_artifact


def _artifact(version: str = "v1") -> RouteArtifact:
    graph = nx.DiGraph()
    graph.add_node(1, y=37.5, x=127.0)
    graph.add_node(2, y=37.501, x=127.001)
    graph.add_edge(1, 2, length=140.0, edge_score=72.0, safety_cost=210.0)
    return RouteArtifact(
        version=version,
        region="seoul-gyeonggi",
        graph_by_period={"day": graph, "night": graph.copy()},
        node_ids=[1, 2],
        node_points=np.array([(37.5, 127.0), (37.501, 127.001)]),
    )


def test_published_artifact_becomes_the_current_loadable_version(tmp_path):
    publish_artifact(_artifact(), tmp_path)

    loaded = load_current_artifact(tmp_path)

    assert loaded is not None
    assert loaded.version == "v1"
    assert loaded.region == "seoul-gyeonggi"
    assert loaded.node_ids == [1, 2]
    assert loaded.graph_by_period["day"][1][2]["safety_cost"] == 210.0


def test_checksum_mismatch_rejects_current_artifact(tmp_path):
    publish_artifact(_artifact(), tmp_path)
    manifest = json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))
    artifact_path = tmp_path / manifest["artifact_file"]
    artifact_path.write_bytes(b"tampered")

    assert load_current_artifact(tmp_path) is None


def test_empty_artifact_with_matching_checksum_is_rejected_without_raising(tmp_path):
    publish_artifact(_artifact(), tmp_path)
    manifest_path = tmp_path / "current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_path = tmp_path / manifest["artifact_file"]
    artifact_path.write_bytes(b"")
    manifest["sha256"] = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert load_current_artifact(tmp_path) is None
