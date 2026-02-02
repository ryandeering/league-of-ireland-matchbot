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
    table_headers,
    match_table_headers,
    normalise_team_name,
    ordinal_suffix,
    get_last_matches,
    parse_match_datetime,
    format_live_fixture,
    load_cache,
    save_cache,
    filter_weekly_matches,
    get_match_date_range,
)
from match_client import (
    MatchDataClient,
    LEAGUE_ID_FIRST,
    convert_raw_match,
    convert_raw_table,
)

config = MatchbotConfig()
client = MatchDataClient()


def get_matches_for_league():
    """Fetch all matches for First Division.

    Returns:
        List of match fixtures in api-football compatible format
    """
    matches = []

    fixtures_data = client.get_league_matches(LEAGUE_ID_FIRST, tab="fixtures")
    for match in client.extract_matches(fixtures_data):
        match["_league_id"] = LEAGUE_ID_FIRST
        matches.append(convert_raw_match(match))

    results_data = client.get_league_matches(LEAGUE_ID_FIRST, tab="results")
    for match in client.extract_matches(results_data):
        match["_league_id"] = LEAGUE_ID_FIRST
        matches.append(convert_raw_match(match))

    return matches


def get_league_table():
    """Fetch league table.

    Returns:
        List of team standings in api-football compatible format
    """
    raw_table = client.get_league_table(LEAGUE_ID_FIRST)
    return convert_raw_table(raw_table)


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


def build_post_body(matches_data, league_table):
    """Build the body text for the Reddit post."""

    matches_by_date = {}
    for match in matches_data:
        date = match["fixture"]["date"][:10]
        matches_by_date.setdefault(date, []).append(match)

    body = "*Live scores will be updated during matches*\n\n"

    for date, matches_list in sorted(matches_by_date.items()):
        date_extracted = datetime.strptime(date, "%Y-%m-%d")
        date_header = date_extracted.strftime(
            f"%A, %B {ordinal_suffix(date_extracted.day)}"
        )
        section_header = f"## {date_header}\n\n"

        matches = [format_live_fixture(match) for match in matches_list]

        match_table = tabulate(
            matches, headers=match_table_headers, tablefmt='pipe'
        )
        body += f"{section_header}{match_table}\n\n"

    table_data = [
        [
            item["rank"],
            normalise_team_name(item["team"]["name"]),
            item["all"]["played"],
            item["all"]["win"],
            item["all"]["draw"],
            item["all"]["lose"],
            item["all"]["goals"]["for"],
            item["all"]["goals"]["against"],
            item["goalsDiff"],
            item["points"],
            get_last_matches(item["team"]["id"], league_table),
        ]
        for item in league_table
    ]

    if league_table:
        body += "## Current League Table\n\n"
        standings_table = tabulate(
            table_data, headers=table_headers, tablefmt='pipe'
        )
        body += f"{standings_table}\n\n"

    body += (
        "\n\n Welcome to the discussion thread for the League of Ireland"
        " First Division. Remember to follow the subreddit rules and be"
        " civil to each other. Enjoy the game. \n\n"
    )
    body += (
        "\n\n This post was created by a bot. If you have any feedback or"
        " suggestions, please message /u/LOIMatchThreads."
    )

    return body


def main():
    """Main entry point: post weekly thread on Friday."""
    now = datetime.now(ZoneInfo("Europe/Dublin"))
    today = now.date()

    if now.weekday() != 4:  # 4 = Friday
        print(f"Not Friday (today is {now.strftime('%A')}), exiting.")
        return

    try:
        all_matches = get_matches_for_league()
        weekly_matches = filter_weekly_matches(all_matches, today)

        if not weekly_matches:
            print("No matches in next 7 days, exiting.")
            return

        first_match_date, last_match_date = get_match_date_range(weekly_matches)

        title = (
            f"LOI First Division - Fixtures / "
            f"{first_match_date.strftime('%d-%m-%Y')} to {last_match_date.strftime('%d-%m-%Y')}"
        )

        league_table = get_league_table()
        body = build_post_body(weekly_matches, league_table)

        post_id = submit_reddit_post(title, body)

        # Save post metadata to cache for live updater
        cache = load_cache()
        match_dates = sorted({
            parse_match_datetime(m["fixture"]["date"]).date().isoformat()
            for m in weekly_matches
        })

        cache["first_division"] = {
            "post_id": post_id,
            "match_dates": match_dates,
            "posted_at": now.isoformat()
        }
        save_cache(cache)

        print(f"Posted First Division thread: {post_id}")
        print(f"Match dates: {match_dates}")

    except Exception as e:
        print(f"Error running main function: {e}")
        raise


if __name__ == "__main__":
    main()
