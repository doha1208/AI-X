from app.services.road_score import road_safety_score


def test_lit_road_beats_unlit_road_at_night():
    lit = road_safety_score({"highway": "residential", "lit": "yes"}, "night")
    unlit = road_safety_score({"highway": "residential", "lit": "no"}, "night")
    assert lit > unlit


def test_lighting_matters_less_by_day_than_at_night():
    def gap(period):
        return road_safety_score({"highway": "residential", "lit": "yes"}, period) - road_safety_score(
            {"highway": "residential", "lit": "no"}, period
        )

    assert gap("night") > gap("day")


def test_main_street_with_sidewalk_beats_footpath():
    street = road_safety_score({"highway": "tertiary", "sidewalk": "both"}, "night")
    trail = road_safety_score({"highway": "path"}, "night")
    assert street > trail


def test_dead_end_is_penalised():
    tags = {"highway": "residential"}
    assert road_safety_score(tags, "night", dead_end=True) < road_safety_score(tags, "night")


def test_merged_edge_with_list_tags_uses_the_worst_case():
    # osmnx가 간선을 합치면 서로 다른 태그 값이 리스트로 들어온다
    mixed = road_safety_score({"highway": ["residential", "path"], "lit": ["yes", "no"]}, "night")
    good = road_safety_score({"highway": "residential", "lit": "yes"}, "night")
    bad = road_safety_score({"highway": "path", "lit": "no"}, "night")
    assert mixed == bad < good


def test_unknown_tags_are_neutral_and_score_stays_in_range():
    assert 0 <= road_safety_score({}, "day") <= 100
    assert 0 <= road_safety_score({"highway": "track", "lit": "no"}, "night", dead_end=True) <= 100
