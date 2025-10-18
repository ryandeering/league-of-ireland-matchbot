"""
Just for common code shared bettwen our modules.
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple, Any

normalised_team_names = {
    "St Patrick's Athl.": "St Patrick's Athletic",
    "Dundalk": "Dundalk FC",
    "Kerry": "Kerry FC",
    "Waterford": "Waterford FC",
    "Wexford": "Wexford FC",
}

match_table_headers = ["Home Team", "Score", "Away Team", "Ground", "Status"]


table_headers = [
    "Position",
    "Team",
    "Played",
    "Won",
    "Draw",
    "Lost",
    "GF",
    "GA",
    "GD",
    "Points",
    "Form",
]


CACHE_FILE = "match_cache.json"


def normalise_team_name(team_name: str) -> str:
    """Normalise team name.

    Args:
        team_name: Team name from API

    Returns:
        Normalized team name or original if no mapping exists
    """
    return normalised_team_names.get(team_name, team_name)


def ordinal_suffix(day: int) -> str:
    """Add suffix to date header.

    Args:
        day: Day of month (1-31)

    Returns:
        Day with ordinal suffix (e.g., "1st", "22nd", "3rd")
    """
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    if 4 <= day <= 20 or 24 <= day <= 30:
        return f"{day}th"
    return f"{day}{suffixes.get(day % 10, 'th')}"


def get_last_matches(team_id: int, league_table: List[Dict[str, Any]]) -> str:
    """Return last five match results through emojis for a team.

    Args:
        team_id: Team ID from API
        league_table: League standings data

    Returns:
        String of emoji representing form (e.g., "✅⚪❌✅✅")
    """
    last_matches = 5
    team_form = next(
        (team["form"] for team in league_table
         if team["team"]["id"] == team_id),
        None
    )
    if team_form:
        return (
            team_form[-last_matches:]
            .replace("W", "✅")
            .replace("D", "⚪")
            .replace("L", "❌")
        )
    return ""


def parse_match_datetime(
        match_date_str: str,
        timezone_str: str = "Europe/Dublin") -> datetime:
    """Parse the match datetime string and adjust for daylight saving time.

    Args:
        match_date_str: ISO format datetime string from API
        timezone_str: Target timezone (default: Europe/Dublin IST)

    Returns:
        datetime object in the specified timezone
    """
    timezone = ZoneInfo(timezone_str)

    # Parse the match datetime in UTC and convert to the local timezone
    match_datetime_local = datetime.fromisoformat(
        match_date_str
    ).astimezone(timezone)

    return match_datetime_local


def get_match_status_display(fixture: Dict[str, Any]) -> Tuple[str, str]:
    """Get display text for match status and score.

    Args:
        fixture: Fixture dictionary from API-Football

    Returns:
        Tuple of (score_display, status_display)
        Examples: ("2-1", "45'"), ("vs", "19:45"), ("1-0", "FT")
    """
    # Defensive null-checking for API response structure
    status = fixture.get("fixture", {}).get("status", {}).get("short", "NS")
    elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed")
    home_score = fixture.get("goals", {}).get("home", 0)
    away_score = fixture.get("goals", {}).get("away", 0)

    # Ensure scores are not None (API can return null during pre-match)
    home_score = home_score if home_score is not None else 0
    away_score = away_score if away_score is not None else 0

    score_display = f"{home_score}-{away_score}"

    # Get kickoff time with null-safety
    fixture_date = fixture.get("fixture", {}).get("date")
    if fixture_date:
        kickoff_time = parse_match_datetime(fixture_date).strftime("%H:%M")
    else:
        kickoff_time = "TBD"

    # Pre-match
    if status in ["TBD", "NS"]:
        return "vs", kickoff_time

    # Live match statuses - map status codes to display text
    status_map = {
        "1H": f"{elapsed}'" if elapsed else "1H",
        "HT": "HT",
        "2H": f"{elapsed}'" if elapsed else "2H",
        "ET": "ET",
        "P": "Pens",
        "FT": "FT",
        "AET": "AET",
        "PEN": "Pens",
    }

    if status in status_map:
        return score_display, status_map[status]

    # Default fallback
    return "vs", status


def format_live_fixture(fixture: Dict[str, Any]) -> List[str]:
    """Format a fixture for display in match table with live score.

    Args:
        fixture: Fixture dictionary from API-Football

    Returns:
        List: [home_team, score, away_team, venue, status]
    """
    home_team = normalise_team_name(
        fixture.get("teams", {}).get("home", {}).get("name", "Unknown")
    )
    away_team = normalise_team_name(
        fixture.get("teams", {}).get("away", {}).get("name", "Unknown")
    )
    venue = fixture.get("fixture", {}).get("venue", {}).get("name", "TBD")
    score, status = get_match_status_display(fixture)

    return [home_team, score, away_team, venue, status]


def load_cache() -> Dict[str, Any]:
    """Load post metadata cache from JSON file.

    Returns:
        Dictionary containing cached post metadata for each competition
    """
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache_data: Dict[str, Any]) -> None:
    """Save post metadata cache to JSON file.

    Args:
        cache_data: Dictionary containing post metadata to cache
    """
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)


def extract_scorers(
        fixture: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Extract goal scorers from fixture events.

    Args:
        fixture: Fixture dictionary containing events

    Returns:
        Dictionary with 'home' and 'away' lists of scorer dictionaries.
        Each scorer dict contains: {name, minute, penalty, own_goal}
    """
    scorers = {"home": [], "away": []}

    if "events" not in fixture:
        return scorers

    for event in fixture["events"]:
        if event.get("type") != "Goal":
            continue

        scorer_info = {
            "name": event.get("player", {}).get("name", "Unknown"),
            "minute": event.get("time", {}).get("elapsed", 0),
            "penalty": event.get("detail", "") == "Penalty",
            "own_goal": event.get("detail", "") == "Own Goal",
        }

        team = event.get("team", {}).get("name")
        home_team = fixture.get("teams", {}).get("home", {}).get("name")

        if team and home_team and team == home_team:
            scorers["home"].append(scorer_info)
        elif team:
            scorers["away"].append(scorer_info)

    return scorers


def format_scorers_inline(fixture: Dict[str, Any]) -> str:
    """Format goal scorers as a compact inline string (fully dynamic).

    Returns scorers in format: "Team: Player (min'), Player (min') | Team: ..."
    Only includes teams with goals. Returns empty string if no goals.

    Precedence: Home team first, then away team (only if both have scored).
    If only one team scored, shows that team only.

    Args:
        fixture: Fixture dictionary

    Returns:
        Formatted inline string, or empty string if no scorers
    """
    scorers = extract_scorers(fixture)

    home_team = normalise_team_name(
        fixture.get("teams", {}).get("home", {}).get("name", "Home")
    )
    away_team = normalise_team_name(
        fixture.get("teams", {}).get("away", {}).get("name", "Away")
    )

    # Only show scorers if goals have been scored
    if not scorers["home"] and not scorers["away"]:
        return ""

    parts = []

    # Helper function to format scorer list
    def format_scorer_list(scorer_list: List[Dict[str, Any]]) -> List[str]:
        """Format a list of scorers."""
        formatted = []
        for scorer in scorer_list:
            minute_str = f"{scorer['minute']}'"
            if scorer["own_goal"]:
                formatted.append(f"{scorer['name']} (OG {minute_str})")
            elif scorer["penalty"]:
                formatted.append(f"{scorer['name']} (P {minute_str})")
            else:
                formatted.append(f"{scorer['name']} ({minute_str})")
        return formatted

    # Home team scorers (show if any goals) - FIRST precedence
    if scorers["home"]:
        scorer_list = format_scorer_list(scorers["home"])
        parts.append(f"**{home_team}:** {', '.join(scorer_list)}")

    # Away team scorers (show if any goals) - SECOND precedence
    if scorers["away"]:
        scorer_list = format_scorer_list(scorers["away"])
        parts.append(f"**{away_team}:** {', '.join(scorer_list)}")

    # Dynamically build result
    if len(parts) == 2:
        # Both teams scored: show with pipe separator
        return " | ".join(parts)
    if len(parts) == 1:
        # Only one team scored: show just that team
        return parts[0]

    return ""
