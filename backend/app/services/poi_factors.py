import math

import numpy as np
from scipy.spatial import cKDTree

# 이보다 먼 경찰서는 "멀다"로 똑같이 취급한다(이상치가 min-max 정규화를 망치지 않게).
POLICE_DIST_CAP_M = 3000.0

_M_PER_DEG_LAT = 111_320.0
# 서울·경기(위도 약 37.5도)에서 경도 1도의 길이 보정.
_LNG_SCALE = math.cos(math.radians(37.5))

Point = tuple[float, float]


def to_meters(points) -> np.ndarray:
    """(lat, lng) 목록/배열을 서로 거리를 미터로 잴 수 있는 평면 좌표 (n, 2)로 바꾼다."""
    arr = np.asarray(points, dtype=float).reshape(-1, 2)
    return np.column_stack((arr[:, 0] * _M_PER_DEG_LAT, arr[:, 1] * _M_PER_DEG_LAT * _LNG_SCALE))


def nearest_police_distances_m(centroids: list[Point], police_points: list[Point]) -> list[float]:
    """각 (lat, lng) 지점에서 가장 가까운 경찰서/파출소까지의 거리(m). CAP으로 상한."""
    if not police_points:
        return [POLICE_DIST_CAP_M] * len(centroids)
    tree = cKDTree(to_meters(police_points))
    dists, _ = tree.query(to_meters(centroids))
    return [min(float(d), POLICE_DIST_CAP_M) for d in dists]
