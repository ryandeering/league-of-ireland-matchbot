"""Match data client for League of Ireland.

This client fetches match data from external football data APIs.
"""

import logging
import re
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

# League IDs for League of Ireland competitions
LEAGUE_ID_PREMIER = 126  # Premier Division
LEAGUE_ID_FIRST = 218    # First Division
LEAGUE_ID_FAI_CUP = 219  # FAI Cup

# API Configuration
_API_BASE_URL = "https://www.fotmob.com/api"
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
MIN_REQUEST_INTERVAL = 0.2  # 200ms between requests


class MatchDataClient:
    """Client for fetching match data from external API."""

    def __init__(self):
        """Initialize the match data client."""
        self.base_url = _API_BASE_URL
        self.headers = {"User-Agent": _DEFAULT_USER_AGENT}
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _get(
        self, endpoint: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Make a GET request to the API.

        Args:
            endpoint: API endpoint (e.g., "/leagues")
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            requests.exceptions.RequestException: On network/HTTP errors
        """
        self._rate_limit()
        url = f"{self.base_url}{endpoint}"

        response = requests.get(
            url,
            params=params,
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def get_league_matches(
        self,
        league_id: int,
        tab: str = "fixtures"
    ) -> dict[str, Any]:
        """Fetch matches for a league.

        Args:
            league_id: League ID (126=Premier, 218=First, 219=FAI Cup)
            tab: "fixtures" for upcoming, "results" for finished

        Returns:
            Full league response including matches
        """
        try:
            return self._get("/leagues", params={"id": league_id, "tab": tab})
        except requests.exceptions.RequestException as exc:
            logger.error("Error fetching league %s matches: %s", league_id, exc)
            return {}

    def get_match_details(self, match_id: int) -> dict[str, Any]:
        """Fetch detailed information for a specific match.

        Args:
            match_id: Match ID

        Returns:
            Match details including events, lineups, stats
        """
        try:
            return self._get("/matchDetails", params={"matchId": match_id})
        except requests.exceptions.RequestException as exc:
            logger.error("Error fetching match %s details: %s", match_id, exc)
            return {}

    def get_all_matches(self, league_id: int) -> list[dict[str, Any]]:
        """Get all matches (fixtures + results) for a league.

        Args:
            league_id: League ID

        Returns:
            List of all match dictionaries
        """
        all_matches = []

        fixtures_data = self.get_league_matches(league_id, tab="fixtures")
        if fixtures_data:
            matches = self.extract_matches(fixtures_data)
            all_matches.extend(matches)

        results_data = self.get_league_matches(league_id, tab="results")
        if results_data:
            matches = self.extract_matches(results_data)
            all_matches.extend(matches)

        return all_matches

    def extract_matches(
        self, league_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract match list from league API response.

        Args:
            league_data: Raw league API response

        Returns:
            List of match dictionaries
        """
        fixtures = league_data.get("fixtures", {})
        if not fixtures:
            fixtures = league_data.get("results", {})

        return fixtures.get("allMatches", [])

    def get_league_table(
        self, league_id: int
    ) -> Optional[list[dict[str, Any]]]:
        """Get league standings table.

        Args:
            league_id: League ID

        Returns:
            List of team standings, or None if the request fails
        """
        try:
            data = self._get("/leagues", params={"id": league_id})
            table_data = data.get("table", [])
            if table_data:
                return (
                    table_data[0]
                    .get("data", {})
                    .get("table", {})
                    .get("all", [])
                )
            return []
        except requests.exceptions.RequestException as exc:
            logger.error("Error fetching league %s table: %s", league_id, exc)
            return None

    def get_live_matches(self, league_ids: list[int]) -> list[dict[str, Any]]:
        """Get currently live matches for specified leagues.

        Args:
            league_ids: List of league IDs

        Returns:
            List of live match dictionaries
        """
        live_matches = []

        for league_id in league_ids:
            data = self.get_league_matches(league_id, tab="fixtures")
            if not data:
                continue

            matches = self.extract_matches(data)

            for match in matches:
                status = match.get("status", {})
                if status.get("started") and not status.get("finished"):
                    match["_league_id"] = league_id
                    live_matches.append(match)

        return live_matches


def _determine_match_status(status: dict[str, Any]) -> str:
    """Determine the short status code from match status data.

    Args:
        status: Status dictionary from raw match data

    Returns:
        Short status code (NS, 1H, HT, 2H, FT, CANC, LIVE)
    """
    if status.get("cancelled"):
        return "CANC"
    if status.get("finished"):
        return "FT"
    if not status.get("started"):
        return "NS"

    live_time = status.get("liveTime", {})
    short_time = live_time.get("short", "")
    clean_short = re.sub(r'[^\dHT+]', '', short_time)

    if "HT" in clean_short:
        return "HT"
    if clean_short:
        max_time = live_time.get("maxTime", 45)
        return "1H" if max_time <= 45 else "2H"
    return "LIVE"


def _extract_elapsed_time(status: dict[str, Any]) -> Optional[int]:
    """Extract elapsed time from match status.

    Args:
        status: Status dictionary from raw match data

    Returns:
        Elapsed minutes or None
    """
    if not status.get("started") or status.get("finished"):
        return None

    live_time = status.get("liveTime", {})
    elapsed_str = live_time.get("short", "")

    if not elapsed_str or elapsed_str in ("HT", "FT"):
        return None

    try:
        clean_str = re.sub(r'[^\d+]', '', elapsed_str)
        if clean_str:
            parts = clean_str.split("+")
            return int(parts[0]) if parts[0] else None
    except (ValueError, IndexError):
        pass

    return None


def convert_raw_match(raw_match: dict[str, Any]) -> dict[str, Any]:
    """Convert raw match format to api-football compatible format.

    This allows existing code to work with minimal changes.

    Args:
        raw_match: Match data from external API

    Returns:
        Match data in api-football format
    """
    status = raw_match.get("status", {})

    status_short = _determine_match_status(status)
    elapsed = _extract_elapsed_time(status)

    utc_time = status.get("utcTime", "")
    match_date = utc_time if utc_time else datetime.now(ZoneInfo("UTC")).isoformat()

    score = status.get("score", {})
    home_score = score.get("home")
    away_score = score.get("away")

    home_data = raw_match.get("home", {})
    away_data = raw_match.get("away", {})

    return {
        "fixture": {
            "id": int(raw_match.get("id", 0)),
            "date": match_date,
            "status": {
                "short": status_short,
                "elapsed": elapsed,
            },
            "venue": {
                "name": raw_match.get("venue", "TBD"),
            },
        },
        "league": {
            "id": raw_match.get("_league_id", 0),
            "round": f"Regular Season - {raw_match.get('round') or ''}",
        },
        "teams": {
            "home": {
                "id": int(home_data.get("id", 0)),
                "name": home_data.get("name", "Unknown"),
            },
            "away": {
                "id": int(away_data.get("id", 0)),
                "name": away_data.get("name", "Unknown"),
            },
        },
        "goals": {
            "home": home_score,
            "away": away_score,
        },
        "events": [],
        "_source_id": raw_match.get("id"),
    }


def _parse_scores_str(scores_str: str) -> tuple[int, int]:
    """Parse a 'GF-GA' string into separate goal counts.

    Args:
        scores_str: Score string from API (e.g. "10-4")

    Returns:
        Tuple of (goals_for, goals_against), defaults to (0, 0)
    """
    if scores_str and "-" in scores_str:
        parts = scores_str.split("-")
        try:
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass
    return 0, 0


def convert_raw_table(raw_table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw table format to api-football compatible format.

    Args:
        raw_table: Table data from external API

    Returns:
        Table data in api-football format
    """
    converted = []

    for row in raw_table:
        goals_for, goals_against = _parse_scores_str(row.get("scoresStr", ""))

        converted.append({
            "rank": row.get("idx", 0),
            "team": {
                "id": row.get("id", 0),
                "name": row.get("name", "Unknown"),
            },
            "all": {
                "played": row.get("played", 0),
                "win": row.get("wins", 0),
                "draw": row.get("draws", 0),
                "lose": row.get("losses", 0),
                "goals": {
                    "for": goals_for,
                    "against": goals_against,
                },
            },
            "goalsDiff": row.get("goalConDiff", 0),
            "points": row.get("pts", 0),
            "form": "",
        })

    return converted


def extract_venue_from_details(match_details: dict[str, Any]) -> str:
    """Extract venue name from match details.

    Args:
        match_details: Full match details from API

    Returns:
        Venue name or empty string if not found
    """
    content = match_details.get("content", {})
    match_facts = content.get("matchFacts", {})
    info_box = match_facts.get("infoBox", {})
    stadium = info_box.get("Stadium")
    if not stadium:
        return ""
    return stadium.get("name", "")


def extract_score_from_details(
    match_details: dict[str, Any],
) -> tuple[Optional[int], Optional[int]]:
    """Extract home and away scores from match details header.

    FotMob's leagues endpoint can return null scores for LOI matches,
    but the matchDetails endpoint includes them in header.teams[].score.

    Args:
        match_details: Full match details from API

    Returns:
        Tuple of (home_score, away_score), or (None, None) if not found
    """
    header = match_details.get("header", {})
    teams = header.get("teams", [])
    if len(teams) >= 2:
        home_score = teams[0].get("score")
        away_score = teams[1].get("score")
        if home_score is not None and away_score is not None:
            return int(home_score), int(away_score)
    return None, None


def enrich_fixtures_with_venues(
    client: MatchDataClient,
    fixtures: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fetch venue and score data for each fixture from match details endpoint.

    Also fills in missing scores from matchDetails when the leagues
    endpoint returns null (common for LOI).

    Args:
        client: MatchDataClient instance
        fixtures: List of fixtures in api-football format

    Returns:
        Same fixtures with venue names and scores populated
    """
    for fixture in fixtures:
        match_id = fixture.get("fixture", {}).get("id")
        if match_id:
            details = client.get_match_details(match_id)
            if details:
                venue = extract_venue_from_details(details)
                if venue:
                    fixture["fixture"]["venue"]["name"] = venue
                if fixture.get("goals", {}).get("home") is None:
                    home, away = extract_score_from_details(details)
                    if home is not None:
                        fixture["goals"]["home"] = home
                        fixture["goals"]["away"] = away
    return fixtures


def convert_match_events(match_details: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract and convert events from match details.

    Args:
        match_details: Full match details from API

    Returns:
        List of events in api-football format
    """
    events = []

    content = match_details.get("content", {})
    match_facts = content.get("matchFacts", {})

    header = match_details.get("header", {})
    teams = header.get("teams", [])
    home_team = teams[0].get("name", "Home") if teams else "Home"
    away_team = teams[1].get("name", "Away") if len(teams) > 1 else "Away"

    events_data = match_facts.get("events", {})

    for event in events_data.get("events", []):
        event_type = event.get("type", "")

        if event_type == "Goal":
            is_home = event.get("isHome", True)
            team_name = home_team if is_home else away_team

            detail = "Normal Goal"
            if event.get("ownGoal"):
                detail = "Own Goal"
            elif (event.get("isPenalty")
                  or event.get("goalDescriptionKey") == "penalty"):
                detail = "Penalty"

            events.append({
                "type": "Goal",
                "team": {"name": team_name},
                "player": {"name": event.get("nameStr", "Unknown")},
                "time": {"elapsed": event.get("time", 0)},
                "detail": detail,
                "isHome": is_home,
            })

    return events
