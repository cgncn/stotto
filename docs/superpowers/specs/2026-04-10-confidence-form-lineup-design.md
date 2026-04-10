# Confidence Score, Form Weighting & Typical-XI Lineup Design

**Date:** 2026-04-10
**Status:** Approved

---

## Problem

Three related issues degrade prediction quality:

1. **Confidence scores are universally too low.** `feature_stability` (15% weight) is literally `lineup_certainty` again — double-counting a value that is 0.0 whenever the starting lineup hasn't been announced. For matches imported a week in advance, 25% of the confidence formula collapses to zero even when the probability gap is clear.

2. **Season-level strength outweighs recent form.** `strength_edge` (season PPG, goal diff, attack/defense index) has 18% weight vs `form_edge` (last 5, exponentially weighted) at 14%. Recent form is a better predictor of current team state, especially late in the season.

3. **Injury impact ignores actual starting role.** `compute_lineup_penalty` and `compute_key_absences` count injured players by position role only — they have no concept of whether that player would have started. A fringe squad player's injury is treated the same as a first-choice starter's.

4. **Goals and margins from last 5 matches are unused.** The probability formula only sees an aggregated W/D/L form score from the standings API — it ignores actual goals scored and conceded in recent games, which carry richer information about attacking and defensive quality.

---

## Design

### 1. Confidence Formula Fix

**File:** `backend/app/scoring/engine.py`

Remove the double-counted `feature_stability` property (which is just `lineup_certainty`). Merge into a single 15% slot with a **floor of 0.30** — when no lineup is confirmed yet, assume 30% certainty rather than 0%.

**New formula:**
```python
lineup_cert_floored = max(0.30, f.lineup_certainty)

confidence_raw = (
    0.50 * (p_max - p_second)     # was 0.40 — stronger signal gets more weight
  + 0.15 * market_agreement       # unchanged
  + 0.15 * lineup_cert_floored    # merged slot, floor at 0.30 so early-week ≠ 0
  + 0.10 * h2h_alignment          # unchanged
  + 0.10 * motivation_clarity     # unchanged
)
```

All existing suppressors (derby ×0.75, international break ×0.88, lucky form ×0.90, long unbeaten ×0.93) remain unchanged.

Delete the `feature_stability` property from the snapshot proxy class.

---

### 2. Form vs Strength Weight Swap

**File:** `backend/app/scoring/engine.py`

In `Score_1` (home win) and `Score_2` (away win), swap `strength_edge` and `form_edge` weights:

| Signal | Old weight | New weight |
|--------|-----------|-----------|
| `strength_edge` | 0.18 | **0.14** |
| `form_edge` | 0.14 | **0.18** |

`Score_X` (draw) is unchanged — it doesn't use these signals directly.

The form score already does the right thing internally (`[1.00, 0.85, 0.72, 0.61, 0.52]` decay over last 5 results). This change just gives it the priority it deserves over full-season averages.

---

### 3. Last 5 Match Performance in Probability

**Files:** `backend/app/features/form.py`, `backend/app/features/engine.py`, `backend/app/scoring/engine.py`

#### 3a. New dataclass and computation function (`form.py`)

```python
@dataclass
class Last5Metrics:
    goals_scored_avg: float    # weighted avg goals scored per game
    goals_conceded_avg: float  # weighted avg goals conceded per game
    points_per_game: float     # weighted avg points per game (W=3, D=1, L=0) / 3
    goal_diff_avg: float       # weighted avg goal difference per game
```

New function `compute_last5_from_fixtures(team_id: int, db: Session) -> Last5Metrics`:
- Queries `Fixture` table for team's last 5 completed (`status == "FT"`) matches (home or away)
- Applies exponential decay weights `[1.0, 0.85, 0.72, 0.61, 0.52]` — most recent first
- Normalizes each metric to `[0, 1]` range before returning:
  - `goals_scored_avg`: clamp to `[0, 4]`, divide by 4
  - `goals_conceded_avg`: clamp to `[0, 4]`, divide by 4 (lower is better, inverted in edge calculation)
  - `points_per_game`: already `[0, 1]` after dividing by 3
  - `goal_diff_avg`: clamp to `[-4, 4]`, shift to `[0, 1]` via `(val + 4) / 8`
- Falls back to neutral values (0.5) if fewer than 2 fixtures available

#### 3b. Two new match-level signals (`engine.py`)

Computed in `_compute_match_features` after calling `compute_last5_from_fixtures` for both teams:

```python
home_l5 = compute_last5_from_fixtures(fixture.home_team_id, db)
away_l5 = compute_last5_from_fixtures(fixture.away_team_id, db)

# How well home attacks vs how well away defends (both from last 5)
last_5_attack_edge = (home_l5.goals_scored_avg - (1.0 - away_l5.goals_conceded_avg)) / 2 + 0.5

# How well away attacks vs how well home defends
last_5_defense_edge = (away_l5.goals_scored_avg - (1.0 - home_l5.goals_conceded_avg)) / 2 + 0.5
```

Stored in `MatchFeatureSnapshot.raw_features["last_5"]` JSON — no migration needed.

#### 3c. Updated scoring weights (`scoring/engine.py`)

Each score function gets one new signal, funded by trimming its own `strength_edge`. Totals remain 1.00.

**Score_1 (home win):** add `last_5_attack_edge` (how well home attacks vs away defends, from last 5 games)

| Signal | Old | New |
|--------|-----|-----|
| `strength_edge` | 0.14 (after step 2) | **0.08** |
| `form_edge` | 0.18 | 0.18 |
| `last_5_attack_edge` | — | **+0.06** |

**Score_2 (away win):** add `last_5_defense_edge` (how well away attacks vs home defends, from last 5 games)

| Signal | Old | New |
|--------|-----|-----|
| `away_strength_edge` | 0.14 (after step 2) | **0.08** |
| `away_form_edge` | 0.18 | 0.18 |
| `last_5_defense_edge` | — | **+0.06** |

---

### 4. Typical-XI Lineup Penalty

**Files:** `backend/app/features/lineup.py`, `backend/app/features/engine.py`

#### 4a. Build typical XI (`lineup.py`)

New function `build_typical_xi(team_external_id: int, db: Session) -> set[int] | None`:
- Queries last 5 `FixtureLineupsSnapshot` records involving `team_external_id`, ordered by `snapshot_time DESC`
- For each snapshot, extracts the list of starting 11 player external IDs for that team
- Counts appearances per player across the 5 snapshots
- Returns the set of player external IDs who started **3 or more** of the 5 games
- Returns `None` if fewer than 2 lineup snapshots are available (falls back to legacy behavior)

#### 4b. Updated penalty functions (`lineup.py`)

Both `compute_lineup_penalty` and `compute_key_absences` gain an optional `typical_xi: set[int] | None` parameter:

```python
def compute_lineup_penalty(
    injuries_payload: list[dict],
    team_external_id: int,
    typical_xi: set[int] | None = None,
) -> float:
```

When `typical_xi` is provided:
- Filter the injuries list to only include players whose `player.id` is in `typical_xi`
- Apply existing severity × role weight logic to that filtered list only

When `typical_xi` is `None`:
- Fall back to current behavior (count all injured players by role)

Same pattern applies to `compute_key_absences`.

#### 4c. Wire up in feature engine (`engine.py`)

In `_compute_match_features`, before computing lineup penalties:

```python
home_typical_xi = build_typical_xi(home_team.external_provider_id, db)
away_typical_xi = build_typical_xi(away_team.external_provider_id, db)

home_lineup_penalty = compute_lineup_penalty(injuries_payload, home_team.external_provider_id, home_typical_xi)
away_lineup_penalty = compute_lineup_penalty(injuries_payload, away_team.external_provider_id, away_typical_xi)
home_key_absences = compute_key_absences(injuries_payload, home_team.external_provider_id, home_typical_xi)
away_key_absences = compute_key_absences(injuries_payload, away_team.external_provider_id, away_typical_xi)
```

No new API calls or DB migrations required — uses existing `FixtureLineupsSnapshot` and `Fixture` data.

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/scoring/engine.py` | New confidence formula; swap form/strength weights; add last_5 signals to Score_1/Score_2; delete `feature_stability` property |
| `backend/app/features/form.py` | Add `Last5Metrics` dataclass + `compute_last5_from_fixtures()` |
| `backend/app/features/engine.py` | Call `compute_last5_from_fixtures` for both teams; call `build_typical_xi`; pass typical_xi to lineup functions |
| `backend/app/features/lineup.py` | Add `build_typical_xi()`; add `typical_xi` param to `compute_lineup_penalty` and `compute_key_absences` |

No database migrations required. No new API calls required.

---

## Verification

1. Run `backend/tests/` — all 43 tests should still pass
2. Trigger a recompute on an existing pool (`POST /admin/recompute-week/{pool_id}`)
3. Check confidence scores in admin panel — expect values in the 40–80 range for clear favorites instead of 10–30
4. Verify that a match with a strong H2H favorite and recent goal-heavy form scores higher than an even match
5. For a team with a confirmed injured starting player (in typical XI): verify `lineup_penalty` is non-zero; for a fringe player injury: verify penalty is zero or near-zero
6. Check that `raw_features["last_5"]` is populated on `MatchFeatureSnapshot` after recompute
