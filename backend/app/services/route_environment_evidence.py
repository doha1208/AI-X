"""Compatibility adapter for the common facility evidence calculation."""
from app.services.facility_assessment import AssessmentSample, observe_facilities, summarize_facility_evidence


def assess_available_evidence(cells, *, at, period, policy, indexes):
    samples = [AssessmentSample(str(i), c.midpoint, c.end_m - c.start_m) for i, c in enumerate(cells)]
    observations = observe_facilities([s.point for s in samples], at=at, period=period, policy=policy, indexes=indexes)
    return summarize_facility_evidence(samples, observations, active_factors=policy.active_factors(period))
