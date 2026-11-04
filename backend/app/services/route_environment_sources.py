"""Trusted batch descriptors: counts, estimates and unverified absence are never coverage."""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import logging
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point as GeoPoint, shape
from shapely.ops import transform, unary_union

from app.services.poi_factors import to_meters
from app.services.time_period import KST

logger = logging.getLogger(__name__)
FACTORS = {"cctv", "lighting", "open_store", "bell"}


def source_evidence_files(record: dict) -> list[tuple[str, str]]:
    evidence = record.get("collection_evidence") or {}
    if not evidence:
        return []
    files = [(evidence["original_file"], evidence["original_sha256"])]
    files.extend((page["file"], page["sha256"]) for page in evidence.get("response_pages", []))
    boundary = evidence.get("boundary_evidence")
    if boundary:
        files.append((boundary["original_file"], boundary["original_sha256"]))
    return files


@dataclass
class FacilitySource:
    source_id: str
    factor: str
    source_url: str
    observed_at: str
    retrieved_at: str
    sha256: str
    coverage_geometry: dict | None = None
    completeness: str = "partial"
    coordinate_crs: str = "EPSG:4326"
    purpose: str | None = None
    opening_hours_evidence: str | None = None
    opening_hours: dict[str, list[list[int]]] | None = None
    points: list[tuple[float, float]] = field(default_factory=list)
    coverage_basis: str | None = None
    collection_evidence: dict | None = None
    schedule_status: str | None = None
    staffing_status: str | None = None

    def collection_verified(self) -> bool:
        evidence = self.collection_evidence or {}
        received = evidence.get("received_records", 0)
        return (self.coverage_basis == "declared_agency_boundary" and evidence.get("status") == "complete"
                and evidence.get("method") in {"official_api", "official_csv"}
                and (evidence.get("method") != "official_api" or bool(evidence.get("response_pages")))
                and isinstance(received, int) and received > 0 and evidence.get("expected_records") == received
                and evidence.get("coordinate_missing") == 0 and evidence.get("date_missing") == 0
                and bool(evidence.get("scope", {}).get("agency_code"))
                and len(evidence.get("original_sha256", "")) == 64)

    def eligible(self) -> bool:
        complete = self.completeness == "verified_complete" or (self.completeness == "verified_collection" and self.collection_verified())
        return (self.factor in FACTORS and complete
                and bool(self.coverage_geometry) and self.coordinate_crs == "EPSG:4326"
                and bool(self.source_url) and bool(self.observed_at) and bool(self.retrieved_at) and bool(self.sha256)
                and (self.factor != "cctv" or self.purpose == "crime_prevention")
                and (self.factor != "open_store" or bool(self.opening_hours_evidence and self.opening_hours)))

    def is_open(self, at: datetime) -> bool:
        if self.factor != "open_store":
            return True
        local = at.replace(tzinfo=KST) if at.tzinfo is None else at.astimezone(KST)
        minute = local.hour * 60 + local.minute
        hours = self.opening_hours or {}
        for start, end in hours.get(str(local.weekday()), []):
            if (start < end and start <= minute < end) or (start > end and minute >= start):
                return True
        return any(start > end and minute < end for start, end in hours.get(str((local.weekday() - 1) % 7), []))


@dataclass
class SourceIndex:
    source: FacilitySource
    tree: cKDTree | None
    coverage: object | None


@dataclass
class EnvironmentIndex:
    sources: list[SourceIndex] = field(default_factory=list)


def _project_geometry(geometry):
    # Same fixed local metric projection as the existing facility index.
    scale = math.cos(math.radians(37.5))
    return transform(lambda x, y, z=None: (np.asarray(x) * 111320 * scale, np.asarray(y) * 111320), geometry)


def build_environment_index(sources: list[FacilitySource]) -> EnvironmentIndex:
    entries = []
    for source in sources:
        geometry = _project_geometry(shape(source.coverage_geometry)) if source.coverage_geometry else None
        entries.append(SourceIndex(source, cKDTree(to_meters(source.points)) if source.points else None, geometry))
    return EnvironmentIndex(entries)


def eligible_factors(indexes: EnvironmentIndex, route_geometries, period, policy):
    routes = []
    for points in route_geometries:
        if not points:
            continue
        xy = [(lng, lat) for lat, lng in points]
        routes.append(_project_geometry(LineString(xy) if len(xy) > 1 else GeoPoint(xy[0])))
    used, excluded = set(), {}
    for factor in policy.active_factors(period):
        entries = [e for e in indexes.sources if e.source.factor == factor and e.source.eligible()]
        covered = unary_union([e.coverage for e in entries]) if entries else None
        if covered is not None and routes and all(covered.covers(g.buffer(policy.radius(factor))) for g in routes):
            used.add(factor)
        else:
            available = [e.source for e in indexes.sources if e.source.factor == factor]
            if not available:
                reason = "source_missing"
            elif factor == "open_store" and not any(s.opening_hours_evidence and s.opening_hours for s in available):
                reason = "opening_hours_unverified"
            elif not any(s.source_url and s.observed_at and s.retrieved_at for s in available):
                reason = "provenance_unverified"
            elif factor == "cctv" and not any(s.purpose == "crime_prevention" for s in available):
                reason = "purpose_unverified"
            elif not entries:
                reason = "coverage_unverified"
            else:
                reason = "outside_source_coverage"
            excluded[factor] = reason
    return frozenset(used), excluded


def load_environment_sources(path: Path) -> list[FacilitySource]:
    """Only read files inside this batch descriptor directory; verify content before trusting metadata."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            return []
        records = payload["sources"]
        if not isinstance(records, list):
            return []
    except (OSError, ValueError, KeyError, AttributeError):
        return []
    sources, seen, original_hashes = [], set(), {}
    root = path.parent.resolve()
    for record in records:
        try:
            if record.get("estimated") or record["factor"] not in FACTORS or record.get("coordinate_crs") != "EPSG:4326":
                continue
            relative = Path(record["points_file"])
            target = (root / relative).resolve()
            if relative.is_absolute() or not target.is_relative_to(root):
                continue
            raw = target.read_bytes()
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                continue
            for filename, expected_hash in source_evidence_files(record):
                relative_original = Path(filename)
                original = (root / relative_original).resolve()
                if relative_original.is_absolute() or not original.is_relative_to(root):
                    raise ValueError("Evidence file escapes snapshot directory")
                if original not in original_hashes:
                    with original.open("rb") as stream:
                        original_hashes[original] = hashlib.file_digest(stream, "sha256").hexdigest()
                if original_hashes[original] != expected_hash:
                    raise ValueError("Evidence file checksum mismatch")
            data = json.loads(raw)
            points = data[record["points_key"]] if record.get("points_key") else data
            if not isinstance(points, list):
                continue
            normalized = []
            for point in points:
                if len(point) != 2:
                    raise ValueError("Only coordinate pairs are accepted")
                lat, lng = map(float, point)
                if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
                    raise ValueError("Invalid WGS84 coordinate")
                normalized.append((lat, lng))
            fields = {k: v for k, v in record.items() if k in FacilitySource.__dataclass_fields__ and k != "points"}
            source = FacilitySource(**fields, points=normalized)
            if source.source_id in seen or (source.source_url and not source.source_url.startswith(("https://", "http://"))):
                continue
            for date in (source.observed_at, source.retrieved_at):
                if date:
                    datetime.fromisoformat(date)
            if source.coverage_geometry:
                geometry = shape(source.coverage_geometry)
                if geometry.geom_type not in ("Polygon", "MultiPolygon") or not geometry.is_valid or geometry.is_empty:
                    continue
            if source.opening_hours is not None:
                for day, intervals in source.opening_hours.items():
                    if day not in {str(d) for d in range(7)}:
                        raise ValueError("Invalid weekday")
                    for start, end in intervals:
                        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < 1440 and 0 <= end <= 1440 and start != end):
                            raise ValueError("Invalid opening interval")
            seen.add(source.source_id)
            sources.append(source)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            logger.warning("Invalid environment source descriptor; factor omitted")
    return sources
