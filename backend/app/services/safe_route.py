import logging
import socket
import threading
from pathlib import Path

import networkx as nx
import osmnx as ox
from scipy.spatial import cKDTree

from app.models.safety_zone import SafetyZone
from app.services.geo import haversine_km
from app.services.safety_score import Period, compute_zone_period_scores

logger = logging.getLogger(__name__)

# scripts/extract_seoul_walk_network.py로 미리 추출해둔 서울 권역 보행자
# 도로망. 있으면 이 파일만으로 그래프를 만들어 Overpass 호출 자체를 건너뛴다
# (독일 서버 왕복 없이 완전히 로컬/오프라인으로 동작). BBOX는 그 스크립트의
# BBOX와 반드시 같아야 한다.
LOCAL_WALK_NETWORK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "osm" / "seoul-walk.osm"
LOCAL_WALK_NETWORK_BBOX = (126.76, 37.42, 127.18, 37.70)

_local_graph: nx.MultiDiGraph | None = None
_local_graph_attempted = False
_local_graph_lock = threading.Lock()


def _load_local_graph() -> nx.MultiDiGraph | None:
    """서울 보행자 도로망(94MB XML) 파싱에 수십 초가 걸린다. 플래그만으로
    가드하면 로딩 중 들어온 동시 요청이 아직 None인 _local_graph를 받아
    Overpass 실시간 폴백으로 새 지연을 겪는다 — 락으로 대기시켜 막는다."""
    global _local_graph, _local_graph_attempted
    if _local_graph_attempted:
        return _local_graph
    with _local_graph_lock:
        if _local_graph_attempted:
            return _local_graph
        _local_graph_attempted = True
        if not LOCAL_WALK_NETWORK_PATH.exists():
            return None
        try:
            _local_graph = ox.graph_from_xml(LOCAL_WALK_NETWORK_PATH, bidirectional=True)
            logger.info(
                "Loaded local OSM walk network: %d nodes, %d edges",
                _local_graph.number_of_nodes(),
                _local_graph.number_of_edges(),
            )
        except Exception:
            logger.warning("Failed to load local OSM walk network", exc_info=True)
            _local_graph = None
    return _local_graph

# overpass-api.de는 DNS가 여러 서버로 라운드로빈되는데, 이 중 하나가 이
# 네트워크에서 접속 불가일 때가 있다. requests/urllib3는(표준 socket과 달리)
# 실패한 첫 주소에서 다음 주소로 자동으로 넘어가지 않고 그대로 타임아웃
# 처리해버려서, osmnx의 내부 재시도(3회)까지 겹치면 90초 넘게 걸릴 수 있다.
# 그래서 프로세스 시작 후 최초 조회 시 각 주소에 짧게 연결해보고, 실제로
# 연결되는 주소를 앞에 두도록 DNS 응답 순서를 재정렬해둔다.
_OVERPASS_HOST = "overpass-api.de"
_addr_order_cache: dict[str, list[int]] = {}
_addr_order_lock = threading.Lock()
_orig_getaddrinfo = socket.getaddrinfo


def _probe_connect(family: int, sockaddr: tuple, timeout: float = 4.0) -> bool:
    try:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(sockaddr[:2])
        return True
    except OSError:
        return False


def _reachability_sorted_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    results = _orig_getaddrinfo(host, port, family, type, proto, flags)
    if host != _OVERPASS_HOST:
        return results

    order = _addr_order_cache.get(host)
    if order is None:
        with _addr_order_lock:
            order = _addr_order_cache.get(host)
            if order is None:
                reachable = [False] * len(results)

                def _check(i: int, r: tuple) -> None:
                    reachable[i] = _probe_connect(r[0], r[4])

                threads = [threading.Thread(target=_check, args=(i, r)) for i, r in enumerate(results)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=5.0)
                order = sorted(range(len(results)), key=lambda i: not reachable[i])
                _addr_order_cache[host] = order
                logger.info("Overpass address reachability probe: %s", list(zip(results, reachable)))

    if len(order) == len(results):
        return [results[i] for i in order]
    return results


socket.getaddrinfo = _reachability_sorted_getaddrinfo

# 기본 180초는 사용자를 너무 오래 기다리게 한다 — 위 재정렬 덕분에 이제
# 첫 번째로 시도하는 주소가 실제로 접속 가능한 주소이므로 짧게 잡아도 된다.
ox.settings.requests_timeout = 15

# 안전점수가 낮을수록 그 구간의 실제 거리 대비 비용을 이만큼 부풀린다.
# score=100 → 배수 1.0(페널티 없음), score=0 → 배수 1+SAFETY_PENALTY_FACTOR.
SAFETY_PENALTY_FACTOR = 5.0

# 시작/도착점만 감싸는 bbox가 아니라 우회 여유를 주기 위한 최소 여백(도 단위, 약 1.1km).
MIN_MARGIN_DEG = 0.01

# 서버 기동 시 warm_cache()로 미리 받아둘 안전구역 전체 커버 영역의 여백.
WARM_MARGIN_DEG = 0.02

# 안전가중치 경로 후보를 최대 몇 개까지 보여줄지.
K_ALTERNATIVES = 3

_graph_cache: dict[tuple[float, float, float, float], nx.MultiDiGraph] = {}


def _route_bbox(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> tuple[float, float, float, float]:
    lats = [start_lat, end_lat]
    lngs = [start_lng, end_lng]
    margin = max(MIN_MARGIN_DEG, (max(lats) - min(lats)) * 0.3, (max(lngs) - min(lngs)) * 0.3)
    return (min(lngs) - margin, min(lats) - margin, max(lngs) + margin, max(lats) + margin)


def _bbox_covers(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    o_west, o_south, o_east, o_north = outer
    i_west, i_south, i_east, i_north = inner
    return o_west <= i_west and o_south <= i_south and o_east >= i_east and o_north >= i_north


def _get_graph(bbox: tuple[float, float, float, float]) -> nx.MultiDiGraph | None:
    if _bbox_covers(LOCAL_WALK_NETWORK_BBOX, bbox):
        local = _load_local_graph()
        if local is not None:
            return local
        # 로컬 파일이 없으면 아래에서 기존 방식(캐시 → 실시간 Overpass)으로 폴백.

    key = tuple(round(v, 3) for v in bbox)
    if key in _graph_cache:
        return _graph_cache[key]

    # 요청 bbox를 이미 통째로 포함하는 캐시(예: 기동 시 warm_cache로 받아둔
    # 더 넓은 영역)가 있으면 그걸 재사용한다 — 키가 정확히 같을 때만
    # 캐시를 쓰면 warm_cache가 실제 경로 요청에 전혀 도움이 안 된다.
    for cached_bbox, graph in _graph_cache.items():
        if _bbox_covers(cached_bbox, bbox):
            return graph

    try:
        graph = ox.graph_from_bbox(bbox, network_type="walk")
    except Exception:
        logger.warning("OSM graph fetch failed for bbox=%s", bbox, exc_info=True)
        return None
    _graph_cache[key] = graph
    return graph


def warm_cache(zones: list[SafetyZone]) -> None:
    """서버 기동 시 안전구역을 모두 감싸는 지역의 도로망을 미리 받아둔다.

    로컬로 미리 추출해둔 파일(LOCAL_WALK_NETWORK_PATH)이 있으면 그걸 로드하는
    것으로 끝난다(네트워크 불필요, 수백 ms 수준). 없을 때만 Overpass 실시간
    조회로 폴백한다.

    ponytail: 백그라운드 스레드에서 호출하는 걸 전제로 함(블로킹 I/O).
    실패해도 조용히 넘어가고, 실제 요청이 들어올 때 다시 시도한다.
    """
    if not zones:
        return

    lats = [z.lat for z in zones]
    lngs = [z.lng for z in zones]
    bbox = (
        min(lngs) - WARM_MARGIN_DEG,
        min(lats) - WARM_MARGIN_DEG,
        max(lngs) + WARM_MARGIN_DEG,
        max(lats) + WARM_MARGIN_DEG,
    )

    if _bbox_covers(LOCAL_WALK_NETWORK_BBOX, bbox):
        _load_local_graph()
        return

    _get_graph(bbox)


def _nearest_node(graph: nx.Graph, lat: float, lng: float) -> int:
    return min(
        graph.nodes(data=True),
        key=lambda item: haversine_km(lat, lng, item[1]["y"], item[1]["x"]),
    )[0]


def _build_zone_index(zones: list[SafetyZone]) -> cKDTree:
    """zones 순서와 1:1로 대응하는 (lat, lng) KD-tree.

    ponytail: 위경도를 평면 유클리드 좌표처럼 취급 — 서울 규모 지역에서는
    최근접 순위가 실제 하버사인 거리와 사실상 동일해 근사로 충분하다.
    """
    points = [(z.lat, z.lng) for z in zones]
    return cKDTree(points)


def _edge_cost(length_m: float, safety_score: float) -> float:
    multiplier = 1 + (100 - safety_score) / 100 * SAFETY_PENALTY_FACTOR
    return length_m * multiplier


def _build_scored_graph(
    graph: nx.MultiDiGraph,
    zones: list[SafetyZone],
    score_map: dict[str, float],
    zone_index: cKDTree,
) -> nx.DiGraph:
    """안전점수 배정(KD-tree 최근접 질의)과 평행 간선 단순화(대안 경로 탐색인
    `shortest_simple_paths`는 MultiDiGraph를 지원하지 않음)를 한 번에 한다.

    원본 MultiDiGraph는 건드리지 않는다 — 이 그래프는 day/night 여러 period가
    공유하는 프로세스 전역 싱글턴이라, 제자리에서 mutate하면 동시에 들어온
    다른 period 요청과 서로의 안전점수를 덮어쓸 수 있다."""
    simple = nx.DiGraph()
    simple.add_nodes_from(graph.nodes(data=True))
    for u, v, data in graph.edges(data=True):
        mid_lat = (graph.nodes[u]["y"] + graph.nodes[v]["y"]) / 2
        mid_lng = (graph.nodes[u]["x"] + graph.nodes[v]["x"]) / 2
        _, idx = zone_index.query((mid_lat, mid_lng))
        score = score_map[zones[idx].dong_code]
        cost = _edge_cost(data.get("length", 0.0), score)
        if simple.has_edge(u, v):
            if cost < simple[u][v]["safety_cost"]:
                simple[u][v].update(data, zone_score=score, safety_cost=cost)
        else:
            simple.add_edge(u, v, **data, zone_score=score, safety_cost=cost)
    return simple


# (graph 객체 id, period) -> 이미 안전점수를 배정하고 단순화한 그래프.
# 안전점수는 zones의 원시 카운트(cctv/streetlight/crime)만으로 정해지고
# 그 카운트는 서버가 떠 있는 동안 안 바뀌므로, period가 같으면 매 요청마다
# 간선 수십만 개를 다시 훑을 필요가 없다 — 한 번만 만들고 재사용한다.
# ponytail: 안전구역 데이터를 재수집(ingest)했다면 서버를 재시작해야 반영됨
# (기존 _local_graph/_graph_cache도 이미 같은 특성 — 새로운 제약이 아니다).
_scored_graph_cache: dict[tuple[int, Period], nx.DiGraph] = {}
_scored_graph_lock = threading.Lock()


def _get_scored_graph(
    graph: nx.MultiDiGraph,
    zones: list[SafetyZone],
    score_map: dict[str, float],
    zone_index: cKDTree,
    period: Period,
) -> nx.DiGraph:
    key = (id(graph), period)
    cached = _scored_graph_cache.get(key)
    if cached is not None:
        return cached
    with _scored_graph_lock:
        cached = _scored_graph_cache.get(key)
        if cached is not None:
            return cached
        simple = _build_scored_graph(graph, zones, score_map, zone_index)
        _scored_graph_cache[key] = simple
        return simple


def _summarize_path(graph: nx.DiGraph, path: list[int]) -> dict:
    points = [(graph.nodes[n]["y"], graph.nodes[n]["x"]) for n in path]
    total_length = 0.0
    weighted_score = 0.0
    for u, v in zip(path[:-1], path[1:]):
        edge = graph[u][v]
        total_length += edge["length"]
        weighted_score += edge["length"] * edge["zone_score"]
    avg_score = weighted_score / total_length if total_length else 0.0
    return {"points": points, "score": avg_score, "distance_m": total_length}


def find_safe_routes(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    zones: list[SafetyZone],
    k: int = K_ALTERNATIVES,
    period: Period = "day",
) -> list[dict] | None:
    """도로망 그래프(OSM) + 안전구역 점수로 가중치를 준 경로를 최대 k개까지 찾는다.

    안전점수가 가장 높은(비용이 가장 낮은) 순서로 정렬되어 반환된다.
    period(day/night)에 따라 안전점수 계산 가중치가 달라진다.

    ponytail: bbox 단위 인메모리 캐시만 사용 — osmnx 자체 디스크 캐시가 있어
    동일 지역 재요청은 이미 빠르다. 그래프 다운로드 실패/미커버 지역이면
    None을 반환해 호출부가 Tmap/직선 샘플링으로 폴백하게 한다.
    """
    if not zones:
        return None

    score_map = compute_zone_period_scores(zones, period)
    zone_index = _build_zone_index(zones)
    bbox = _route_bbox(start_lat, start_lng, end_lat, end_lng)
    graph = _get_graph(bbox)
    if graph is None or graph.number_of_nodes() == 0:
        return None

    try:
        orig = _nearest_node(graph, start_lat, start_lng)
        dest = _nearest_node(graph, end_lat, end_lng)
        simple = _get_scored_graph(graph, zones, score_map, zone_index, period)
        path_iter = nx.shortest_simple_paths(simple, orig, dest, weight="safety_cost")

        routes: list[dict] = []
        for path in path_iter:
            routes.append(_summarize_path(simple, path))
            if len(routes) >= k:
                break
    except (nx.NetworkXNoPath, nx.NodeNotFound, ValueError) as exc:
        logger.warning("Safety-weighted path search failed: %s", exc)
        return None

    return routes or None
