"""
Just for common code shared bettwen our modules.
Tempting to put the reddit posting stuff here 
-- maybe overengineering..
"""

from datetime import datetime
import pytz

normalised_team_names = {
    "St Patrick's Athl.": "St Patrick's Athletic",
    "Dundalk": "Dundalk FC",
    "Kerry": "Kerry FC",
    "Waterford": "Waterford FC",
    "Wexford": "Wexford FC",
}

match_table_headers = ["Home Team", "Kickoff", "Away Team", "Ground"]


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


def normalise_team_name(team_name):
    """Normalise team name."""
    return normalised_team_names.get(team_name, team_name)


def ordinal_suffix(day):
    """Add suffix to date header. Why is this not built into the Python standard library!?!"""
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    if 4 <= day <= 20 or 24 <= day <= 30:
        return f"{day}th"
    return f"{day}{suffixes.get(day % 10, 'th')}"


def get_last_matches(team_id, league_table):
    """Return last five match results through emojis for a team."""
    last_matches = 5
    team_form = next(
        (team["form"] for team in league_table if team["team"]["id"] == team_id), None
    )
    if team_form:
        return (
            team_form[-last_matches:]
            .replace("W", "✅")
            .replace("D", "⚪")
            .replace("L", "❌")
        )
    return ""


def parse_match_datetime(match_date_str, timezone_str="Europe/Dublin"):
    """
    Parse the match datetime string and adjust for daylight saving time.
    """
    timezone = pytz.timezone(timezone_str)

    # Parse the match datetime in UTC and convert to the local timezone
    match_datetime_local = datetime.fromisoformat(match_date_str).astimezone(timezone)

    return match_datetime_local
