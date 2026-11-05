"""Batch-only unsimplified boundary mapping and weekday facility summaries."""
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
from shapely import get_parts
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from app.services.facility_assessment import MODEL_VERSION, assess_facility_samples
from app.services.route_environment_sources import coverage_known_mask
from app.services.time_period import KST
from app.services.walk_environment_samples import SAMPLING_VERSION, sample_zone_walk_scope

logger = logging.getLogger(__name__)
SCHEDULE_VERSION = "weekday-two-slots-v1"


@dataclass
class AssessmentBoundaries:
    boundaries: dict
    version: str
    missing_codes: list[str]
    invalid_codes: list[str]


def load_assessment_boundaries(manifest_path: Path, wanted_codes: set[str]) -> AssessmentBoundaries:
    from scripts.build_gyeonggi_boundaries import build_features
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return AssessmentBoundaries({}, "unavailable", sorted(wanted_codes), [])
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = {(b["original_file"], b["original_sha256"]) for record in payload.get("sources", [])
               if (b := (record.get("collection_evidence") or {}).get("boundary_evidence"))}
    if not records:
        return AssessmentBoundaries({}, "unavailable", sorted(wanted_codes), [])
    if len(records) != 1:
        raise ValueError("boundary_source_versions_mixed")
    relative, expected = next(iter(records))
    target = (manifest_path.parent / relative).resolve()
    if not target.is_relative_to(manifest_path.parent.resolve()):
        raise ValueError("boundary_source_path_invalid")
    raw = target.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected:
        raise ValueError("boundary_source_hash_mismatch")
    features = build_features(json.loads(raw), wanted_codes, simplify=False)
    geometries, invalid = {}, set()
    for feature in features:
        code = feature["properties"]["adm_cd2"]
        geometry = shape(feature["geometry"])
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            invalid.add(code)
            continue
        geometries.setdefault(code, []).append(geometry)
    boundaries = {code: mapping(unary_union(parts)) for code, parts in geometries.items() if code not in invalid}
    version = hashlib.sha256(json.dumps([digest, sorted(wanted_codes), "raw-adm-cd2-v1"]).encode()).hexdigest()
    return AssessmentBoundaries(boundaries, version, sorted(wanted_codes - boundaries.keys()), sorted(invalid))


def _common_scope_factors(geometry, *, indexes, policy, period):
    if geometry.is_empty:
        return frozenset()
    common = set()
    bounds = box(*geometry.bounds)
    for factor in policy.active_factors(period):
        radius = policy.radius(factor)
        # Use the same exact boundary-distance predicate as sample observation.
        # Polygonal radius buffers under-approximate round caps and can admit
        # unknown samples on short clipped residuals. All parts must be covered.
        parts = get_parts(geometry)
        if coverage_known_mask(indexes, factor, np.array([bounds], dtype=object), radius).all() or all(
            coverage_known_mask(indexes, factor, parts[start:start + 256], radius).all()
            for start in range(0, len(parts), 256)
        ):
            common.add(factor)
    return frozenset(common)


def build_zone_environment_summaries(walk_index, boundaries, wanted_codes, *, policy, indexes, at=None, boundary_version="unknown"):
    now = at or datetime.now(KST)
    now = now.replace(tzinfo=KST) if now.tzinfo is None else now.astimezone(KST)
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    result = {}
    for number, code in enumerate(sorted(wanted_codes), 1):
        reason, scope = None, None
        if code not in boundaries:
            reason = "boundary_missing"
        else:
            try:
                scope = sample_zone_walk_scope(walk_index, boundary=boundaries[code], step_m=policy.step_m)
            except ValueError as exc:
                reason = str(exc)
        samples = scope.samples if scope is not None else []
        templates = {}
        for period, hour in (("day", 12), ("night", 23)):
            common = _common_scope_factors(scope.geometry, indexes=indexes, policy=policy, period=period) if scope else frozenset()
            for weekday in range(7):
                reference = (monday + timedelta(days=weekday)).replace(hour=hour)
                signature = (period, tuple((e.source.source_id, e.source.is_open(reference)) for e in indexes.sources if e.source.factor == "open_store"))
                if signature not in templates:
                    assessment = assess_facility_samples(samples, scope="zone", at=reference, policy=policy, indexes=indexes, common_factors=common)
                    templates[signature] = {f.name: getattr(assessment, f.name) for f in fields(assessment) if f.name != "observations"}
                identity = [MODEL_VERSION, policy.fingerprint(), SAMPLING_VERSION, boundary_version, SCHEDULE_VERSION, sorted(common), period, weekday, hour]
                result[(code, weekday, period)] = {**templates[signature], "assessed_at": now.isoformat(),
                    "reference_at": reference.isoformat(), "reference_weekday": weekday, "reference_hour": hour,
                    "comparison_basis_id": hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]}
                if reason:
                    result[(code, weekday, period)]["unavailable_reason"] = reason
        if number % 25 == 0:
            logger.info("Facility zone summaries prepared: %d/%d", number, len(wanted_codes))
    return result
