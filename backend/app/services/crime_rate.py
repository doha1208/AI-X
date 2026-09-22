"""시·군·구 범죄 건수를 주민등록 인구로 나눈 1만 명당 범죄율.

범죄 통계는 시·군·구 단위 총건수라, 인구가 적은 지역이 (건수가 적다는 이유로) 안전해 보이는
왜곡이 있었다 — 인구로 나눠 지역 규모를 보정한다.

ponytail: 범죄는 '발생지' 기준이고 인구는 '주민등록' 기준이라 유동인구가 많은 도심(중구·종로구·
강남구 등)은 범죄율이 실제보다 높게 나온다. 유동인구 보정은 하지 않았다.
"""
import csv
import re
from pathlib import Path

# 범죄 통계에 있는 서울·경기만 쓴다.
_SIDO_PREFIXES = ("서울특별시 ", "경기도 ")
_TRAILING_CODE = re.compile(r"\s*\(\d+\)\s*$")  # "수원시 (4111000000)"의 행정코드
_TOTAL_POPULATION_SUFFIX = "_총인구수"


def _to_int(cell: str) -> int:
    return int(cell.replace(",", "").strip())


def parse_population_csv(path: Path) -> dict[str, float]:
    """행정안전부 주민등록 인구 및 세대현황(월간, 여러 달) CSV -> {지역명: 기간 평균 총인구}.

    지역명은 시도 접두어를 뗀 형태("종로구", "수원시", "수원시 장안구")다.
    """
    with path.open(encoding="cp949", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        total_cols = [i for i, name in enumerate(header) if name.endswith(_TOTAL_POPULATION_SUFFIX)]
        if not total_cols:
            raise ValueError(f"'{_TOTAL_POPULATION_SUFFIX}' 컬럼이 없음: {path}")

        result: dict[str, float] = {}
        for row in reader:
            if not row:
                continue
            name = " ".join(_TRAILING_CODE.sub("", row[0]).split())
            prefix = next((p for p in _SIDO_PREFIXES if name.startswith(p)), None)
            if prefix is None:
                continue  # 시도 합계 행("서울특별시")이거나 서울·경기 밖
            monthly = [_to_int(row[i]) for i in total_cols if i < len(row) and row[i].strip()]
            if monthly:
                result[name[len(prefix):]] = sum(monthly) / len(monthly)
    return result


def region_key_for(gu_name: str, known: set[str]) -> str:
    """동 격자의 지역명("수원시 장안구")을 통계가 쓰는 단위("수원시")로 맞춘다.

    범죄 통계와 인구를 같은 단위로 묶기 위해, 그대로 없으면 시 단위(첫 토큰)로 올린다.
    어디에도 없으면 조용히 0으로 처리하지 않고 KeyError로 알린다.
    """
    if gu_name in known:
        return gu_name
    city = gu_name.split()[0]
    if city in known:
        return city
    raise KeyError(f"통계에 없는 지역: {gu_name}")


def crime_rate_per_10k(crime_count: float, population: float) -> float:
    if population <= 0:
        raise ValueError("인구가 0 이하")
    return crime_count / population * 10_000
