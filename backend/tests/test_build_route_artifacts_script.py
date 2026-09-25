import sys

import networkx as nx
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.session import Base
from app.models.safety_zone import SafetyZone
from app.services.route_artifact import RouteArtifact, load_current_artifact
from scripts import build_route_artifacts as script


def _artifact(version: str) -> RouteArtifact:
    graph = nx.DiGraph()
    graph.add_node(1, y=37.5, x=127.0)
    graph.add_node(2, y=37.501, x=127.001)
    graph.add_edge(1, 2, length=140.0, edge_score=70.0, safety_cost=210.0)
    return RouteArtifact(
        version=version,
        region="seoul-gyeonggi",
        graph_by_period={"day": graph, "night": graph.copy()},
        node_ids=[1, 2],
        node_points=np.array([(37.5, 100.75587421698687), (37.501, 100.75666757032717)]),
    )


def test_batch_builder_publishes_the_built_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "build_route_artifact", lambda zones, **kwargs: _artifact(kwargs["version"]))

    artifact_dir = script.build_and_publish_route_artifact(
        zones=[object()], directory=tmp_path, version="v1", region="seoul-gyeonggi"
    )

    assert artifact_dir == tmp_path / "v1"
    assert load_current_artifact(tmp_path).version == "v1"


def test_main_builds_an_artifact_from_scoped_zones_only(monkeypatch, tmp_path):
    captured: dict[str, object] = {}
    engine = create_engine(f"sqlite:///{tmp_path / 'zones.db'}")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_local()
    db.add_all(
        [
            SafetyZone(dong_code="11110101", dong_name="서울", lat=37.5, lng=127.0),
            SafetyZone(dong_code="41110101", dong_name="경기", lat=37.4, lng=127.1),
        ]
    )
    db.commit()
    db.close()

    monkeypatch.setattr(script, "SessionLocal", session_local)
    monkeypatch.setattr(settings, "region_scope_prefix", "11")
    monkeypatch.setattr(
        script,
        "build_and_publish_route_artifact",
        lambda **kwargs: captured.update(kwargs) or tmp_path / "v1",
    )
    monkeypatch.setattr(sys, "argv", ["build_route_artifacts.py", "--directory", str(tmp_path)])

    script.main()

    assert [zone.dong_code for zone in captured["zones"]] == ["11110101"]
