import networkx as nx

from app.services import safe_route as sr
from app.services.geo import haversine_km


def _graph_with_longitude_trap() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    g.add_node(1, y=37.5011, x=127.0000)  # 위도 방향으로 약 122m
    g.add_node(2, y=37.5000, x=127.0012)  # 경도 방향으로 약 106m (실제로 더 가까움)
    g.add_node(3, y=37.5100, x=127.0100)
    return g


def test_nearest_node_agrees_with_haversine_despite_longitude_shrinkage():
    # 위경도를 그냥 평면 좌표로 쓰면 1번(0.0011도)이 2번(0.0012도)보다 가까워 보이지만
    # 서울 위도에선 경도 1도가 위도 1도보다 짧아서 실제로는 2번이 더 가깝다.
    g = _graph_with_longitude_trap()
    lat, lng = 37.5000, 127.0000
    expected = min(
        g.nodes(data=True), key=lambda item: haversine_km(lat, lng, item[1]["y"], item[1]["x"])
    )[0]
    assert expected == 2
    assert sr._nearest_node(g, lat, lng) == expected


def test_nearest_node_builds_index_once_per_graph():
    g = _graph_with_longitude_trap()
    sr._nearest_node(g, 37.5, 127.0)
    first_tree, _ = sr._node_index(g)
    sr._nearest_node(g, 37.51, 127.01)
    second_tree, _ = sr._node_index(g)
    assert second_tree is first_tree


def test_walking_distance_routes_keep_alternatives():
    assert sr._alternatives_for(3.0, 3) == 3
    assert sr._alternatives_for(6.0, 3) == 3


def test_long_routes_fall_back_to_single_route():
    assert sr._alternatives_for(6.01, 3) == 1
    assert sr._alternatives_for(20.0, 3) == 1
