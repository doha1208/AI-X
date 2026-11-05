import math

import networkx as nx
import osmnx as ox
import pytest
from xml.etree import ElementTree as ET
from shapely.geometry import LineString, Polygon, mapping

from app.services import walk_environment_samples as walks


def point(x, y):
    return (37.5 + y / 111320, 127 + x / (111320 * math.cos(math.radians(37.5))))


def graph(edges):
    result = nx.MultiDiGraph(crs="EPSG:4326")
    for u, v, a, b, data in edges:
        result.add_node(u, y=a[0], x=a[1])
        result.add_node(v, y=b[0], x=b[1])
        result.add_edge(u, v, **data)
    return result


def index(edges):
    return walks.build_walk_environment_index(graph(edges), source_version="test-source")


def test_reverse_edges_are_one_physical_road_but_parallel_shapes_survive():
    a, b = point(0, 0), point(0, 100)
    curved = LineString([(a[1], a[0]), (point(50, 50)[1], point(50, 50)[0]), (b[1], b[0])])
    result = index([(1, 2, a, b, {"osmid": 1}), (2, 1, b, a, {"osmid": 1}),
                    (1, 2, a, b, {"osmid": 2, "geometry": curved})])
    assert len(result.segments) == 2
    samples = walks.sample_area_walks(result, lat=a[0], lng=a[1], radius_m=200, step_m=20)
    assert sum(s.weight for s in samples) == pytest.approx(100 + math.sqrt(2) * 100)


def test_a_road_crossing_the_radius_is_clipped_even_with_both_endpoints_outside():
    center = point(0, 0)
    result = index([(1, 2, point(-1500, 0), point(1500, 0), {})])
    samples = walks.sample_area_walks(result, lat=center[0], lng=center[1], radius_m=100, step_m=20)
    assert sum(s.weight for s in samples) == pytest.approx(200)
    assert all(0 < s.weight <= 20 for s in samples)


def test_disconnected_roads_are_kept_without_inventing_a_connecting_path():
    center = point(0, 0)
    result = index([(1, 2, point(-80, 0), point(-40, 0), {}), (3, 4, point(40, 0), point(80, 0), {})])
    samples = walks.sample_area_walks(result, lat=center[0], lng=center[1], radius_m=100, step_m=20)
    assert sum(s.weight for s in samples) == pytest.approx(80)
    assert len({s.sample_id for s in samples}) == len(samples)


def test_zone_boundary_clipping_preserves_only_the_interior_road_length():
    result = index([(1, 2, point(-100, 0), point(100, 0), {})])
    vertices = [point(-30, -50), point(30, -50), point(30, 50), point(-30, 50)]
    boundary = mapping(Polygon([(lng, lat) for lat, lng in vertices]))
    samples = walks.sample_zone_walks(result, boundary=boundary, step_m=20)
    assert sum(s.weight for s in samples) == pytest.approx(60)


def test_car_only_edges_and_empty_scope_do_not_create_fake_samples():
    center = point(0, 0)
    result = index([(1, 2, point(0, 0), point(100, 0), {"highway": "motorway"})])
    assert walks.sample_area_walks(result, lat=center[0], lng=center[1], radius_m=100, step_m=20) == []


def test_sample_limit_fails_instead_of_silently_truncating_roads(monkeypatch):
    center = point(0, 0)
    result = index([(1, 2, point(0, 0), point(100, 0), {})])
    monkeypatch.setattr(walks, "MAX_SCOPE_SAMPLES", 3)
    with pytest.raises(ValueError, match="walk_sample_limit_exceeded"):
        walks.sample_area_walks(result, lat=center[0], lng=center[1], radius_m=200, step_m=20)


def source_xml(way_id=1):
    root = ET.Element("osm", version="0.6")
    for i, (lat, lng) in enumerate([point(0, 0), point(100, 0), point(1000, 0), point(1100, 0)], 1):
        ET.SubElement(root, "node", id=str(i), lat=str(lat), lon=str(lng))
    for number, ids in enumerate(([1, 2], [3, 4]), way_id):
        way = ET.SubElement(root, "way", id=str(number))
        for ref in ids:
            ET.SubElement(way, "nd", ref=str(ref))
        ET.SubElement(way, "tag", k="highway", v="footway")
    return ET.tostring(root)


def test_source_loader_retains_all_components_and_uses_its_own_versioned_cache(tmp_path, monkeypatch):
    source = tmp_path / "walk.xml"
    source.write_bytes(source_xml())
    calls = []
    def no_full_graph(*args, **kwargs):
        raise AssertionError("Physical indexing must stream XML without a second full NetworkX graph")
    monkeypatch.setattr(ox, "graph_from_xml", no_full_graph)
    cache = tmp_path / "sampling.pickle"
    first = walks.load_walk_source_for_sampling(source, cache_path=cache, before_source_load=lambda: calls.append(1))
    second = walks.load_walk_source_for_sampling(source, cache_path=cache)
    assert len(first.segments) == len(second.segments) == 2
    assert len(calls) == 1
    source.write_bytes(source_xml(way_id=10))
    third = walks.load_walk_source_for_sampling(source, cache_path=cache, before_source_load=lambda: calls.append(1))
    assert len(calls) == 2 and third.source_version != first.source_version


def test_corrupted_sampling_cache_is_not_loaded(tmp_path):
    source = tmp_path / "walk.xml"
    source.write_bytes(source_xml())
    cache = tmp_path / "sampling.pickle"
    walks.load_walk_source_for_sampling(source, cache_path=cache)
    cache.write_bytes(b"corrupt")
    assert len(walks.load_walk_source_for_sampling(source, cache_path=cache).segments) == 2
