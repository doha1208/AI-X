"""주소 문자열을 카카오 주소검색 질의로 만들고, 그 응답에서 좌표를 꺼낸다(네트워크 호출은 스크립트 몫).

보안등 표준데이터에는 좌표 없이 주소만 올린 지자체(강남·마포·용산·고양·김포 등)가 있어서,
scripts/geocode_light_addresses.py가 이 함수들로 주소를 좌표로 바꾼다.
"""
import re

Point = tuple[float, float]

_BUILDING_NUMBER = re.compile(r"\d+(-\d+)?")
_ROAD_NAME_END = re.compile(r"(로|길)\d*$")  # "양화로", "양화로15길"
# 구/군 이름(앞에 한글 1~5자가 있어야 함) 바로 뒤에 공백 없이 동/읍/면/리가 붙은 경우.
_MISSING_DISTRICT_SPACE = re.compile(r"\b([가-힣]{1,5}(?:구|군))([가-힣0-9]+(?:동|읍|면|리|가))\b")


def _without_trailing_name(road: str) -> str:
    """"양화로 129 디키즈코리아" -> "양화로 129" (건물번호 뒤의 상호·층 등을 뗀다)."""
    tokens = road.split()
    for i in range(1, len(tokens)):
        if _BUILDING_NUMBER.fullmatch(tokens[i]) and _ROAD_NAME_END.search(tokens[i - 1]):
            return " ".join(tokens[: i + 1])
    return road


def _with_district_space(address: str) -> str:
    """"용산구한남동" -> "용산구 한남동" (구/군과 동/읍/면/리가 붙어서 들어온 주소를 바로잡는다)."""
    return _MISSING_DISTRICT_SPACE.sub(r"\1 \2", address)


def query_candidates(jibun: str, road: str) -> list[str]:
    """시도할 주소 질의를 정확한 것부터 나열한다(빈 값·중복 제외).

    지번주소 -> 띄어쓰기를 바로잡은 지번주소 -> 도로명주소 -> 도로명주소에서 끝의 상호명을 뗀 것 순서.
    """
    jibun, road = jibun.strip(), road.strip()
    ordered = [jibun, _with_district_space(jibun), road, _without_trailing_name(road) if road else ""]
    seen: set[str] = set()
    result: list[str] = []
    for query in ordered:
        if query and query not in seen:
            seen.add(query)
            result.append(query)
    return result


def parse_address_response(payload: dict) -> Point | None:
    """카카오 주소검색 응답의 첫 결과를 (lat, lng)로. 결과가 없으면 None."""
    documents = payload.get("documents") or []
    if not documents:
        return None
    first = documents[0]
    return float(first["y"]), float(first["x"])
