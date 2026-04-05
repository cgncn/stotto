from __future__ import annotations
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MatchScoreOut(BaseModel):
    p1: float
    px: float
    p2: float
    primary_pick: str
    secondary_pick: str | None
    recommended_coverage: str | None
    confidence_score: float | None
    coverage_need_score: float | None
    reason_codes: list[str]

    model_config = {"from_attributes": True}


class PoolMatchSummary(BaseModel):
    id: int
    sequence_no: int
    fixture_external_id: int
    kickoff_at: datetime | None
    status: str
    is_locked: bool
    result: str | None
    home_team: str
    away_team: str
    latest_score: MatchScoreOut | None

    model_config = {"from_attributes": True}


class PoolSummaryOut(BaseModel):
    id: int
    week_code: str
    status: str
    announcement_time: datetime | None
    deadline_at: datetime | None
    match_count: int
    locked_count: int

    model_config = {"from_attributes": True}


class MatchDetailOut(BaseModel):
    id: int
    sequence_no: int
    fixture_external_id: int
    kickoff_at: datetime | None
    status: str
    is_locked: bool
    result: str | None
    home_team: str
    away_team: str
    latest_score: MatchScoreOut | None
    score_history: list[dict[str, Any]]
    features: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class CouponPickOut(BaseModel):
    pool_match_id: int
    sequence_no: int
    coverage_pick: str
    coverage_type: str


class CouponScenarioOut(BaseModel):
    id: int
    scenario_type: str
    total_columns: int
    expected_coverage_score: float | None
    picks: list[CouponPickOut]

    model_config = {"from_attributes": True}


class CouponOptimizeRequest(BaseModel):
    max_columns: int = 192
    max_doubles: int = 8
    max_triples: int = 3
    risk_profile: str = "medium"


class ScoreChangeOut(BaseModel):
    id: int
    created_at: datetime
    sequence_no: int | None
    old_primary_pick: str | None
    new_primary_pick: str | None
    old_coverage_pick: str | None
    new_coverage_pick: str | None
    change_reason_code: str | None
    triggered_by: str | None

    model_config = {"from_attributes": True}
