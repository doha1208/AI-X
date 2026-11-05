"""Collect official route sources with immutable originals and explicit evidence."""
import argparse
import csv
from collections import Counter
from datetime import UTC, date, datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

from app.services.route_environment_inputs import atomic_json
from app.services.route_build_state import builder_lock
from scripts.build_gyeonggi_boundaries import SOURCE_URL as BOUNDARY_SOURCE_URL, ATTRIBUTION

HOST = "https://file.localdata.go.kr"
LIGHT_API = "https://api.data.go.kr/openapi/tn_pubr_public_scrty_lmp_api"
SOURCE_URLS = {
    "cctv": "https://www.data.go.kr/data/15013094/standard.do",
    "bell": "https://www.data.go.kr/data/15028206/standard.do",
    "lighting": "https://www.data.go.kr/data/15017320/standard.do",
}
FILE_KINDS = {"cctv": "cctv_info", "bell": "emergency_call_box_info"}


def request_bytes(url: str, *, referer="https://www.data.go.kr/") -> bytes:
    """Bounded requests; never propagate credential-bearing URLs in exceptions."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": referer})
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = response.read(150_000_001)
            if len(raw) > 150_000_000:
                raise ValueError("Official source exceeds size limit")
            return raw
        except urllib.error.HTTPError as error:
            code = error.code
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f"official_download_http_{code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise RuntimeError("official_download_network_error") from None
        time.sleep(2 ** attempt)
    raise RuntimeError("official_download_failed")


def cached_download(url: str, path: Path, *, validator, refresh=False, referer=None, public_url=None):
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if not refresh and path.exists() and receipt_path.exists():
        raw = path.read_bytes()
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if hashlib.sha256(raw).hexdigest() == receipt.get("sha256"):
            validator(raw)
            return raw, receipt["retrieved_at"]
    raw = request_bytes(url, **({"referer": referer} if referer else {}))
    validator(raw)
    captured = datetime.now(UTC).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)
    # API callers supply a key-free public URL. No credential is persisted.
    atomic_json(receipt_path, {"url": public_url or url, "sha256": hashlib.sha256(raw).hexdigest(), "retrieved_at": captured})
    return raw, captured


def parse_light_body(raw: bytes) -> dict:
    response = json.loads(raw)
    if response.get("header", {}).get("resultCode") != "00" or "totalCount" not in response.get("body", {}):
        raise ValueError("Official lighting API did not return a successful collection")
    return response["body"]


def load_api_key() -> str:
    key = os.environ.get("SECURITY_LIGHT_API_KEY", "")
    if not key and Path(".env").exists():
        key = next((s.split("=", 1)[1].strip() for s in Path(".env").read_text(encoding="utf-8").splitlines()
                    if s.startswith("SECURITY_LIGHT_API_KEY=")), "")
    if not key:
        raise RuntimeError("lighting_api_key_unavailable")
    return urllib.parse.unquote(key)


def archive_original(raw: bytes, directory: Path, suffix: str) -> tuple[str, str]:
    digest = hashlib.sha256(raw).hexdigest()
    relative = f"originals/{digest}.{suffix}"
    target = directory / relative
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(target)
    return relative, digest


def archive_response(raw: bytes, directory: Path, *, page_no: int, public_url: str, retrieved_at: str) -> dict:
    relative, digest = archive_original(raw, directory, "json")
    return {"page_no": page_no, "file": relative, "sha256": digest, "url": public_url, "retrieved_at": retrieved_at}


def load_boundary_source(directory: Path, *, custom_path: Path | None = None, refresh=False):
    def validate(raw):
        data = json.loads(raw)
        if data.get("type") != "FeatureCollection" or not data.get("features"):
            raise ValueError("Invalid administrative boundary source")
    if custom_path is not None:
        raw = custom_path.read_bytes()
        validate(raw)
        source_url = None
    else:
        raw, _ = cached_download(BOUNDARY_SOURCE_URL, directory / "downloads" / "boundaries.geojson",
                                 validator=validate, refresh=refresh)
        source_url = BOUNDARY_SOURCE_URL
    relative, digest = archive_original(raw, directory, "geojson")
    return json.loads(raw), {"source_url": source_url, "original_file": relative, "original_sha256": digest,
                             "processing": "municipal_union_without_simplification", "attribution": ATTRIBUTION}


def parse_agencies(raw: bytes) -> dict[str, str]:
    result = {}
    for attrs, label in re.findall(r"<option([^>]*)>([^<]*)</option>", raw.decode("utf-8")):
        code = re.search(r'\bvalue="(\d+)"', attrs)
        if 'data-upper="6410000_ALL"' in attrs and code:
            result[code[1]] = label.strip()
    if not result:
        raise ValueError("Official agency registry is unavailable")
    return result


def refresh_sources(directory: Path, geojson: dict, *, factors, agency_codes=None, refresh=False, boundary_evidence=None) -> dict:
    """Failed upstream retrieval keeps the previous published collection intact."""
    manifest = directory / "environment_sources.json"
    previous = json.loads(manifest.read_text(encoding="utf-8"))["sources"] if manifest.exists() else []
    records = {r["source_id"]: r for r in previous}
    report = {"checked_at": datetime.now(UTC).isoformat(), "errors": [], "collections": [], "unsubmitted": []}
    cache = directory / "downloads" / datetime.now(UTC).strftime("%Y%m%d")
    try:
        registry_url = HOST + "/file/cctv_info/info"
        registry, _ = cached_download(registry_url, cache / "agencies.html", validator=parse_agencies,
                                     referer=SOURCE_URLS["cctv"], refresh=refresh)
        registry_agencies = parse_agencies(registry)
        agencies = agency_boundaries(geojson, registry_agencies)
        report["unmatched_agencies"] = [{"agency_code": k, "agency_name": v, "reason": "no_boundary_match"}
                                          for k, v in registry_agencies.items() if k not in agencies]
        if agency_codes:
            unknown = set(agency_codes) - set(agencies)
            if unknown:
                raise ValueError("Requested agency has no matching boundary")
            agencies = {k: v for k, v in agencies.items() if k in agency_codes}
        if not agencies:
            raise ValueError("No declared agency boundaries")
    except Exception as error:
        report["errors"].append({"source": "agency_registry", "reason": str(error) if isinstance(error, RuntimeError) else type(error).__name__})
        atomic_json(directory / "collection_report.json", report)
        return report
    successes = 0
    for factor in factors:
        scopes = list(agencies) if factor == "lighting" else [None]
        for code in scopes:
            try:
                if factor in FILE_KINDS:
                    kind = FILE_KINDS[factor]
                    url = f"{HOST}/file/download/{kind}/info?orgCode=6410000_ALL"
                    raw, captured = cached_download(url, cache / f"{factor}.csv", validator=read_csv,
                                                   referer=f"{HOST}/file/{kind}/info", refresh=refresh)
                    scoped = agencies
                else:
                    key = load_api_key()
                    captures = []
                    response_pages = []
                    def fetch(page):
                        public_query = urllib.parse.urlencode({"pageNo": page, "numOfRows": 1000, "type": "json", "insttCode": code})
                        public_url = LIGHT_API + "?" + public_query
                        url = public_url + "&" + urllib.parse.urlencode({"serviceKey": key})
                        data, captured_page = cached_download(url, cache / "lighting" / f"{code}-{page}.json",
                                                             validator=parse_light_body, refresh=refresh, public_url=public_url)
                        captures.append(captured_page)
                        response_pages.append(archive_response(data, directory, page_no=page, public_url=public_url, retrieved_at=captured_page))
                        time.sleep(0.1)
                        return parse_light_body(data)
                    items = collect_light_pages(fetch)
                    if any(str(item.get("insttCode")) != code for item in items):
                        raise ValueError("Lighting API ignored institution filter")
                    raw = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                    captured = min(captures)
                    url = LIGHT_API + "?" + urllib.parse.urlencode({"insttCode": code})
                    scoped = {code: agencies[code]}
                fresh = publish_collection(raw, factor=factor, agencies=scoped, directory=directory,
                                           retrieved_at=captured, download_url=url,
                                           response_pages=response_pages if factor == "lighting" else None,
                                           boundary_evidence=boundary_evidence)
                seen = {r["collection_evidence"]["scope"]["agency_code"] for r in fresh}
                for missing in set(scoped) - seen:
                    supplied_rows = sum(str(row.get("개방자치단체코드", "")) == missing for row in read_csv(raw)) if factor in FILE_KINDS else len(items)
                    reason = "purpose_not_qualified" if supplied_rows and factor == "cctv" else "upstream_no_records"
                    report["unsubmitted"].append({"factor": factor, "agency_code": missing,
                                                  "agency_name": scoped[missing][0], "received_records": supplied_rows, "reason": reason})
                    old_id = f"official-{factor}-{missing}"
                    if old_id in records:
                        stale = dict(records[old_id], completeness="partial")
                        stale["collection_evidence"] = dict(stale["collection_evidence"], status="upstream_no_records")
                        records[old_id] = stale
                records.update({r["source_id"]: r for r in fresh})
                report["collections"].extend({"source_id": r["source_id"], "completeness": r["completeness"], **r["collection_evidence"]} for r in fresh)
                successes += 1
                print(f"{factor} {code or 'gyeonggi'}: {len(fresh)} agency collections", flush=True)
            except Exception as error:
                report["errors"].append({"factor": factor, "agency_code": code,
                                         "reason": str(error) if isinstance(error, RuntimeError) else type(error).__name__})
                print(f"{factor} {code or 'gyeonggi'}: collection failed ({type(error).__name__})", flush=True)
    if successes:
        atomic_json(manifest, {"schema_version": 1, "sources": sorted(records.values(), key=lambda r: r["source_id"])})
    atomic_json(directory / "collection_report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/osm/official_sources"))
    parser.add_argument("--boundaries", type=Path, help="Explicit unsimplified boundary source; default uses the versioned original")
    parser.add_argument("--factors", nargs="+", choices=list(SOURCE_URLS), default=list(SOURCE_URLS))
    parser.add_argument("--agency", action="append", help="Official provider code; omit for all Gyeonggi agencies")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch instead of resuming today's validated downloads")
    args = parser.parse_args()
    with builder_lock(args.directory) as acquired:
        if not acquired:
            raise SystemExit("source_collection_already_running")
        geojson, boundary_evidence = load_boundary_source(args.directory, custom_path=args.boundaries, refresh=args.refresh)
        report = refresh_sources(args.directory, geojson, factors=args.factors, agency_codes=args.agency,
                                 refresh=args.refresh, boundary_evidence=boundary_evidence)
    print(f"Completed collections: {len(report['collections'])}; unavailable scopes: {len(report['unsubmitted'])}; errors: {len(report['errors'])}")
    if report["errors"]:
        raise SystemExit(1)


def read_csv(raw: bytes) -> list[dict]:
    if raw.lstrip().startswith((b"<", b"{")):
        raise ValueError("Expected official CSV, received an error document")
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Invalid CSV encoding")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"개방자치단체코드", "WGS84위도", "WGS84경도", "데이터기준일자"} <= set(reader.fieldnames):
        raise ValueError("Unexpected official CSV columns")
    rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Incomplete CSV rows")
    return rows


def agency_boundaries(geojson: dict, agencies: dict[str, str]) -> dict:
    result = {}
    for code, label in agencies.items():
        name = label.removeprefix("경기도 ").removeprefix("경기")
        geometries = [shape(f["geometry"]) for f in geojson["features"]
                      if f["properties"].get("sggnm", "").startswith(name)]
        if geometries:
            result[code] = (name, mapping(unary_union(geometries)))
    return result


def collect_light_pages(fetch_page, *, page_size=1000) -> list[dict]:
    first = fetch_page(1)
    total = int(first["totalCount"])
    rows = []
    seen_pages = set()
    for number in range(1, max(1, math.ceil(total / page_size)) + 1):
        body = first if number == 1 else fetch_page(number)
        if int(body["totalCount"]) != total:
            raise ValueError("incomplete lighting snapshot: totalCount changed")
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        expected = min(page_size, max(0, total - (number - 1) * page_size))
        if len(items) != expected:
            raise ValueError("incomplete lighting pagination")
        page_digest = hashlib.sha256(json.dumps(sorted(json.dumps(r, sort_keys=True) for r in items)).encode()).hexdigest()
        if items and page_digest in seen_pages:
            raise ValueError("repeated lighting page")
        if body.get("pageNo") is not None and int(body["pageNo"]) != number:
            raise ValueError("repeated or incorrect lighting page number")
        seen_pages.add(page_digest)
        rows.extend(items)
    return rows


def publish_collection(raw: bytes, *, factor: str, agencies: dict, directory: Path,
                       retrieved_at: str | None = None, download_url: str | None = None,
                       response_pages: list | None = None, boundary_evidence: dict | None = None) -> list[dict]:
    """A completed official list is distinct from a census of real-world facilities."""
    retrieved_at = retrieved_at or datetime.now(UTC).isoformat()
    rows = json.loads(raw) if factor == "lighting" else read_csv(raw)
    suffix = "json" if factor == "lighting" else "csv"
    relative_original, digest = archive_original(raw, directory, suffix)
    groups = {}
    for row in rows:
        code = str(row.get("insttCode" if factor == "lighting" else "개방자치단체코드", "")).strip()
        if code not in agencies:
            continue
        if factor == "cctv" and row.get("설치목적구분", "").strip() != "생활방범":
            continue
        groups.setdefault(code, []).append(row)
    records = []
    for code, group in sorted(groups.items()):
        name, geometry = agencies[code]
        boundary = shape(geometry)
        points, dates, missing, undated, outside = set(), [], 0, 0, 0
        broken = 0
        for row in group:
            try:
                dates.append(date.fromisoformat(row.get("referenceDate" if factor == "lighting" else "데이터기준일자", "").strip()).isoformat())
            except (ValueError, TypeError, AttributeError):
                undated += 1
            if factor == "bell" and row.get("최종점검결과구분", "").strip() == "N":
                broken += 1
                continue
            try:
                lat = float(row.get("latitude" if factor == "lighting" else "WGS84위도"))
                lng = float(row.get("longitude" if factor == "lighting" else "WGS84경도"))
                if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
                    raise ValueError("Invalid coordinate")
                if not boundary.covers(Point(lng, lat)):
                    outside += 1
                points.add((lat, lng))
            except (ValueError, TypeError):
                missing += 1
        point_bytes = json.dumps(sorted(points), separators=(",", ":")).encode()
        point_sha = hashlib.sha256(point_bytes).hexdigest()
        atomic_json(directory / "objects" / f"{point_sha}.json", sorted(points))
        evidence = {"status": "complete", "method": "official_api" if factor == "lighting" else "official_csv",
                    "original_sha256": digest, "original_file": relative_original,
                    "download_url": download_url or SOURCE_URLS[factor], "retrieved_at": retrieved_at,
                    "scope": {"agency_code": code, "agency_name": name},
                    "expected_records": len(group), "received_records": len(group), "file_total_records": len(rows),
                    "coordinate_missing": missing, "coordinate_outside_scope": outside,
                    "date_missing": undated, "unique_points": len(points),
                    "basis_date_min": min(dates) if dates else None, "basis_date_max": max(dates) if dates else None,
                    "real_world_completeness": "unknown"}
        if response_pages:
            evidence["response_pages"] = response_pages
        if boundary_evidence:
            evidence["boundary_evidence"] = boundary_evidence
        if factor == "bell":
            evidence.update(known_nonworking=broken,
                            inspection_results=dict(Counter(r.get("최종점검결과구분", "") for r in group)),
                            police_linked=sum(r.get("경찰연계유무", "").strip() == "Y" for r in group),
                            installation_place_types=dict(Counter(r.get("설치장소유형", "") for r in group)))
        record = {"source_id": f"official-{factor}-{code}", "factor": factor,
                  "source_url": SOURCE_URLS[factor], "observed_at": max(dates) if dates else "", "retrieved_at": retrieved_at,
                  "sha256": point_sha, "points_file": f"objects/{point_sha}.json", "coordinate_crs": "EPSG:4326",
                  "coverage_geometry": geometry, "coverage_basis": "declared_agency_boundary",
                  "collection_evidence": evidence,
                  "completeness": "verified_collection" if points and not (missing or undated) and (factor != "lighting" or response_pages) else "partial"}
        if factor == "cctv":
            record["purpose"] = "crime_prevention"
        records.append(record)
    atomic_json(directory / "receipts" / f"{factor}-{digest}.json", {
        "source_url": SOURCE_URLS[factor], "download_url": download_url or SOURCE_URLS[factor],
        "original_sha256": digest, "retrieved_at": retrieved_at, "total_rows": len(rows),
        "sources": [r["collection_evidence"] for r in records]})
    return records


if __name__ == "__main__":
    main()
