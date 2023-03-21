"""
Matchbot by Ryan Deering (github.com/ryandeering)
Used for the League of Ireland subreddit
"""

from datetime import datetime
from tabulate import tabulate
import praw
import requests
from matchbot_config import MatchbotConfig

LEAGUE_ID = 357
SEASON = 2023

normalised_team_names = {
    "St Patrick's Athl.": "St Patrick's Athletic",
    "Dundalk": "Dundalk FC",
}

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
                'season': SEASON,
            },
            timeout=5,
        )
        response.raise_for_status()
        return response.json()['response'][0]['league']['standings'][0]
    except requests.exceptions.RequestException as request_exception:
        print(f"Error getting league table: {request_exception}")
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

    post = subreddit.submit(title, selftext=body, flair_id="804acfe4-ef26-11eb-8f17-862a215ae082")
    post.mod.suggested_sort(sort="new")
    post.mod.sticky()

def build_post_body(matches_data, league_table, gameweek_number):
    """Build the body text for the Reddit post."""

    match_table_headers = ['Home Team', 'Kickoff', 'Away Team', 'Ground']

    matches_by_date = {}
    for match in matches_data:
        date = match["fixture"]["date"][:10]
        matches_by_date.setdefault(date, []).append(match)

    body = ""
    for date, matches_list in matches_by_date.items():
        date_extracted = datetime.strptime(date, "%Y-%m-%d")
        date_header = date_extracted.strftime(f"%A, %B {ordinal_suffix(date_extracted.day)}")
        section_header = f"##{date_header}\n\n"

        matches = [
            [
                normalise_team_name(match["teams"]["home"]["name"]),
                datetime.fromisoformat(match["fixture"]["date"]).strftime("%H:%M"),
                normalise_team_name(match["teams"]["away"]["name"]),
                match["fixture"]["venue"]["name"],
            ]
            for match in matches_list
        ]

        body += (f"{section_header}"
                f"{tabulate(matches, headers=match_table_headers, tablefmt='pipe')}\n\n")

    table_data = [
        [
            item['rank'],
            normalise_team_name(item['team']['name']),
            item['all']['played'],
            item['all']['win'],
            item['all']['draw'],
            item['all']['lose'],
            item['all']['goals']['for'],
            item['all']['goals']['against'],
            item['goalsDiff'],
            item['points'],
            get_last_matches(item['team']['id'], league_table)
        ]
        for item in league_table
    ]

    table_headers = [
        "Position", "Team", "Played", "Won", "Draw", "Lost", "GF", "GA", "GD",
        "Points", "Form"
    ]

    body += f"## League Table, as of Round {gameweek_number-1}\n\n" \
        f"{tabulate(table_data, headers=table_headers, tablefmt='pipe')}\n\n"
    body += "\n\n Welcome to the discussion thread for the League of Ireland" \
        " Premier Division. Remember to follow the subreddit rules and be" \
        " civil to each other. Enjoy the game. \n\n"
    body += "\n\n This post was created by a bot. If you have any feedback or" \
        " suggestions, please message /u/LOIMatchThreads."

    return body

def get_last_matches(team_id, league_table):
    """Return last five match results through emojis for a team."""
    last_matches = 5
    team_form = next((team['form'] for team in league_table if team['team']['id'] == team_id), None)
    if team_form:
        return team_form[-last_matches:].replace('W', '✅').replace('D', '⚪').replace('L', '❌')
    return ''

def normalise_team_name(team_name):
    """Normalise team name."""
    return normalised_team_names.get(team_name, team_name)

def ordinal_suffix(day):
    """Add suffix to date header. Why is this not built into the Python standard library!?!"""
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    if 4 <= day <= 20 or 24 <= day <= 30:
        return f"{day}th"
    return f"{day}{suffixes.get(day % 10, 'th')}"

def main():
    """Main function."""
    today = datetime.now()

    try:
        current_gameweek = get_current_gameweek()
        gameweek_number = int(current_gameweek.split(" ")[-1])

        matches = get_matches_for_gameweek(current_gameweek)

        first_match_date = matches[0]["fixture"]["date"][:10]
        if first_match_date != today.strftime("%Y-%m-%d"):
            return

        title = f"LOI Premier Division - Round {gameweek_number} Discussion Thread / " \
        f"{today.strftime('%d-%m-%Y')}"

        league_table = get_league_table()
        body = build_post_body(matches, league_table, gameweek_number)

        submit_reddit_post(title, body)

    except requests.exceptions.RequestException as request_exception:
        print(f"Error running main function: {request_exception}")
        raise

if __name__ == "__main__":
    main()
