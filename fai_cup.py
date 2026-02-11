"""
Matchbot by Ryan Deering (github.com/ryandeering)
Used for the League of Ireland subreddit
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from tabulate import tabulate
import praw

from matchbot_config import MatchbotConfig
from common import (
    parse_match_datetime,
    format_live_fixture,
    match_table_headers,
    load_cache,
    save_cache,
    get_fixture_dublin_date,
)
from match_client import (
    MatchDataClient,
    LEAGUE_ID_FAI_CUP,
    convert_raw_match,
)

config = MatchbotConfig()
client = MatchDataClient()

ROUND_DISPLAY_NAMES = {
    "1/16": "Round of 32",
    "1/8": "Round of 16",
    "1/4": "Quarter-finals",
    "1/2": "Semi-finals",
    "final": "Final",
}


def get_current_round(matches):
    """Determine current round from matches.

    Args:
        matches: List of match fixtures

    Returns:
        Round name string (e.g., "Quarter-finals")
    """
    now = datetime.now(ZoneInfo("UTC"))

    # Find the next upcoming match to get the current round
    for match in sorted(matches, key=lambda m: m["fixture"]["date"]):
        match_date = parse_match_datetime(match["fixture"]["date"])
        if match_date >= now:
            round_info = match.get("league", {}).get("round", "")
            if round_info:
                # Extract just the round name (e.g., "Quarter-finals")
                if " - " in round_info:
                    extracted = round_info.split(" - ")[-1]
                    if extracted:
                        return extracted
                else:
                    return round_info

    # Fallback: use the last match's round (by date)
    if matches:
        latest_match = sorted(matches, key=lambda m: m["fixture"]["date"])[-1]
        round_info = latest_match.get("league", {}).get("round", "FAI Cup")
        if " - " in round_info:
            extracted = round_info.split(" - ")[-1]
            if extracted:
                return extracted
        elif round_info:
            return round_info

    return "FAI Cup"


def get_matches_for_cup():
    """Fetch all matches for FAI Cup.

    Returns:
        List of match fixtures in api-football compatible format
    """
    fixtures_by_id = {}

    for tab in ["fixtures", "results"]:
        data = client.get_league_matches(LEAGUE_ID_FAI_CUP, tab=tab)
        for match in client.extract_matches(data):
            match["_league_id"] = LEAGUE_ID_FAI_CUP
            converted = convert_raw_match(match)
            fixture_id = converted["fixture"]["id"]
            # Results tab has more accurate data for finished matches
            if fixture_id not in fixtures_by_id or tab == "results":
                fixtures_by_id[fixture_id] = converted

    return list(fixtures_by_id.values())


def _extract_round_name(round_str: str) -> str:
    """Extract the round name from a full round string.

    Args:
        round_str: Full round string (e.g., "Regular Season - Quarter-finals")

    Returns:
        Extracted round name (e.g., "Quarter-finals"), or original string
    """
    if " - " in round_str:
        return round_str.split(" - ")[-1]
    return round_str


def _normalise_round_key(round_str: str) -> str:
    """Normalise round key for case-insensitive exact comparisons."""
    return _extract_round_name(round_str).strip().lower()


def get_round_display_name(round_key: str) -> str:
    """Return human-friendly round label for post title/body.

    Args:
        round_key: Raw round key from API or extracted round name

    Returns:
        Display-friendly round name (e.g., "Quarter-finals")
    """
    if not round_key:
        return "FAI Cup"
    normalised = _normalise_round_key(round_key)
    return ROUND_DISPLAY_NAMES.get(normalised, _extract_round_name(round_key))


def get_matches_for_round(matches, current_round):
    """Filter matches to only include current round.

    Uses exact matching on the extracted round name to avoid
    substring collisions (e.g., round "1" matching "10" or "11").

    Args:
        matches: All cup matches
        current_round: Current round name

    Returns:
        List of matches in the current round (empty if current_round is blank)
    """
    if not current_round:
        return []
    current_round_key = _normalise_round_key(current_round)
    return [
        m for m in matches
        if _normalise_round_key(m.get("league", {}).get("round", ""))
        == current_round_key
    ]


def submit_reddit_post(title, body):
    """Submit a post to the subreddit and return the post ID."""
    reddit = praw.Reddit(
        client_id=config.client_id,
        client_secret=config.client_secret,
        username=config.bot_username,
        password=config.bot_password,
        user_agent=config.user_agent,
    )

    subreddit = reddit.subreddit(config.subreddit)

    post = subreddit.submit(
        title, selftext=body, flair_id="804acfe4-ef26-11eb-8f17-862a215ae082"
    )
    post.mod.suggested_sort(sort="new")
    post.mod.sticky()

    return post.id


def build_post_body(matches_data, current_round):
    """Build the body text for the Reddit post.

    All matches in one table with scorers in a column.
    """
    matches_by_date = {}
    for match in matches_data:
        date = get_fixture_dublin_date(match)
        matches_by_date.setdefault(date, []).append(match)

    body = (
        f"*Live scores will be updated during matches*\n\n"
        f"## {current_round}\n\n"
    )

    for date, matches_list in sorted(matches_by_date.items()):
        date_extracted = datetime.strptime(date, "%Y-%m-%d")
        date_header = date_extracted.strftime(f"%A, %B {date_extracted.day}")
        body += f"### {date_header}\n\n"

        match_rows = [format_live_fixture(match) for match in matches_list]
        match_table = tabulate(
            match_rows, headers=match_table_headers, tablefmt='pipe'
        )
        body += f"{match_table}\n\n"

    body += (
        "\n\n Welcome to the discussion thread for the Sports Direct "
        "FAI Cup. Remember to follow the subreddit rules and be civil "
        "to each other. Enjoy the game. \n\n"
    )

    body += (
        "\n\n This post was created by a bot. If you have any feedback or "
        "suggestions, please message /u/LOIMatchThreads."
    )

    return body


def main():
    """Main function."""
    now = datetime.now(ZoneInfo("Europe/Dublin"))
    today = now.date()

    try:
        all_matches = get_matches_for_cup()
        current_round_key = get_current_round(all_matches)

        round_matches = get_matches_for_round(all_matches, current_round_key)
        current_round_display = get_round_display_name(current_round_key)

        if not round_matches:
            print(f"No matches found for round: {current_round_display}")
            return

        round_matches.sort(key=lambda m: m["fixture"]["date"])
        first_match_date = get_fixture_dublin_date(round_matches[0])
        if first_match_date != today.isoformat():
            print(f"First match is on {first_match_date}, not today. Exiting.")
            return

        title = (
            f"Sports Direct FAI Cup - {current_round_display} Discussion Thread / "
            f"{today.strftime('%d-%m-%Y')}"
        )

        body = build_post_body(round_matches, current_round_display)

        post_id = submit_reddit_post(title, body)

        # Save post metadata to cache for live updater
        cache = load_cache()
        match_dates = sorted({
            parse_match_datetime(m["fixture"]["date"]).date().isoformat()
            for m in round_matches
        })

        cache["fai_cup"] = {
            "post_id": post_id,
            "match_dates": match_dates,
            "round": current_round_display,
            "posted_at": now.isoformat()
        }
        save_cache(cache)

        print(f"Posted FAI Cup thread: {post_id}")
        print(f"Match dates: {match_dates}")

    except Exception as e:
        print(f"Error running main function: {e}")
        raise


if __name__ == "__main__":
    main()
