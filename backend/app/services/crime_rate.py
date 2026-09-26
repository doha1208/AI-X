"""시·군·구 범죄 건수를 인구로 나눈 1만 명당 범죄율.

범죄 통계는 시·군·구 단위 총건수라, 인구가 적은 지역이 (건수가 적다는 이유로) 안전해 보이는
왜곡이 있었다 — 인구로 나눠 지역 규모를 보정한다.

주민등록인구(등록 기준, 정적)만 쓰면 유동인구가 많은 도심은 범죄율이 실제보다 높게 나온다
— 경기데이터드림 행정동 단위 시간대별 유동인구가 있는 구는 이 값으로 대신 보정한다
(parse_floating_population_csv). 데이터가 없는 구(주로 서울)는 등록인구를 그대로 쓴다.
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


def parse_floating_population_csv(path: Path) -> dict[str, float]:
    """경기데이터드림 행정동 단위 시간대별 유동인구 CSV -> {구/시 이름: 평균 체류인구}.

    각 행은 (행정동, 날짜, 시간대, 내외국인구분)별 연령·성별 인구수다. 구 단위로 다 더한 뒤
    (날짜, 시간대) 조합 수로 나눠 '그 구에 평균적으로 몇 명이 머무는지'를 근사한다 — 등록인구처럼
    한 시점의 정적 headcount가 아니라 하루 중 시간대별 실제 체류 인구의 평균이다.

    범죄 통계는 구가 나뉜 시(수원시 등)도 시 단위 합계 하나로만 나온다 — "수원시 영통구" 같은
    구 단위 값과 별도로, 같은 시에 속한 구를 다 더한 시 단위("수원시") 값도 함께 반환한다.
    """
    with path.open(encoding="cp949", newline="") as f:
        reader = csv.DictReader(f)
        age_gender_cols = [c for c in reader.fieldnames if c.endswith("인구수")]
        gu_totals: dict[str, float] = {}
        gu_periods: dict[str, set[tuple[str, str]]] = {}
        city_totals: dict[str, float] = {}
        city_periods: dict[str, set[tuple[str, str]]] = {}
        for row in reader:
            gu = row["시군구명"].strip()
            city = gu.split()[0]
            period = (row["기준년월일"], row["시간대별"])
            value = sum(float(row[c]) for c in age_gender_cols)
            gu_totals[gu] = gu_totals.get(gu, 0.0) + value
            gu_periods.setdefault(gu, set()).add(period)
            city_totals[city] = city_totals.get(city, 0.0) + value
            city_periods.setdefault(city, set()).add(period)

    result = {gu: gu_totals[gu] / len(gu_periods[gu]) for gu in gu_totals}
    result.update({city: city_totals[city] / len(city_periods[city]) for city in city_totals})
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
