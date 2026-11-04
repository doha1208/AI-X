"""Prepared facility evidence for bounded OSM candidate generation, never final scores."""
from itertools import islice

import networkx as nx
import numpy as np

from app.services.poi_factors import to_meters
from app.services.route_environment import RouteCandidate
from app.services.time_period import period_for


def annotate_environment_graph(graph, indexes, policy):
    iterator = iter(graph.edges(data=True))
    while chunk := list(islice(iterator, 10000)):
        midpoints = [((graph.nodes[u]["y"] + graph.nodes[v]["y"]) / 2,
                      (graph.nodes[u]["x"] + graph.nodes[v]["x"]) / 2) for u, v, _ in chunk]
        meters = to_meters(midpoints)
        hits = [[] for _ in chunk]
        for number, entry in enumerate(indexes.sources):
            if entry.source.eligible() and entry.tree is not None:
                near = entry.tree.query_ball_point(meters, r=policy.radius(entry.source.factor), return_length=True) > 0
                for i in np.flatnonzero(near):
                    hits[i].append(number)
        for (_, _, data), found in zip(chunk, hits):
            if found:
                data["environment_sources"] = tuple(found)


def find_candidates(graph, origin, destination, *, at, policy, indexes, straight_km, edge_points):
    baseline = nx.shortest_path(graph, origin, destination, weight="length")
    paths = [baseline]
    active = {i: e.source.factor for i, e in enumerate(indexes.sources)
              if e.source.eligible() and e.source.factor in policy.active_factors(period_for(at)) and e.source.is_open(at)}
    limit, attempts = (7, 16) if straight_km <= 6 else (2, 4)  # reserve a slot for Tmap
    factors = sorted(set(active.values()))
    if not factors:
        attempts = 0
    used = set(zip(baseline[:-1], baseline[1:]))
    for attempt in range(attempts):
        if len(paths) >= limit:
            break
        factor = factors[attempt] if attempt < len(factors) else None

        def cost(u, v, data):
            hit = {active[i] for i in data.get("environment_sources", ()) if i in active}
            coverage = float(factor in hit) if factor else len(hit) / len(factors)
            multiplier = 2 if attempt > len(factors) and ((u, v) in used or (v, u) in used) else 1
            return data["length"] * (2 - coverage) * multiplier

        path = nx.shortest_path(graph, origin, destination, weight=cost)
        edges = set(zip(path[:-1], path[1:]))
        used |= edges
        if path in paths:
            continue
        total = sum(graph[u][v]["length"] for u, v in edges)
        overlap = max((sum(graph[u][v]["length"] for u, v in edges & set(zip(p[:-1], p[1:]))) / total
                       if total else 1) for p in paths)
        if overlap <= 0.6:
            paths.append(path)
    result = []
    for i, path in enumerate(paths):
        points = [(graph.nodes[path[0]]["y"], graph.nodes[path[0]]["x"])]
        for u, v in zip(path[:-1], path[1:]):
            points.extend(edge_points(graph, u, v)[1:])
        result.append(RouteCandidate(f"osm-{i}", points, "osm"))
    return result
