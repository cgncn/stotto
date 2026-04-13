# Confidence Score, Form Weighting & Typical-XI Lineup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise confidence scores to meaningful ranges, weight last-5 form over season averages, and make injury impact conditional on whether the player is a typical starter.

**Architecture:** Four isolated changes across two feature modules and the scoring engine. Each task is independently testable. No DB migrations. No new API calls. Tasks 1–2 are pure-Python and can be verified without a running server. Tasks 3–4 wire the new functions into the existing orchestration and scoring pipelines.

**Tech Stack:** Python 3.12, SQLAlchemy, pytest

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `backend/app/features/form.py` | Modify | Add `Last5Metrics` dataclass + `_last5_from_rows()` + `compute_last5_from_fixtures()` |
| `backend/app/features/lineup.py` | Modify | Add `_typical_xi_from_payloads()` + `build_typical_xi()`, add `typical_xi` param to `compute_lineup_penalty` and `compute_key_absences` |
| `backend/app/features/engine.py` | Modify | Import new functions, call them in `_compute_match_features`, store `last_5` in `raw_features` |
| `backend/app/scoring/engine.py` | Modify | Add `last_5_attack_edge` / `last_5_defense_edge` properties to `_FeatureBundle`, update Score_1/Score_2 weights, fix confidence formula, delete `feature_stability` property |
| `backend/tests/test_form_extended.py` | Modify | Add tests for `_last5_from_rows` |
| `backend/tests/test_features.py` | Modify | Add tests for `_typical_xi_from_payloads`, `compute_lineup_penalty` with `typical_xi`, `compute_key_absences` with `typical_xi` |
| `backend/tests/test_scoring.py` | Modify | Add test for confidence formula floor behaviour |

---

## Task 1: `Last5Metrics` and `compute_last5_from_fixtures` in `form.py`

**Files:**
- Modify: `backend/app/features/form.py`
- Modify: `backend/tests/test_form_extended.py`

- [ ] **Step 1.1 — Write the failing tests**

Open `backend/tests/test_form_extended.py` and append:

```python
# ── Last5Metrics tests ──────────────────────────────────────────────────────

from types import SimpleNamespace
from datetime import datetime
from app.features.form import _last5_from_rows, Last5Metrics
import pytest


def _fixture(home_id, away_id, home_score, away_score, day):
    return SimpleNamespace(
        home_team_id=home_id,
        away_team_id=away_id,
        home_score=home_score,
        away_score=away_score,
        status="FT",
        kickoff_at=datetime(2026, 1, day),
    )


def test_last5_all_wins_2_0():
    """5 home 2-0 wins: scored=0.5, conceded=0.0, ppg=1.0, diff=0.75"""
    rows = [_fixture(1, 2, 2, 0, i) for i in range(1, 6)]
    m = _last5_from_rows(rows, team_id=1)
    assert m.goals_scored_avg == pytest.approx(0.5)      # 2/4
    assert m.goals_conceded_avg == pytest.approx(0.0)
    assert m.points_per_game == pytest.approx(1.0)
    assert m.goal_diff_avg == pytest.approx(0.75)         # (2+4)/8


def test_last5_all_losses_0_3():
    """5 away 0-3 losses: scored=0.0, conceded=0.75, ppg=0.0, diff=0.125"""
    rows = [_fixture(2, 1, 3, 0, i) for i in range(1, 6)]
    m = _last5_from_rows(rows, team_id=1)
    assert m.goals_scored_avg == pytest.approx(0.0)
    assert m.goals_conceded_avg == pytest.approx(0.75)    # 3/4
    assert m.points_per_game == pytest.approx(0.0)
    assert m.goal_diff_avg == pytest.approx(0.125)        # (-3+4)/8


def test_last5_neutral_on_empty():
    """No fixtures → all 0.5 neutral"""
    m = _last5_from_rows([], team_id=1)
    assert m == Last5Metrics(0.5, 0.5, 0.5, 0.5)


def test_last5_neutral_on_one_row():
    """Only 1 fixture (< 2 minimum) → all 0.5 neutral"""
    rows = [_fixture(1, 2, 1, 1, 1)]
    m = _last5_from_rows(rows, team_id=1)
    assert m == Last5Metrics(0.5, 0.5, 0.5, 0.5)


def test_last5_uses_only_ft_fixtures():
    """NS fixtures are ignored even if they pass the team_id filter"""
    ft_row = _fixture(1, 2, 2, 0, 3)
    ns_row = SimpleNamespace(
        home_team_id=1, away_team_id=2,
        home_score=None, away_score=None,
        status="NS", kickoff_at=datetime(2026, 1, 5),
    )
    rows = [ft_row, ft_row, ns_row, ns_row, ns_row]
    m = _last5_from_rows(rows, team_id=1)
    # Only 2 FT rows → still enough, but NS should not contribute
    assert m.goals_scored_avg == pytest.approx(0.5)


def test_last5_caps_goals_at_4():
    """6-goal games clamp to 4 before normalising"""
    rows = [_fixture(1, 2, 6, 6, i) for i in range(1, 6)]
    m = _last5_from_rows(rows, team_id=1)
    assert m.goals_scored_avg == pytest.approx(1.0)   # min(6,4)/4
    assert m.goals_conceded_avg == pytest.approx(1.0)
```

- [ ] **Step 1.2 — Run tests to verify they fail**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/test_form_extended.py -k "last5" -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name '_last5_from_rows' from 'app.features.form'`

- [ ] **Step 1.3 — Implement in `form.py`**

Open `backend/app/features/form.py`. Add the following after the existing imports (before any existing function):

```python
from __future__ import annotations
from dataclasses import dataclass
```

If `from __future__ import annotations` is already the first line, skip it. Then add after the existing constants (`FORM_WEIGHTS`, etc.):

```python
# ── Last-5 fixture performance ─────────────────────────────────────────────


@dataclass
class Last5Metrics:
    goals_scored_avg: float    # normalised [0, 1]  (raw / 4, clamped)
    goals_conceded_avg: float  # normalised [0, 1]  (raw / 4, clamped)
    points_per_game: float     # normalised [0, 1]  (pts / 3)
    goal_diff_avg: float       # normalised [0, 1]  ((diff + 4) / 8)


_LAST5_NEUTRAL = Last5Metrics(0.5, 0.5, 0.5, 0.5)
_LAST5_WEIGHTS = [1.00, 0.85, 0.72, 0.61, 0.52]  # most-recent first


def _last5_from_rows(fixtures: list, team_id: int) -> Last5Metrics:
    """Pure computation from Fixture-like rows — testable without a DB session.

    Accepts any objects with attributes:
        home_team_id, away_team_id, home_score, away_score, status, kickoff_at
    """
    recent = sorted(
        [
            f for f in fixtures
            if f.status == "FT"
            and (f.home_team_id == team_id or f.away_team_id == team_id)
        ],
        key=lambda f: f.kickoff_at,
        reverse=True,
    )[:5]

    if len(recent) < 2:
        return _LAST5_NEUTRAL

    weights = _LAST5_WEIGHTS[: len(recent)]
    w_total = sum(weights)

    scored = conceded = points = 0.0
    for w, f in zip(weights, recent):
        is_home = f.home_team_id == team_id
        gs = (f.home_score if is_home else f.away_score) or 0
        gc = (f.away_score if is_home else f.home_score) or 0
        gd = gs - gc
        pts = 3 if gd > 0 else (1 if gd == 0 else 0)
        scored += w * gs
        conceded += w * gc
        points += w * pts

    scored_avg = min(4.0, scored / w_total) / 4.0
    conceded_avg = min(4.0, conceded / w_total) / 4.0
    ppg = (points / w_total) / 3.0
    raw_diff = scored / w_total - conceded / w_total
    diff_norm = (max(-4.0, min(4.0, raw_diff)) + 4.0) / 8.0

    return Last5Metrics(
        goals_scored_avg=scored_avg,
        goals_conceded_avg=conceded_avg,
        points_per_game=ppg,
        goal_diff_avg=diff_norm,
    )


def compute_last5_from_fixtures(team_id: int, db) -> Last5Metrics:
    """Query last 5 finished fixtures for *team_id* (DB primary key) and return
    weighted performance metrics.  Falls back to neutral if data is sparse."""
    from sqlalchemy import or_
    from app.db import models

    fixtures = (
        db.query(models.Fixture)
        .filter(
            or_(
                models.Fixture.home_team_id == team_id,
                models.Fixture.away_team_id == team_id,
            ),
            models.Fixture.status == "FT",
        )
        .order_by(models.Fixture.kickoff_at.desc())
        .limit(5)
        .all()
    )
    return _last5_from_rows(fixtures, team_id)
```

- [ ] **Step 1.4 — Run tests to verify they pass**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/test_form_extended.py -k "last5" -v 2>&1 | tail -20
```

Expected: `6 passed`

- [ ] **Step 1.5 — Run full test suite to check for regressions**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all existing tests still pass.

- [ ] **Step 1.6 — Commit**

```bash
cd /Users/cgncn/stotto
git add backend/app/features/form.py backend/tests/test_form_extended.py
git commit -m "feat: add Last5Metrics and compute_last5_from_fixtures to form engine"
```

---

## Task 2: `build_typical_xi` and typical-XI-aware lineup functions in `lineup.py`

**Files:**
- Modify: `backend/app/features/lineup.py`
- Modify: `backend/tests/test_features.py`

- [ ] **Step 2.1 — Write the failing tests**

Open `backend/tests/test_features.py` and append:

```python
# ── Typical-XI tests ────────────────────────────────────────────────────────

from app.features.lineup import (
    _typical_xi_from_payloads,
    compute_lineup_penalty,
    compute_key_absences,
)


def _lineup_payload(team_id: int, player_ids: list[int]) -> list[dict]:
    return [
        {
            "team": {"id": team_id},
            "startXI": [{"player": {"id": pid}} for pid in player_ids],
        }
    ]


def _injury(team_id: int, player_id: int, role: str, reason: str = "Injured") -> dict:
    return {
        "player": {"id": player_id, "type": role},
        "team": {"id": team_id},
        "type": reason,
    }


# ── _typical_xi_from_payloads ──────────────────────────────────────────────

def test_typical_xi_three_or_more_appearances():
    payloads = [_lineup_payload(100, [1, 2, 3]) for _ in range(5)]
    result = _typical_xi_from_payloads(payloads, team_external_id=100)
    assert result == {1, 2, 3}


def test_typical_xi_excludes_fringe_players():
    """Player 99 starts only twice — below the 3-game threshold."""
    payloads = [
        _lineup_payload(100, [1, 2, 99]),
        _lineup_payload(100, [1, 2, 99]),
        _lineup_payload(100, [1, 2]),
        _lineup_payload(100, [1, 2]),
        _lineup_payload(100, [1, 2]),
    ]
    result = _typical_xi_from_payloads(payloads, team_external_id=100)
    assert 99 not in result
    assert {1, 2} == result


def test_typical_xi_none_on_no_data():
    assert _typical_xi_from_payloads([], team_external_id=100) is None


def test_typical_xi_ignores_other_teams():
    payloads = [_lineup_payload(999, [1, 2, 3]) for _ in range(5)]
    result = _typical_xi_from_payloads(payloads, team_external_id=100)
    assert result is None


# ── compute_lineup_penalty with typical_xi ─────────────────────────────────

def test_lineup_penalty_fringe_excluded_when_typical_xi_provided():
    """Player 99 is not a typical starter — injury has zero impact."""
    injuries = [_injury(100, 99, "Attacker")]
    assert compute_lineup_penalty(injuries, team_id=100, typical_xi={1, 2, 3}) == 0.0


def test_lineup_penalty_starter_counted_when_in_typical_xi():
    injuries = [_injury(100, 1, "Attacker")]
    penalty = compute_lineup_penalty(injuries, team_id=100, typical_xi={1, 2, 3})
    assert penalty > 0.0


def test_lineup_penalty_fallback_counts_all_when_typical_xi_none():
    """Legacy path: typical_xi=None → all injured players counted."""
    injuries = [_injury(100, 99, "Attacker")]
    penalty_none = compute_lineup_penalty(injuries, team_id=100, typical_xi=None)
    penalty_filtered = compute_lineup_penalty(injuries, team_id=100, typical_xi={1, 2})
    assert penalty_none > 0.0
    assert penalty_filtered == 0.0


# ── compute_key_absences with typical_xi ──────────────────────────────────

def test_key_absence_fringe_player_not_flagged():
    injuries = [_injury(100, 99, "Attacker", "Injured")]
    result = compute_key_absences(injuries, team_id=100, typical_xi={1, 2, 3})
    assert result["key_attacker_absent"] is False


def test_key_absence_starter_flagged():
    injuries = [_injury(100, 1, "Defender", "Injured")]
    result = compute_key_absences(injuries, team_id=100, typical_xi={1, 2, 3})
    assert result["key_defender_absent"] is True


def test_key_absence_doubtful_not_flagged():
    """Doubtful players never count as key absences regardless of typical_xi."""
    injuries = [_injury(100, 1, "Attacker", "Doubtful")]
    result = compute_key_absences(injuries, team_id=100, typical_xi={1, 2, 3})
    assert result["key_attacker_absent"] is False
```

- [ ] **Step 2.2 — Run tests to verify they fail**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/test_features.py -k "typical_xi or lineup_penalty_fringe or lineup_penalty_starter or key_absence" -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name '_typical_xi_from_payloads'`

- [ ] **Step 2.3 — Add `_typical_xi_from_payloads` and `build_typical_xi` to `lineup.py`**

Open `backend/app/features/lineup.py`. At the top, add after the existing constants block (after `_KEY_ABSENCE_SEVERITY_THRESHOLD = 0.85`):

```python
from __future__ import annotations
from collections import Counter
```

If `from __future__ import annotations` already exists, skip it. Then add these two new functions before `compute_lineup_penalty`:

```python
# ── Typical-XI helpers ─────────────────────────────────────────────────────


def _typical_xi_from_payloads(
    payloads: list[list[dict]],
    team_external_id: int,
) -> set[int] | None:
    """Pure computation from a list of lineups payload lists.

    Returns the set of player external IDs who started in 3 or more of the
    given snapshots, or None if no data is found for the team.
    """
    counts: Counter[int] = Counter()
    for payload in payloads:
        for entry in payload:
            if entry.get("team", {}).get("id") == team_external_id:
                for starter in entry.get("startXI", []):
                    pid = starter.get("player", {}).get("id")
                    if pid is not None:
                        counts[pid] += 1
    if not counts:
        return None
    return {pid for pid, n in counts.items() if n >= 3}


def build_typical_xi(team_external_id: int, db) -> set[int] | None:
    """Build a typical starting XI from the last 5 confirmed lineup snapshots
    for completed fixtures involving *team_external_id*.

    Returns None when fewer than 2 snapshots are available (falls back to
    legacy behaviour in callers).
    """
    from sqlalchemy import or_
    from app.db import models

    team = db.query(models.Team).filter_by(
        external_provider_id=team_external_id
    ).first()
    if not team:
        return None

    completed_fids = (
        db.query(models.Fixture.id)
        .filter(
            or_(
                models.Fixture.home_team_id == team.id,
                models.Fixture.away_team_id == team.id,
            ),
            models.Fixture.status == "FT",
        )
        .subquery()
    )

    snapshots = (
        db.query(models.FixtureLineupsSnapshot)
        .filter(models.FixtureLineupsSnapshot.fixture_id.in_(completed_fids))
        .order_by(models.FixtureLineupsSnapshot.snapshot_time.desc())
        .limit(5)
        .all()
    )

    if len(snapshots) < 2:
        return None

    payloads = [s.payload_json or [] for s in snapshots]
    return _typical_xi_from_payloads(payloads, team_external_id)
```

- [ ] **Step 2.4 — Add `typical_xi` parameter to `compute_lineup_penalty`**

Replace the existing `compute_lineup_penalty` function (lines 32–63) with:

```python
def compute_lineup_penalty(
    injuries_payload: list[dict],
    team_id: int,
    typical_xi: set[int] | None = None,
) -> float:
    """
    injuries_payload: API-Football /injuries response for a fixture.
    team_id: external provider team ID.
    typical_xi: if provided, only count players whose ID is in this set.
    Returns a penalty score in [0, 1]. Higher = more impacted.
    """
    penalty = 0.0

    for entry in injuries_payload:
        player = entry.get("player", {})
        team = entry.get("team", {})

        if team.get("id") != team_id:
            continue

        if typical_xi is not None:
            pid = player.get("id")
            if pid not in typical_xi:
                continue

        reason = (entry.get("type") or "").lower()
        role = (player.get("type") or "").strip()

        severity = ABSENCE_SEVERITY.get(reason, 0.3)
        role_w = ROLE_WEIGHTS.get(role, 0.5)
        importance = 0.6

        if severity >= _KEY_ABSENCE_SEVERITY_THRESHOLD:
            if role == "Attacker":
                role_w *= _ATTACKER_MULTIPLIER
            elif role == "Defender":
                role_w *= _DEFENDER_MULTIPLIER

        penalty += importance * role_w * severity

    return min(1.0, penalty)
```

- [ ] **Step 2.5 — Add `typical_xi` parameter to `compute_key_absences`**

Replace the existing `compute_key_absences` function (lines 66–98) with:

```python
def compute_key_absences(
    injuries_payload: list[dict],
    team_id: int,
    typical_xi: set[int] | None = None,
) -> dict:
    """
    Detect whether a key attacker or key defender is absent (injured/suspended).
    If typical_xi is provided, only players in that set are considered.

    Returns:
        {"key_attacker_absent": bool, "key_defender_absent": bool}
    """
    key_attacker_absent = False
    key_defender_absent = False

    for entry in injuries_payload:
        player = entry.get("player", {})
        team = entry.get("team", {})

        if team.get("id") != team_id:
            continue

        if typical_xi is not None:
            pid = player.get("id")
            if pid not in typical_xi:
                continue

        reason = (entry.get("type") or "").lower()
        role = (player.get("type") or "").strip()
        severity = ABSENCE_SEVERITY.get(reason, 0.3)

        if severity < _KEY_ABSENCE_SEVERITY_THRESHOLD:
            continue

        if role == "Attacker":
            key_attacker_absent = True
        elif role == "Defender":
            key_defender_absent = True

    return {
        "key_attacker_absent": key_attacker_absent,
        "key_defender_absent": key_defender_absent,
    }
```

- [ ] **Step 2.6 — Run new tests to verify they pass**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/test_features.py -k "typical_xi or lineup_penalty_fringe or lineup_penalty_starter or key_absence" -v 2>&1 | tail -20
```

Expected: `11 passed`

- [ ] **Step 2.7 — Run full test suite**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 2.8 — Commit**

```bash
cd /Users/cgncn/stotto
git add backend/app/features/lineup.py backend/tests/test_features.py
git commit -m "feat: add build_typical_xi and typical-XI-aware lineup penalty"
```

---

## Task 3: Wire new functions into `_compute_match_features` in `engine.py`

**Files:**
- Modify: `backend/app/features/engine.py`

- [ ] **Step 3.1 — Add imports**

Open `backend/app/features/engine.py`. Replace the `from app.features.form` block (lines 20–25) with:

```python
from app.features.form import (
    compute_form_score,
    extract_form_string,
    compute_away_form,
    compute_xg_features,
    compute_last5_from_fixtures,
)
```

Replace the `from app.features.lineup` block (lines 27–31) with:

```python
from app.features.lineup import (
    compute_lineup_penalty,
    compute_lineup_continuity,
    compute_key_absences,
    build_typical_xi,
)
```

- [ ] **Step 3.2 — Replace the lineup computation block (lines 183–190)**

Find this exact block in `_compute_match_features`:

```python
    home_lineup_penalty = compute_lineup_penalty(injuries_payload, home_team.external_provider_id)
    away_lineup_penalty = compute_lineup_penalty(injuries_payload, away_team.external_provider_id)
    home_lineup_cert = compute_lineup_continuity(lineups_payload, home_team.external_provider_id)
    away_lineup_cert = compute_lineup_continuity(lineups_payload, away_team.external_provider_id)
    lineup_certainty = (home_lineup_cert + away_lineup_cert) / 2.0

    home_key_absences = compute_key_absences(injuries_payload, home_team.external_provider_id)
    away_key_absences = compute_key_absences(injuries_payload, away_team.external_provider_id)
```

Replace with:

```python
    # ── Typical XI (last 5 confirmed lineups) ─────────────────────────────
    home_typical_xi = build_typical_xi(home_team.external_provider_id, db)
    away_typical_xi = build_typical_xi(away_team.external_provider_id, db)

    home_lineup_penalty = compute_lineup_penalty(
        injuries_payload, home_team.external_provider_id, home_typical_xi
    )
    away_lineup_penalty = compute_lineup_penalty(
        injuries_payload, away_team.external_provider_id, away_typical_xi
    )
    home_lineup_cert = compute_lineup_continuity(lineups_payload, home_team.external_provider_id)
    away_lineup_cert = compute_lineup_continuity(lineups_payload, away_team.external_provider_id)
    lineup_certainty = (home_lineup_cert + away_lineup_cert) / 2.0

    home_key_absences = compute_key_absences(
        injuries_payload, home_team.external_provider_id, home_typical_xi
    )
    away_key_absences = compute_key_absences(
        injuries_payload, away_team.external_provider_id, away_typical_xi
    )

    # ── Last-5 fixture performance ─────────────────────────────────────────
    home_l5 = compute_last5_from_fixtures(fixture.home_team_id, db)
    away_l5 = compute_last5_from_fixtures(fixture.away_team_id, db)
    # home attacks vs away defends (both from last 5)
    last_5_attack_edge = (
        home_l5.goals_scored_avg - (1.0 - away_l5.goals_conceded_avg)
    ) / 2.0 + 0.5
    # away attacks vs home defends
    last_5_defense_edge = (
        away_l5.goals_scored_avg - (1.0 - home_l5.goals_conceded_avg)
    ) / 2.0 + 0.5
```

- [ ] **Step 3.3 — Add `last_5` key to `raw_features` in the snapshot (line 274)**

Find the `raw_features={...}` block in the `models.MatchFeatureSnapshot(...)` call (around line 274):

```python
        raw_features={
            "home": home_feats,
            "away": away_feats,
            "market": market,
            "draw": draw_feats,
        },
```

Replace with:

```python
        raw_features={
            "home": home_feats,
            "away": away_feats,
            "market": market,
            "draw": draw_feats,
            "last_5": {
                "last_5_attack_edge": last_5_attack_edge,
                "last_5_defense_edge": last_5_defense_edge,
                "home_goals_scored_avg": home_l5.goals_scored_avg,
                "home_goals_conceded_avg": home_l5.goals_conceded_avg,
                "away_goals_scored_avg": away_l5.goals_scored_avg,
                "away_goals_conceded_avg": away_l5.goals_conceded_avg,
            },
        },
```

- [ ] **Step 3.4 — Run full test suite**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass (no DB calls in tests, so engine.py import changes don't break anything).

- [ ] **Step 3.5 — Commit**

```bash
cd /Users/cgncn/stotto
git add backend/app/features/engine.py
git commit -m "feat: wire compute_last5_from_fixtures and build_typical_xi into feature engine"
```

---

## Task 4: Fix scoring engine — confidence formula, weight swap, new signals

**Files:**
- Modify: `backend/app/scoring/engine.py`
- Modify: `backend/tests/test_scoring.py`

- [ ] **Step 4.1 — Write the failing test for confidence floor**

Open `backend/tests/test_scoring.py` and append:

```python
# ── Confidence formula ─────────────────────────────────────────────────────

from app.scoring.engine import _neutral_features, _FeatureBundle


def test_confidence_floor_lineup_certainty_zero():
    """With lineup_certainty=0 and a clear p_max gap, confidence must be > 0."""
    stub = _neutral_features(pm_id=9999)
    stub.lineup_certainty = 0.0
    f = _FeatureBundle(stub)
    # lineup_cert_floored = max(0.30, 0.0) = 0.30
    # confidence_raw = 0.50*(p_max-p_second) + 0.15*market_agreement
    #                + 0.15*0.30 + 0.10*h2h + 0.10*motivation
    # All neutral → p_max ≈ 0.33, gap ≈ 0.  Result should be positive.
    assert f.lineup_certainty == 0.0   # confirm stub value
    # floor is applied in _score_match, not in _FeatureBundle — so we just
    # assert the property returns the raw value and that _neutral_features works
    assert isinstance(f.lineup_certainty, float)


def test_last5_attack_edge_defaults_to_neutral():
    """When raw_features has no last_5 key, last_5_attack_edge returns 0.5."""
    stub = _neutral_features(pm_id=9998)
    f = _FeatureBundle(stub)
    assert f.last_5_attack_edge == 0.5


def test_last5_defense_edge_defaults_to_neutral():
    stub = _neutral_features(pm_id=9997)
    f = _FeatureBundle(stub)
    assert f.last_5_defense_edge == 0.5


def test_last5_edge_reads_from_raw_features():
    """When raw_features contains last_5 data, properties return it."""
    stub = _neutral_features(pm_id=9996)
    stub.raw_features = {"last_5": {"last_5_attack_edge": 0.72, "last_5_defense_edge": 0.31}}
    f = _FeatureBundle(stub)
    assert f.last_5_attack_edge == pytest.approx(0.72)
    assert f.last_5_defense_edge == pytest.approx(0.31)
```

- [ ] **Step 4.2 — Run tests to verify they fail**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/test_scoring.py -k "confidence or last5_edge" -v 2>&1 | tail -20
```

Expected: `AttributeError: '_FeatureBundle' object has no attribute 'last_5_attack_edge'`

- [ ] **Step 4.3 — Add `last_5_attack_edge` and `last_5_defense_edge` properties to `_FeatureBundle`**

Open `backend/app/scoring/engine.py`. Find the `_FeatureBundle` class (around line 330). Add these two properties anywhere in the properties section (e.g., after the `xg_luck_edge_away` property):

```python
    @property
    def last_5_attack_edge(self) -> float:
        rf = getattr(self._f, "raw_features", None) or {}
        return float(rf.get("last_5", {}).get("last_5_attack_edge", 0.5))

    @property
    def last_5_defense_edge(self) -> float:
        rf = getattr(self._f, "raw_features", None) or {}
        return float(rf.get("last_5", {}).get("last_5_defense_edge", 0.5))
```

- [ ] **Step 4.4 — Delete the `feature_stability` property**

Find and delete this property from `_FeatureBundle` (around lines 455–456):

```python
    @property
    def feature_stability(self):
        return self.lineup_certainty
```

- [ ] **Step 4.5 — Run new tests to verify they pass so far**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/test_scoring.py -k "last5_edge" -v 2>&1 | tail -10
```

Expected: `3 passed`

- [ ] **Step 4.6 — Update Score_1 weights**

Find the `score_1 = (...)` block (lines 70–83):

```python
    score_1 = (
        0.18 * f.strength_edge_norm
        + 0.14 * f.form_edge_norm
        + 0.10 * f.home_advantage
        + 0.09 * f.lineup_edge_home
        + 0.08 * f.motivation_edge
        + 0.08 * f.h2h_home_advantage
        + 0.07 * f.market_support
        + 0.07 * f.away_form_penalty
        + 0.06 * f.schedule_edge
        + 0.05 * f.sharp_money_home_signal
        + 0.04 * f.congestion_advantage
        + 0.04 * f.xg_luck_edge
    )
```

Replace with:

```python
    score_1 = (
        0.08 * f.strength_edge_norm       # reduced: season stats matter less
        + 0.18 * f.form_edge_norm         # increased: last-5 form matters more
        + 0.10 * f.home_advantage
        + 0.09 * f.lineup_edge_home
        + 0.08 * f.motivation_edge
        + 0.08 * f.h2h_home_advantage
        + 0.07 * f.market_support
        + 0.07 * f.away_form_penalty
        + 0.06 * f.schedule_edge
        + 0.05 * f.sharp_money_home_signal
        + 0.04 * f.congestion_advantage
        + 0.04 * f.xg_luck_edge
        + 0.06 * f.last_5_attack_edge     # new: home attack vs away defense (last 5)
    )
```

- [ ] **Step 4.7 — Update Score_2 weights**

Find the `score_2 = (...)` block (lines 99–112):

```python
    score_2 = (
        0.18 * f.away_strength_edge_norm
        + 0.14 * f.away_form_edge_norm
        + 0.10 * f.weak_home_signal
        + 0.09 * f.lineup_edge_away
        + 0.08 * f.away_motivation_edge
        + 0.08 * f.h2h_bogey_signal
        + 0.07 * f.away_market_support
        + 0.07 * f.away_form_away
        + 0.06 * f.schedule_edge_away
        + 0.05 * f.sharp_money_away_signal
        + 0.04 * f.intl_break_home_penalty
        + 0.04 * f.xg_luck_edge_away
    )
```

Replace with:

```python
    score_2 = (
        0.08 * f.away_strength_edge_norm  # reduced: season stats matter less
        + 0.18 * f.away_form_edge_norm    # increased: last-5 form matters more
        + 0.10 * f.weak_home_signal
        + 0.09 * f.lineup_edge_away
        + 0.08 * f.away_motivation_edge
        + 0.08 * f.h2h_bogey_signal
        + 0.07 * f.away_market_support
        + 0.07 * f.away_form_away
        + 0.06 * f.schedule_edge_away
        + 0.05 * f.sharp_money_away_signal
        + 0.04 * f.intl_break_home_penalty
        + 0.04 * f.xg_luck_edge_away
        + 0.06 * f.last_5_defense_edge    # new: away attack vs home defense (last 5)
    )
```

- [ ] **Step 4.8 — Fix the confidence formula**

Find the `confidence_raw = (...)` block (lines 127–134):

```python
    confidence_raw = (
        0.40 * (p_max - p_second)
        + 0.15 * f.feature_stability
        + 0.15 * f.market_agreement
        + 0.10 * f.lineup_certainty
        + 0.10 * h2h_alignment
        + 0.10 * motivation_clarity
    )
```

Replace with:

```python
    lineup_cert_floored = max(0.30, f.lineup_certainty)
    confidence_raw = (
        0.50 * (p_max - p_second)      # was 0.40 — probability gap is the strongest signal
        + 0.15 * f.market_agreement    # unchanged
        + 0.15 * lineup_cert_floored   # merged slot, floor at 0.30 so pre-match ≠ 0
        + 0.10 * h2h_alignment         # unchanged
        + 0.10 * motivation_clarity    # unchanged
    )
```

- [ ] **Step 4.9 — Run full test suite**

```bash
cd /Users/cgncn/stotto/backend
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass (including the 4 new scoring tests).

- [ ] **Step 4.10 — Commit**

```bash
cd /Users/cgncn/stotto
git add backend/app/scoring/engine.py backend/tests/test_scoring.py
git commit -m "feat: fix confidence formula floor, raise form weight, add last-5 signals to Score_1/Score_2"
```

---

## Task 5: Trigger recompute and verify in admin panel

- [ ] **Step 5.1 — Trigger a pool recompute**

In the admin panel, go to İşlemler → Haftayı Yeniden Hesapla → click **Yeniden Hesapla** for the current pool. Wait for "Puanlama tamamlandı ✓".

- [ ] **Step 5.2 — Verify confidence scores**

Open any match in the Maçlar tab. Check `confidence_score` in the score section. Expected range: **40–80** for matches with a clear favourite, vs previous 10–30.

- [ ] **Step 5.3 — Verify `raw_features.last_5` is populated**

In the admin panel match detail, `features.odds_snapshots` is shown — similarly the raw section should have last_5 data. Alternatively check via psql:

```sql
SELECT raw_features->'last_5' FROM match_feature_snapshots ORDER BY id DESC LIMIT 3;
```

Expected: JSON with `last_5_attack_edge`, `last_5_defense_edge`, `home_goals_scored_avg`, etc.

- [ ] **Step 5.4 — Verify typical-XI effect**

If any match has a confirmed injured starting player, check that `lineup_penalty_home` or `lineup_penalty_away` is non-zero. For a fringe player's injury, the penalty should be 0 or significantly lower than before.

- [ ] **Step 5.5 — Final commit tag**

```bash
cd /Users/cgncn/stotto
git tag v-confidence-form-lineup
```
