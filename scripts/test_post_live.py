"""
Test script to post a formatted match thread to r/test.
Uses actual formatting code with simulated live match data.
"""

import praw
from match_client import convert_raw_match
from live_updater import build_premier_body
from matchbot_config import MatchbotConfig

config = MatchbotConfig()


def create_test_fixtures():
    """Create simulated Round 15 fixtures with various match states."""
    return [
        {
            'id': '1', 'round': '15',
            'home': {'id': '1', 'name': 'Shamrock Rovers'},
            'away': {'id': '2', 'name': 'Bohemian FC'},
            'status': {
                'utcTime': '2026-02-06T19:45:00Z',
                'started': True, 'finished': False,
                'score': {'home': 2, 'away': 1},
                'liveTime': {'short': '67'}
            },
            '_league_id': 126
        },
        {
            'id': '2', 'round': '15',
            'home': {'id': '3', 'name': "St Patrick's Athletic"},
            'away': {'id': '4', 'name': 'Shelbourne'},
            'status': {
                'utcTime': '2026-02-06T19:45:00Z',
                'started': True, 'finished': False,
                'score': {'home': 0, 'away': 0},
                'liveTime': {'short': 'HT'}
            },
            '_league_id': 126
        },
        {
            'id': '3', 'round': '15',
            'home': {'id': '5', 'name': 'Derry City'},
            'away': {'id': '6', 'name': 'Sligo Rovers'},
            'status': {
                'utcTime': '2026-02-06T19:45:00Z',
                'started': True, 'finished': False,
                'score': {'home': 1, 'away': 0},
                'liveTime': {'short': '34'}
            },
            '_league_id': 126
        },
        {
            'id': '4', 'round': '15',
            'home': {'id': '7', 'name': 'Dundalk FC'},
            'away': {'id': '8', 'name': 'Drogheda United'},
            'status': {
                'utcTime': '2026-02-06T20:00:00Z',
                'started': False, 'finished': False,
            },
            '_league_id': 126
        },
    ]


def create_test_table():
    """Create simulated league table data."""
    return [
        {"rank": 1, "team": {"id": 1, "name": "Shamrock Rovers"},
         "all": {"played": 14, "win": 10, "draw": 3, "lose": 1,
                 "goals": {"for": 28, "against": 10}},
         "goalsDiff": 18, "points": 33, "form": "WWDWW"},
        {"rank": 2, "team": {"id": 4, "name": "Shelbourne"},
         "all": {"played": 14, "win": 9, "draw": 3, "lose": 2, "goals": {"for": 25, "against": 12}},
         "goalsDiff": 13, "points": 30, "form": "WDWWL"},
        {"rank": 3, "team": {"id": 3, "name": "St Patrick's Athletic"},
         "all": {"played": 14, "win": 8, "draw": 4, "lose": 2, "goals": {"for": 22, "against": 14}},
         "goalsDiff": 8, "points": 28, "form": "DWWDW"},
        {"rank": 4, "team": {"id": 5, "name": "Derry City"},
         "all": {"played": 14, "win": 7, "draw": 4, "lose": 3, "goals": {"for": 20, "against": 15}},
         "goalsDiff": 5, "points": 25, "form": "WLDWW"},
        {"rank": 5, "team": {"id": 2, "name": "Bohemian FC"},
         "all": {"played": 14, "win": 6, "draw": 3, "lose": 5, "goals": {"for": 18, "against": 18}},
         "goalsDiff": 0, "points": 21, "form": "LDWLW"},
    ]


def main():
    """Post test thread to r/test."""
    raw_fixtures = create_test_fixtures()
    converted = [convert_raw_match(f) for f in raw_fixtures]

    # Simulate Aaron Greene scoring twice
    converted[0]['events'] = [
        {'type': 'Goal', 'team': {'name': 'Shamrock Rovers'},
         'player': {'name': 'Aaron Greene'}, 'time': {'elapsed': 23}, 'detail': 'Normal Goal'},
        {'type': 'Goal', 'team': {'name': 'Bohemian FC'},
         'player': {'name': 'Dawson Devoy'}, 'time': {'elapsed': 34}, 'detail': 'Penalty'},
        {'type': 'Goal', 'team': {'name': 'Shamrock Rovers'},
         'player': {'name': 'Aaron Greene'}, 'time': {'elapsed': 62}, 'detail': 'Normal Goal'},
    ]
    converted[2]['events'] = [
        {'type': 'Goal', 'team': {'name': 'Derry City'},
         'player': {'name': 'Patrick McEleney'}, 'time': {'elapsed': 12}, 'detail': 'Normal Goal'},
    ]

    league_table = create_test_table()
    body = build_premier_body(converted, league_table, 15)

    print("=" * 60)
    print("POST PREVIEW")
    print("=" * 60)
    print(body)
    print("=" * 60)
    reddit = praw.Reddit(
        client_id=config.client_id,
        client_secret=config.client_secret,
        username=config.bot_username,
        password=config.bot_password,
        user_agent=config.user_agent,
    )

    title = "[TEST] LOI Premier Division - Round 15 Discussion Thread / 06-02-2026"

    subreddit = reddit.subreddit(config.subreddit)
    post = subreddit.submit(title, selftext=body)

    print(f"\nPosted to: https://reddit.com{post.permalink}")
    print(f"Post ID: {post.id}")

    return post.id


if __name__ == "__main__":
    main()
