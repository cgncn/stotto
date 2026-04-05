from pydantic import BaseModel


class WeeklyImportRequest(BaseModel):
    week_code: str
    fixture_external_ids: list[int]


class ManualOverrideRequest(BaseModel):
    weekly_pool_match_id: int
    primary_pick: str
    coverage_pick: str
    reason: str = "manual_override"
