import os

import networkx as nx

from app.services import safe_route as sr


def _tiny_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    g.add_node(1, y=37.5, x=127.0)
    g.add_node(2, y=37.501, x=127.001)
    g.add_edge(1, 2, length=140.0)
    return g


class _CountingParser:
    """XML 파싱(수 분 걸리는 osmnx.graph_from_xml)을 흉내내면서 호출 횟수를 센다."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, _path):
        self.calls += 1
        return _tiny_graph()


def _set_mtime(path, seconds: float) -> None:
    os.utime(path, (seconds, seconds))


def test_first_load_parses_xml_and_writes_cache(tmp_path):
    xml, cache = tmp_path / "walk.osm", tmp_path / "walk.pickle"
    xml.write_text("<osm/>")
    parser = _CountingParser()

    graph = sr._read_graph_cached(xml, cache, parser)

    assert parser.calls == 1
    assert cache.exists()
    assert graph.number_of_nodes() == 2


def test_second_load_uses_cache_without_parsing(tmp_path):
    xml, cache = tmp_path / "walk.osm", tmp_path / "walk.pickle"
    xml.write_text("<osm/>")
    parser = _CountingParser()
    sr._read_graph_cached(xml, cache, parser)

    graph = sr._read_graph_cached(xml, cache, parser)

    assert parser.calls == 1
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1
    assert graph.nodes[1]["y"] == 37.5


def test_newer_xml_invalidates_cache(tmp_path):
    xml, cache = tmp_path / "walk.osm", tmp_path / "walk.pickle"
    xml.write_text("<osm/>")
    parser = _CountingParser()
    sr._read_graph_cached(xml, cache, parser)
    _set_mtime(xml, cache.stat().st_mtime + 100)

    sr._read_graph_cached(xml, cache, parser)

    assert parser.calls == 2


def test_corrupt_cache_falls_back_to_parsing_and_is_repaired(tmp_path):
    xml, cache = tmp_path / "walk.osm", tmp_path / "walk.pickle"
    xml.write_text("<osm/>")
    cache.write_bytes(b"not a pickle")
    _set_mtime(xml, cache.stat().st_mtime - 100)
    parser = _CountingParser()

    graph = sr._read_graph_cached(xml, cache, parser)

    assert parser.calls == 1
    assert graph.number_of_nodes() == 2
    # 깨진 캐시가 정상 캐시로 교체돼서 다음 로딩부터는 파싱이 필요 없어야 한다.
    sr._read_graph_cached(xml, cache, parser)
    assert parser.calls == 1
