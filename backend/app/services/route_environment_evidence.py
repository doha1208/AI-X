"""Length-weighted known evidence and bounds; unknown never becomes known absence."""
import numpy as np
from shapely import covers, distance, points as geo_points

from app.services.poi_factors import to_meters
from app.services.route_environment_sources import verified_factor_coverage


def assess_available_evidence(cells, *, at, period, policy, indexes):
    active = policy.active_factors(period)
    weights = np.asarray([c.end_m - c.start_m for c in cells])
    length = float(weights.sum())
    ratios, evidence_factors = {}, []
    any_known = np.zeros(len(cells), dtype=bool)
    positive_length = unknown_length = 0.0
    meters = to_meters([c.midpoint for c in cells])
    locations = geo_points(meters[:, [1, 0]]) if len(cells) else None
    for factor in active:
        positive = np.zeros(len(cells), dtype=bool)
        for entry in indexes.sources:
            if entry.source.factor == factor and entry.source.presence_eligible() and entry.source.is_open(at) and entry.tree is not None and len(cells):
                positive |= entry.tree.query_ball_point(meters, r=policy.radius(factor), return_length=True) > 0
        known = positive.copy()
        area = verified_factor_coverage(indexes, factor)
        if area is not None and len(cells):
            known |= covers(area, locations) & (distance(area.boundary, locations) + 1e-8 >= policy.radius(factor))
        ratios[factor] = float(weights[known].sum() / length) if length else 0.0
        if np.any(known):
            evidence_factors.append(factor)
        any_known |= known
        positive_length += float(weights[positive].sum())
        unknown_length += float(weights[~known].sum())
    denominator = length * len(active)
    lower = 100 * positive_length / denominator if denominator else 0.0
    upper = min(100.0, 100 * (positive_length + unknown_length) / denominator) if denominator else 100.0
    return {"evidence_factors": sorted(evidence_factors), "factor_evaluation_ratio": ratios,
            "verified_distance_ratio": float(weights[any_known].sum() / length) if length else 0.0,
            "bounds": {"lower": lower, "upper": upper} if evidence_factors and length else None}
