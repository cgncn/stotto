"""
Celery tasks for STOTTO.

Task flow:
  task_weekly_import
    → task_baseline_scoring
        → (feature engine, scoring engine, optimizer)
  task_daily_refresh          (periodic)
  task_pre_kickoff_check      (periodic, every 15 min)
  task_settle_check           (periodic, every 5 min)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from celery import chain

from app.workers.celery_app import celery_app
from app.db.base import SessionLocal
from app.db import models
from app.adapters.api_football import APIFootballAdapter, APIFootballError

logger = logging.getLogger(__name__)

# Minutes before kickoff that trigger a pre-kickoff refresh
PRE_KICKOFF_WINDOWS = [90, 60, 15]


def compute_brier(picks_json: dict, match_scores: dict) -> Optional[float]:
    """Compute Brier score for a coupon against model probability scores.

    picks_json: {sequence_no_str: "1"|"X"|"2"}
    match_scores: {sequence_no_int: MatchModelScore ORM object}
    """
    total = 0.0
    count = 0
    for seq_str, pick in picks_json.items():
        seq = int(seq_str)
        score = match_scores.get(seq)
        if score is None:
            continue
        # Probabilities for the picked outcome
        prob_map = {"1": score.p1, "X": score.px, "2": score.p2}
        prob = prob_map.get(pick)
        if prob is None:
            continue
        # Brier score: mean squared error, lower is better
        # For picked outcome: (1 - prob)^2, for others: (0 - p)^2
        other_probs = {"1": score.p1, "X": score.px, "2": score.p2}
        brier_sum = (1.0 - prob) ** 2
        for outcome, p in other_probs.items():
            if outcome != pick:
                brier_sum += (0.0 - p) ** 2
        total += brier_sum
        count += 1
    return total / count if count > 0 else None


def settle_user_coupons(weekly_pool_id: int, db) -> None:
    """Compute and store performance metrics for all saved user coupons for this week."""
    pool = db.query(models.WeeklyPool).filter_by(id=weekly_pool_id).first()
    if not pool:
        return

    matches = db.query(models.WeeklyPoolMatch).filter_by(weekly_pool_id=weekly_pool_id).all()
    actual_results = {m.sequence_no: m.result for m in matches}

    # Build match_scores dict: sequence_no -> MatchModelScore (latest)
    from app.db.models import MatchModelScore
    match_scores = {}
    for m in matches:
        score = (
            db.query(MatchModelScore)
            .filter_by(weekly_pool_match_id=m.id)
            .order_by(MatchModelScore.created_at.desc())
            .first()
        )
        if score:
            match_scores[m.sequence_no] = score

    coupons = db.query(models.UserCoupon).filter_by(weekly_pool_id=weekly_pool_id).all()
    for coupon in coupons:
        # Skip if performance already recorded
        existing = db.query(models.UserCouponPerformance).filter_by(
            user_coupon_id=coupon.id
        ).first()
        if existing:
            continue

        picks = coupon.picks_json or {}
        correct = sum(
            1
            for seq_str, pick in picks.items()
            if actual_results.get(int(seq_str)) == pick
        )

        perf = models.UserCouponPerformance(
            user_coupon_id=coupon.id,
            user_id=coupon.user_id,
            week_code=pool.week_code,
            correct_count=correct,
            total_picks=len(picks),
            brier_score=compute_brier(picks, match_scores),
        )
        db.add(perf)

    db.commit()


# ── Weekly import ──────────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.tasks.task_weekly_import", bind=True, max_retries=3)
def task_weekly_import(self, week_code: str, fixture_external_ids: list[int]):
    """
    Import 15 fixtures for the given week.
    Creates weekly_pool + weekly_pool_matches, fetches initial snapshots,
    then chains into baseline scoring.
    """
    logger.info("Weekly import started: week=%s, fixtures=%s", week_code, fixture_external_ids)

    with SessionLocal() as db:
        # Idempotent: re-use existing pool if already created
        pool = db.query(models.WeeklyPool).filter_by(week_code=week_code).first()
        if not pool:
            pool = models.WeeklyPool(week_code=week_code, status=models.PoolStatus.open)
            db.add(pool)
            db.flush()

        adapter = APIFootballAdapter(db)

        for seq, ext_id in enumerate(fixture_external_ids, start=1):
            if seq > 1:
                time.sleep(6)  # Stay within 10 req/min rate limit

            # Fetch and upsert fixture + teams
            try:
                raw = adapter.fetch_fixture(ext_id)
            except APIFootballError as exc:
                logger.error("Failed to fetch fixture %d: %s", ext_id, exc)
                continue

            fixture = adapter.upsert_fixture(raw)

            # Idempotent pool match
            pm = db.query(models.WeeklyPoolMatch).filter_by(
                weekly_pool_id=pool.id, sequence_no=seq
            ).first()
            if not pm:
                pm = models.WeeklyPoolMatch(
                    weekly_pool_id=pool.id,
                    sequence_no=seq,
                    fixture_id=fixture.id,
                    fixture_external_id=ext_id,
                    kickoff_at=fixture.kickoff_at,
                    status=models.MatchStatus.pending,
                )
                db.add(pm)

            # Initial snapshots: odds + injuries
            try:
                adapter.fetch_odds(ext_id)
            except APIFootballError as exc:
                logger.warning("Odds unavailable for fixture %d: %s", ext_id, exc)

            try:
                adapter.fetch_injuries(ext_id)
            except APIFootballError as exc:
                logger.warning("Injuries unavailable for fixture %d: %s", ext_id, exc)

        db.commit()

        # ── Fetch standings for every unique league in this pool ──────────────
        fixtures = (
            db.query(models.Fixture)
            .join(models.WeeklyPoolMatch, models.WeeklyPoolMatch.fixture_id == models.Fixture.id)
            .filter(models.WeeklyPoolMatch.weekly_pool_id == pool.id)
            .all()
        )
        seen_league_seasons: set[tuple[int, int]] = set()
        for f in fixtures:
            key = (f.league_id, f.season)
            if key not in seen_league_seasons:
                seen_league_seasons.add(key)
                time.sleep(6)
                try:
                    adapter.fetch_standings(f.league_id, f.season)
                    logger.info("Standings fetched: league=%d season=%d", f.league_id, f.season)
                except APIFootballError as exc:
                    logger.warning("Standings unavailable: league=%d season=%d: %s", f.league_id, f.season, exc)
        db.commit()

        pool_id = pool.id

    logger.info("Weekly import complete: pool_id=%d", pool_id)
    task_baseline_scoring.delay(pool_id)
    return {"status": "ok", "pool_id": pool_id}


# ── Baseline scoring ───────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.tasks.task_baseline_scoring", bind=True, max_retries=3)
def task_baseline_scoring(self, weekly_pool_id: int):
    """Run feature engine + scoring + optimizer for the given pool."""
    from app.features.engine import run_feature_engine
    from app.scoring.engine import run_scoring_engine
    from app.optimizer.engine import run_optimizer

    logger.info("Baseline scoring started: pool_id=%d", weekly_pool_id)

    with SessionLocal() as db:
        pool = db.query(models.WeeklyPool).get(weekly_pool_id)
        if not pool:
            logger.error("Pool %d not found", weekly_pool_id)
            return {"status": "error", "reason": "pool_not_found"}

        run_feature_engine(db, pool)
        db.flush()

        run_scoring_engine(db, pool)
        db.flush()

        run_optimizer(db, pool)
        db.commit()

    logger.info("Baseline scoring complete: pool_id=%d", weekly_pool_id)
    return {"status": "ok", "pool_id": weekly_pool_id}


# ── Daily refresh ──────────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.tasks.task_daily_refresh", bind=True, max_retries=3)
def task_daily_refresh(self):
    """Refresh odds and injuries for all unlocked matches in the active pool."""
    with SessionLocal() as db:
        active_pool = (
            db.query(models.WeeklyPool)
            .filter(models.WeeklyPool.status == models.PoolStatus.open)
            .order_by(models.WeeklyPool.created_at.desc())
            .first()
        )
        if not active_pool:
            logger.info("No active pool — skipping daily refresh")
            return {"status": "skipped"}

        adapter = APIFootballAdapter(db)
        refreshed = 0

        for pm in active_pool.matches:
            if pm.is_locked:
                continue
            try:
                adapter.fetch_odds(pm.fixture_external_id)
                adapter.fetch_injuries(pm.fixture_external_id)
                refreshed += 1
            except APIFootballError as exc:
                logger.warning("Refresh failed for fixture %d: %s", pm.fixture_external_id, exc)

        db.commit()

    # Re-score all matches after refresh
    task_baseline_scoring.delay(active_pool.id)
    logger.info("Daily refresh complete: pool=%d, refreshed=%d", active_pool.id, refreshed)
    return {"status": "ok", "pool_id": active_pool.id, "refreshed": refreshed}


# ── Pre-kickoff check ──────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.tasks.task_pre_kickoff_check", bind=True, max_retries=3)
def task_pre_kickoff_check(self):
    """
    Every 15 minutes: check for matches kicking off within a window
    (90/60/15 minutes) and trigger a lineup + injury refresh + re-score.
    """
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        active_pool = (
            db.query(models.WeeklyPool)
            .filter(models.WeeklyPool.status == models.PoolStatus.open)
            .order_by(models.WeeklyPool.created_at.desc())
            .first()
        )
        if not active_pool:
            return {"status": "skipped"}

        adapter = APIFootballAdapter(db)
        triggered = 0

        for pm in active_pool.matches:
            if pm.is_locked or not pm.kickoff_at:
                continue
            kickoff = pm.kickoff_at
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            minutes_to_kickoff = (kickoff - now).total_seconds() / 60

            if any(abs(minutes_to_kickoff - w) <= 8 for w in PRE_KICKOFF_WINDOWS):
                try:
                    adapter.fetch_lineups(pm.fixture_external_id)
                    adapter.fetch_injuries(pm.fixture_external_id)
                    triggered += 1
                except APIFootballError as exc:
                    logger.warning("Pre-kickoff refresh failed fixture %d: %s", pm.fixture_external_id, exc)

        if triggered:
            db.commit()
            task_baseline_scoring.delay(active_pool.id)

    return {"status": "ok", "triggered": triggered}


# ── Settlement check ───────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.tasks.task_settle_check", bind=True, max_retries=3)
def task_settle_check(self):
    """
    Every 5 minutes: check if any match has finished and lock the result.
    When all 15 matches are settled, close the pool.
    """
    with SessionLocal() as db:
        active_pool = (
            db.query(models.WeeklyPool)
            .filter(models.WeeklyPool.status == models.PoolStatus.open)
            .order_by(models.WeeklyPool.created_at.desc())
            .first()
        )
        if not active_pool:
            return {"status": "skipped"}

        adapter = APIFootballAdapter(db)
        settled = 0

        for pm in active_pool.matches:
            if pm.is_locked:
                continue
            try:
                raw = adapter.fetch_fixture(pm.fixture_external_id)
                fixture_status = raw.get("fixture", {}).get("status", {}).get("short", "NS")
                if fixture_status == "FT":
                    goals = raw.get("goals", {})
                    home_goals = goals.get("home", 0) or 0
                    away_goals = goals.get("away", 0) or 0
                    if home_goals > away_goals:
                        pm.result = "1"
                    elif home_goals < away_goals:
                        pm.result = "2"
                    else:
                        pm.result = "X"
                    pm.is_locked = True
                    pm.status = models.MatchStatus.finished
                    settled += 1
            except APIFootballError as exc:
                logger.warning("Settlement fetch failed for fixture %d: %s", pm.fixture_external_id, exc)

        # If all matches settled, close the pool
        all_done = all(pm.is_locked for pm in active_pool.matches)
        if all_done and active_pool.matches:
            active_pool.status = models.PoolStatus.settled

        db.commit()

        if all_done and active_pool.matches:
            settle_user_coupons(active_pool.id, db)

    return {"status": "ok", "settled": settled}
