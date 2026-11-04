import csv
import io
import json

import pytest

from scripts import collect_route_public_sources as collect


AREA = {"type": "Polygon", "coordinates": [[[126, 37], [128, 37], [128, 38], [126, 38], [126, 37]]]}


def csv_bytes(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("cp949")


def row(**changes):
    record = {"개방자치단체코드": "4060000", "설치목적구분": "생활방범", "WGS84위도": "37.5", "WGS84경도": "127.0", "데이터기준일자": "2026-06-30", "관리기관명": "경기도 파주시"}
    record.update(changes)
    return record


def test_reads_real_cp949_headers_and_rejects_html():
    assert collect.read_csv(csv_bytes([row()]))[0]["관리기관명"] == "경기도 파주시"
    with pytest.raises(ValueError, match="CSV"):
        collect.read_csv(b"<!DOCTYPE html><html>unavailable</html>")


def test_complete_official_collection_is_not_claimed_as_real_world_census(tmp_path):
    records = collect.publish_collection(csv_bytes([row(), row()]), factor="cctv", agencies={"4060000": ("파주시", AREA)}, directory=tmp_path)
    source = records[0]
    assert source["completeness"] == "verified_collection"
    assert source["collection_evidence"]["received_records"] == 2
    assert source["collection_evidence"]["coordinate_missing"] == 0
    assert source["collection_evidence"]["real_world_completeness"] == "unknown"
    assert source["purpose"] == "crime_prevention"
    assert json.loads((tmp_path / source["points_file"]).read_text()) == [[37.5, 127.0]]


def test_missing_coordinates_or_dates_do_not_become_verified_or_zero(tmp_path):
    records = collect.publish_collection(csv_bytes([row(), row(WGS84위도=""), row(데이터기준일자="")]), factor="cctv", agencies={"4060000": ("파주시", AREA)}, directory=tmp_path)
    source = records[0]
    assert source["completeness"] == "partial"
    assert source["collection_evidence"]["coordinate_missing"] == 1
    assert source["collection_evidence"]["date_missing"] == 1
    assert source["coverage_geometry"] == AREA


def test_preserves_cctv_purpose_and_does_not_invent_unsubmitted_city(tmp_path):
    records = collect.publish_collection(csv_bytes([row(설치목적구분="교통단속")]), factor="cctv", agencies={"4060000": ("파주시", AREA), "999": ("누락시", AREA)}, directory=tmp_path)
    assert records == []


def test_lighting_api_detects_incomplete_pagination():
    pages = {1: {"totalCount": 3, "items": {"item": [{"latitude": "37.5", "longitude": "127"}]}}, 2: {"totalCount": 3, "items": {"item": []}}}
    with pytest.raises(ValueError, match="incomplete"):
        collect.collect_light_pages(lambda page: pages[page], page_size=2)


def test_lighting_api_preserves_reference_date_and_agency():
    item = {"latitude": "37.5", "longitude": "127", "referenceDate": "2026-07-01", "insttCode": "4060000", "institutionNm": "파주시", "lnmadr": "경기도 파주시"}
    rows = collect.collect_light_pages(lambda _: {"totalCount": 1, "items": {"item": item}})
    assert rows == [item]


def test_regional_boundaries_combine_city_districts_without_other_cities():
    geojson = {"features": [{"properties": {"sggnm": "수원시장안구"}, "geometry": AREA}, {"properties": {"sggnm": "파주시"}, "geometry": AREA}]}
    result = collect.agency_boundaries(geojson, {"4060000": "경기파주시"})
    assert list(result) == ["4060000"]
    assert result["4060000"][0] == "파주시"


def test_failed_download_does_not_replace_a_valid_cached_original(tmp_path, monkeypatch):
    good = csv_bytes([row()])
    monkeypatch.setattr(collect, "request_bytes", lambda *a, **k: good)
    path = tmp_path / "source.csv"
    raw, captured = collect.cached_download("https://file.localdata.go.kr/test", path, validator=collect.read_csv)
    assert raw == good
    monkeypatch.setattr(collect, "request_bytes", lambda *a, **k: b"<html>error</html>")
    with pytest.raises(ValueError, match="CSV"):
        collect.cached_download("https://file.localdata.go.kr/test", path, validator=collect.read_csv, refresh=True)
    assert path.read_bytes() == good
    assert collect.cached_download("https://file.localdata.go.kr/test", path, validator=collect.read_csv)[1] == captured


def test_download_cache_checks_content_hash(tmp_path, monkeypatch):
    good = csv_bytes([row()])
    monkeypatch.setattr(collect, "request_bytes", lambda *a, **k: good)
    path = tmp_path / "source.csv"
    collect.cached_download("https://file.localdata.go.kr/test", path, validator=collect.read_csv)
    path.write_bytes(b"broken")
    assert collect.cached_download("https://file.localdata.go.kr/test", path, validator=collect.read_csv)[0] == good


def test_refresh_keeps_previous_manifest_on_download_failure(tmp_path, monkeypatch):
    manifest = tmp_path / "environment_sources.json"
    manifest.write_text('{"schema_version":1,"sources":[]}', encoding="utf-8")
    original = manifest.read_bytes()
    monkeypatch.setattr(collect, "cached_download", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("official_download_http_503")))
    report = collect.refresh_sources(tmp_path, {}, factors=["cctv"])
    assert report["errors"]
    assert manifest.read_bytes() == original


def test_parses_agency_scope_from_official_options():
    html = '<option value="6410000_ALL">경기도</option><option data-upper="6410000_ALL" value="4060000">경기파주시</option><option data-upper="6110000_ALL" value="3000000">서울</option>'
    assert collect.parse_agencies(html.encode()) == {"4060000": "경기파주시"}


def test_known_broken_bells_do_not_add_access_but_inspection_evidence_is_kept(tmp_path):
    raw = csv_bytes([row(최종점검결과구분="Y"), row(최종점검결과구분="N", WGS84위도="37.6")])
    records = collect.publish_collection(raw, factor="bell", agencies={"4060000": ("파주시", AREA)}, directory=tmp_path)
    source = records[0]
    assert json.loads((tmp_path / source["points_file"]).read_text()) == [[37.5, 127.0]]
    assert source["collection_evidence"]["known_nonworking"] == 1
    assert source["collection_evidence"]["received_records"] == 2


def test_boundary_mismatch_does_not_discard_an_entire_official_collection(tmp_path):
    records = collect.publish_collection(csv_bytes([row(), row(WGS84경도="128.0001")]), factor="cctv", agencies={"4060000": ("파주시", AREA)}, directory=tmp_path)
    assert records[0]["completeness"] == "verified_collection"
    assert records[0]["collection_evidence"]["coordinate_outside_scope"] == 1


def test_repeated_lighting_page_cannot_be_claimed_complete():
    duplicate = [{"lmpLcNm": "one"}, {"lmpLcNm": "two"}]
    with pytest.raises(ValueError, match="repeated"):
        collect.collect_light_pages(lambda _: {"totalCount": 4, "items": {"item": duplicate}}, page_size=2)


def test_raw_page_evidence_survives_later_downloads(tmp_path):
    first = b'{"header":{"resultCode":"00"},"body":{"totalCount":1}}'
    second = first.replace(b':1', b':2')
    a = collect.archive_response(first, tmp_path, page_no=1, public_url="https://api.data.go.kr/test", retrieved_at="2026-11-04T00:00:00+00:00")
    collect.archive_response(second, tmp_path, page_no=1, public_url="https://api.data.go.kr/test", retrieved_at="2026-11-04T01:00:00+00:00")
    assert (tmp_path / a["file"]).read_bytes() == first


def test_default_collection_uses_unsimplified_boundaries_not_display_geometry(tmp_path, monkeypatch):
    original = {"type": "FeatureCollection", "features": [{"properties": {"sggnm": "파주시", "adm_cd2": "4148000000"}, "geometry": AREA}]}
    calls = []
    def download(url, *args, **kwargs):
        calls.append(url)
        return json.dumps(original).encode(), "2026-11-04T00:00:00+00:00"
    monkeypatch.setattr(collect, "cached_download", download)
    geojson, evidence = collect.load_boundary_source(tmp_path)
    assert geojson == original
    assert calls == [collect.BOUNDARY_SOURCE_URL]
    assert evidence["processing"] == "municipal_union_without_simplification"
    assert (tmp_path / evidence["original_file"]).is_file()
