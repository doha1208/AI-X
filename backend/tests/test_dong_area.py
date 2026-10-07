import math

from app.services.dong_area import estimate_dong_areas_km2


def test_estimated_area_sums_the_grid_cells_assigned_to_each_dong():
    cells = {
        "37.0:127.0": {"dong_code": "A"},
        "37.0:127.005": {"dong_code": "A"},
        "37.0:127.01": {"dong_code": "B"},
    }

    areas = estimate_dong_areas_km2(0.005, cells)

    assert math.isclose(areas["A"], areas["B"] * 2, rel_tol=1e-9)
    assert areas["A"] > 0
