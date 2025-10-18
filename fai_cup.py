"""
Matchbot by Ryan Deering (github.com/ryandeering)
Used for the League of Ireland subreddit
"""

from datetime import datetime
from tabulate import tabulate
import praw
import requests
from matchbot_config import MatchbotConfig
from common import (
    parse_match_datetime,
    format_live_fixture,
    match_table_headers,
    load_cache,
    save_cache,
)

TOURNAMENT_ID = 359
SEASON = datetime.now().year

config = MatchbotConfig()


def get_current_round():
    """Return the current round."""
    try:
        response = requests.get(
            f"{config.base_url}/fixtures/rounds",
            params={
                "league": TOURNAMENT_ID,
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
        print(f"Error getting current round: {request_exception}")
        raise


def get_matches_for_round(current_round):
    """Return matches for the current round."""
    try:
        response = requests.get(
            f"{config.base_url}/fixtures",
            params={
                "league": TOURNAMENT_ID,
                "season": SEASON,
                "round": current_round,
            },
            headers=config.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()["response"]
    except requests.exceptions.RequestException as request_exception:
        print(f"Error getting matches for round: {request_exception}")
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


def build_post_body(matches_data, current_round):
    """Build the body text for the Reddit post."""

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
        section_header = f"### {date_header}\n\n"

        matches = [format_live_fixture(match) for match in matches_list]

        match_table = tabulate(
            matches, headers=match_table_headers, tablefmt='pipe'
        )
        body += f"{section_header}{match_table}\n\n"

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
    today = datetime.now()

    try:
        current_round = get_current_round()

        matches = get_matches_for_round(current_round)

        first_match_date = matches[0]["fixture"]["date"][:10]
        if first_match_date != today.strftime("%Y-%m-%d"):
            return

        title = (
            f"Sports Direct FAI Cup - {current_round} Discussion Thread / "
            f"{today.strftime('%d-%m-%Y')}"
        )

        body = build_post_body(matches, current_round)

        post_id = submit_reddit_post(title, body)

        # Save post metadata to cache for live updater
        cache = load_cache()
        match_dates = sorted({
            parse_match_datetime(m["fixture"]["date"]).date().isoformat()
            for m in matches
        })

        cache["fai_cup"] = {
            "post_id": post_id,
            "match_dates": match_dates,
            "round": current_round,
            "posted_at": today.isoformat()
        }
        save_cache(cache)

        print(f"Posted FAI Cup thread: {post_id}")
        print(f"Match dates: {match_dates}")

    except requests.exceptions.RequestException as request_exception:
        print(f"Error running main function: {request_exception}")
        raise


if __name__ == "__main__":
    main()
