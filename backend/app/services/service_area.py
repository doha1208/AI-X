"""서울·경기 서비스 범위를 런타임 요청 좌표에 적용한다."""

import json
from functools import lru_cache
from pathlib import Path


SERVICE_AREA_GRID_PATH = Path(__file__).resolve().parent.parent / "data" / "dong_grid.json"


@lru_cache(maxsize=1)
def _load_service_area_grid() -> tuple[float, dict[str, dict], tuple[float, float, float, float]]:
    data = json.loads(SERVICE_AREA_GRID_PATH.read_text(encoding="utf-8"))
    return float(data["step"]), data["cells"], tuple(data["bbox"])


def service_area_dong(lat: float, lng: float, *, region_scope_prefix: str = "") -> dict | None:
    """좌표가 서울·경기 행정동 격자에 속하면 해당 동을 반환한다.

    생성 중 일시적으로 비어 있던 경계 칸은 데이터 적재와 같은 방식으로 인접 3x3
    칸에서 보완하되, 서울·경기가 아닌 칸은 격자에 없으므로 서비스 범위로 인정하지 않는다.
    """

    step, cells, bbox = _load_service_area_grid()
    west, south, east, north = bbox
    if not (west - step <= lng <= east + step and south - step <= lat <= north + step):
        return None

    grid_lat = round(round((lat - south) / step) * step + south, 5)
    grid_lng = round(round((lng - west) / step) * step + west, 5)
    candidates: list[dict] = []
    for dlat in (-step, 0.0, step):
        for dlng in (-step, 0.0, step):
            key = f"{round(grid_lat + dlat, 5)}:{round(grid_lng + dlng, 5)}"
            cell = cells.get(key)
            if cell and (
                not region_scope_prefix or str(cell.get("dong_code", "")).startswith(region_scope_prefix)
            ):
                candidates.append(cell)

    if not candidates:
        return None
    return min(
        candidates,
        key=lambda cell: (float(cell["lat"]) - lat) ** 2 + (float(cell["lng"]) - lng) ** 2,
    )


def is_in_service_area(lat: float, lng: float, *, region_scope_prefix: str = "") -> bool:
    return service_area_dong(lat, lng, region_scope_prefix=region_scope_prefix) is not None
