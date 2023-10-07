"""
Matchbot by Ryan Deering (github.com/ryandeering)
Used for the League of Ireland subreddit
"""

from datetime import datetime, timedelta
from tabulate import tabulate
import praw
import requests
from matchbot_config import MatchbotConfig

TOURNAMENT_ID = 359
SEASON = 2023

normalised_team_names = {
    "St Patrick's Athl.": "St Patrick's Athletic",
    "Dundalk": "Dundalk FC",
    "Kerry": "Kerry FC",
    "Waterford": "Waterford FC",
    "Wexford": "Wexford FC",
}

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
    """Submit a post to the subreddit."""
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


def build_post_body(matches_data, current_round):
    """Build the body text for the Reddit post."""
    match_table_headers = ["Home Team", "Kickoff", "Away Team", "Ground"]

    matches_by_date = {}
    for match in matches_data:
        date = match["fixture"]["date"][:10]
        matches_by_date.setdefault(date, []).append(match)

    body = f"## {current_round}\n\n"
    for date, matches_list in sorted(matches_by_date.items()):
        date_extracted = datetime.strptime(date, "%Y-%m-%d")
        date_header = date_extracted.strftime(f"%A, %B {date_extracted.day}")
        section_header = f"### {date_header}\n\n"

        matches = [
            [
                normalised_team_names.get(
                    match["teams"]["home"]["name"], match["teams"]["home"]["name"]
                ),
                (
                    datetime.fromisoformat(match["fixture"]["date"])
                    + timedelta(hours=1)
                ).strftime("%H:%M"),
                normalised_team_names.get(
                    match["teams"]["away"]["name"], match["teams"]["away"]["name"]
                ),
                match["fixture"]["venue"]["name"],
            ]
            for match in matches_list
        ]

        body += (
            f"{section_header}"
            f"{tabulate(matches, headers=match_table_headers, tablefmt='pipe')}\n\n"
        )

    body += (
        "\n\n Welcome to the discussion thread for the Sports Direct FAI Cup. "
        "Remember to follow the subreddit rules and be civil to each other. Enjoy the game. \n\n"
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

        submit_reddit_post(title, body)

    except requests.exceptions.RequestException as request_exception:
        print(f"Error running main function: {request_exception}")
        raise


if __name__ == "__main__":
    main()
