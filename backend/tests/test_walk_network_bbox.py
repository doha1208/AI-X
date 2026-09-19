import re
from pathlib import Path

from app.services import safe_route as sr
from scripts import build_dong_grid

EXTRACT_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "extract_seoul_walk_network.py"


def test_route_network_bbox_matches_dong_grid_bbox():
    # 격자(동 조회)와 도로망(경로 탐색)의 범위가 다르면 한쪽에서만 데이터가 있는 구간이 생긴다.
    assert sr.LOCAL_WALK_NETWORK_BBOX == build_dong_grid.BBOX


def test_route_network_bbox_matches_extract_script():
    # osmium이 없는 환경에서도 돌도록 스크립트를 import하지 않고 텍스트에서 읽는다.
    text = EXTRACT_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^BBOX = \(([^)]*)\)", text, re.MULTILINE)
    assert match, "extract script BBOX not found"
    extracted = tuple(float(v) for v in match.group(1).split(","))
    assert sr.LOCAL_WALK_NETWORK_BBOX == extracted


def test_route_network_file_is_the_one_the_extract_script_writes():
    text = EXTRACT_SCRIPT.read_text(encoding="utf-8")
    assert f'DATA_DIR / "{sr.LOCAL_WALK_NETWORK_PATH.name}"' in text
