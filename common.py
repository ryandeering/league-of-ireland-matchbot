"""
Just for common code shared bettwen our modules.
"""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple, Any

normalised_team_names = {
    "St Patrick's Athl.": "St. Patrick's Athletic",
}

match_table_headers = ["Home Team", "Score", "Away Team", "Ground", "Status", "Kickoff", "Scorers"]


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
        Normalized team name with FC suffix removed
    """
    name = normalised_team_names.get(team_name, team_name)
    # Remove FC suffix from all team names
    if name.endswith(" FC"):
        name = name[:-3]
    return name


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
        (team.get("form", "") for team in league_table
         if team.get("team", {}).get("id") == team_id),
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


def get_fixture_dublin_date(fixture: Dict[str, Any]) -> str:
    """Get fixture date as a Dublin-local ISO date string (YYYY-MM-DD).

    Handles DST correctly so late UTC matches are grouped under the
    right local day.

    Args:
        fixture: Fixture dictionary (outer dict containing "fixture" key)

    Returns:
        Date string in YYYY-MM-DD format (Dublin timezone), or ""
    """
    date_str = fixture.get("fixture", {}).get("date", "")
    if not date_str:
        return ""
    return parse_match_datetime(date_str).date().isoformat()


def get_match_status_display(fixture: Dict[str, Any]) -> Tuple[str, str]:
    """Get display text for match status and score.

    Args:
        fixture: Fixture dictionary from API-Football

    Returns:
        Tuple of (score_display, status_display)
        Examples: ("2-1", "45'"), ("vs", "19:45"), ("1-0", "FT")
    """
    status = fixture.get("fixture", {}).get("status", {}).get("short", "NS")
    elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed")
    home_score = fixture.get("goals", {}).get("home")
    away_score = fixture.get("goals", {}).get("away")

    fixture_date = fixture.get("fixture", {}).get("date")
    if fixture_date:
        kickoff_time = parse_match_datetime(fixture_date).strftime("%H:%M")
    else:
        kickoff_time = "TBD"

    # Pre-match
    if status in ["TBD", "NS"]:
        return "vs", kickoff_time

    # For started/finished matches, handle missing scores
    if home_score is not None and away_score is not None:
        score_display = f"{home_score}-{away_score}"
    else:
        score_display = "vs"

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
        "LIVE": f"{elapsed}'" if elapsed else "LIVE",
        "CANC": "CANC",
    }

    if status in status_map:
        return score_display, status_map[status]

    # Default fallback
    return "vs", status


def format_scorers_compact(fixture: Dict[str, Any]) -> str:
    """Format goal scorers as a compact string for table column.

    Returns scorers in format: "Home scorers - Away scorers"
    e.g., "Greene 23', 62' - Devoy P34'"
    Groups multiple goals by the same player.

    Args:
        fixture: Fixture dictionary

    Returns:
        Compact scorer string, or empty string if no scorers
    """
    scorers = extract_scorers(fixture)

    if not scorers["home"] and not scorers["away"]:
        return ""

    def format_list(scorer_list: List[Dict[str, Any]]) -> str:
        # Group goals by player name
        player_goals: Dict[str, List[str]] = {}
        for s in scorer_list:
            name = s["name"]
            if s["own_goal"]:
                minute_str = f"OG{s['minute']}'"
            elif s["penalty"]:
                minute_str = f"P{s['minute']}'"
            else:
                minute_str = f"{s['minute']}'"

            if name not in player_goals:
                player_goals[name] = []
            player_goals[name].append(minute_str)

        # Format as "Player min1', min2'" for multiple goals
        parts = []
        for name, minutes in player_goals.items():
            parts.append(f"{name} {', '.join(minutes)}")
        return ", ".join(parts)

    home_str = format_list(scorers["home"])
    away_str = format_list(scorers["away"])

    if home_str and away_str:
        return f"{home_str} - {away_str}"
    return home_str or away_str


def format_live_fixture(fixture: Dict[str, Any]) -> List[str]:
    """Format a fixture for display in match table with live score.

    Args:
        fixture: Fixture dictionary from API-Football

    Returns:
        List: [home_team, score, away_team, venue, status, kickoff, scorers]
    """
    home_team = normalise_team_name(
        fixture.get("teams", {}).get("home", {}).get("name", "Unknown")
    )
    away_team = normalise_team_name(
        fixture.get("teams", {}).get("away", {}).get("name", "Unknown")
    )
    venue = fixture.get("fixture", {}).get("venue", {}).get("name", "TBD")
    score, status = get_match_status_display(fixture)

    # Always include kickoff time
    fixture_date = fixture.get("fixture", {}).get("date")
    if fixture_date:
        kickoff = parse_match_datetime(fixture_date).strftime("%H:%M")
    else:
        kickoff = "TBD"

    # Compact scorers for table column
    scorers = format_scorers_compact(fixture)

    return [home_team, score, away_team, venue, status, kickoff, scorers]


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

        # Prefer isHome flag from matchDetails (avoids name-variant mismatches)
        is_home = event.get("isHome")
        if is_home is not None:
            if is_home:
                scorers["home"].append(scorer_info)
            else:
                scorers["away"].append(scorer_info)
        else:
            # Fallback to team name comparison
            team = event.get("team", {}).get("name")
            home_team = fixture.get("teams", {}).get("home", {}).get("name")
            if team and home_team and team == home_team:
                scorers["home"].append(scorer_info)
            elif team:
                scorers["away"].append(scorer_info)

    return scorers


def filter_weekly_matches(all_matches, today_date):
    """Filter matches to the current weekly window.

    Args:
        all_matches: List of match fixtures from API
        today_date: Today's date (datetime.date object)

    Returns:
        List of matches from today up to (but not including)
        the same weekday next week
    """
    week_end_exclusive = today_date + timedelta(days=7)
    return [
        m for m in all_matches
        if (today_date <=
            parse_match_datetime(m["fixture"]["date"]).date() <
            week_end_exclusive)
    ]


def get_match_date_range(matches):
    """Get first and last match dates from list.

    Args:
        matches: List of match fixtures

    Returns:
        Tuple of (first_match_date, last_match_date)
    """
    first_date = min(
        parse_match_datetime(m["fixture"]["date"]).date()
        for m in matches
    )
    last_date = max(
        parse_match_datetime(m["fixture"]["date"]).date()
        for m in matches
    )
    return first_date, last_date
