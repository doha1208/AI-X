import networkx as nx
import osmnx as ox

from app.models.safety_zone import SafetyZone
from app.services import safe_route as sr
from app.services.facility_density import build_facility_index

_OSM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
  <node id="1" lat="37.5000000" lon="127.0000000"/>
  <node id="2" lat="37.5010000" lon="127.0000000"/>
  <node id="3" lat="37.5020000" lon="127.0000000"/>
  <way id="10">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/>
    <tag k="highway" v="residential"/>
    <tag k="lit" v="no"/>
    <tag k="sidewalk" v="both"/>
  </way>
</osm>
"""


def test_lit_and_sidewalk_tags_survive_graph_loading(tmp_path):
    xml = tmp_path / "walk.osm"
    xml.write_text(_OSM_XML, encoding="utf-8")

    graph = ox.graph_from_xml(xml, bidirectional=True)

    edge = next(iter(graph.edges(data=True)))[2]
    assert edge["lit"] == "no"
    assert edge["sidewalk"] == "both"


def _two_route_graph(top_lit: str, bottom_lit: str) -> nx.MultiDiGraph:
    # 1 -> 2 -> 4 (위쪽 길)와 1 -> 3 -> 4 (아래쪽 길)는 길이가 같고 가로등 태그만 다르다.
    g = nx.MultiDiGraph()
    nodes = {1: (37.500, 127.000), 2: (37.501, 127.001), 3: (37.499, 127.001), 4: (37.500, 127.002)}
    for node, (lat, lng) in nodes.items():
        g.add_node(node, y=lat, x=lng)
    for u, v, lit in [(1, 2, top_lit), (2, 4, top_lit), (1, 3, bottom_lit), (3, 4, bottom_lit)]:
        g.add_edge(u, v, length=150.0, highway="residential", lit=lit)
        g.add_edge(v, u, length=150.0, highway="residential", lit=lit)
    return g


def _zones() -> list[SafetyZone]:
    return [SafetyZone(dong_code="Z", dong_name="테스트동", lat=37.5, lng=127.001)]


def _best_path(graph: nx.MultiDiGraph, period: str, facilities=None) -> list[int]:
    zones = _zones()
    scored = sr._build_scored_graph(graph, zones, {"Z": 60.0}, sr._build_zone_index(zones), period, facilities)
    return nx.shortest_path(scored, 1, 4, weight="safety_cost")


def test_night_route_prefers_the_street_with_more_nearby_lights():
    # 두 길은 도로 종류·태그·길이가 모두 같고, 아래쪽 두 구간(1→3, 3→4)의 중간점에만
    # 보안등 좌표가 있다.
    graph = _two_route_graph(top_lit="unknown", bottom_lit="unknown")
    lamps_on_bottom_edges = [(37.4995, 127.0005)] * 2 + [(37.4995, 127.0015)] * 2
    index = build_facility_index(cctv=[], lights=lamps_on_bottom_edges)

    assert _best_path(graph, "night", index) == [1, 3, 4]


def test_without_facility_points_the_scoring_still_works():
    graph = _two_route_graph(top_lit="no", bottom_lit="yes")
    assert _best_path(graph, "night", None) == [1, 3, 4]


def test_night_route_prefers_the_lit_street():
    assert _best_path(_two_route_graph(top_lit="no", bottom_lit="yes"), "night") == [1, 3, 4]
    assert _best_path(_two_route_graph(top_lit="yes", bottom_lit="no"), "night") == [1, 2, 4]
