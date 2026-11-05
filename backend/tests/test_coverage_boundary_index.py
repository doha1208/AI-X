import pickle

import numpy as np
from shapely import covers, distance, points
from shapely.geometry import MultiPolygon, Polygon, box

from app.services import route_environment_sources as sources


def test_indexed_boundary_mask_matches_full_geometry_with_holes_and_islands():
    area = MultiPolygon([
        Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)],
                holes=[[(300, 300), (700, 300), (700, 700), (300, 700)]]),
        box(1200, 0, 1800, 800),
    ])
    locations = points(np.random.default_rng(71).uniform([-100, -100], [1900, 1100], (4000, 2)))
    indexes = sources.EnvironmentIndex(coverage_by_factor={"bell": area})
    for radius in (40, 60, 200):
        expected = covers(area, locations) & (distance(area.boundary, locations) + 1e-8 >= radius)
        assert np.array_equal(sources.coverage_known_mask(indexes, "bell", locations, radius), expected)


def test_exact_radius_tolerance_and_polygon_edges_are_preserved():
    area = box(0, 0, 1000, 1000)
    locations = points([(0, 500), (60 - 2e-8, 500), (60 - 5e-9, 500), (60, 500),
                        (60 + 2e-8, 500), (500, 500), (-100, 500)])
    indexes = sources.EnvironmentIndex(coverage_by_factor={"bell": area})
    assert sources.coverage_known_mask(indexes, "bell", locations, 60).tolist() == [False, False, True, True, True, True, False]


def test_missing_coverage_and_empty_points_never_prove_absence():
    indexes = sources.EnvironmentIndex()
    assert sources.coverage_known_mask(indexes, "bell", points([(0, 0)]), 60).tolist() == [False]
    assert sources.coverage_known_mask(indexes, "bell", points(np.empty((0, 2))), 60).size == 0


def test_boundary_cache_is_reused_and_old_pickled_indexes_remain_readable(monkeypatch):
    indexes = sources.EnvironmentIndex(coverage_by_factor={"bell": box(0, 0, 1000, 1000)})
    # Pre-extension pickles have no boundary-cache instance field.
    indexes.__dict__.pop("coverage_boundary_indexes", None)
    indexes = pickle.loads(pickle.dumps(indexes))
    locations = points([(100, 500)])
    assert sources.coverage_known_mask(indexes, "bell", locations, 60).tolist() == [True]
    restored = pickle.loads(pickle.dumps(indexes))
    def reject_rebuild(*args, **kwargs):
        raise AssertionError("same snapshot must reuse the boundary index")
    monkeypatch.setattr(sources, "STRtree", reject_rebuild)
    assert sources.coverage_known_mask(indexes, "bell", locations, 200).tolist() == [False]
    assert sources.coverage_known_mask(restored, "bell", locations, 60).tolist() == [True]
