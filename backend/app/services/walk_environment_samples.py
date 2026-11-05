"""Batch-prepared physical walk segments and bounded, clipped length samples."""
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import tempfile
from xml.etree import ElementTree as ET

import numpy as np
import shapely
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, shape

from app.services.facility_assessment import AssessmentSample
from app.services.road_score import is_car_only
from app.services.route_environment_sources import _project_geometry
from app.services.route_environment_inputs import atomic_json

SAMPLING_VERSION = "walk-physical-stream-v1"
MAX_SCOPE_SAMPLES = 250_000
_M_LAT = 111320.0
_M_LNG = _M_LAT * math.cos(math.radians(37.5))


@dataclass(frozen=True)
class PhysicalWalkSegment:
    segment_id: str
    geometry: object  # metric x=longitude metres, y=latitude metres


@dataclass
class WalkEnvironmentIndex:
    segments: tuple[PhysicalWalkSegment, ...]
    source_version: str
    sampling_version: str = SAMPLING_VERSION
    _tree: object = field(init=False, repr=False)

    def __post_init__(self):
        self._tree = shapely.STRtree([segment.geometry for segment in self.segments])


@dataclass
class WalkScope:
    samples: list[AssessmentSample]
    geometry: object


def build_walk_environment_index(graph, *, source_version) -> WalkEnvironmentIndex:
    segments = {}
    for u, v, data in graph.edges(data=True):
        highways = data.get("highway", [])
        highways = highways if isinstance(highways, (list, tuple)) else [highways]
        if is_car_only(data) or {str(h) for h in highways} & {"motorway", "motorway_link"}:
            continue
        a, b = graph.nodes[u], graph.nodes[v]
        line = data.get("geometry")
        if line is None:
            line = LineString([(a["x"], a["y"]), (b["x"], b["y"])])
        if line.geom_type != "LineString" or not line.is_valid or not np.isfinite(shapely.get_coordinates(line)).all():
            raise ValueError("invalid_walk_geometry")
        if line.is_empty or line.length == 0:
            continue
        coords = shapely.get_coordinates(line)
        if np.any(np.abs(coords[:, 0]) > 180) or np.any(np.abs(coords[:, 1]) > 90):
            raise ValueError("walking_source_crs_must_be_wgs84")
        osmids = data.get("osmid")
        identity = sorted(map(str, osmids if isinstance(osmids, (list, tuple)) else [osmids])) if osmids is not None else sorted([str(u), str(v)])
        key = hashlib.sha256(line.normalize().wkb + json.dumps(identity).encode()).hexdigest()
        if key not in segments:
            segments[key] = PhysicalWalkSegment(key, _project_geometry(line))
    return WalkEnvironmentIndex(tuple(segments[key] for key in sorted(segments)), source_version)


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _xml_elements(path):
    context = ET.iterparse(path, events=("start", "end"))
    _, root = next(context)
    for event, element in context:
        if event == "end" and element.tag in {"node", "way", "relation"}:
            yield element
            root.clear()


def _stream_source_segments(path, source_version):
    # Two passes resolve all references, including XML with ways before nodes.
    nodes = {int(element.attrib["id"]): {"x": float(element.attrib["lon"]), "y": float(element.attrib["lat"])}
             for element in _xml_elements(path) if element.tag == "node"}
    class SourceWays:
        def __init__(self):
            self.nodes = nodes

        def edges(self, data=True):
            for element in _xml_elements(path):
                if element.tag != "way":
                    continue
                refs = [int(child.attrib["ref"]) for child in element if child.tag == "nd"]
                if len(refs) < 2:
                    continue
                if any(ref not in nodes for ref in refs):
                    raise ValueError("walking_source_node_missing")
                tags = {child.attrib["k"]: child.attrib["v"] for child in element if child.tag == "tag"}
                if tags.get("foot") == "no" or tags.get("access") == "private" or tags.get("area") == "yes":
                    continue
                tags["osmid"] = element.attrib["id"]
                tags["geometry"] = LineString([(nodes[ref]["x"], nodes[ref]["y"]) for ref in refs])
                yield refs[0], refs[-1], tags
    return build_walk_environment_index(SourceWays(), source_version=source_version)


def load_walk_source_for_sampling(xml_path: Path, *, cache_path: Path, before_source_load=None) -> WalkEnvironmentIndex:
    """Own trusted cache; never reuse the largest-component route graph cache."""
    xml_path, cache_path = Path(xml_path), Path(cache_path)
    signature = {"xml_sha256": _sha256(xml_path), "sampling_version": SAMPLING_VERSION,
                 "code_sha256": _sha256(Path(__file__)), "road_filter_sha256": _sha256(Path(__file__).with_name("road_score.py")),
                 "parser": "osm-xml-iterparse-v1", "retain_all": True}
    metadata_path = cache_path.with_suffix(cache_path.suffix + ".json")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("signature") == signature and metadata.get("sha256") == _sha256(cache_path):
            with cache_path.open("rb") as stream:
                cached = pickle.load(stream)
            if isinstance(cached, WalkEnvironmentIndex) and cached.source_version == signature["xml_sha256"] and cached.sampling_version == SAMPLING_VERSION:
                return cached
    except (OSError, ValueError, TypeError, AttributeError, EOFError, pickle.PickleError):
        pass
    if before_source_load is not None:
        before_source_load()
    index = _stream_source_segments(xml_path, signature["xml_sha256"])
    if _sha256(xml_path) != signature["xml_sha256"]:
        raise ValueError("input_changed_during_build")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=cache_path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        pickle.dump(index, stream, protocol=pickle.HIGHEST_PROTOCOL)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(cache_path)
    atomic_json(metadata_path, {"signature": signature, "sha256": _sha256(cache_path)})
    return index


def _samples_in(index, area, step_m):
    if not math.isfinite(step_m) or step_m <= 0:
        raise ValueError("step_m must be positive")
    samples, lines = [], []
    for number in sorted(index._tree.query(area, predicate="intersects")):
        segment = index.segments[int(number)]
        clipped = segment.geometry.intersection(area)
        parts = list(shapely.get_parts(clipped))
        for part_no, line in enumerate(parts):
            if line.geom_type != "LineString" or line.length <= 0:
                continue
            lines.append(line)
            starts = np.arange(0, line.length, step_m)
            if len(samples) + len(starts) > MAX_SCOPE_SAMPLES:
                raise ValueError("walk_sample_limit_exceeded")
            ends = np.minimum(starts + step_m, line.length)
            points = shapely.line_interpolate_point(line, (starts + ends) / 2)
            for i, (p, weight) in enumerate(zip(points, ends - starts)):
                samples.append(AssessmentSample(f"{segment.segment_id}:{part_no}:{i}",
                                                (float(p.y / _M_LAT), float(p.x / _M_LNG)), float(weight)))
    return WalkScope(samples, MultiLineString(lines) if lines else GeometryCollection())


def sample_area_walks(index, *, lat, lng, radius_m, step_m):
    return sample_area_walk_scope(index, lat=lat, lng=lng, radius_m=radius_m, step_m=step_m).samples


def sample_area_walk_scope(index, *, lat, lng, radius_m, step_m):
    if not all(math.isfinite(v) for v in (lat, lng, radius_m)) or radius_m <= 0 or abs(lat) > 90 or abs(lng) > 180:
        raise ValueError("Invalid walking assessment area")
    return _samples_in(index, Point(lng * _M_LNG, lat * _M_LAT).buffer(radius_m), step_m)


def sample_zone_walks(index, *, boundary, step_m):
    return sample_zone_walk_scope(index, boundary=boundary, step_m=step_m).samples


def sample_zone_walk_scope(index, *, boundary, step_m):
    geometry = shape(boundary)
    if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
        raise ValueError("invalid_assessment_boundary")
    return _samples_in(index, _project_geometry(geometry), step_m)
