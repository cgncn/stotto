"""
Feature engine orchestrator.
Reads all available snapshots for each WeeklyPoolMatch and writes
TeamFeatureSnapshot + MatchFeatureSnapshot records.

v2: adds H2H, real rest days, international break, fixture congestion, derby,
odds movement, away-specific form, xG proxy / luck flags, motivation / objective,
and role-specific absence detection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import models
from app.features.strength import compute_strength_score, extract_strength_features
from app.features.form import (
    compute_form_score,
    extract_form_string,
    compute_away_form,
    compute_xg_features,
    compute_last5_from_fixtures,
)
from app.features.draw import compute_draw_tendency, extract_draw_features, get_draw_rate
from app.features.lineup import (
    compute_lineup_penalty,
    compute_lineup_continuity,
    compute_key_absences,
    build_typical_xi,
)
from app.features.market import compute_market_support, compute_odds_movement
from app.features.h2h import compute_h2h_features
from app.features.context import compute_context_features
from app.features.motivation import compute_motivation_features, parse_standings_entries
from app.features.rivalries import is_derby as check_derby

logger = logging.getLogger(__name__)

FEATURE_SET_VERSION = "v2"


def run_feature_engine(db: Session, pool: models.WeeklyPool) -> None:
    """Compute and persist features for all matches in the pool."""
    logger.info("Feature engine v2 running for pool %d", pool.id)

    for pm in pool.matches:
        if pm.is_locked:
            continue
        try:
            _compute_match_features(db, pm)
        except Exception as exc:
            logger.error("Feature computation failed for match %d: %s", pm.id, exc, exc_info=True)


def _compute_match_features(db: Session, pm: models.WeeklyPoolMatch) -> None:  # noqa: C901
    fixture = pm.fixture
    home_team = fixture.home_team
    away_team = fixture.away_team
    kickoff_at = fixture.kickoff_at

    # ── Standings snapshots ────────────────────────────────────────────────
    all_standings_entries = _all_standings_entries(db, fixture.league_id, fixture.season)
    home_standings = _find_team_entry(all_standings_entries, home_team.external_provider_id)
    away_standings = _find_team_entry(all_standings_entries, away_team.external_provider_id)

    # ── All odds snapshots (ordered ASC for movement delta) ────────────────
    all_odds_snaps = (
        db.query(models.FixtureOddsSnapshot)
        .filter_by(fixture_id=fixture.id)
        .order_by(models.FixtureOddsSnapshot.snapshot_time.asc())
        .all()
    )
    odds_dicts = [
        {"home_odds": s.home_odds, "draw_odds": s.draw_odds, "away_odds": s.away_odds}
        for s in all_odds_snaps
    ]
    latest_odds_snap = all_odds_snaps[-1] if all_odds_snaps else None
    home_odds = latest_odds_snap.home_odds if latest_odds_snap else None
    draw_odds = latest_odds_snap.draw_odds if latest_odds_snap else None
    away_odds = latest_odds_snap.away_odds if latest_odds_snap else None

    # ── Injuries ──────────────────────────────────────────────────────────
    latest_injuries = (
        db.query(models.FixtureInjuriesSnapshot)
        .filter_by(fixture_id=fixture.id)
        .order_by(models.FixtureInjuriesSnapshot.snapshot_time.desc())
        .first()
    )
    injuries_payload = (latest_injuries.payload_json or []) if latest_injuries else []

    # ── Lineups ───────────────────────────────────────────────────────────
    latest_lineups = (
        db.query(models.FixtureLineupsSnapshot)
        .filter_by(fixture_id=fixture.id)
        .order_by(models.FixtureLineupsSnapshot.snapshot_time.desc())
        .first()
    )
    lineups_payload = (latest_lineups.payload_json or []) if latest_lineups else []

    # ── H2H ───────────────────────────────────────────────────────────────
    h2h_snap = (
        db.query(models.FixtureH2HSnapshot)
        .filter_by(fixture_id=fixture.id)
        .order_by(models.FixtureH2HSnapshot.snapshot_time.desc())
        .first()
    )
    h2h_payload = (h2h_snap.payload_json or []) if h2h_snap else []
    h2h = compute_h2h_features(
        past_fixtures=h2h_payload,
        home_team_ext_id=home_team.external_provider_id,
        away_team_ext_id=away_team.external_provider_id,
        current_venue=fixture.venue,
    )

    # ── Rest days (actual from DB) ─────────────────────────────────────────
    home_last_kickoff = _last_completed_fixture_date(db, home_team.id, kickoff_at)
    away_last_kickoff = _last_completed_fixture_date(db, away_team.id, kickoff_at)

    # ── Fixture congestion (upcoming fixtures in next 7 days) ─────────────
    home_upcoming = _upcoming_fixture_count(db, home_team.id, kickoff_at)
    away_upcoming = _upcoming_fixture_count(db, away_team.id, kickoff_at)

    # ── Derby flag ─────────────────────────────────────────────────────────
    derby = check_derby(home_team.external_provider_id, away_team.external_provider_id)
    # Also honour admin override
    derby = derby or bool(pm.is_derby)
    if derby and not pm.is_derby:
        pm.is_derby = True  # persist detection

    admin_flags = pm.admin_flags or {}

    # ── Context features ──────────────────────────────────────────────────
    ctx = compute_context_features(
        kickoff_at=kickoff_at,
        home_last_kickoff=home_last_kickoff,
        away_last_kickoff=away_last_kickoff,
        home_upcoming_count=home_upcoming,
        away_upcoming_count=away_upcoming,
        is_derby=derby,
        admin_flags=admin_flags,
    )

    # ── Motivation features ────────────────────────────────────────────────
    mot_home = compute_motivation_features(home_standings, all_standings_entries)
    mot_away = compute_motivation_features(away_standings, all_standings_entries)

    # ── Away-specific form ────────────────────────────────────────────────
    away_form_home = compute_away_form(home_standings)
    away_form_away = compute_away_form(away_standings)

    # ── xG proxy from past statistics snapshots ───────────────────────────
    home_xg = _compute_team_xg(db, home_team.id, home_team.external_provider_id)
    away_xg = _compute_team_xg(db, away_team.id, away_team.external_provider_id)

    # ── Team-level features ────────────────────────────────────────────────
    home_feats = _build_team_features(home_standings, is_home=True)
    away_feats = _build_team_features(away_standings, is_home=False)

    _save_team_feature_snapshot(db, home_team.id, fixture.id, home_feats)
    _save_team_feature_snapshot(db, away_team.id, fixture.id, away_feats)

    # ── Market features ───────────────────────────────────────────────────
    market = compute_market_support(home_odds, draw_odds, away_odds)
    odds_movement = compute_odds_movement(odds_dicts)

    # ── Draw features ─────────────────────────────────────────────────────
    home_goals_pg = _goals_per_game(home_standings)
    away_goals_pg = _goals_per_game(away_standings)
    home_draw_rate = get_draw_rate(home_standings)
    away_draw_rate = get_draw_rate(away_standings)

    draw_feats = extract_draw_features(
        home_strength=home_feats["strength_score"],
        away_strength=away_feats["strength_score"],
        home_goals_per_game=home_goals_pg,
        away_goals_per_game=away_goals_pg,
        home_draw_rate=home_draw_rate,
        away_draw_rate=away_draw_rate,
    )

    # ── Lineup features ───────────────────────────────────────────────────
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

    # ── Volatility ────────────────────────────────────────────────────────
    draw_tendency = compute_draw_tendency(**draw_feats)
    volatility = 0.5 * market["bookmaker_dispersion"] + 0.5 * (1.0 - abs(draw_tendency - 0.5) * 2)

    # ── Persist MatchFeatureSnapshot ──────────────────────────────────────
    snapshot = models.MatchFeatureSnapshot(
        weekly_pool_match_id=pm.id,
        snapshot_time=datetime.now(timezone.utc),
        feature_set_version=FEATURE_SET_VERSION,
        # Core existing
        strength_edge=home_feats["strength_score"] - away_feats["strength_score"],
        form_edge=home_feats["form_score"] - away_feats["form_score"],
        home_advantage=0.06,
        draw_tendency=draw_tendency,
        balance_score=draw_feats["balance_score"],
        low_tempo_signal=draw_feats["low_tempo_signal"],
        low_goal_signal=draw_feats["low_goal_signal"],
        draw_history=draw_feats["draw_history"],
        tactical_symmetry=draw_feats["tactical_symmetry"],
        lineup_continuity=lineup_certainty,
        market_support=market["implied_p1"],
        volatility_score=volatility,
        rest_days_home=int(ctx.rest_days_home),
        rest_days_away=int(ctx.rest_days_away),
        lineup_penalty_home=home_lineup_penalty,
        lineup_penalty_away=away_lineup_penalty,
        lineup_certainty=lineup_certainty,
        # H2H
        h2h_home_win_rate=h2h.h2h_home_win_rate,
        h2h_away_win_rate=h2h.h2h_away_win_rate,
        h2h_draw_rate=h2h.h2h_draw_rate,
        h2h_venue_home_win_rate=h2h.h2h_venue_home_win_rate,
        h2h_bogey_flag=h2h.h2h_bogey_flag,
        h2h_sample_size=h2h.h2h_sample_size,
        # Real rest days
        rest_days_home_actual=ctx.rest_days_home,
        rest_days_away_actual=ctx.rest_days_away,
        # International break
        post_intl_break_home=ctx.post_intl_break_home,
        post_intl_break_away=ctx.post_intl_break_away,
        # Congestion
        congestion_risk_home=ctx.congestion_risk_home,
        congestion_risk_away=ctx.congestion_risk_away,
        # Derby
        is_derby=ctx.is_derby,
        derby_confidence_suppressor=ctx.derby_confidence_suppressor,
        # Odds movement
        opening_odds_home=odds_movement["opening_odds_home"],
        opening_odds_draw=odds_movement["opening_odds_draw"],
        opening_odds_away=odds_movement["opening_odds_away"],
        odds_delta_home=odds_movement["odds_delta_home"],
        sharp_money_signal=odds_movement["sharp_money_signal"],
        # Away form
        away_form_home=away_form_home,
        away_form_away=away_form_away,
        # xG proxy & luck
        xg_proxy_home=home_xg.get("xg_proxy"),
        xg_proxy_away=away_xg.get("xg_proxy"),
        xg_luck_home=home_xg.get("xg_luck"),
        xg_luck_away=away_xg.get("xg_luck"),
        lucky_form_home=home_xg.get("lucky_form", False),
        lucky_form_away=away_xg.get("lucky_form", False),
        unlucky_form_home=home_xg.get("unlucky_form", False),
        unlucky_form_away=away_xg.get("unlucky_form", False),
        # Motivation
        motivation_home=mot_home.motivation,
        motivation_away=mot_away.motivation,
        points_above_relegation_home=mot_home.points_above_relegation,
        points_above_relegation_away=mot_away.points_above_relegation,
        points_to_top4_home=mot_home.points_to_top4,
        points_to_top4_away=mot_away.points_to_top4,
        points_to_top6_home=mot_home.points_to_top6,
        points_to_top6_away=mot_away.points_to_top6,
        points_to_title_home=mot_home.points_to_title,
        points_to_title_away=mot_away.points_to_title,
        long_unbeaten_home=mot_home.long_unbeaten,
        long_unbeaten_away=mot_away.long_unbeaten,
        # Key absences
        key_attacker_absent_home=home_key_absences["key_attacker_absent"],
        key_attacker_absent_away=away_key_absences["key_attacker_absent"],
        key_defender_absent_home=home_key_absences["key_defender_absent"],
        key_defender_absent_away=away_key_absences["key_defender_absent"],
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
    )
    db.add(snapshot)
    db.flush()


# ── Team helpers ───────────────────────────────────────────────────────────────

def _build_team_features(standings_entry: dict | None, is_home: bool) -> dict:
    sf = extract_strength_features(standings_entry, is_home)
    strength = compute_strength_score(**sf)
    form_chars = extract_form_string(standings_entry)
    form = compute_form_score(form_chars)
    return {
        "strength_score": strength,
        "form_score": form,
        **sf,
    }


def _save_team_feature_snapshot(db: Session, team_id: int, fixture_id: int, feats: dict) -> None:
    snap = models.TeamFeatureSnapshot(
        team_id=team_id,
        fixture_id=fixture_id,
        snapshot_time=datetime.now(timezone.utc),
        feature_set_version=FEATURE_SET_VERSION,
        strength_score=feats["strength_score"],
        season_ppg=feats.get("season_ppg"),
        goal_diff_per_game=feats.get("goal_diff_per_game"),
        attack_index=feats.get("attack_index"),
        defense_index=feats.get("defense_index"),
        opponent_adjusted_score=feats.get("opponent_adjusted_score"),
        form_score=feats["form_score"],
        raw_features=feats,
    )
    db.add(snap)


def _goals_per_game(standings_entry: dict | None) -> float:
    if not standings_entry:
        return 1.3
    played = (standings_entry.get("all") or {}).get("played") or 1
    goals = (standings_entry.get("all") or {}).get("goals", {}).get("for") or 0
    return goals / max(1, played)


# ── Standings helpers ──────────────────────────────────────────────────────────

def _all_standings_entries(db: Session, league_id: int, season: int) -> list[dict]:
    """Return flat list of all team standings entries from the latest snapshot."""
    snapshot = (
        db.query(models.StandingsSnapshot)
        .filter_by(league_id=league_id, season=season)
        .order_by(models.StandingsSnapshot.snapshot_time.desc())
        .first()
    )
    if not snapshot or not snapshot.payload_json:
        return []
    return parse_standings_entries(snapshot.payload_json)


def _find_team_entry(entries: list[dict], team_ext_id: int) -> dict | None:
    for entry in entries:
        if (entry.get("team") or {}).get("id") == team_ext_id:
            return entry
    return None


# ── Context helpers (DB queries) ───────────────────────────────────────────────

def _last_completed_fixture_date(
    db: Session, team_db_id: int, before: datetime
) -> datetime | None:
    """Most recent completed fixture kickoff for a team, before a given datetime."""
    before_naive = before.replace(tzinfo=None) if before.tzinfo else before
    fix = (
        db.query(models.Fixture)
        .filter(
            or_(
                models.Fixture.home_team_id == team_db_id,
                models.Fixture.away_team_id == team_db_id,
            ),
            models.Fixture.status == "FT",
            models.Fixture.kickoff_at < before_naive,
        )
        .order_by(models.Fixture.kickoff_at.desc())
        .first()
    )
    return fix.kickoff_at if fix else None


def _upcoming_fixture_count(
    db: Session, team_db_id: int, after: datetime
) -> int:
    """Count of fixtures scheduled for a team within 7 days after a given datetime."""
    after_naive = after.replace(tzinfo=None) if after.tzinfo else after
    window_end = after_naive + timedelta(days=7)
    return (
        db.query(models.Fixture)
        .filter(
            or_(
                models.Fixture.home_team_id == team_db_id,
                models.Fixture.away_team_id == team_db_id,
            ),
            models.Fixture.kickoff_at > after_naive,
            models.Fixture.kickoff_at <= window_end,
        )
        .count()
    )


def _compute_team_xg(db: Session, team_db_id: int, team_ext_id: int) -> dict:
    """
    Compute xG proxy and luck flags for a team from their last 5 completed fixtures.
    """
    past_fixtures = (
        db.query(models.Fixture)
        .filter(
            or_(
                models.Fixture.home_team_id == team_db_id,
                models.Fixture.away_team_id == team_db_id,
            ),
            models.Fixture.status == "FT",
        )
        .order_by(models.Fixture.kickoff_at.desc())
        .limit(5)
        .all()
    )

    stats_entries = []
    for fix in past_fixtures:
        stats_snap = (
            db.query(models.FixtureStatisticsSnapshot)
            .filter_by(fixture_id=fix.id)
            .order_by(models.FixtureStatisticsSnapshot.snapshot_time.desc())
            .first()
        )
        if not stats_snap or not stats_snap.payload_json:
            continue

        # Determine goals scored by this team in this fixture
        if fix.home_team_id == team_db_id:
            team_goals = fix.home_score
        else:
            team_goals = fix.away_score

        if team_goals is None:
            continue

        stats_entries.append({
            "stats": stats_snap.payload_json,
            "team_goals": team_goals,
            "team_ext_id": team_ext_id,
        })

    from app.features.form import compute_xg_features
    return compute_xg_features(stats_entries, team_ext_id)
