"""행정동 격자에서 점수 계산용 면적을 추정한다.

원본 시설 개수는 그대로 보존하고, CCTV·보안등·상점처럼 행정동 크기에 따라
커지는 값만 km²당 밀도로 바꿀 때 사용한다. 정밀 측량 면적이 아니라
``dong_grid.json``에서 해당 동에 배정된 격자 셀 면적의 합이다.
"""

import json
import math
from functools import lru_cache
from pathlib import Path


GRID_PATH = Path(__file__).resolve().parent.parent / "data" / "dong_grid.json"
_KM_PER_DEG_LAT = 111.32


def estimate_dong_areas_km2(step: float, cells: dict) -> dict[str, float]:
    """격자 셀 중심 위도와 간격으로 동별 근사 면적(km²)을 계산한다."""

    areas: dict[str, float] = {}
    lat_height_km = step * _KM_PER_DEG_LAT
    for key, cell in cells.items():
        try:
            cell_lat = float(key.split(":", 1)[0])
            dong_code = cell["dong_code"]
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        lng_width_km = step * _KM_PER_DEG_LAT * math.cos(math.radians(cell_lat))
        areas[dong_code] = areas.get(dong_code, 0.0) + lat_height_km * lng_width_km
    return areas


@lru_cache(maxsize=1)
def load_dong_areas_km2(path: Path = GRID_PATH) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return estimate_dong_areas_km2(float(data["step"]), data["cells"])
