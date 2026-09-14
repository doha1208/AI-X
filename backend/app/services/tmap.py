import httpx

from app.core.config import settings

TMAP_PEDESTRIAN_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"


async def get_pedestrian_route(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> list[tuple[float, float]] | None:
    """Tmap 보행자 경로안내 API로 실제 도보 경로 좌표를 가져온다.

    ponytail: 키 미설정/API 실패 시 None 반환 → 호출부에서 직선 샘플링으로 폴백.
    """
    if not settings.tmap_app_key:
        return None

    payload = {
        "startX": start_lng,
        "startY": start_lat,
        "endX": end_lng,
        "endY": end_lat,
        "startName": "출발지",
        "endName": "도착지",
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "0",
    }
    headers = {"appKey": settings.tmap_app_key, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.post(TMAP_PEDESTRIAN_URL, json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()
    except (httpx.HTTPError, ValueError):
        return None

    points: list[tuple[float, float]] = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "LineString":
            continue
        for lng, lat in geometry.get("coordinates", []):
            points.append((lat, lng))

    return points or None
