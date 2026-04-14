from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session, joinedload

from app.db.base import get_db
from app.db import models
from app.api.deps import get_optional_user, require_subscriber
from app.schemas.pool import (
    PoolSummaryOut,
    PoolMatchSummary,
    MatchDetailOut,
    MatchScoreOut,
    CouponScenarioOut,
    CouponPickOut,
    CouponOptimizeRequest,
    ScoreChangeOut,
)

router = APIRouter()


# ── History / accuracy schemas ─────────────────────────────────────────────────

class PoolAccuracySummary(BaseModel):
    id: int
    week_code: str
    created_at: str
    match_count: int
    scored_count: int
    correct_count: int
    brier_score: Optional[float]
    avg_confidence: Optional[float]


class MatchResultRow(BaseModel):
    sequence_no: int
    home_team: str
    away_team: str
    kickoff_at: Optional[str]
    result: Optional[str]
    home_score: Optional[int]
    away_score: Optional[int]
    primary_pick: Optional[str]
    p1: Optional[float]
    px: Optional[float]
    p2: Optional[float]
    confidence_score: Optional[float]
    correct: Optional[bool]


# ── Subscription tier scrubbing ────────────────────────────────────────────────

def scrub_for_free_tier(data: dict, user) -> dict:
    """Remove subscriber-only fields for FREE users and unauthenticated requests."""
    if user is not None and user.is_subscriber:
        return data
    # Null out subscriber-only fields
    subscriber_only_keys = [
        "home_features", "away_features",  # radar/team feature data
        "odds_history",                     # odds movement
        "secondary_pick",                   # secondary pick
        "recommended_coverage",             # coverage recommendation
        "coverage_need_score",              # coverage need score
    ]
    for key in subscriber_only_keys:
        if key in data:
            data[key] = None
    return data


# ── Helper ─────────────────────────────────────────────────────────────────────

def _get_pool_or_404(pool_id: int, db: Session) -> models.WeeklyPool:
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hafta bulunamadı")
    return pool


def _latest_score(db: Session, pm: models.WeeklyPoolMatch) -> MatchScoreOut | None:
    score = (
        db.query(models.MatchModelScore)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchModelScore.created_at.desc())
        .first()
    )
    if not score:
        return None
    return MatchScoreOut(
        p1=score.p1,
        px=score.px,
        p2=score.p2,
        primary_pick=score.primary_pick,
        secondary_pick=score.secondary_pick,
        recommended_coverage=score.coverage_pick,
        confidence_score=score.confidence_score,
        coverage_need_score=score.coverage_need_score,
        reason_codes=score.reason_codes or [],
    )


def _pm_to_summary(db: Session, pm: models.WeeklyPoolMatch, feat: models.MatchFeatureSnapshot | None = None) -> PoolMatchSummary:
    sharp_money_flag = None
    post_intl_break = None
    if feat is not None:
        if feat.sharp_money_signal is not None:
            sharp_money_flag = abs(feat.sharp_money_signal) > 0.5
        pib_h = feat.post_intl_break_home or False
        pib_a = feat.post_intl_break_away or False
        post_intl_break = pib_h or pib_a
    return PoolMatchSummary(
        id=pm.id,
        sequence_no=pm.sequence_no,
        fixture_external_id=pm.fixture_external_id,
        kickoff_at=pm.kickoff_at,
        status=pm.status.value if pm.status else "pending",
        is_locked=pm.is_locked,
        result=pm.result,
        home_team=pm.fixture.home_team.name if pm.fixture and pm.fixture.home_team else "",
        away_team=pm.fixture.away_team.name if pm.fixture and pm.fixture.away_team else "",
        latest_score=_latest_score(db, pm),
        is_derby=pm.is_derby or False,
        sharp_money_flag=sharp_money_flag,
        post_intl_break=post_intl_break,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/history", response_model=list[PoolAccuracySummary])
def get_pool_history(db: Session = Depends(get_db)):
    """Return settled pools with prediction accuracy statistics."""
    settled_pools = (
        db.query(models.WeeklyPool)
        .filter(models.WeeklyPool.status == models.PoolStatus.settled)
        .order_by(models.WeeklyPool.created_at.desc())
        .all()
    )

    result = []
    for pool in settled_pools:
        pm_ids = [pm.id for pm in pool.matches]
        match_count = len(pm_ids)

        if not pm_ids:
            result.append(PoolAccuracySummary(
                id=pool.id,
                week_code=pool.week_code,
                created_at=pool.created_at.isoformat() if pool.created_at else "",
                match_count=0,
                scored_count=0,
                correct_count=0,
                brier_score=None,
                avg_confidence=None,
            ))
            continue

        # Build subquery: latest score id per match
        latest_score_subq = (
            db.query(
                models.MatchModelScore.weekly_pool_match_id,
                func.max(models.MatchModelScore.created_at).label("max_created"),
            )
            .filter(models.MatchModelScore.weekly_pool_match_id.in_(pm_ids))
            .group_by(models.MatchModelScore.weekly_pool_match_id)
            .subquery()
        )
        latest_scores = (
            db.query(models.MatchModelScore)
            .join(
                latest_score_subq,
                and_(
                    models.MatchModelScore.weekly_pool_match_id == latest_score_subq.c.weekly_pool_match_id,
                    models.MatchModelScore.created_at == latest_score_subq.c.max_created,
                ),
            )
            .all()
        )
        score_by_pm = {s.weekly_pool_match_id: s for s in latest_scores}

        # Build result_by_pm from pool matches
        result_by_pm = {pm.id: pm.result for pm in pool.matches}

        scored_count = 0
        correct_count = 0
        brier_total = 0.0
        confidence_total = 0.0
        confidence_count = 0

        for pm in pool.matches:
            score = score_by_pm.get(pm.id)
            if score is None:
                continue
            scored_count += 1
            actual = result_by_pm.get(pm.id)
            if actual in ("1", "X", "2"):
                i1 = 1.0 if actual == "1" else 0.0
                ix = 1.0 if actual == "X" else 0.0
                i2 = 1.0 if actual == "2" else 0.0
                brier_total += (score.p1 - i1) ** 2 + (score.px - ix) ** 2 + (score.p2 - i2) ** 2
                if score.primary_pick == actual:
                    correct_count += 1
            if score.confidence_score is not None:
                confidence_total += score.confidence_score
                confidence_count += 1

        brier_score = (brier_total / scored_count) if scored_count > 0 else None
        avg_confidence = (confidence_total / confidence_count) if confidence_count > 0 else None

        result.append(PoolAccuracySummary(
            id=pool.id,
            week_code=pool.week_code,
            created_at=pool.created_at.isoformat() if pool.created_at else "",
            match_count=match_count,
            scored_count=scored_count,
            correct_count=correct_count,
            brier_score=brier_score,
            avg_confidence=avg_confidence,
        ))

    return result


@router.get("/current", response_model=PoolSummaryOut)
def get_current_pool(db: Session = Depends(get_db)):
    pool = (
        db.query(models.WeeklyPool)
        .filter(models.WeeklyPool.status == models.PoolStatus.open)
        .order_by(models.WeeklyPool.created_at.desc())
        .first()
    )
    if not pool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aktif hafta bulunamadı")
    locked_count = sum(1 for m in pool.matches if m.is_locked)
    return PoolSummaryOut(
        id=pool.id,
        week_code=pool.week_code,
        status=pool.status.value,
        announcement_time=pool.announcement_time,
        deadline_at=pool.deadline_at,
        match_count=len(pool.matches),
        locked_count=locked_count,
    )


@router.get("/{pool_id}/results", response_model=list[MatchResultRow])
def get_pool_results(pool_id: int, db: Session = Depends(get_db)):
    """Return match-level prediction vs actual result for a settled pool."""
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hafta bulunamadı")

    pm_ids = [pm.id for pm in pool.matches]

    # Latest score per match
    latest_score_subq = (
        db.query(
            models.MatchModelScore.weekly_pool_match_id,
            func.max(models.MatchModelScore.created_at).label("max_created"),
        )
        .filter(models.MatchModelScore.weekly_pool_match_id.in_(pm_ids))
        .group_by(models.MatchModelScore.weekly_pool_match_id)
        .subquery()
    )
    latest_scores = (
        db.query(models.MatchModelScore)
        .join(
            latest_score_subq,
            and_(
                models.MatchModelScore.weekly_pool_match_id == latest_score_subq.c.weekly_pool_match_id,
                models.MatchModelScore.created_at == latest_score_subq.c.max_created,
            ),
        )
        .all()
    )
    score_by_pm = {s.weekly_pool_match_id: s for s in latest_scores}

    rows = []
    for pm in sorted(pool.matches, key=lambda m: m.sequence_no):
        score = score_by_pm.get(pm.id)
        fixture = pm.fixture
        home_team = fixture.home_team.name if fixture and fixture.home_team else ""
        away_team = fixture.away_team.name if fixture and fixture.away_team else ""
        kickoff = pm.kickoff_at.isoformat() if pm.kickoff_at else None
        actual = pm.result

        correct = None
        if score is not None and actual in ("1", "X", "2"):
            correct = score.primary_pick == actual

        rows.append(MatchResultRow(
            sequence_no=pm.sequence_no,
            home_team=home_team,
            away_team=away_team,
            kickoff_at=kickoff,
            result=actual,
            home_score=fixture.home_score if fixture else None,
            away_score=fixture.away_score if fixture else None,
            primary_pick=score.primary_pick if score else None,
            p1=score.p1 if score else None,
            px=score.px if score else None,
            p2=score.p2 if score else None,
            confidence_score=score.confidence_score if score else None,
            correct=correct,
        ))

    return rows


@router.get("/{pool_id}", response_model=list[PoolMatchSummary])
def get_pool(pool_id: int, db: Session = Depends(get_db)):
    pool = _get_pool_or_404(pool_id, db)
    pm_ids = [pm.id for pm in pool.matches]

    # Batch-load latest feature snapshot per match (avoid N+1)
    subq = (
        db.query(
            models.MatchFeatureSnapshot.weekly_pool_match_id,
            func.max(models.MatchFeatureSnapshot.snapshot_time).label("max_time"),
        )
        .filter(models.MatchFeatureSnapshot.weekly_pool_match_id.in_(pm_ids))
        .group_by(models.MatchFeatureSnapshot.weekly_pool_match_id)
        .subquery()
    )
    feat_rows = (
        db.query(models.MatchFeatureSnapshot)
        .join(
            subq,
            and_(
                models.MatchFeatureSnapshot.weekly_pool_match_id == subq.c.weekly_pool_match_id,
                models.MatchFeatureSnapshot.snapshot_time == subq.c.max_time,
            ),
        )
        .all()
    )
    feat_by_pm = {f.weekly_pool_match_id: f for f in feat_rows}
    return [_pm_to_summary(db, pm, feat_by_pm.get(pm.id)) for pm in pool.matches]


@router.get("/{pool_id}/matches/{match_id}", response_model=MatchDetailOut)
def get_match_detail(
    pool_id: int,
    match_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    pool = _get_pool_or_404(pool_id, db)
    pm = next((m for m in pool.matches if m.id == match_id), None)
    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maç bulunamadı")

    scores = (
        db.query(models.MatchModelScore)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchModelScore.created_at.desc())
        .all()
    )
    score_history = [
        {
            "created_at": s.created_at.isoformat(),
            "p1": s.p1,
            "px": s.px,
            "p2": s.p2,
            "primary_pick": s.primary_pick,
            "coverage_pick": s.coverage_pick,
            "confidence_score": s.confidence_score,
        }
        for s in scores
    ]

    # Feature snapshot for deep analysis
    feat_snap = (
        db.query(models.MatchFeatureSnapshot)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchFeatureSnapshot.snapshot_time.desc())
        .first()
    )

    # Team feature snapshots
    home_team_snap = (
        db.query(models.TeamFeatureSnapshot)
        .filter_by(team_id=pm.fixture.home_team_id, fixture_id=pm.fixture_id)
        .order_by(models.TeamFeatureSnapshot.snapshot_time.desc())
        .first()
    ) if pm.fixture else None
    away_team_snap = (
        db.query(models.TeamFeatureSnapshot)
        .filter_by(team_id=pm.fixture.away_team_id, fixture_id=pm.fixture_id)
        .order_by(models.TeamFeatureSnapshot.snapshot_time.desc())
        .first()
    ) if pm.fixture else None

    # Odds snapshot
    odds_snap = (
        db.query(models.FixtureOddsSnapshot)
        .filter_by(fixture_id=pm.fixture_id)
        .order_by(models.FixtureOddsSnapshot.snapshot_time.desc())
        .first()
    ) if pm.fixture else None

    # All odds snapshots (ASC) for movement display
    all_odds_snaps = []
    if pm.fixture:
        all_odds_snaps = (
            db.query(models.FixtureOddsSnapshot)
            .filter_by(fixture_id=pm.fixture_id)
            .order_by(models.FixtureOddsSnapshot.snapshot_time.asc())
            .all()
        )

    features = None
    if feat_snap:
        rf = feat_snap.raw_features or {}
        home_rf = rf.get("home", {})
        away_rf = rf.get("away", {})
        market_rf = rf.get("market", {})
        features = {
            # v1
            "strength_edge": feat_snap.strength_edge,
            "form_edge": feat_snap.form_edge,
            "home_advantage": feat_snap.home_advantage,
            "draw_tendency": feat_snap.draw_tendency,
            "balance_score": feat_snap.balance_score,
            "low_tempo_signal": feat_snap.low_tempo_signal,
            "low_goal_signal": feat_snap.low_goal_signal,
            "draw_history": feat_snap.draw_history,
            "tactical_symmetry": feat_snap.tactical_symmetry,
            "lineup_continuity": feat_snap.lineup_continuity,
            "market_support": feat_snap.market_support,
            "volatility_score": feat_snap.volatility_score,
            "lineup_penalty_home": feat_snap.lineup_penalty_home,
            "lineup_penalty_away": feat_snap.lineup_penalty_away,
            "lineup_certainty": feat_snap.lineup_certainty,
            # v2: H2H
            "h2h_home_win_rate": feat_snap.h2h_home_win_rate,
            "h2h_away_win_rate": feat_snap.h2h_away_win_rate,
            "h2h_draw_rate": feat_snap.h2h_draw_rate,
            "h2h_venue_home_win_rate": feat_snap.h2h_venue_home_win_rate,
            "h2h_bogey_flag": feat_snap.h2h_bogey_flag,
            "h2h_sample_size": feat_snap.h2h_sample_size,
            # v2: schedule
            "rest_days_home_actual": feat_snap.rest_days_home_actual,
            "rest_days_away_actual": feat_snap.rest_days_away_actual,
            "post_intl_break_home": feat_snap.post_intl_break_home,
            "post_intl_break_away": feat_snap.post_intl_break_away,
            "congestion_risk_home": feat_snap.congestion_risk_home,
            "congestion_risk_away": feat_snap.congestion_risk_away,
            # v2: derby
            "is_derby": feat_snap.is_derby,
            "derby_confidence_suppressor": feat_snap.derby_confidence_suppressor,
            # v2: odds movement
            "opening_odds_home": feat_snap.opening_odds_home,
            "opening_odds_away": feat_snap.opening_odds_away,
            "opening_odds_draw": feat_snap.opening_odds_draw,
            "odds_delta_home": feat_snap.odds_delta_home,
            "sharp_money_signal": feat_snap.sharp_money_signal,
            # v2: away form
            "away_form_home": feat_snap.away_form_home,
            "away_form_away": feat_snap.away_form_away,
            # v2: xG / luck
            "xg_proxy_home": feat_snap.xg_proxy_home,
            "xg_proxy_away": feat_snap.xg_proxy_away,
            "xg_luck_home": feat_snap.xg_luck_home,
            "xg_luck_away": feat_snap.xg_luck_away,
            "lucky_form_home": feat_snap.lucky_form_home,
            "lucky_form_away": feat_snap.lucky_form_away,
            "unlucky_form_home": feat_snap.unlucky_form_home,
            "unlucky_form_away": feat_snap.unlucky_form_away,
            # v2: motivation
            "motivation_home": feat_snap.motivation_home,
            "motivation_away": feat_snap.motivation_away,
            "points_above_relegation_home": feat_snap.points_above_relegation_home,
            "points_above_relegation_away": feat_snap.points_above_relegation_away,
            "points_to_top4_home": feat_snap.points_to_top4_home,
            "points_to_top4_away": feat_snap.points_to_top4_away,
            "points_to_top6_home": feat_snap.points_to_top6_home,
            "points_to_top6_away": feat_snap.points_to_top6_away,
            "points_to_title_home": feat_snap.points_to_title_home,
            "points_to_title_away": feat_snap.points_to_title_away,
            "long_unbeaten_home": feat_snap.long_unbeaten_home,
            "long_unbeaten_away": feat_snap.long_unbeaten_away,
            # v2: key absences
            "key_attacker_absent_home": feat_snap.key_attacker_absent_home,
            "key_attacker_absent_away": feat_snap.key_attacker_absent_away,
            "key_defender_absent_home": feat_snap.key_defender_absent_home,
            "key_defender_absent_away": feat_snap.key_defender_absent_away,
            # team snapshots
            "home": {
                "strength_score": home_team_snap.strength_score if home_team_snap else home_rf.get("strength_score"),
                "form_score": home_team_snap.form_score if home_team_snap else home_rf.get("form_score"),
                "season_ppg": home_team_snap.season_ppg if home_team_snap else home_rf.get("season_ppg"),
                "goal_diff_per_game": home_team_snap.goal_diff_per_game if home_team_snap else home_rf.get("goal_diff_per_game"),
                "attack_index": home_team_snap.attack_index if home_team_snap else home_rf.get("attack_index"),
                "defense_index": home_team_snap.defense_index if home_team_snap else home_rf.get("defense_index"),
                "raw": home_rf,
            },
            "away": {
                "strength_score": away_team_snap.strength_score if away_team_snap else away_rf.get("strength_score"),
                "form_score": away_team_snap.form_score if away_team_snap else away_rf.get("form_score"),
                "season_ppg": away_team_snap.season_ppg if away_team_snap else away_rf.get("season_ppg"),
                "goal_diff_per_game": away_team_snap.goal_diff_per_game if away_team_snap else away_rf.get("goal_diff_per_game"),
                "attack_index": away_team_snap.attack_index if away_team_snap else away_rf.get("attack_index"),
                "defense_index": away_team_snap.defense_index if away_team_snap else away_rf.get("defense_index"),
                "raw": away_rf,
            },
            "odds": {
                "home": odds_snap.home_odds if odds_snap else None,
                "draw": odds_snap.draw_odds if odds_snap else None,
                "away": odds_snap.away_odds if odds_snap else None,
            },
            "odds_snapshots": [
                {
                    "snapshot_time": s.snapshot_time.isoformat(),
                    "home": s.home_odds,
                    "draw": s.draw_odds,
                    "away": s.away_odds,
                }
                for s in all_odds_snaps
            ],
            "market": market_rf,
        }

    # H2H: last 5 fixtures between these two teams in the DB
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
            .limit(5)
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

    response_obj = MatchDetailOut(
        id=pm.id,
        sequence_no=pm.sequence_no,
        fixture_external_id=pm.fixture_external_id,
        kickoff_at=pm.kickoff_at,
        status=pm.status.value if pm.status else "pending",
        is_locked=pm.is_locked,
        result=pm.result,
        home_team=pm.fixture.home_team.name if pm.fixture and pm.fixture.home_team else "",
        away_team=pm.fixture.away_team.name if pm.fixture and pm.fixture.away_team else "",
        latest_score=_latest_score(db, pm),
        score_history=score_history,
        features=features,
        h2h=h2h,
    )
    response_data = response_obj.model_dump()
    # Scrub top-level subscriber-only keys
    response_data = scrub_for_free_tier(response_data, current_user)
    # Scrub subscriber-only keys nested inside latest_score
    if response_data.get("latest_score") is not None:
        response_data["latest_score"] = scrub_for_free_tier(response_data["latest_score"], current_user)
    return response_data


@router.get("/{pool_id}/coupon-scenarios", response_model=list[CouponScenarioOut])
def get_coupon_scenarios(
    pool_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_subscriber),
):
    _get_pool_or_404(pool_id, db)
    scenarios = (
        db.query(models.CouponScenario)
        .filter_by(weekly_pool_id=pool_id)
        .order_by(models.CouponScenario.created_at.desc())
        .limit(9)  # 3 scenarios × up to 3 runs
        .all()
    )
    result = []
    for s in scenarios:
        picks = [CouponPickOut(**p) for p in (s.picks_json or [])]
        result.append(CouponScenarioOut(
            id=s.id,
            scenario_type=s.scenario_type if isinstance(s.scenario_type, str) else s.scenario_type.value,
            total_columns=s.total_columns,
            expected_coverage_score=s.expected_coverage_score,
            picks=picks,
        ))
    return result


@router.post("/{pool_id}/coupon-optimize", response_model=CouponScenarioOut)
def coupon_optimize(
    pool_id: int,
    body: CouponOptimizeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_subscriber),
):
    pool = _get_pool_or_404(pool_id, db)
    from app.optimizer.engine import run_optimizer_custom
    picks_json = run_optimizer_custom(
        db=db,
        pool=pool,
        max_columns=body.max_columns,
        max_doubles=body.max_doubles,
        max_triples=body.max_triples,
        risk_profile=body.risk_profile,
    )
    db.commit()
    picks = [CouponPickOut(**p) for p in picks_json]
    total_cols = 1
    for p in picks:
        total_cols *= {"single": 1, "double": 2, "triple": 3}.get(p.coverage_type, 1)
    return CouponScenarioOut(
        id=0,
        scenario_type="balanced",
        total_columns=total_cols,
        expected_coverage_score=None,
        picks=picks,
    )


@router.get("/{pool_id}/changes", response_model=list[ScoreChangeOut])
def get_changes(pool_id: int, db: Session = Depends(get_db)):
    pool = _get_pool_or_404(pool_id, db)
    pm_ids = [pm.id for pm in pool.matches]
    pm_seq = {pm.id: pm.sequence_no for pm in pool.matches}

    changes = (
        db.query(models.ScoreChangeLog)
        .filter(models.ScoreChangeLog.weekly_pool_match_id.in_(pm_ids))
        .order_by(models.ScoreChangeLog.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        ScoreChangeOut(
            id=c.id,
            created_at=c.created_at,
            sequence_no=pm_seq.get(c.weekly_pool_match_id),
            old_primary_pick=c.old_primary_pick,
            new_primary_pick=c.new_primary_pick,
            old_coverage_pick=c.old_coverage_pick,
            new_coverage_pick=c.new_coverage_pick,
            change_reason_code=c.change_reason_code,
            triggered_by=c.triggered_by,
        )
        for c in changes
    ]
