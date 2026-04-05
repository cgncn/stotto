"""
Feature engine orchestrator.
Reads all available snapshots for each WeeklyPoolMatch and writes
TeamFeatureSnapshot + MatchFeatureSnapshot records.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import models
from app.features.strength import compute_strength_score, extract_strength_features
from app.features.form import compute_form_score, extract_form_string
from app.features.draw import compute_draw_tendency, extract_draw_features, get_draw_rate
from app.features.lineup import compute_lineup_penalty, compute_lineup_continuity
from app.features.market import compute_market_support

logger = logging.getLogger(__name__)

FEATURE_SET_VERSION = "v1"


def run_feature_engine(db: Session, pool: models.WeeklyPool) -> None:
    """Compute and persist features for all matches in the pool."""
    logger.info("Feature engine running for pool %d", pool.id)

    for pm in pool.matches:
        if pm.is_locked:
            continue
        try:
            _compute_match_features(db, pm)
        except Exception as exc:
            logger.error("Feature computation failed for match %d: %s", pm.id, exc)


def _compute_match_features(db: Session, pm: models.WeeklyPoolMatch) -> None:
    fixture = pm.fixture
    home_team = fixture.home_team
    away_team = fixture.away_team

    # ── Standings snapshots ────────────────────────────────────────────────
    home_standings = _latest_team_standings(db, home_team.external_provider_id, fixture.league_id, fixture.season)
    away_standings = _latest_team_standings(db, away_team.external_provider_id, fixture.league_id, fixture.season)

    # ── Odds ──────────────────────────────────────────────────────────────
    latest_odds = (
        db.query(models.FixtureOddsSnapshot)
        .filter_by(fixture_id=fixture.id)
        .order_by(models.FixtureOddsSnapshot.snapshot_time.desc())
        .first()
    )
    home_odds = latest_odds.home_odds if latest_odds else None
    draw_odds = latest_odds.draw_odds if latest_odds else None
    away_odds = latest_odds.away_odds if latest_odds else None

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

    # ── Team-level features ────────────────────────────────────────────────
    home_feats = _build_team_features(home_standings, is_home=True)
    away_feats = _build_team_features(away_standings, is_home=False)

    _save_team_feature_snapshot(db, home_team.id, fixture.id, home_feats)
    _save_team_feature_snapshot(db, away_team.id, fixture.id, away_feats)

    # ── Market features ───────────────────────────────────────────────────
    market = compute_market_support(home_odds, draw_odds, away_odds)

    # ── Draw features ─────────────────────────────────────────────────────
    home_goals_pg = (home_standings.get("all", {}).get("goals", {}).get("for") or 1) / max(1, (home_standings.get("all", {}).get("played") or 1)) if home_standings else 1.3
    away_goals_pg = (away_standings.get("all", {}).get("goals", {}).get("for") or 1) / max(1, (away_standings.get("all", {}).get("played") or 1)) if away_standings else 1.3

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
    home_lineup_penalty = compute_lineup_penalty(injuries_payload, home_team.external_provider_id)
    away_lineup_penalty = compute_lineup_penalty(injuries_payload, away_team.external_provider_id)
    home_lineup_cert = compute_lineup_continuity(lineups_payload, home_team.external_provider_id)
    away_lineup_cert = compute_lineup_continuity(lineups_payload, away_team.external_provider_id)
    lineup_certainty = (home_lineup_cert + away_lineup_cert) / 2.0

    # ── Rest days (simplified: fixture data doesn't always include schedule) ─
    rest_days_home = 7
    rest_days_away = 7

    # ── Volatility ────────────────────────────────────────────────────────
    # Higher = more unpredictable; combine market dispersion + draw tendency midzone
    draw_tendency = compute_draw_tendency(**draw_feats)
    volatility = 0.5 * market["bookmaker_dispersion"] + 0.5 * (1.0 - abs(draw_tendency - 0.5) * 2)

    # ── Persist MatchFeatureSnapshot ─────────────────────────────────────
    snapshot = models.MatchFeatureSnapshot(
        weekly_pool_match_id=pm.id,
        snapshot_time=datetime.now(timezone.utc),
        feature_set_version=FEATURE_SET_VERSION,
        strength_edge=home_feats["strength_score"] - away_feats["strength_score"],
        form_edge=home_feats["form_score"] - away_feats["form_score"],
        home_advantage=0.06,  # baseline home advantage constant
        draw_tendency=draw_tendency,
        balance_score=draw_feats["balance_score"],
        low_tempo_signal=draw_feats["low_tempo_signal"],
        low_goal_signal=draw_feats["low_goal_signal"],
        draw_history=draw_feats["draw_history"],
        tactical_symmetry=draw_feats["tactical_symmetry"],
        lineup_continuity=(home_lineup_cert + away_lineup_cert) / 2.0,
        market_support=market["implied_p1"],
        volatility_score=volatility,
        rest_days_home=rest_days_home,
        rest_days_away=rest_days_away,
        lineup_penalty_home=home_lineup_penalty,
        lineup_penalty_away=away_lineup_penalty,
        lineup_certainty=lineup_certainty,
        raw_features={
            "home": home_feats,
            "away": away_feats,
            "market": market,
            "draw": draw_feats,
        },
    )
    db.add(snapshot)
    db.flush()


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


def _latest_team_standings(
    db: Session, team_ext_id: int, league_id: int, season: int
) -> dict | None:
    snapshot = (
        db.query(models.StandingsSnapshot)
        .filter_by(league_id=league_id, season=season)
        .order_by(models.StandingsSnapshot.snapshot_time.desc())
        .first()
    )
    if not snapshot or not snapshot.payload_json:
        return None

    # API-Football standings structure: response[0].league.standings[0] = list of team entries
    try:
        standings_list = snapshot.payload_json[0]["league"]["standings"][0]
        for entry in standings_list:
            if entry.get("team", {}).get("id") == team_ext_id:
                return entry
    except (IndexError, KeyError, TypeError):
        pass
    return None
