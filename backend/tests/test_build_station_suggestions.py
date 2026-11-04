from pathlib import Path

from scripts.build_station_suggestions import collect_stations


def test_collect_stations_keeps_named_railway_stations_in_scope(tmp_path: Path, monkeypatch):
    # osmium은 Windows에서 한글 경로를 열지 못한다 — 임시 폴더로 들어가 상대경로를 ASCII로 만든다.
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "stations.osm"
    source.write_text(
        '<osm version="0.6">'
        '<node id="1" lat="37.302813" lon="126.866778"><tag k="railway" v="station"/><tag k="name" v="상록수역"/></node>'
        '<node id="2" lat="37.302820" lon="126.866780"><tag k="railway" v="station"/><tag k="name" v="상록수역"/></node>'
        '<node id="3" lat="37.300000" lon="127.100000"><tag k="railway" v="station"/><tag k="name" v="범위 밖 역"/></node>'
        '<node id="4" lat="37.300000" lon="126.800000"><tag k="railway" v="subway_entrance"/><tag k="name" v="출입구"/></node>'
        '</osm>', encoding="utf-8"
    )

    assert collect_stations(source, in_scope=lambda lat, lng: lng < 127) == [
        {"name": "상록수역", "lat": 37.302813, "lng": 126.866778}
    ]
