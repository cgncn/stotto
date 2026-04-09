from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session, joinedload

from app.db.base import get_db
from app.db import models
from app.api.deps import require_admin
from typing import Any
from app.schemas.admin import WeeklyImportRequest, ManualOverrideRequest, ResolveListRequest

router = APIRouter()


# ── Fixture lookup ─────────────────────────────────────────────────────────────

@router.get("/fixtures/search")
def search_fixtures_by_date(
    date: str = Query(..., description="ISO date, e.g. 2026-04-10"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Search API-Football for fixtures on a given date (passthrough)."""
    from app.adapters.api_football import APIFootballAdapter
    adapter = APIFootballAdapter(db)
    items = _fetch_fixtures_for_date(adapter, date)

    results = []
    for item in items:
        fix = item.get("fixture", {})
        teams = item.get("teams", {})
        league = item.get("league", {})
        results.append({
            "fixture_id": fix.get("id"),
            "home": teams.get("home", {}).get("name", ""),
            "away": teams.get("away", {}).get("name", ""),
            "kickoff": fix.get("date"),
            "league": league.get("name", ""),
            "country": league.get("country", ""),
        })
    return results


# ── Fixture resolve-list ───────────────────────────────────────────────────────

import re
import unicodedata
from difflib import SequenceMatcher

_CHAR_MAP = {
    'ş': 's', 'ğ': 'g', 'ü': 'u', 'ı': 'i', 'ç': 'c', 'ö': 'o',
    'Ş': 'S', 'Ğ': 'G', 'Ü': 'U', 'İ': 'I', 'Ç': 'C', 'Ö': 'O',
}

_ALIASES: dict[str, str] = {
    "b. dortmund":    "borussia dortmund",
    "b. leverkusen":  "bayer leverkusen",
    "basaksehir fk":  "istanbul basaksehir",
    "basaksehir":     "istanbul basaksehir",
    "gaziantep fk":   "gaziantep",
    "atletico":       "atletico madrid",
}

_STRIP_RE = re.compile(r'\b(a\.s\.|f\.k\.|a\.s|f\.k|fc|cf|sc)\b')
_MATCH_LINE_RE = re.compile(r'^(\d+)\s+(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2})\s+(.+)$')

# Leagues commonly featured in Spor Toto — used as fallback when date-only query is blocked
_SPOR_TOTO_LEAGUES = [203, 78, 39, 140, 135, 61, 2, 3, 848]


def _season_for_date(date_str: str) -> int:
    """Return the API-Football season year for a given ISO date string."""
    year, month = int(date_str[:4]), int(date_str[5:7])
    return year if month >= 7 else year - 1


def _fetch_fixtures_for_date(adapter: Any, date: str) -> list[dict]:
    """Fetch all fixtures for a date.

    Tries the unrestricted date-only query first; if the plan blocks it (403 / token error)
    falls back to querying each known Spor Toto league individually.
    """
    from app.adapters.api_football import APIFootballError
    try:
        data = adapter._get("fixtures", {"date": date})
        results = data.get("response", [])
        if results:
            return results
        # Empty response but no error — could still be a plan restriction; fall through
    except APIFootballError:
        pass

    # Fallback: query per known league
    season = _season_for_date(date)
    all_items: list[dict] = []
    seen: set[int] = set()
    for lid in _SPOR_TOTO_LEAGUES:
        try:
            data = adapter._get("fixtures", {"league": lid, "season": season, "date": date})
            for item in data.get("response", []):
                fid = item.get("fixture", {}).get("id")
                if fid and fid not in seen:
                    seen.add(fid)
                    all_items.append(item)
        except APIFootballError:
            continue
    return all_items


def _norm(name: str) -> str:
    for tr, en in _CHAR_MAP.items():
        name = name.replace(tr, en)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = _STRIP_RE.sub('', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return _ALIASES.get(name, name)


def _score(inp: str, cand: str) -> float:
    s1 = SequenceMatcher(None, inp, cand).ratio()
    in_tok = set(inp.split())
    s2 = len(in_tok & set(cand.split())) / max(len(in_tok), 1)
    longest = max(in_tok, key=len) if in_tok else ""
    s3 = 1.0 if longest and longest in cand else 0.0
    return max(s1, s2, s3)


def _best_split(teams_str: str, candidates: list[dict]) -> tuple[str, str]:
    """Try every '-' split and return the home/away that scores best against candidates."""
    positions = [i for i, c in enumerate(teams_str) if c == '-']
    if not positions:
        return teams_str, ""
    if not candidates:
        # fall back to first '-'
        i = positions[0]
        return teams_str[:i].strip(), teams_str[i + 1:].strip()
    best_score = -1.0
    best_split = (teams_str[:positions[0]].strip(), teams_str[positions[0] + 1:].strip())
    for pos in positions:
        home_try = _norm(teams_str[:pos].strip())
        away_try = _norm(teams_str[pos + 1:].strip())
        for c in candidates:
            combined = _score(home_try, _norm(c["home"])) + _score(away_try, _norm(c["away"]))
            if combined > best_score:
                best_score = combined
                best_split = (teams_str[:pos].strip(), teams_str[pos + 1:].strip())
    return best_split


@router.post("/fixtures/resolve-list")
def resolve_fixture_list(
    body: ResolveListRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Parse raw nesine.com match list text and resolve each row to an API-Football fixture ID."""
    from app.adapters.api_football import APIFootballAdapter, APIFootballError

    # ── 1. Parse lines ─────────────────────────────────────────────────────────
    parsed: list[dict] = []
    for line in body.raw_text.splitlines():
        m = _MATCH_LINE_RE.match(line.strip())
        if not m:
            continue
        seq, dd, mm, yyyy, time_, teams_str = (
            int(m.group(1)), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6),
        )
        iso_date = f"{yyyy}-{mm}-{dd}"
        parsed.append({"seq": seq, "date": iso_date, "time": time_, "teams_str": teams_str})

    if not parsed:
        raise HTTPException(status_code=422, detail="Maç satırı bulunamadı — metni kontrol edin")

    # ── 2. Fetch API-Football per unique date ──────────────────────────────────
    adapter = APIFootballAdapter(db)
    fixtures_by_date: dict[str, list[dict]] = {}
    for date in {p["date"] for p in parsed}:
        items = _fetch_fixtures_for_date(adapter, date)
        fixtures_by_date[date] = [
            {
                "fixture_id": item["fixture"]["id"],
                "home": item["teams"]["home"]["name"],
                "away": item["teams"]["away"]["name"],
                "kickoff": item["fixture"].get("date", ""),
                "league": item.get("league", {}).get("name", ""),
            }
            for item in items
        ]

    # ── 3. Match each row ──────────────────────────────────────────────────────
    resolved = []
    for p in parsed:
        candidates_pool = fixtures_by_date.get(p["date"], [])
        home_raw, away_raw = _best_split(p["teams_str"], candidates_pool)
        home_n, away_n = _norm(home_raw), _norm(away_raw)

        scored = []
        for c in candidates_pool:
            home_cn, away_cn = _norm(c["home"]), _norm(c["away"])
            combined = _score(home_n, home_cn) + _score(away_n, away_cn)
            scored.append((combined, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        top3 = [
            {"fixture_id": c["fixture_id"], "home": c["home"], "away": c["away"],
             "confidence": round(score, 3)}
            for score, c in scored[:3]
        ]

        best_score, best = scored[0] if scored else (0.0, None)
        matched = best_score >= 1.60 and best is not None

        resolved.append({
            "seq": p["seq"],
            "date": p["date"],
            "home_input": home_raw,
            "away_input": away_raw,
            "matched": matched,
            "fixture_id": best["fixture_id"] if matched else None,
            "home_found": best["home"] if matched else None,
            "away_found": best["away"] if matched else None,
            "confidence": round(best_score, 3),
            "candidates": top3,
        })

    resolved.sort(key=lambda r: r["seq"])
    return {"week_code": body.week_code, "resolved": resolved}


# ── Admin data endpoints ───────────────────────────────────────────────────────

@router.get("/pools")
def list_all_pools(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """List all weekly pools, newest first."""
    pools = (
        db.query(models.WeeklyPool)
        .order_by(models.WeeklyPool.created_at.desc())
        .all()
    )
    return [
        {
            "id": p.id,
            "week_code": p.week_code,
            "status": p.status.value if p.status else "unknown",
            "announcement_time": p.announcement_time.isoformat() if p.announcement_time else None,
            "deadline_at": p.deadline_at.isoformat() if p.deadline_at else None,
            "match_count": len(p.matches),
            "locked_count": sum(1 for m in p.matches if m.is_locked),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in pools
    ]


@router.get("/pools/{pool_id}")
def get_admin_pool(
    pool_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """All matches in a pool with full scores (no scrubbing)."""
    pool = (
        db.query(models.WeeklyPool)
        .options(
            joinedload(models.WeeklyPool.matches)
            .joinedload(models.WeeklyPoolMatch.fixture)
            .joinedload(models.Fixture.home_team),
            joinedload(models.WeeklyPool.matches)
            .joinedload(models.WeeklyPoolMatch.fixture)
            .joinedload(models.Fixture.away_team),
        )
        .filter_by(id=pool_id)
        .first()
    )
    if not pool:
        raise HTTPException(status_code=404, detail="Hafta bulunamadı")

    result = []
    for pm in sorted(pool.matches, key=lambda m: m.sequence_no):
        score = (
            db.query(models.MatchModelScore)
            .filter_by(weekly_pool_match_id=pm.id)
            .order_by(models.MatchModelScore.created_at.desc())
            .first()
        )
        result.append({
            "id": pm.id,
            "sequence_no": pm.sequence_no,
            "fixture_external_id": pm.fixture_external_id,
            "kickoff_at": pm.kickoff_at.isoformat() if pm.kickoff_at else None,
            "status": pm.status.value if pm.status else "pending",
            "is_locked": pm.is_locked,
            "result": pm.result,
            "is_derby": pm.is_derby,
            "admin_flags": pm.admin_flags or {},
            "home_team": pm.fixture.home_team.name if pm.fixture and pm.fixture.home_team else "",
            "away_team": pm.fixture.away_team.name if pm.fixture and pm.fixture.away_team else "",
            "score": {
                "p1": score.p1,
                "px": score.px,
                "p2": score.p2,
                "primary_pick": score.primary_pick,
                "secondary_pick": score.secondary_pick,
                "coverage_pick": score.coverage_pick,
                "confidence_score": score.confidence_score,
                "coverage_need_score": score.coverage_need_score,
                "reason_codes": score.reason_codes or [],
                "model_version": score.model_version,
            } if score else None,
        })
    return result


@router.get("/pools/{pool_id}/matches/{match_id}")
def get_admin_match_detail(
    pool_id: int,
    match_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Full unscrubbed match detail including all v2 signals."""
    pool = (
        db.query(models.WeeklyPool)
        .options(
            joinedload(models.WeeklyPool.matches)
            .joinedload(models.WeeklyPoolMatch.fixture)
            .joinedload(models.Fixture.home_team),
            joinedload(models.WeeklyPool.matches)
            .joinedload(models.WeeklyPoolMatch.fixture)
            .joinedload(models.Fixture.away_team),
        )
        .filter_by(id=pool_id)
        .first()
    )
    if not pool:
        raise HTTPException(status_code=404, detail="Hafta bulunamadı")
    pm = next((m for m in pool.matches if m.id == match_id), None)
    if not pm:
        raise HTTPException(status_code=404, detail="Maç bulunamadı")

    # Score history
    scores = (
        db.query(models.MatchModelScore)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchModelScore.created_at.desc())
        .all()
    )
    score_history = [
        {
            "created_at": s.created_at.isoformat(),
            "p1": s.p1, "px": s.px, "p2": s.p2,
            "primary_pick": s.primary_pick,
            "secondary_pick": s.secondary_pick,
            "coverage_pick": s.coverage_pick,
            "confidence_score": s.confidence_score,
            "coverage_need_score": s.coverage_need_score,
            "model_version": s.model_version,
            "reason_codes": s.reason_codes or [],
        }
        for s in scores
    ]

    # Feature snapshot (latest)
    feat = (
        db.query(models.MatchFeatureSnapshot)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchFeatureSnapshot.snapshot_time.desc())
        .first()
    )

    home_snap = away_snap = None
    if pm.fixture:
        home_snap = (
            db.query(models.TeamFeatureSnapshot)
            .filter_by(team_id=pm.fixture.home_team_id, fixture_id=pm.fixture_id)
            .order_by(models.TeamFeatureSnapshot.snapshot_time.desc())
            .first()
        )
        away_snap = (
            db.query(models.TeamFeatureSnapshot)
            .filter_by(team_id=pm.fixture.away_team_id, fixture_id=pm.fixture_id)
            .order_by(models.TeamFeatureSnapshot.snapshot_time.desc())
            .first()
        )

    # All odds snapshots ordered ASC for movement
    odds_snaps = []
    if pm.fixture:
        odds_snaps = (
            db.query(models.FixtureOddsSnapshot)
            .filter_by(fixture_id=pm.fixture_id)
            .order_by(models.FixtureOddsSnapshot.snapshot_time.asc())
            .all()
        )

    features = None
    if feat:
        rf = feat.raw_features or {}
        home_rf = rf.get("home", {})
        away_rf = rf.get("away", {})
        features = {
            # v1 signals
            "strength_edge": feat.strength_edge,
            "form_edge": feat.form_edge,
            "home_advantage": feat.home_advantage,
            "draw_tendency": feat.draw_tendency,
            "balance_score": feat.balance_score,
            "low_tempo_signal": feat.low_tempo_signal,
            "low_goal_signal": feat.low_goal_signal,
            "draw_history": feat.draw_history,
            "tactical_symmetry": feat.tactical_symmetry,
            "lineup_continuity": feat.lineup_continuity,
            "market_support": feat.market_support,
            "volatility_score": feat.volatility_score,
            "lineup_penalty_home": feat.lineup_penalty_home,
            "lineup_penalty_away": feat.lineup_penalty_away,
            "lineup_certainty": feat.lineup_certainty,
            # v2: H2H
            "h2h_home_win_rate": feat.h2h_home_win_rate,
            "h2h_away_win_rate": feat.h2h_away_win_rate,
            "h2h_draw_rate": feat.h2h_draw_rate,
            "h2h_venue_home_win_rate": feat.h2h_venue_home_win_rate,
            "h2h_bogey_flag": feat.h2h_bogey_flag,
            "h2h_sample_size": feat.h2h_sample_size,
            # v2: rest days / schedule
            "rest_days_home_actual": feat.rest_days_home_actual,
            "rest_days_away_actual": feat.rest_days_away_actual,
            "post_intl_break_home": feat.post_intl_break_home,
            "post_intl_break_away": feat.post_intl_break_away,
            "congestion_risk_home": feat.congestion_risk_home,
            "congestion_risk_away": feat.congestion_risk_away,
            # v2: derby
            "is_derby": feat.is_derby,
            "derby_confidence_suppressor": feat.derby_confidence_suppressor,
            # v2: odds movement
            "opening_odds_home": feat.opening_odds_home,
            "opening_odds_away": feat.opening_odds_away,
            "opening_odds_draw": feat.opening_odds_draw,
            "odds_delta_home": feat.odds_delta_home,
            "sharp_money_signal": feat.sharp_money_signal,
            # v2: away form
            "away_form_home": feat.away_form_home,
            "away_form_away": feat.away_form_away,
            # v2: xG / luck
            "xg_proxy_home": feat.xg_proxy_home,
            "xg_proxy_away": feat.xg_proxy_away,
            "xg_luck_home": feat.xg_luck_home,
            "xg_luck_away": feat.xg_luck_away,
            "lucky_form_home": feat.lucky_form_home,
            "lucky_form_away": feat.lucky_form_away,
            "unlucky_form_home": feat.unlucky_form_home,
            "unlucky_form_away": feat.unlucky_form_away,
            # v2: motivation
            "motivation_home": feat.motivation_home,
            "motivation_away": feat.motivation_away,
            "points_above_relegation_home": feat.points_above_relegation_home,
            "points_above_relegation_away": feat.points_above_relegation_away,
            "points_to_top4_home": feat.points_to_top4_home,
            "points_to_top4_away": feat.points_to_top4_away,
            "points_to_top6_home": feat.points_to_top6_home,
            "points_to_top6_away": feat.points_to_top6_away,
            "points_to_title_home": feat.points_to_title_home,
            "points_to_title_away": feat.points_to_title_away,
            "long_unbeaten_home": feat.long_unbeaten_home,
            "long_unbeaten_away": feat.long_unbeaten_away,
            # v2: key absences
            "key_attacker_absent_home": feat.key_attacker_absent_home,
            "key_attacker_absent_away": feat.key_attacker_absent_away,
            "key_defender_absent_home": feat.key_defender_absent_home,
            "key_defender_absent_away": feat.key_defender_absent_away,
            # team snapshots
            "home": {
                "strength_score": home_snap.strength_score if home_snap else home_rf.get("strength_score"),
                "form_score": home_snap.form_score if home_snap else home_rf.get("form_score"),
                "season_ppg": home_snap.season_ppg if home_snap else home_rf.get("season_ppg"),
                "goal_diff_per_game": home_snap.goal_diff_per_game if home_snap else home_rf.get("goal_diff_per_game"),
                "attack_index": home_snap.attack_index if home_snap else home_rf.get("attack_index"),
                "defense_index": home_snap.defense_index if home_snap else home_rf.get("defense_index"),
                "raw": home_rf,
            },
            "away": {
                "strength_score": away_snap.strength_score if away_snap else away_rf.get("strength_score"),
                "form_score": away_snap.form_score if away_snap else away_rf.get("form_score"),
                "season_ppg": away_snap.season_ppg if away_snap else away_rf.get("season_ppg"),
                "goal_diff_per_game": away_snap.goal_diff_per_game if away_snap else away_rf.get("goal_diff_per_game"),
                "attack_index": away_snap.attack_index if away_snap else away_rf.get("attack_index"),
                "defense_index": away_snap.defense_index if away_snap else away_rf.get("defense_index"),
                "raw": away_rf,
            },
            "odds_snapshots": [
                {
                    "snapshot_time": s.snapshot_time.isoformat(),
                    "home": s.home_odds,
                    "draw": s.draw_odds,
                    "away": s.away_odds,
                }
                for s in odds_snaps
            ],
        }

    # H2H fixtures from DB
    h2h = []
    if pm.fixture:
        htid = pm.fixture.home_team_id
        atid = pm.fixture.away_team_id
        past_fixtures = (
            db.query(models.Fixture)
            .filter(
                or_(
                    and_(models.Fixture.home_team_id == htid, models.Fixture.away_team_id == atid),
                    and_(models.Fixture.home_team_id == atid, models.Fixture.away_team_id == htid),
                ),
                models.Fixture.id != pm.fixture_id,
                models.Fixture.status == "FT",
            )
            .order_by(models.Fixture.kickoff_at.desc())
            .limit(10)
            .all()
        )
        for f in past_fixtures:
            is_home = f.home_team_id == htid
            hs = f.home_score if is_home else f.away_score
            as_ = f.away_score if is_home else f.home_score
            if hs is None or as_ is None:
                result = "?"
            elif hs > as_:
                result = "W"
            elif hs < as_:
                result = "L"
            else:
                result = "D"
            h2h.append({
                "kickoff_at": f.kickoff_at.isoformat() if f.kickoff_at else None,
                "home_team": f.home_team.name if f.home_team else "",
                "away_team": f.away_team.name if f.away_team else "",
                "home_score": f.home_score,
                "away_score": f.away_score,
                "result_from_home_perspective": result,
            })

    # Score changes for this match
    changes = (
        db.query(models.ScoreChangeLog)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.ScoreChangeLog.created_at.desc())
        .limit(50)
        .all()
    )

    return {
        "id": pm.id,
        "sequence_no": pm.sequence_no,
        "fixture_external_id": pm.fixture_external_id,
        "kickoff_at": pm.kickoff_at.isoformat() if pm.kickoff_at else None,
        "status": pm.status.value if pm.status else "pending",
        "is_locked": pm.is_locked,
        "result": pm.result,
        "is_derby": pm.is_derby,
        "admin_flags": pm.admin_flags or {},
        "home_team": pm.fixture.home_team.name if pm.fixture and pm.fixture.home_team else "",
        "away_team": pm.fixture.away_team.name if pm.fixture and pm.fixture.away_team else "",
        "latest_score": {
            "p1": scores[0].p1, "px": scores[0].px, "p2": scores[0].p2,
            "primary_pick": scores[0].primary_pick,
            "secondary_pick": scores[0].secondary_pick,
            "coverage_pick": scores[0].coverage_pick,
            "confidence_score": scores[0].confidence_score,
            "coverage_need_score": scores[0].coverage_need_score,
            "reason_codes": scores[0].reason_codes or [],
            "model_version": scores[0].model_version,
        } if scores else None,
        "score_history": score_history,
        "features": features,
        "h2h": h2h,
        "changes": [
            {
                "id": c.id,
                "created_at": c.created_at.isoformat(),
                "old_primary_pick": c.old_primary_pick,
                "new_primary_pick": c.new_primary_pick,
                "old_coverage_pick": c.old_coverage_pick,
                "new_coverage_pick": c.new_coverage_pick,
                "change_reason_code": c.change_reason_code,
                "triggered_by": c.triggered_by,
            }
            for c in changes
        ],
    }


@router.post("/weekly-import")
def trigger_weekly_import(
    body: WeeklyImportRequest,
    _: models.User = Depends(require_admin),
):
    """Trigger a weekly pool import via Celery.

    Accepts either:
      - fixture_external_ids: [123, 456, ...]   (simple list, no flags)
      - fixtures: [{external_id: 123, admin_flags: {thursday_european_away: true}}, ...]
    """
    from app.workers.tasks import task_weekly_import
    items = body.get_fixture_items()
    task = task_weekly_import.delay(
        week_code=body.week_code,
        fixtures_data=[{"external_id": it.external_id, "admin_flags": it.admin_flags} for it in items],
    )
    return {"detail": "İçe aktarma başlatıldı", "task_id": task.id}


@router.post("/recompute-week/{pool_id}")
def recompute_week(
    pool_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    from app.workers.tasks import task_baseline_scoring
    pool = db.query(models.WeeklyPool).get(pool_id)
    if not pool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hafta bulunamadı")
    task = task_baseline_scoring.delay(pool_id)
    return {"detail": "Yeniden hesaplanıyor", "pool_id": pool_id, "task_id": task.id}


@router.post("/recompute-match/{match_id}")
def recompute_match(
    match_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Re-score a single pool match (runs the full feature + score pipeline for it)."""
    from app.features.engine import _compute_match_features
    from app.scoring.engine import _score_match

    pm = db.query(models.WeeklyPoolMatch).get(match_id)
    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maç bulunamadı")
    if pm.is_locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maç kilitli, yeniden hesaplanamaz")

    _compute_match_features(db, pm)
    db.flush()
    _score_match(db, pm)
    db.commit()
    return {"detail": "Maç yeniden hesaplandı", "match_id": match_id}


@router.post("/pools/{pool_id}/matches/{match_id}/flags")
def update_match_flags(
    pool_id: int,
    match_id: int,
    flags: dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """
    Update admin flags for a specific pool match after import.
    Supported flags:
      is_derby: bool               — mark/unmark as derby
      thursday_european_away: bool — away team played European fixture on Thursday
    """
    pm = db.query(models.WeeklyPoolMatch).filter_by(id=match_id, weekly_pool_id=pool_id).first()
    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maç bulunamadı")
    if pm.is_locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maç kilitli")

    if "is_derby" in flags:
        pm.is_derby = bool(flags.pop("is_derby"))

    if flags:
        pm.admin_flags = {**(pm.admin_flags or {}), **flags}

    db.commit()
    return {"detail": "Bayraklar güncellendi", "match_id": match_id, "is_derby": pm.is_derby, "admin_flags": pm.admin_flags}


@router.post("/manual-override")
def manual_override(
    body: ManualOverrideRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    pm = db.query(models.WeeklyPoolMatch).get(body.weekly_pool_match_id)
    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maç bulunamadı")
    if pm.is_locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maç kilitli")

    previous = (
        db.query(models.MatchModelScore)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchModelScore.created_at.desc())
        .first()
    )

    override = models.MatchModelScore(
        weekly_pool_match_id=pm.id,
        model_version="override",
        p1=previous.p1 if previous else 0.33,
        px=previous.px if previous else 0.33,
        p2=previous.p2 if previous else 0.33,
        primary_pick=body.primary_pick,
        coverage_pick=body.coverage_pick,
        reason_codes=["MANUAL_OVERRIDE", body.reason],
    )
    db.add(override)

    change = models.ScoreChangeLog(
        weekly_pool_match_id=pm.id,
        old_primary_pick=previous.primary_pick if previous else None,
        new_primary_pick=body.primary_pick,
        old_coverage_pick=previous.coverage_pick if previous else None,
        new_coverage_pick=body.coverage_pick,
        change_reason_code="MANUAL_OVERRIDE",
        triggered_by=f"admin:{admin.email}",
    )
    db.add(change)
    db.commit()
    return {"detail": "Manuel geçersiz kılma uygulandı", "match_id": body.weekly_pool_match_id}
