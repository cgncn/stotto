from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, and_
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


def _pm_to_summary(db: Session, pm: models.WeeklyPoolMatch) -> PoolMatchSummary:
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
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

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


@router.get("/{pool_id}", response_model=list[PoolMatchSummary])
def get_pool(pool_id: int, db: Session = Depends(get_db)):
    pool = _get_pool_or_404(pool_id, db)
    return [_pm_to_summary(db, pm) for pm in pool.matches]


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

    features = None
    if feat_snap:
        rf = feat_snap.raw_features or {}
        home_rf = rf.get("home", {})
        away_rf = rf.get("away", {})
        market_rf = rf.get("market", {})
        features = {
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
            scenario_type=s.scenario_type.value,
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
