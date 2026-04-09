from typing import Any
from pydantic import BaseModel


class FixtureImportItem(BaseModel):
    external_id: int
    admin_flags: dict[str, Any] = {}
    # Supported keys:
    #   thursday_european_away: bool  — away team played European fixture on Thursday
    #   manager_pressure_home: bool   — home manager under sacking pressure (informational)


class WeeklyImportRequest(BaseModel):
    week_code: str
    # Support both simple list and rich list with per-fixture flags
    fixture_external_ids: list[int] = []
    fixtures: list[FixtureImportItem] = []

    def get_fixture_items(self) -> list[FixtureImportItem]:
        """Return unified list of FixtureImportItems, regardless of which field was used."""
        if self.fixtures:
            return self.fixtures
        return [FixtureImportItem(external_id=eid) for eid in self.fixture_external_ids]


class ResolveListRequest(BaseModel):
    raw_text: str
    week_code: str


class ManualOverrideRequest(BaseModel):
    weekly_pool_match_id: int
    primary_pick: str
    coverage_pick: str
    reason: str = "manual_override"
