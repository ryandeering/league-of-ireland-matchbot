"""
Test script to post a formatted match thread to r/test.
Uses actual formatting code with simulated live match data.
"""

import praw

from match_client import to_fixture
from models import GoalEvent, Standing, Team
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
    """Create simulated league table data as Standings."""
    return [
        Standing(rank=1, team=Team(id=1, name="Shamrock Rovers"),
                 played=14, won=10, drawn=3, lost=1,
                 goals_for=28, goals_against=10,
                 goal_diff=18, points=33, form="WWDWW"),
        Standing(rank=2, team=Team(id=4, name="Shelbourne"),
                 played=14, won=9, drawn=3, lost=2,
                 goals_for=25, goals_against=12,
                 goal_diff=13, points=30, form="WDWWL"),
        Standing(rank=3, team=Team(id=3, name="St Patrick's Athletic"),
                 played=14, won=8, drawn=4, lost=2,
                 goals_for=22, goals_against=14,
                 goal_diff=8, points=28, form="DWWDW"),
        Standing(rank=4, team=Team(id=5, name="Derry City"),
                 played=14, won=7, drawn=4, lost=3,
                 goals_for=20, goals_against=15,
                 goal_diff=5, points=25, form="WLDWW"),
        Standing(rank=5, team=Team(id=2, name="Bohemian FC"),
                 played=14, won=6, drawn=3, lost=5,
                 goals_for=18, goals_against=18,
                 goal_diff=0, points=21, form="LDWLW"),
    ]


def main():
    """Post test thread to r/test."""
    raw_fixtures = create_test_fixtures()
    converted = [to_fixture(f) for f in raw_fixtures]

    # Simulate Aaron Greene scoring twice
    converted[0].events = [
        GoalEvent(player='Aaron Greene', team='Shamrock Rovers', minute=23,
                  is_home=True, is_penalty=False, is_own_goal=False),
        GoalEvent(player='Dawson Devoy', team='Bohemian FC', minute=34,
                  is_home=False, is_penalty=True, is_own_goal=False),
        GoalEvent(player='Aaron Greene', team='Shamrock Rovers', minute=62,
                  is_home=True, is_penalty=False, is_own_goal=False),
    ]
    converted[2].events = [
        GoalEvent(player='Patrick McEleney', team='Derry City', minute=12,
                  is_home=True, is_penalty=False, is_own_goal=False),
    ]

    league_table = create_test_table()
    body = build_premier_body(converted, league_table)

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
