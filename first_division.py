"""
Matchbot by Ryan Deering (github.com/ryandeering)
Used for the League of Ireland subreddit
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from tabulate import tabulate
import praw
import requests
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
)

LEAGUE_ID = 358
SEASON = datetime.now().year

config = MatchbotConfig()


def get_current_gameweek():
    """Return the current gameweek."""
    try:
        response = requests.get(
            f"{config.base_url}/fixtures/rounds",
            params={
                "league": LEAGUE_ID,
                "current": "true",
                "season": SEASON,
            },
            headers=config.headers,
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        return data["response"][0]
    except requests.exceptions.RequestException as request_exception:
        print(f"Error getting current gameweek: {request_exception}")
        raise


def get_matches_for_gameweek(gameweek):
    """Return matches for a gameweek."""
    try:
        response = requests.get(
            f"{config.base_url}/fixtures",
            params={
                "league": LEAGUE_ID,
                "season": SEASON,
                "round": gameweek,
            },
            headers=config.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()["response"]
    except requests.exceptions.RequestException as request_exception:
        print(f"Error getting matches for gameweek: {request_exception}")
        raise


def get_league_table():
    """Return league table."""
    try:
        response = requests.get(
            f"{config.base_url}/standings",
            headers=config.headers,
            params={
                "league": LEAGUE_ID,
                "season": SEASON,
            },
            timeout=5,
        )
        response.raise_for_status()
        return response.json()["response"][0]["league"]["standings"][0]
    except requests.exceptions.RequestException as request_exception:
        print(f"Error getting league table: {request_exception}")
        raise


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


def build_post_body(matches_data, league_table, gameweek_number):
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

    if gameweek_number - 1 > 0:
        body += f"## League Table, as of Round {gameweek_number - 1}\n\n"
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

    # Only post on Fridays
    if now.weekday() != 4:  # 4 = Friday
        print(f"Not Friday (today is {now.strftime('%A')}), exiting.")
        return

    try:
        gw = get_current_gameweek()
        gw_num = int(gw.split()[-1])
        all_matches = get_matches_for_gameweek(gw)

        # Filter to next 7 days only
        week_end = today + timedelta(days=7)
        weekly_matches = [
            m for m in all_matches
            if (today <=
                parse_match_datetime(m["fixture"]["date"]).date() <=
                week_end)
        ]

        if not weekly_matches:
            print(
                f"No matches in next 7 days for round {gw_num}, exiting."
            )
            return

        first_match_date = min(
            parse_match_datetime(m["fixture"]["date"]).date()
            for m in weekly_matches
        )
        last_match_date = max(
            parse_match_datetime(m["fixture"]["date"]).date()
            for m in weekly_matches
        )

        title = (
            f"LOI First Division - Match Thread / "
            f"{first_match_date.strftime('%d-%m-%Y')} to {last_match_date.strftime('%d-%m-%Y')}"
        )

        league_table = get_league_table()
        body = build_post_body(weekly_matches, league_table, gw_num)

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
            "round": gw,
            "posted_at": now.isoformat()
        }
        save_cache(cache)

        print(f"Posted First Division thread: {post_id}")
        print(f"Match dates: {match_dates}")

    except requests.exceptions.RequestException as e:
        print(f"Network/API error: {e}")
        raise


if __name__ == "__main__":
    main()
