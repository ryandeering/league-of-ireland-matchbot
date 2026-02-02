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
)
from match_client import (
    MatchDataClient,
    LEAGUE_ID_FAI_CUP,
    convert_raw_match,
)

config = MatchbotConfig()
client = MatchDataClient()


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
                    return round_info.split(" - ")[-1]
                return round_info

    # Fallback: use the last match's round
    if matches:
        round_info = matches[-1].get("league", {}).get("round", "FAI Cup")
        if " - " in round_info:
            return round_info.split(" - ")[-1]
        return round_info

    return "FAI Cup"


def get_matches_for_cup():
    """Fetch all matches for FAI Cup.

    Returns:
        List of match fixtures in api-football compatible format
    """
    matches = []

    fixtures_data = client.get_league_matches(LEAGUE_ID_FAI_CUP, tab="fixtures")
    for match in client.extract_matches(fixtures_data):
        match["_league_id"] = LEAGUE_ID_FAI_CUP
        matches.append(convert_raw_match(match))

    results_data = client.get_league_matches(LEAGUE_ID_FAI_CUP, tab="results")
    for match in client.extract_matches(results_data):
        match["_league_id"] = LEAGUE_ID_FAI_CUP
        matches.append(convert_raw_match(match))

    return matches


def get_matches_for_round(matches, current_round):
    """Filter matches to only include current round.

    Args:
        matches: All cup matches
        current_round: Current round name

    Returns:
        List of matches in the current round
    """
    return [
        m for m in matches
        if current_round in m.get("league", {}).get("round", "")
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
        date = match["fixture"]["date"][:10]
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
        current_round = get_current_round(all_matches)

        round_matches = get_matches_for_round(all_matches, current_round)

        if not round_matches:
            print(f"No matches found for round: {current_round}")
            return

        round_matches.sort(key=lambda m: m["fixture"]["date"])
        first_match_date = round_matches[0]["fixture"]["date"][:10]
        if first_match_date != today.strftime("%Y-%m-%d"):
            print(f"First match is on {first_match_date}, not today. Exiting.")
            return

        title = (
            f"Sports Direct FAI Cup - {current_round} Discussion Thread / "
            f"{today.strftime('%d-%m-%Y')}"
        )

        body = build_post_body(round_matches, current_round)

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
            "round": current_round,
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
