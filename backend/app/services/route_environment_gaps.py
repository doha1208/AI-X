"""Continuous gaps use route chainage, not graph-edge identities."""


def _intervals(cells, covered):
    intervals = []
    for cell, present in zip(cells, covered):
        if present:
            continue
        if intervals and abs(intervals[-1]["end_m"] - cell.start_m) < 1e-6:
            intervals[-1]["end_m"] = cell.end_m
        else:
            intervals.append({"start_m": cell.start_m, "end_m": cell.end_m})
    return intervals


def summarize_gaps(cells, observations, *, period, common_factors):
    pair = ("lighting", "open_store") if period == "night" else ("cctv", "open_store")
    per_factor = {k: _intervals(cells, observations[k]) for k in common_factors}
    if not cells or not set(pair).issubset(common_factors):
        return dict(longest_support_gap_m=None, total_support_gap_m=None, gap_intervals=[], per_factor_gaps=per_factor)
    intervals = _intervals(cells, [a or b for a, b in zip(observations[pair[0]], observations[pair[1]])])
    lengths = [v["end_m"] - v["start_m"] for v in intervals]
    return dict(longest_support_gap_m=max(lengths, default=0.0), total_support_gap_m=sum(lengths),
                gap_intervals=intervals, per_factor_gaps=per_factor)
