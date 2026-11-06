"""Read prepared weekday summaries without re-evaluating walking geometry."""
from collections import defaultdict
from hashlib import sha256
import json
from math import floor, isfinite

from app.schemas.safety import FacilityBasisGroup, FacilityZone, FacilityZoneAssessment, FacilityZoneComparison, FacilityZonePeriods, FacilityZoneResponse
from app.services.zone_environment_summaries import SCHEDULE_VERSION

MIN_RELATIVE_GROUP_SIZE = 20


class ComparisonBasisChanged(ValueError):
    def __init__(self, groups: list[FacilityBasisGroup]):
        super().__init__("comparison_basis_changed")
        self.groups = groups


def _prepared(snapshot):
    artifact = snapshot.artifact if snapshot is not None else None
    summaries = artifact.zone_facility_summaries if artifact and artifact.schema_version == 4 else {}
    return artifact, summaries


def _assessment(artifact, summaries, code, weekday, period):
    hour = 12 if period == "day" else 23
    meta = {"artifact_version": artifact.version if artifact else None,
            "schedule_key": f"{SCHEDULE_VERSION}:{weekday}:{period}:{hour}"}
    raw = summaries.get((code, weekday, period))
    if raw:
        reason = raw.get("unavailable_reason")
        if reason == "boundary_missing" and code in artifact.boundary_diagnostics.get("invalid_codes", []):
            reason = "boundary_invalid"
        return FacilityZoneAssessment.model_validate({
            **raw, **meta, "basis_id": raw.get("comparison_basis_id"), "unavailable_reason": reason,
        })
    if not summaries:
        return FacilityZoneAssessment(status="pending", unavailable_reason="zone_artifact_pending", **meta)
    diagnostics = artifact.boundary_diagnostics
    reason = "boundary_invalid" if code in diagnostics.get("invalid_codes", []) else (
        "boundary_missing" if code in diagnostics.get("missing_codes", []) else "zone_summary_missing"
    )
    return FacilityZoneAssessment(status="unavailable", unavailable_reason=reason, **meta)


def facility_zone_periods(*, snapshot, dong_code, weekday):
    artifact, summaries = _prepared(snapshot)
    return FacilityZonePeriods(**{
        period: _assessment(artifact, summaries, dong_code, weekday, period) for period in ("day", "night")
    })


def _compare(by_code, codes):
    rows = [by_code[code].assessment for code in codes]
    factors = sorted(set.intersection(*(set(row.used_factors) & row.factor_coverage.keys() for row in rows)))
    scores = {code: 100 * sum(row.factor_coverage[factor] for factor in factors) / len(factors)
              for code, row in zip(codes, rows)} if factors else {}
    return FacilityZoneComparison(dong_codes=codes, used_factors=factors, scores=scores,
        evaluation_basis="multi_factor" if len(factors) >= 2 else "single_factor" if factors else "not_comparable")


def _rank_group(rows: list[FacilityZone], group: FacilityBasisGroup) -> list[FacilityZone]:
    by_score: dict[int, list[FacilityZone]] = defaultdict(list)
    for row in rows:
        score = row.assessment.score
        assert score is not None  # Only eligible multi-factor rows enter a group.
        by_score[floor(score + .5)].append(row)

    count = len(rows)
    if count < MIN_RELATIVE_GROUP_SIZE:
        group.relative_status = "insufficient_group"
    elif len(by_score) == 1:
        group.relative_status = "no_variation"
    else:
        group.relative_status = "available"

    ranked: list[FacilityZone] = []
    for score in sorted(by_score, reverse=True):
        tied_rows = sorted(by_score[score], key=lambda row: row.dong_code)
        rank = len(ranked) + 1
        lower_count = count - len(ranked) - len(tied_rows)
        percentile = (round(100 * (lower_count + len(tied_rows) / 2) / count, 1)
                      if group.relative_status == "available" else None)
        for row in tied_rows:
            row.rank = rank
            row.rank_tied = len(tied_rows) > 1
            row.relative_percentile = percentile
        ranked.extend(tied_rows)
    return ranked


def list_facility_zones(*, snapshot, zones, period, weekday, basis_id=None, compare_codes=()) -> FacilityZoneResponse:
    artifact, summaries = _prepared(snapshot)
    members, by_code = defaultdict(list), {}
    for zone in zones:
        code = zone.dong_code
        assessment = _assessment(artifact, summaries, code, weekday, period)
        row = FacilityZone(dong_code=code, dong_name=zone.dong_name, lat=zone.lat, lng=zone.lng, assessment=assessment)
        by_code[code] = row
        if (assessment.basis_id and assessment.evaluation_basis == "multi_factor"
                and len(assessment.used_factors) >= 2 and assessment.score is not None and isfinite(assessment.score)):
            members[assessment.basis_id].append(row)
    groups = []
    for basis, rows in members.items():
        sources = {}
        for row in rows:
            sources.update(summaries[(row.dong_code, weekday, period)].get("source_versions", {}))
        identity = json.dumps([basis, artifact.version, sources], sort_keys=True).encode()
        group = FacilityBasisGroup(basis_id=basis, result_group_id=sha256(identity).hexdigest()[:24],
            used_factors=sorted(rows[0].assessment.used_factors), zone_count=len(rows))
        groups.append(group)
        for row in rows:
            row.result_group_id = group.result_group_id
    groups.sort(key=lambda group: (-group.zone_count, group.used_factors, group.basis_id))
    if basis_id is not None and basis_id not in members:
        raise ComparisonBasisChanged(groups)
    selected = basis_id or (groups[0].basis_id if groups else None)
    selected_group = next((group for group in groups if group.basis_id == selected), None)
    ranked = _rank_group(members[selected_group.basis_id], selected_group) if selected_group else []
    remaining = sorted((row for row in by_code.values() if row.rank is None), key=lambda row: (row.dong_name, row.dong_code))
    return FacilityZoneResponse(status="available" if summaries else "pending", period=period, weekday=weekday,
        reference_hour=12 if period == "day" else 23, basis_id=selected, artifact_version=artifact.version if artifact else None,
        relative_method="midrank-percentile-v1" if selected_group else None,
        groups=groups, zones=ranked + remaining, comparison=_compare(by_code, compare_codes) if len(compare_codes) >= 2 else None)
