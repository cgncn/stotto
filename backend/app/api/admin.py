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
_SEQ_RE = re.compile(r'^\d+$')
_DATE_TIME_RE = re.compile(r'^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2})$')


def _parse_raw_text(raw_text: str) -> list[dict]:
    """Parse match list in either single-line or multi-line Nesine format.

    Single-line format (space/tab-separated per row):
        1 17.04.2026 20:00 Antalyaspor-Konyaspor

    Multi-line format (one field per line, matches separated by blank lines):
        1
        17.04.2026 20:00
        Antalyaspor-Konyaspor

    Returns list of dicts with keys: seq, date (ISO), time, teams_str.
    """
    lines = [ln.strip() for ln in raw_text.splitlines()]
    parsed: list[dict] = []

    # ── Try single-line format first ────────────────────────────────────────
    for line in lines:
        m = _MATCH_LINE_RE.match(line)
        if m:
            seq, dd, mm, yyyy, time_, teams_str = (
                int(m.group(1)), m.group(2), m.group(3),
                m.group(4), m.group(5), m.group(6),
            )
            parsed.append({"seq": seq, "date": f"{yyyy}-{mm}-{dd}",
                           "time": time_, "teams_str": teams_str})

    if parsed:
        return parsed

    # ── Fall back to multi-line format ──────────────────────────────────────
    # Expected structure (blank lines between entries are ignored):
    #   <seq>
    #   <DD.MM.YYYY HH:MM>
    #   <HomeTeam-AwayTeam>
    i = 0
    while i < len(lines):
        # Skip blank lines
        if not lines[i]:
            i += 1
            continue

        # Expect: sequence number
        if not _SEQ_RE.match(lines[i]):
            i += 1
            continue
        seq = int(lines[i])

        # Next non-blank line: date+time
        j = i + 1
        while j < len(lines) and not lines[j]:
            j += 1
        if j >= len(lines):
            break
        dm = _DATE_TIME_RE.match(lines[j])
        if not dm:
            i += 1
            continue
        dd, mm, yyyy, time_ = dm.group(1), dm.group(2), dm.group(3), dm.group(4)

        # Next non-blank line: teams string
        k = j + 1
        while k < len(lines) and not lines[k]:
            k += 1
        if k >= len(lines):
            break
        teams_str = lines[k]

        parsed.append({"seq": seq, "date": f"{yyyy}-{mm}-{dd}",
                       "time": time_, "teams_str": teams_str})
        i = k + 1

    return parsed

# Last-resort hardcoded fallback (used only if all detection fails)
_FALLBACK_LEAGUES = [203, 78, 39, 140, 135, 61, 2, 3, 848]

# Map normalised keyword → league ID  (first match wins per team name)
_TEAM_LEAGUE_HINTS: dict[str, int] = {
    # Turkish Süper Lig (203)
    "besiktas": 203, "galatasaray": 203, "fenerbahce": 203, "trabzonspor": 203,
    "istanbul basaksehir": 203, "basaksehir": 203, "alanyaspor": 203, "kayserispor": 203,
    "konyaspor": 203, "goztepe": 203, "kasimpasa": 203, "antalyaspor": 203,
    "eyupspor": 203, "samsunspor": 203, "rizespor": 203, "gaziantep": 203,
    "karagumruk": 203, "kocaelispor": 203, "genclerbirligi": 203, "sivasspor": 203,
    "adana demirspor": 203, "adanaspor": 203, "ankaragucu": 203,
    # Bundesliga (78)
    "borussia dortmund": 78, "dortmund": 78, "bayer leverkusen": 78, "leverkusen": 78,
    "bayern": 78, "frankfurt": 78, "rb leipzig": 78, "leipzig": 78,
    "wolfsburg": 78, "freiburg": 78, "hoffenheim": 78, "borussia monchengladbach": 78,
    "gladbach": 78, "werder": 78, "augsburg": 78, "mainz": 78,
    "bochum": 78, "heidenheim": 78, "stuttgart": 78, "union berlin": 78,
    "st. pauli": 78,
    # Premier League (39)
    "liverpool": 39, "chelsea": 39, "arsenal": 39, "manchester city": 39,
    "manchester united": 39, "manchester": 39, "tottenham": 39, "newcastle": 39,
    "brighton": 39, "fulham": 39, "everton": 39, "nottingham": 39,
    "brentford": 39, "bournemouth": 39, "ipswich": 39, "leicester": 39,
    "southampton": 39, "aston villa": 39, "crystal palace": 39, "west ham": 39,
    "wolverhampton": 39, "wolves": 39,
    # La Liga (140)
    "real madrid": 140, "barcelona": 140, "atletico madrid": 140, "sevilla": 140,
    "villarreal": 140, "valencia": 140, "real betis": 140, "betis": 140,
    "osasuna": 140, "girona": 140, "celta": 140, "mallorca": 140,
    "getafe": 140, "alaves": 140, "athletic": 140, "real sociedad": 140,
    "espanyol": 140, "rayo vallecano": 140, "leganes": 140, "las palmas": 140,
    "valladolid": 140,
    # Serie A (135)
    "juventus": 135, "ac milan": 135, "inter milan": 135, "inter": 135,
    "napoli": 135, "roma": 135, "lazio": 135, "atalanta": 135,
    "fiorentina": 135, "torino": 135, "bologna": 135, "parma": 135,
    "genoa": 135, "udinese": 135, "verona": 135, "monza": 135,
    "lecce": 135, "empoli": 135, "cagliari": 135, "como": 135, "venezia": 135,
    # Ligue 1 (61)
    "paris saint-germain": 61, "psg": 61, "paris": 61, "marseille": 61,
    "lyon": 61, "monaco": 61, "lille": 61, "nice": 61,
    "lens": 61, "rennes": 61, "strasbourg": 61, "toulouse": 61,
    "brest": 61, "nantes": 61, "reims": 61, "montpellier": 61,
    "saint-etienne": 61, "angers": 61,
    # Primeira Liga Portugal (94)
    "porto": 94, "benfica": 94, "sporting cp": 94, "sporting": 94,
    "braga": 94, "vitoria": 94, "guimaraes": 94,
    # Eredivisie Netherlands (88)
    "ajax": 88, "psv": 88, "feyenoord": 88, "az alkmaar": 88, "az": 88,
    "utrecht": 88, "twente": 88,
    # Scottish Premiership (179)
    "celtic": 179, "rangers": 179,
    # Belgian Pro League (144)
    "anderlecht": 144, "club brugge": 144, "brugge": 144, "gent": 144,
    # Austrian Bundesliga (218)
    "salzburg": 218, "rapid wien": 218, "sturm graz": 218,
    # Swiss Super League (207)
    "young boys": 207, "basel": 207, "zurich": 207,
    # Ukrainian Premier League (332)
    "shakhtar": 332, "dynamo kyiv": 332,
    # Greek Super League (197)
    "olympiakos": 197, "panathinaikos": 197, "aek": 197,
    # Turkish 1. Lig / TFF First League (204)  — second division TR
    # (lower priority; most weekends are Süper Lig so we don't add widely)
}

# These competition IDs are always included regardless of detected teams
_ALWAYS_INCLUDE_LEAGUES = [2, 3, 848]  # UCL, UEL, UECL


def _detect_leagues_from_teams(teams_strs: list[str]) -> list[int]:
    """Detect league IDs from team name strings using keyword hints.

    Normalises each string, scans _TEAM_LEAGUE_HINTS keywords, collects unique
    league IDs, then appends _ALWAYS_INCLUDE_LEAGUES. Falls back to
    _FALLBACK_LEAGUES when nothing is detected.
    """
    detected: set[int] = set()
    for raw in teams_strs:
        n = _norm(raw)
        for keyword, league_id in _TEAM_LEAGUE_HINTS.items():
            if keyword in n:
                detected.add(league_id)
    result = list(detected) + [lid for lid in _ALWAYS_INCLUDE_LEAGUES if lid not in detected]
    return result if detected else _FALLBACK_LEAGUES


def _season_for_date(date_str: str) -> int:
    year, month = int(date_str[:4]), int(date_str[5:7])
    return year if month >= 7 else year - 1


def _coverage_score(item: dict) -> int:
    """Score a league by how complete its API coverage is.

    Top-division leagues have full coverage (odds, predictions, lineups, stats).
    Lower divisions have partial coverage. Higher score = more likely top division.
    """
    seasons = item.get("seasons", [])
    current = next((s for s in seasons if s.get("current")), {})
    cov = current.get("coverage", {})
    fix = cov.get("fixtures", {})
    return sum([
        bool(cov.get("odds")),
        bool(cov.get("predictions")),
        bool(cov.get("standings")),
        bool(cov.get("players")),
        bool(fix.get("statistics_fixtures")),
        bool(fix.get("statistics_players")),
        bool(fix.get("lineups")),
        bool(fix.get("events")),
    ])


def _fetch_main_league_ids(adapter: Any, season: int) -> list[int]:
    """Return one top-division league per country plus all international competitions.

    Fetches the full active league list in one API call, groups by country,
    and picks the league with the highest coverage score (top divisions have
    full odds/stats/lineup coverage; lower divisions don't).
    Falls back to the hardcoded list if the endpoint is restricted.
    """
    from app.adapters.api_football import APIFootballError
    try:
        data = adapter._get("leagues", {"season": season, "current": "true"})
    except APIFootballError:
        return _FALLBACK_LEAGUES

    by_country: dict[str, list[dict]] = {}
    for item in data.get("response", []):
        if not item.get("league", {}).get("id"):
            continue
        country = item.get("country", {}).get("name", "Unknown")
        # International competitions (World, Europe, etc.) each get their own slot
        if country in ("World", "Europe", "South America", "North America",
                       "Asia", "Africa", "Oceania"):
            key = f"__intl_{item['league']['id']}"
        else:
            key = country
        by_country.setdefault(key, []).append(item)

    selected = []
    for leagues in by_country.values():
        best = max(leagues, key=_coverage_score)
        selected.append(best["league"]["id"])

    return selected if selected else _FALLBACK_LEAGUES


def _fetch_fixtures_for_date(adapter: Any, date: str, league_ids: list[int] | None = None) -> list[dict]:
    """Fetch fixtures for a specific date.

    Strategy (free-tier compatible):
    1. Try date-only query — works on paid plans.
    2. For each detected league: try league+season+date (may work on some plans).
    3. For each league that blocked step 2: fetch full league+season, filter by date in Python.
       This is always available on the free tier.
    """
    from app.adapters.api_football import APIFootballError
    try:
        data = adapter._get("fixtures", {"date": date})
        results = data.get("response", [])
        if results:
            return results
    except APIFootballError:
        pass

    season = _season_for_date(date)
    if league_ids is None:
        league_ids = _FALLBACK_LEAGUES

    all_items: list[dict] = []
    seen: set[int] = set()
    for lid in league_ids:
        try:
            data = adapter._get("fixtures", {"league": lid, "season": season, "date": date})
            for item in data.get("response", []):
                fid = item.get("fixture", {}).get("id")
                if fid and fid not in seen:
                    seen.add(fid)
                    all_items.append(item)
        except APIFootballError:
            # Free tier blocks date filter — fall back to full season + Python filter
            try:
                data = adapter._get("fixtures", {"league": lid, "season": season})
                for item in data.get("response", []):
                    fix_date = (item.get("fixture", {}).get("date") or "")[:10]
                    if fix_date != date:
                        continue
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

    # ── 1. Parse lines (single-line or multi-line Nesine format) ───────────────
    parsed: list[dict] = _parse_raw_text(body.raw_text)

    if not parsed:
        raise HTTPException(status_code=422, detail="Maç satırı bulunamadı — metni kontrol edin")

    # ── 2. Detect leagues from team names, fetch season data once per league ──────
    adapter = APIFootballAdapter(db)
    team_tokens = [p["teams_str"] for p in parsed]
    league_ids = _detect_leagues_from_teams(team_tokens)
    unique_dates = {p["date"] for p in parsed}
    sample_date = next(iter(unique_dates))
    season = _season_for_date(sample_date)

    # Fetch each league once (league+season, free-tier compatible) and group by date.
    # This uses exactly len(league_ids) API calls regardless of how many dates we have.
    fixtures_by_date: dict[str, list[dict]] = {d: [] for d in unique_dates}
    seen_ids: set[int] = set()
    for lid in league_ids:
        try:
            data = adapter._get("fixtures", {"league": lid, "season": season})
            for item in data.get("response", []):
                fix_date = (item.get("fixture", {}).get("date") or "")[:10]
                if fix_date not in unique_dates:
                    continue
                fid = item.get("fixture", {}).get("id")
                if not fid or fid in seen_ids:
                    continue
                seen_ids.add(fid)
                fixtures_by_date[fix_date].append({
                    "fixture_id": fid,
                    "home": item["teams"]["home"]["name"],
                    "away": item["teams"]["away"]["name"],
                    "kickoff": item["fixture"].get("date", ""),
                    "league": item.get("league", {}).get("name", ""),
                })
        except APIFootballError:
            continue

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
            .options(
                joinedload(models.Fixture.home_team),
                joinedload(models.Fixture.away_team),
            )
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
            try:
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
            except Exception:
                pass

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


@router.get("/task/{task_id}/status")
def get_task_status(task_id: str, _: models.User = Depends(require_admin)):
    from celery.result import AsyncResult
    from app.workers.celery_app import celery_app
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": result.state,
        "result": result.result if result.ready() else None,
        "error": str(result.info) if result.failed() else None,
    }


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


# ── Model Calibration ──────────────────────────────────────────────────────────

_BASE_WEIGHTS: dict[str, dict[str, float]] = {
    "score_1": {
        "strength_edge_norm": 0.08, "form_edge_norm": 0.18, "home_advantage": 0.10,
        "lineup_edge_home": 0.09, "motivation_edge": 0.08, "h2h_home_advantage": 0.08,
        "market_support": 0.07, "away_form_penalty": 0.07, "schedule_edge": 0.06,
        "sharp_money_home_signal": 0.05, "congestion_advantage": 0.04,
        "xg_luck_edge": 0.04, "last_5_home_attack_edge": 0.06,
    },
    "score_x": {
        "draw_tendency": 0.22, "balance_score": 0.14, "low_tempo_signal": 0.11,
        "low_goal_signal": 0.10, "h2h_draw_rate": 0.09, "market_draw_signal": 0.09,
        "equal_motivation": 0.08, "tactical_symmetry": 0.08, "volatility_mid_zone": 0.09,
    },
    "score_2": {
        "away_strength_edge_norm": 0.08, "away_form_edge_norm": 0.18, "weak_home_signal": 0.10,
        "lineup_edge_away": 0.09, "away_motivation_edge": 0.08, "h2h_bogey_signal": 0.08,
        "away_market_support": 0.07, "away_form_away": 0.07, "schedule_edge_away": 0.06,
        "sharp_money_away_signal": 0.05, "intl_break_home_penalty": 0.04,
        "xg_luck_edge_away": 0.04, "last_5_away_attack_edge": 0.06,
    },
}

_MIN_MATCHES = 10   # require at least this many labelled matches before auto-applying
_LEARNING_RATE = 0.05
_SOFTMAX_T = 0.4


def _brier_score(p1: float, px: float, p2: float, result: str) -> float:
    y1 = 1.0 if result == "1" else 0.0
    yx = 1.0 if result == "X" else 0.0
    y2 = 1.0 if result == "2" else 0.0
    return (p1 - y1) ** 2 + (px - yx) ** 2 + (p2 - y2) ** 2


def _softmax3(s1: float, sx: float, s2: float, T: float = _SOFTMAX_T):
    import math
    vals = [s1 / T, sx / T, s2 / T]
    m = max(vals)
    exps = [math.exp(v - m) for v in vals]
    total = sum(exps)
    return exps[0] / total, exps[1] / total, exps[2] / total


def _collect_calibration_data(db: Session):
    """Return list of {p1,px,p2,result,features} for all scored+settled matches."""
    from sqlalchemy import func as sqlfunc

    # Subquery: latest score per match
    latest_score_sq = (
        db.query(
            models.MatchModelScore.weekly_pool_match_id,
            sqlfunc.max(models.MatchModelScore.created_at).label("max_ts"),
        )
        .group_by(models.MatchModelScore.weekly_pool_match_id)
        .subquery()
    )

    rows = (
        db.query(models.WeeklyPoolMatch, models.MatchModelScore, models.MatchFeatureSnapshot)
        .join(
            latest_score_sq,
            models.MatchModelScore.weekly_pool_match_id == latest_score_sq.c.weekly_pool_match_id,
        )
        .filter(models.MatchModelScore.created_at == latest_score_sq.c.max_ts)
        .outerjoin(
            models.MatchFeatureSnapshot,
            models.MatchFeatureSnapshot.weekly_pool_match_id == models.WeeklyPoolMatch.id,
        )
        .join(models.WeeklyPool, models.WeeklyPool.id == models.WeeklyPoolMatch.weekly_pool_id)
        .filter(
            models.WeeklyPool.status == models.PoolStatus.settled,
            models.WeeklyPoolMatch.result.isnot(None),
        )
        .all()
    )

    data = []
    for pm, score, feat in rows:
        if not pm.result or score.p1 is None:
            continue
        feat_vals = {}
        if feat and feat.raw_features:
            # We'll compute gradients from stored feature values via _FeatureBundle proxy
            from app.scoring.engine import _FeatureBundle
            bundle = _FeatureBundle(feat)
            for section in ("score_1", "score_x", "score_2"):
                feat_vals[section] = {
                    sig: getattr(bundle, sig, 0.5)
                    for sig in _BASE_WEIGHTS[section]
                }
        data.append({
            "p1": score.p1, "px": score.px, "p2": score.p2,
            "result": pm.result,
            "features": feat_vals,
        })
    return data


def _compute_gradients(data: list[dict]) -> dict:
    """
    Compute mean Brier-score gradient w.r.t. each signal weight.

    For score_1 signal s with weight w:
      dBS/dw ≈ mean_over_matches[ 2*(p1-y1) * p1*(1-p1)/T * feature_s ]

    Positive gradient → weight is too high (reduce it).
    Negative gradient → weight is too low (increase it).
    """
    gradients: dict[str, dict[str, float]] = {k: {} for k in _BASE_WEIGHTS}

    for section, score_label in [("score_1", "1"), ("score_x", "X"), ("score_2", "2")]:
        for sig in _BASE_WEIGHTS[section]:
            grads = []
            for d in data:
                if section not in d["features"]:
                    continue
                p = d["p1"] if score_label == "1" else (d["px"] if score_label == "X" else d["p2"])
                y = 1.0 if d["result"] == score_label else 0.0
                feat_val = d["features"][section].get(sig, 0.5)
                dpds = p * (1.0 - p) / _SOFTMAX_T   # softmax Jacobian diagonal approx
                grads.append(2.0 * (p - y) * dpds * feat_val)
            gradients[section][sig] = sum(grads) / len(grads) if grads else 0.0

    return gradients


def _apply_gradient_step(
    current_multipliers: dict,
    gradients: dict,
    lr: float = _LEARNING_RATE,
) -> dict:
    """Nudge multipliers one step in the negative-gradient direction, clamp to [0.2, 5.0]."""
    new_mults: dict[str, dict[str, float]] = {}
    for section in _BASE_WEIGHTS:
        new_mults[section] = {}
        for sig in _BASE_WEIGHTS[section]:
            current = current_multipliers.get(section, {}).get(sig, 1.0)
            grad = gradients.get(section, {}).get(sig, 0.0)
            updated = current - lr * grad
            new_mults[section][sig] = max(0.2, min(5.0, updated))
    return new_mults


@router.get("/calibration")
def get_calibration(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return current calibration state and per-signal gradient analysis."""
    data = _collect_calibration_data(db)
    n = len(data)

    if n == 0:
        return {"n_matches": 0, "brier_score": None, "gradients": {}, "active_multipliers": {}, "ready": False}

    brier = sum(_brier_score(d["p1"], d["px"], d["p2"], d["result"]) for d in data) / n

    # Accuracy
    correct = sum(1 for d in data if (
        (d["p1"] >= d["px"] and d["p1"] >= d["p2"] and d["result"] == "1") or
        (d["px"] >= d["p1"] and d["px"] >= d["p2"] and d["result"] == "X") or
        (d["p2"] >= d["p1"] and d["p2"] >= d["px"] and d["result"] == "2")
    ))

    gradients = _compute_gradients(data)

    # Active multipliers
    active = db.query(models.ModelCalibration).filter_by(is_active=True).order_by(
        models.ModelCalibration.created_at.desc()
    ).first()
    active_mults = active.multipliers if active else {}

    # Calibration by confidence tier
    tiers = {"low": [], "mid": [], "high": []}
    scored = (
        db.query(models.WeeklyPoolMatch, models.MatchModelScore)
        .join(models.MatchModelScore, models.MatchModelScore.weekly_pool_match_id == models.WeeklyPoolMatch.id)
        .join(models.WeeklyPool, models.WeeklyPool.id == models.WeeklyPoolMatch.weekly_pool_id)
        .filter(
            models.WeeklyPool.status == models.PoolStatus.settled,
            models.WeeklyPoolMatch.result.isnot(None),
            models.MatchModelScore.confidence_score.isnot(None),
        )
        .all()
    )
    for pm, sc in scored:
        tier = "high" if sc.confidence_score >= 60 else ("mid" if sc.confidence_score >= 35 else "low")
        is_correct = sc.primary_pick == pm.result
        tiers[tier].append(is_correct)

    confidence_calibration = {
        t: {
            "n": len(v),
            "accuracy_pct": round(100 * sum(v) / len(v)) if v else None,
        }
        for t, v in tiers.items()
    }

    return {
        "n_matches": n,
        "brier_score": round(brier, 4),
        "accuracy_pct": round(100 * correct / n) if n else None,
        "confidence_calibration": confidence_calibration,
        "gradients": {
            section: {
                sig: round(g, 5)
                for sig, g in sigs.items()
            }
            for section, sigs in gradients.items()
        },
        "active_multipliers": active_mults,
        "ready": n >= _MIN_MATCHES,
        "min_matches_required": _MIN_MATCHES,
    }


@router.post("/calibrate")
def apply_calibration(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Apply one gradient-descent step to the active calibration multipliers.

    Requires at least MIN_MATCHES settled+scored matches.
    Deactivates the previous calibration row and inserts a new one.
    """
    data = _collect_calibration_data(db)
    n = len(data)

    if n < _MIN_MATCHES:
        raise HTTPException(
            status_code=422,
            detail=f"Yetersiz veri: {n}/{_MIN_MATCHES} maç gerekli",
        )

    brier_before = sum(_brier_score(d["p1"], d["px"], d["p2"], d["result"]) for d in data) / n

    # Load current multipliers (or start from identity)
    active = db.query(models.ModelCalibration).filter_by(is_active=True).order_by(
        models.ModelCalibration.created_at.desc()
    ).first()
    current_mults = active.multipliers if active else {}

    gradients = _compute_gradients(data)
    new_mults = _apply_gradient_step(current_mults, gradients)

    # Deactivate previous
    if active:
        active.is_active = False

    # Insert new
    cal_row = models.ModelCalibration(
        applied_by=f"admin:{admin.email}",
        multipliers=new_mults,
        brier_before=round(brier_before, 4),
        n_matches=n,
        is_active=True,
    )
    db.add(cal_row)
    db.commit()

    return {
        "detail": "Kalibrasyon uygulandı",
        "n_matches": n,
        "brier_before": round(brier_before, 4),
        "top_adjustments": {
            section: sorted(
                [
                    {"signal": sig, "multiplier": round(new_mults[section][sig], 3),
                     "gradient": round(gradients[section].get(sig, 0), 5)}
                    for sig in new_mults[section]
                ],
                key=lambda x: abs(x["gradient"]),
                reverse=True,
            )[:3]
            for section in new_mults
        },
    }
