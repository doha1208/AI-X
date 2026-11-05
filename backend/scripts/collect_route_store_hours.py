"""Acquire published chain schedules; never infer weekdays, staffing or all-shop coverage."""
import argparse
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
import time
import urllib.parse

from app.services.route_build_state import builder_lock
from app.services.route_environment_inputs import atomic_json
from scripts.collect_route_public_sources import cached_download

SOURCE = "https://m.emart24.co.kr/store"
API = "https://m.emart24.co.kr/api1/store"


def normalize_place(row: dict) -> dict:
    full_time = row.get("SVR_24") in (1, "1")
    start, end = str(row.get("START_HHMM", "")), str(row.get("END_HHMM", ""))
    def hhmm(value):
        return bool(re.fullmatch(r"(?:[01]\d|2[0-3])[0-5]\d", value))
    hours = ["00:00", "24:00"] if full_time else [f"{start[:2]}:{start[2:]}", f"{end[:2]}:{end[2:]}"] if hhmm(start) and hhmm(end) and start != end else None
    try:
        lat, lng = float(row["LATITUDE"]), float(row["LONGITUDE"])
        point = [lat, lng] if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180 else None
    except (KeyError, ValueError, TypeError):
        point = None
    return {"source_id": "emart24-" + str(row["CODE"]), "name": row.get("TITLE"),
            "address": row.get("ADDRESS"), "address_detail": row.get("ADDRESS_DE"), "point": point,
            "source_url": f"{SOURCE}/{row['CODE']}", "hours_status": "published_schedule" if hours else "unknown",
            "published_hours": hours, "published_24_hours": full_time, "weekdays": None,
            "unmanned_capable": row.get("SVR_AUTO") in (1, "1"), "staffed": None,
            "business_open_date": row.get("OPEN_DATE"), "business_end_date": row.get("END_DATE")}


def parse_response(raw: bytes) -> dict:
    data = json.loads(raw)
    if data.get("error") != 0 or not isinstance(data.get("data"), list) or not isinstance(data.get("count"), int):
        raise ValueError("Store hours service did not return a successful list")
    return data


def collect_pages(fetch_page) -> list[dict]:
    first = fetch_page(1)
    total = int(first["count"])
    size = len(first["data"])
    if total and not size:
        raise ValueError("incomplete store hours response")
    rows = []
    for page in range(1, max(1, math.ceil(total / size) if size else 1) + 1):
        response = first if page == 1 else fetch_page(page)
        if response.get("error") != 0 or response["count"] != total or len(response["data"]) != min(size, total - len(rows)):
            raise ValueError("incomplete store hours pagination")
        rows.extend(response["data"])
    if len({r["CODE"] for r in rows}) != total:
        raise ValueError("incomplete store hours: duplicate IDs")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/osm/store_hours"))
    parser.add_argument("--search", default="경기도")
    args = parser.parse_args()
    with builder_lock(args.directory) as acquired:
        if not acquired:
            raise SystemExit("store_hours_collection_already_running")
        captures = []
        cache = args.directory / "downloads" / datetime.now(UTC).strftime("%Y%m%d") / args.search
        def fetch(page):
            url = API + "?" + urllib.parse.urlencode({"page": page, "search": args.search, "AREA1": "", "AREA2": "", "top": "", "bottom": "", "left": "", "right": ""})
            raw, captured = cached_download(url, cache / f"{page}.json", validator=parse_response, referer=SOURCE)
            captures.append(captured)
            time.sleep(0.1)
            return parse_response(raw)
        rows = collect_pages(fetch)
        places = [normalize_place(r) for r in rows if str(r.get("ADDRESS", "")).startswith("경기도")]
        payload = {"source_url": SOURCE, "retrieved_at": min(captures), "query": args.search,
                   "reported_result_count": len(rows), "places": places,
                   "coverage_status": "one_chain_subset", "weekday_status": "not_provided", "staffing_status": "unverified"}
        atomic_json(args.directory / "place_hours.json", payload)
    print(f"Published schedules: {sum(p['hours_status'] == 'published_schedule' for p in places)}/{len(places)} stores; weekdays and staffing remain unverified")


if __name__ == "__main__":
    main()
