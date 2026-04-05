"""
Form score.
FormScore = Σ(metric_i * weight_i)
weights = [1.00, 0.85, 0.72, 0.61, 0.52]  (most recent first)
"""
from __future__ import annotations

FORM_WEIGHTS = [1.00, 0.85, 0.72, 0.61, 0.52]
WEIGHT_SUM = sum(FORM_WEIGHTS)


def compute_form_score(recent_results: list[str | None]) -> float:
    """
    recent_results: list of up to 5 most recent results, most recent first.
    Each element: 'W', 'D', 'L', or None (unknown).
    Returns a normalized form score in [0, 1].
    """
    result_values = {"W": 1.0, "D": 0.5, "L": 0.0}
    score = 0.0
    effective_weight = 0.0

    for i, result in enumerate(recent_results[:5]):
        if result is None:
            continue
        w = FORM_WEIGHTS[i]
        score += result_values.get(result.upper(), 0.5) * w
        effective_weight += w

    if effective_weight == 0:
        return 0.5  # degrade to neutral when no data

    return score / effective_weight


def extract_form_string(standings_entry: dict | None) -> list[str | None]:
    """
    Parse API-Football form string (e.g. 'WDLWW') into a list of characters,
    most recent first.
    """
    if not standings_entry:
        return [None] * 5
    form_str = standings_entry.get("form") or ""
    chars = list(form_str.upper())
    chars.reverse()  # API returns oldest → newest; we want newest first
    result = chars[:5]
    while len(result) < 5:
        result.append(None)
    return result
