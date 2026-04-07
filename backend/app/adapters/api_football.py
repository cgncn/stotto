"""
API-Football adapter.
Single source of truth for all external HTTP calls.
Raw payloads are stored as snapshots before being returned.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db import models

logger = logging.getLogger(__name__)

_BACKOFF_DELAYS = [1, 2, 4]  # seconds


class APIFootballError(Exception):
    pass


class APIFootballAdapter:
    def __init__(self, db: Session):
        self.db = db
        self.base_url = settings.api_football_base_url.rstrip("/")
        self.headers = {
            "x-apisports-key": settings.api_football_key,
        }

    # ── Internal HTTP ──────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_exc: Exception | None = None

        for attempt, delay in enumerate([0] + _BACKOFF_DELAYS, start=1):
            if delay:
                time.sleep(delay)
            try:
                response = httpx.get(url, headers=self.headers, params=params or {}, timeout=15)
            except httpx.RequestError as exc:
                logger.warning("Request error (attempt %d): %s", attempt, exc)
                last_exc = exc
                continue

            if response.status_code == 429:
                logger.warning("Rate limited (attempt %d), backing off", attempt)
                last_exc = APIFootballError("Rate limited")
                time.sleep(7)
                continue

            if response.status_code >= 500:
                logger.warning("Server error %d (attempt %d)", response.status_code, attempt)
                last_exc = APIFootballError(f"HTTP {response.status_code}")
                continue

            if response.status_code != 200:
                raise APIFootballError(f"HTTP {response.status_code}: {response.text[:200]}")

            data = response.json()
            errors = data.get("errors", {})
            if errors:
                if "rateLimit" in errors:
                    logger.warning("API rate limit hit (attempt %d), sleeping 7s", attempt)
                    last_exc = APIFootballError(f"API errors: {errors}")
                    time.sleep(7)
                    continue
                raise APIFootballError(f"API errors: {errors}")

            return data

        raise APIFootballError(f"All retries failed: {last_exc}") from last_exc

    def _flag_missing(self, payload: dict, required_keys: list[str], context: str) -> list[str]:
        missing = [k for k in required_keys if payload.get(k) is None]
        if missing:
            logger.warning("[%s] Missing fields: %s", context, missing)
        return missing

    # ── Fixtures ───────────────────────────────────────────────────────────

    def fetch_fixture(self, fixture_id: int) -> dict[str, Any]:
        data = self._get("fixtures", {"id": fixture_id})
        response_list = data.get("response", [])
        if not response_list:
            raise APIFootballError(f"No fixture data for id={fixture_id}")
        raw = response_list[0]
        self._flag_missing(
            raw.get("fixture", {}),
            ["id", "date", "status"],
            f"fixture:{fixture_id}",
        )
        return raw

    def fetch_fixtures_by_league(self, league_id: int, season: int) -> list[dict]:
        data = self._get("fixtures", {"league": league_id, "season": season})
        return data.get("response", [])

    # ── Standings ──────────────────────────────────────────────────────────

    def fetch_standings(self, league_id: int, season: int, db: Session | None = None) -> list[dict]:
        db = db or self.db
        data = self._get("standings", {"league": league_id, "season": season})
        response_list = data.get("response", [])

        snapshot = models.StandingsSnapshot(
            league_id=league_id,
            season=season,
            snapshot_time=datetime.now(timezone.utc),
            payload_json=response_list,
        )
        db.add(snapshot)
        db.flush()

        return response_list

    # ── Odds ───────────────────────────────────────────────────────────────

    def fetch_odds(self, fixture_id: int) -> dict[str, Any] | None:
        data = self._get("odds", {"fixture": fixture_id, "bookmaker": 8})  # bookmaker 8 = Bet365
        response_list = data.get("response", [])
        if not response_list:
            logger.warning("No odds found for fixture=%d", fixture_id)
            return None

        raw = response_list[0]
        home_odds, draw_odds, away_odds = self._parse_1x2_odds(raw)

        snapshot = models.FixtureOddsSnapshot(
            fixture_id=self._get_fixture_db_id(fixture_id),
            snapshot_time=datetime.now(timezone.utc),
            home_odds=home_odds,
            draw_odds=draw_odds,
            away_odds=away_odds,
            bookmaker="bet365",
            raw_payload=raw,
        )
        self.db.add(snapshot)
        self.db.flush()

        return {"home_odds": home_odds, "draw_odds": draw_odds, "away_odds": away_odds, "raw": raw}

    def _parse_1x2_odds(self, raw: dict) -> tuple[float | None, float | None, float | None]:
        try:
            bookmakers = raw.get("bookmakers", [])
            for bm in bookmakers:
                for bet in bm.get("bets", []):
                    if bet.get("name") == "Match Winner":
                        values = {v["value"]: float(v["odd"]) for v in bet.get("values", [])}
                        return values.get("Home"), values.get("Draw"), values.get("Away")
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse 1X2 odds: %s", exc)
        return None, None, None

    # ── Lineups ────────────────────────────────────────────────────────────

    def fetch_lineups(self, fixture_id: int) -> list[dict]:
        data = self._get("fixtures/lineups", {"fixture": fixture_id})
        response_list = data.get("response", [])

        snapshot = models.FixtureLineupsSnapshot(
            fixture_id=self._get_fixture_db_id(fixture_id),
            snapshot_time=datetime.now(timezone.utc),
            payload_json=response_list,
        )
        self.db.add(snapshot)
        self.db.flush()

        if not response_list:
            logger.warning("No lineups for fixture=%d — using empty list", fixture_id)
        return response_list

    # ── Injuries / Suspensions ─────────────────────────────────────────────

    def fetch_injuries(self, fixture_id: int) -> list[dict]:
        data = self._get("injuries", {"fixture": fixture_id})
        response_list = data.get("response", [])

        snapshot = models.FixtureInjuriesSnapshot(
            fixture_id=self._get_fixture_db_id(fixture_id),
            snapshot_time=datetime.now(timezone.utc),
            payload_json=response_list,
        )
        self.db.add(snapshot)
        self.db.flush()

        return response_list

    # ── Head-to-Head ───────────────────────────────────────────────────────

    def fetch_h2h(self, home_ext_id: int, away_ext_id: int, fixture_db_id: int) -> list[dict]:
        """
        Fetch last 10 head-to-head fixtures between two teams and store snapshot.
        Returns list of past fixture dicts from API-Football.
        """
        data = self._get(
            "fixtures/headtohead",
            {"h2h": f"{home_ext_id}-{away_ext_id}", "last": 10},
        )
        response_list = data.get("response", [])

        snapshot = models.FixtureH2HSnapshot(
            fixture_id=fixture_db_id,
            snapshot_time=datetime.now(timezone.utc),
            home_team_id=home_ext_id,
            away_team_id=away_ext_id,
            payload_json=response_list,
        )
        self.db.add(snapshot)
        self.db.flush()

        return response_list

    # ── Statistics ─────────────────────────────────────────────────────────

    def fetch_statistics(self, fixture_id: int) -> list[dict]:
        data = self._get("fixtures/statistics", {"fixture": fixture_id})
        response_list = data.get("response", [])

        snapshot = models.FixtureStatisticsSnapshot(
            fixture_id=self._get_fixture_db_id(fixture_id),
            snapshot_time=datetime.now(timezone.utc),
            payload_json=response_list,
        )
        self.db.add(snapshot)
        self.db.flush()

        return response_list

    # ── Upsert helpers ─────────────────────────────────────────────────────

    def upsert_fixture(self, raw: dict) -> models.Fixture:
        fix_data = raw.get("fixture", {})
        teams_data = raw.get("teams", {})
        ext_id = fix_data["id"]

        home = self._upsert_team(teams_data["home"])
        away = self._upsert_team(teams_data["away"])

        fixture = self.db.query(models.Fixture).filter_by(external_provider_id=ext_id).first()
        kickoff = fix_data.get("date")
        if isinstance(kickoff, str):
            from dateutil.parser import parse as dt_parse
            kickoff = dt_parse(kickoff)

        if fixture:
            fixture.status = fix_data.get("status", {}).get("short", fixture.status)
            fixture.kickoff_at = kickoff or fixture.kickoff_at
            home_score = raw.get("goals", {}).get("home")
            away_score = raw.get("goals", {}).get("away")
            if home_score is not None:
                fixture.home_score = home_score
            if away_score is not None:
                fixture.away_score = away_score
        else:
            league_data = raw.get("league", {})
            fixture = models.Fixture(
                external_provider_id=ext_id,
                season=league_data.get("season", 0),
                league_id=league_data.get("id", 0),
                home_team_id=home.id,
                away_team_id=away.id,
                kickoff_at=kickoff,
                venue=fix_data.get("venue", {}).get("name"),
                status=fix_data.get("status", {}).get("short", "NS"),
            )
            self.db.add(fixture)

        self.db.flush()
        return fixture

    def _upsert_team(self, team_data: dict) -> models.Team:
        ext_id = team_data["id"]
        team = self.db.query(models.Team).filter_by(external_provider_id=ext_id).first()
        if not team:
            team = models.Team(
                external_provider_id=ext_id,
                name=team_data.get("name", ""),
                logo_url=team_data.get("logo"),
            )
            self.db.add(team)
            self.db.flush()
        return team

    def _get_fixture_db_id(self, external_fixture_id: int) -> int:
        fixture = self.db.query(models.Fixture).filter_by(external_provider_id=external_fixture_id).first()
        if not fixture:
            raise APIFootballError(
                f"Fixture with external_id={external_fixture_id} not found in DB. "
                "Call upsert_fixture first."
            )
        return fixture.id
