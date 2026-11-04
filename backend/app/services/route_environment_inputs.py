"""Adapt existing coordinates without inventing source evidence or opening hours."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from app.services.route_environment_sources import load_environment_sources, source_evidence_files


@dataclass
class SourceDiagnostic:
    source_id: str
    factor: str
    record_count: int
    valid_record_count: int
    completeness: str
    reason_codes: list[str]


@dataclass
class PreparedEnvironmentInputs:
    manifest_path: Path
    snapshot_id: str
    diagnostics: list[SourceDiagnostic]


def atomic_json(path: Path, payload) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == encoded:
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_environment_inputs(raw_directory: Path, catalog_path: Path, output_directory: Path) -> PreparedEnvironmentInputs:
    from app.services.route_build_state import builder_lock
    with builder_lock(output_directory) as acquired:
        if not acquired:
            raise RuntimeError("source_preparation_already_running")
        return _prepare_environment_inputs(raw_directory, catalog_path, output_directory)


def _prepare_environment_inputs(raw_directory: Path, catalog_path: Path, output_directory: Path) -> PreparedEnvironmentInputs:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else {"sources": {}}
    metadata = catalog.get("sources", {})
    if not isinstance(metadata, dict):
        raise ValueError("Source catalog must map source IDs to metadata")
    manifest_path = output_directory / "environment_sources.json"
    previous_ids = set()
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_ids = {source["source_id"] for source in previous["sources"]}
    file_sources = {
        "facility_points.json": {"local-cctv", "local-lighting", "local-lighting-geocoded"},
        "store_points.json": {"local-store"},
        "bell_points.json": {"local-bell"},
    }
    records, diagnostics = [], []
    official_manifest = raw_directory / "official_sources" / "environment_sources.json"
    official_sources = []
    if official_manifest.exists():
        import shutil
        official_payload = json.loads(official_manifest.read_text(encoding="utf-8"))
        official_sources = load_environment_sources(official_manifest)
        if len(official_sources) != len(official_payload.get("sources", [])):
            raise ValueError("Official source evidence validation failed")
        copied = set()
        for record in official_payload["sources"]:
            for relative in [record["points_file"], *(name for name, _ in source_evidence_files(record))]:
                if relative in copied:
                    continue
                copied.add(relative)
                source_path = official_manifest.parent / relative
                target = output_directory / relative
                if target.exists() and hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(source_path.read_bytes()).digest():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    with source_path.open("rb") as origin:
                        shutil.copyfileobj(origin, stream)
                temporary.replace(target)
            records.append(record)
        for source in official_sources:
            evidence = source.collection_evidence
            reasons = [] if source.eligible() else ["coverage_unverified"]
            diagnostics.append(SourceDiagnostic(source.source_id, source.factor, evidence["received_records"], len(source.points), source.completeness, reasons))
    elif any(source_id.startswith("official-") for source_id in previous_ids):
        raise ValueError("Previously prepared official evidence is missing")
    hours_path = raw_directory / "store_hours" / "place_hours.json"
    if hours_path.exists():
        raw_hours = hours_path.read_bytes()
        hours = json.loads(raw_hours)
        positions = sorted({tuple(p["point"]) for p in hours["places"] if p.get("hours_status") == "published_schedule" and p.get("point")})
        point_sha = hashlib.sha256(json.dumps(positions, separators=(",", ":")).encode()).hexdigest()
        atomic_json(output_directory / "objects" / f"{point_sha}.json", positions)
        original_sha = hashlib.sha256(raw_hours).hexdigest()
        original = output_directory / "originals" / f"{original_sha}.json"
        original.parent.mkdir(parents=True, exist_ok=True)
        if not original.exists():
            with tempfile.NamedTemporaryFile("wb", dir=original.parent, delete=False) as stream:
                stream.write(raw_hours)
                temporary = Path(stream.name)
            temporary.replace(original)
        records.append({"source_id": "published-hours-emart24", "factor": "open_store", "source_url": hours["source_url"],
                        "observed_at": "", "retrieved_at": hours["retrieved_at"], "sha256": point_sha,
                        "points_file": f"objects/{point_sha}.json", "coordinate_crs": "EPSG:4326", "completeness": "partial",
                        "coverage_basis": "one_chain_subset", "schedule_status": "published_schedule", "staffing_status": "unverified",
                        "opening_hours_evidence": hours["source_url"], "opening_hours": None,
                        "collection_evidence": {"method": "official_chain_schedule_subset", "status": "complete",
                            "original_file": f"originals/{original_sha}.json", "original_sha256": original_sha,
                            "received_records": len(hours["places"]), "expected_records": hours["reported_result_count"],
                            "weekday_status": "not_provided", "real_world_completeness": "unknown"}})
        diagnostics.append(SourceDiagnostic("published-hours-emart24", "open_store", len(hours["places"]), len(positions), "partial", ["opening_hours_unverified", "coverage_unverified"]))
    elif "published-hours-emart24" in previous_ids:
        raise ValueError("Previously prepared published hours evidence is missing")
    files = {}
    for filename in ("facility_points.json", "store_points.json", "bell_points.json"):
        path = raw_directory / filename
        if not path.exists():
            if previous_ids & file_sources[filename]:
                raise ValueError(f"Previously prepared input is missing: {filename}")
            files[filename] = None
        else:
            try:
                files[filename] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise ValueError(f"Invalid coordinate input: {filename}") from error
    facility, stores, bells = files.values()
    if facility is not None and not isinstance(facility, dict) or stores is not None and not isinstance(stores, dict):
        raise ValueError("Facility and store files must contain named coordinate arrays")
    adapters = (
        ("local-cctv", "cctv", None if facility is None else facility.get("cctv", [])),
        ("local-lighting", "lighting", None if facility is None else facility.get("lights", [])),
        ("local-lighting-geocoded", "lighting", None if facility is None else facility.get("lights_geocoded", [])),
        ("local-store", "open_store", None if stores is None else stores.get("stores", []) + stores.get("convenience", [])),
        ("local-bell", "bell", bells),
    )
    fields = {"source_url", "observed_at", "retrieved_at", "coverage_geometry", "completeness", "purpose", "opening_hours_evidence", "opening_hours"}
    for source_id, factor, raw in adapters:
        entry = metadata.get(source_id, {})
        if entry.get("estimated"):
            raise ValueError(f"estimated coordinates are not accepted: {source_id}")
        if raw is None:
            diagnostics.append(SourceDiagnostic(source_id, factor, 0, 0, "missing", ["source_missing"]))
            continue
        if not isinstance(raw, list):
            raise ValueError(f"Coordinates must be an array: {source_id}")
        points, invalid = set(), 0
        for point in raw:
            try:
                lat, lng = map(float, point)
                if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
                    raise ValueError("Invalid coordinate")
                points.add((lat, lng))
            except (TypeError, ValueError):
                invalid += 1
        # Fresh official lists replace legacy observations only within their declared scope.
        replacing = [source.coverage_geometry for source in official_sources if source.factor == factor and source.eligible()]
        if points and replacing:
            from shapely import covers, points as geo_points
            from shapely.geometry import shape
            from shapely.ops import unary_union
            coordinates = sorted(points)
            mask = covers(unary_union([shape(g) for g in replacing]), geo_points([(lng, lat) for lat, lng in coordinates]))
            points = {p for p, covered in zip(coordinates, mask) if not covered}
        content = json.dumps(sorted(points), separators=(",", ":")).encode()
        digest = hashlib.sha256(content).hexdigest()
        coordinate_path = output_directory / "objects" / f"{digest}.json"
        atomic_json(coordinate_path, sorted(points))
        record = dict(source_id=source_id, factor=factor, source_url="", observed_at="", retrieved_at="",
                      completeness="partial", coordinate_crs="EPSG:4326", sha256=digest,
                      points_file=f"objects/{digest}.json")
        record.update({k: v for k, v in entry.items() if k in fields})
        reasons = []
        if invalid:
            record["completeness"] = "partial"
            reasons.append("invalid_coordinates")
        if not all(record.get(k) for k in ("source_url", "observed_at", "retrieved_at")):
            record["completeness"] = "partial"
            reasons.append("provenance_unverified")
        if record["completeness"] != "verified_complete" or not record.get("coverage_geometry"):
            reasons.append("coverage_unverified")
        if factor == "cctv" and record.get("purpose") != "crime_prevention":
            reasons.append("purpose_unverified")
        if factor == "open_store" and not (record.get("opening_hours") and record.get("opening_hours_evidence")):
            reasons.append("opening_hours_unverified")
        diagnostics.append(SourceDiagnostic(source_id, factor, len(raw), len(points), record["completeness"], reasons))
        records.append(record)
    payload = {"schema_version": 1, "sources": records}
    # Validate the candidate before atomically replacing the previous manifest.
    candidate = output_directory / "candidate_sources.json"
    atomic_json(candidate, payload)
    if len(load_environment_sources(candidate)) != len(records):
        raise ValueError("Source catalog failed metadata validation")
    snapshot_id = hashlib.sha256(candidate.read_bytes()).hexdigest()
    atomic_json(manifest_path, payload)
    atomic_json(output_directory / "diagnostics.json", {"snapshot_id": snapshot_id, "sources": [asdict(d) for d in diagnostics]})
    return PreparedEnvironmentInputs(manifest_path, snapshot_id, diagnostics)
