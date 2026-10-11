import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DATA = BACKEND_DIR.parent / "frontend" / "public" / "data"
BOUNDARY_FILES = ("seoul-dong-boundaries.geojson", "gyeonggi-dong-boundaries.geojson")


def _grid_dong_codes() -> set[str]:
    cells = json.loads((BACKEND_DIR / "app" / "data" / "dong_grid.json").read_text(encoding="utf-8"))["cells"]
    return {cell["dong_code"] for cell in cells.values()}


def _boundary_features() -> dict[str, dict]:
    features: dict[str, dict] = {}
    for name in BOUNDARY_FILES:
        geojson = json.loads((PUBLIC_DATA / name).read_text(encoding="utf-8"))
        for feature in geojson["features"]:
            features[feature["properties"]["adm_cd2"]] = feature
    return features


def test_every_grid_dong_has_a_boundary_polygon():
    # 폴리곤이 없는 동은 지도에서 원(circle) 폴백으로 그려져 이웃 동과 모양이 어긋난다.
    missing = _grid_dong_codes() - _boundary_features().keys()
    assert not missing, f"{len(missing)} dongs without boundary, e.g. {sorted(missing)[:5]}"


def test_boundary_geometries_are_frontend_drawable():
    for code, feature in _boundary_features().items():
        geometry = feature["geometry"]
        assert geometry["type"] in ("Polygon", "MultiPolygon"), code
        assert geometry["coordinates"], code
