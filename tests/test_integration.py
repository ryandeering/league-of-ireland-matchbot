"""
Integration tests for end-to-end matchbot workflows.

Tests the complete flow from API fetch → cache → Reddit post update
using mocked external dependencies (PRAW, requests).
"""

import os
from unittest.mock import Mock, patch
from datetime import datetime


class TestPremierDivisionIntegration:
    """Integration tests for Premier Division posting workflow."""

    @patch('premier_division.requests.get')
    @patch('premier_division.praw.Reddit')
    def test_weekly_thread_creation_flow(self, mock_reddit, mock_requests):
        """Test complete flow: fetch data → build post → submit → cache."""
        # Mock API responses
        mock_gameweek_response = Mock()
        mock_gameweek_response.json.return_value = {
            "response": ["Regular Season - 10"]
        }

        mock_fixtures_response = Mock()
        mock_fixtures_response.json.return_value = {
            "response": [
                {
                    "fixture": {
                        "date": (
                            f"{datetime.now().strftime('%Y-%m-%d')}"
                            "T19:45:00+00:00"
                        ),
                        "venue": {"name": "Richmond Park"},
                        "status": {"short": "FT", "elapsed": 90}
                    },
                    "teams": {
                        "home": {"name": "St Patrick's Athl."},
                        "away": {"name": "Shelbourne"}
                    },
                    "goals": {"home": 2, "away": 2},
                    "league": {"id": 357}
                }
            ]
        }

        mock_standings_response = Mock()
        mock_standings_response.json.return_value = {
            "response": [{
                "league": {
                    "standings": [[
                        {
                            "rank": 1,
                            "team": {"id": 3843, "name": "St Patrick's Athl."},
                            "all": {
                                "played": 9, "win": 6, "draw": 2, "lose": 1,
                                "goals": {"for": 18, "against": 7}
                            },
                            "goalsDiff": 11,
                            "points": 20,
                            "form": "WWDWL"
                        }
                    ]]
                }
            }]
        }

        def get_side_effect(url, **kwargs):
            if 'rounds' in url:
                return mock_gameweek_response
            elif 'fixtures' in url:
                return mock_fixtures_response
            elif 'standings' in url:
                return mock_standings_response
            raise ValueError(f"Unexpected URL: {url}")

        mock_requests.side_effect = get_side_effect

        mock_post = Mock()
        mock_post.id = "test123"
        mock_post.mod = Mock()

        mock_subreddit = Mock()
        mock_subreddit.submit.return_value = mock_post

        mock_reddit_instance = Mock()
        mock_reddit_instance.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_reddit_instance

        mock_friday = datetime(2025, 10, 17, 6, 0, 0)
        with patch('premier_division.datetime') as mock_dt:
            mock_dt.now.return_value = mock_friday
            mock_dt.strptime = datetime.strptime

            from premier_division import main
            main()

        assert mock_subreddit.submit.called
        call_args = mock_subreddit.submit.call_args

        title = call_args[0][0]
        assert "LOI Premier Division" in title
        assert "Match Thread" in title

        body = call_args[1]['selftext']
        assert "St Patrick's Athletic" in body
        assert "Shelbourne" in body
        assert "Richmond Park" in body
        assert "2-2" in body

        assert mock_post.mod.sticky.called
        assert mock_post.mod.suggested_sort.called


class TestLiveUpdaterIntegration:
    """Integration tests for live score updater."""

    @patch('live_updater.update_reddit_post')
    @patch('live_updater.get_league_table')
    @patch('live_updater.get_live_fixtures')
    @patch('live_updater.load_cache')
    def test_live_update_flow(
        self,
        mock_load_cache,
        mock_get_fixtures,
        mock_get_table,
        mock_update_post
    ):
        """Test live update: load cache → fetch fixtures → update posts."""
        from live_updater import main

        today = datetime.now().date().isoformat()
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "abc123",
                "match_dates": [today],
                "round": "Regular Season - 10",
                "posted_at": today
            }
        }

        mock_get_fixtures.return_value = [
            {
                "fixture": {
                    "date": f"{today}T18:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                    "status": {"short": "2H", "elapsed": 67}
                },
                "teams": {
                    "home": {"name": "St Patrick's Athl."},
                    "away": {"name": "Shelbourne"}
                },
                "goals": {"home": 2, "away": 1},
                "league": {"id": 357},
                "events": [
                    {
                        "type": "Goal",
                        "team": {"name": "St Patrick's Athl."},
                        "player": {"name": "Mason Melia"},
                        "time": {"elapsed": 18},
                        "detail": "Normal Goal"
                    },
                    {
                        "type": "Goal",
                        "team": {"name": "Shelbourne"},
                        "player": {"name": "Mipo Odubeko"},
                        "time": {"elapsed": 35},
                        "detail": "Normal Goal"
                    },
                    {
                        "type": "Goal",
                        "team": {"name": "St Patrick's Athl."},
                        "player": {"name": "Chris Forrester"},
                        "time": {"elapsed": 67},
                        "detail": "Normal Goal"
                    }
                ]
            }
        ]

        mock_get_table.return_value = [
            {
                "rank": 1,
                "team": {"id": 3843, "name": "St Patrick's Athl."},
                "all": {
                    "played": 9, "win": 6, "draw": 2, "lose": 1,
                    "goals": {"for": 18, "against": 7}
                },
                "goalsDiff": 11,
                "points": 20,
                "form": "WWDWL"
            }
        ]

        mock_update_post.return_value = True

        main()

        assert mock_update_post.called
        call_args = mock_update_post.call_args

        assert call_args[0][0] == "abc123"

        body = call_args[0][1]
        assert "2-1" in body
        assert "67'" in body
        assert "Mason Melia" in body or "Chris Forrester" in body

    @patch('live_updater.update_reddit_post')
    @patch('live_updater.get_live_fixtures')
    @patch('live_updater.load_cache')
    def test_no_matches_today_exits_gracefully(
        self,
        mock_load_cache,
        mock_get_fixtures,
        mock_update_post
    ):
        """Test that updater exits when no matches scheduled."""
        from live_updater import main

        yesterday = "2025-10-17"
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "abc123",
                "match_dates": [yesterday],
                "round": "Regular Season - 10",
                "posted_at": yesterday
            }
        }

        main()

        assert not mock_get_fixtures.called
        assert not mock_update_post.called

    @patch('live_updater.update_reddit_post')
    @patch('live_updater.get_league_table')
    @patch('live_updater.get_live_fixtures')
    @patch('live_updater.load_cache')
    def test_multiple_competitions_updated(
        self,
        mock_load_cache,
        mock_get_fixtures,
        mock_get_table,
        mock_update_post
    ):
        """Test updating multiple competitions in one run."""
        from live_updater import main

        today = datetime.now().date().isoformat()

        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "prem123",
                "match_dates": [today],
                "round": "Regular Season - 10",
                "posted_at": today
            },
            "first_division": {
                "post_id": "first456",
                "match_dates": [today],
                "round": "Regular Season - 8",
                "posted_at": today
            },
            "fai_cup": {
                "post_id": "cup789",
                "match_dates": [today],
                "round": "Quarter-finals",
                "posted_at": today
            }
        }

        mock_get_fixtures.return_value = [
            {
                "fixture": {
                    "date": f"{today}T18:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                    "status": {"short": "2H", "elapsed": 30}
                },
                "teams": {
                    "home": {"name": "St Patrick's Athl."},
                    "away": {"name": "Shelbourne"}
                },
                "goals": {"home": 2, "away": 1},
                "league": {"id": 357},  # Premier
                "events": []
            },
            {
                "fixture": {
                    "date": f"{today}T19:45:00+00:00",
                    "venue": {"name": "UCD Bowl"},
                    "status": {"short": "2H", "elapsed": 67}
                },
                "teams": {
                    "home": {"name": "UCD"},
                    "away": {"name": "Athlone"}
                },
                "goals": {"home": 0, "away": 2},
                "league": {"id": 358},  # First
                "events": []
            },
            {
                "fixture": {
                    "date": f"{today}T17:00:00+00:00",
                    "venue": {"name": "Turner's Cross"},
                    "status": {"short": "FT"}
                },
                "teams": {
                    "home": {"name": "Cork City"},
                    "away": {"name": "St Patrick's Athl."}
                },
                "goals": {"home": 3, "away": 1},
                "league": {"id": 359},  # Cup
                "events": []
            }
        ]

        mock_get_table.return_value = []
        mock_update_post.return_value = True

        main()

        assert mock_update_post.call_count == 3

        post_ids_updated = [
            call_obj[0][0]
            for call_obj in mock_update_post.call_args_list
        ]
        assert "prem123" in post_ids_updated
        assert "first456" in post_ids_updated
        assert "cup789" in post_ids_updated


class TestCacheIntegration:
    """Integration tests for cache file operations."""

    def test_cache_created_after_post(self, tmp_path):
        """Test that cache file is created with correct structure."""
        from common import save_cache, load_cache

        import common
        original_cache_file = common.CACHE_FILE
        common.CACHE_FILE = str(tmp_path / "test_cache.json")

        try:
            cache_data = {
                "premier_division": {
                    "post_id": "test123",
                    "match_dates": ["2025-10-18", "2025-10-19"],
                    "round": "Regular Season - 10",
                    "posted_at": "2025-10-18"
                }
            }

            save_cache(cache_data)

            assert os.path.exists(common.CACHE_FILE)

            loaded = load_cache()
            assert loaded == cache_data
            assert loaded["premier_division"]["post_id"] == "test123"

        finally:
            common.CACHE_FILE = original_cache_file

    def test_cache_updates_preserve_other_competitions(self, tmp_path):
        """Test that updating one competition doesn't overwrite others."""
        from common import save_cache, load_cache

        import common
        original_cache_file = common.CACHE_FILE
        common.CACHE_FILE = str(tmp_path / "test_cache.json")

        try:
            initial_cache = {
                "premier_division": {
                    "post_id": "prem123",
                    "match_dates": ["2025-10-18"],
                    "round": "Regular Season - 10",
                    "posted_at": "2025-10-18"
                }
            }
            save_cache(initial_cache)

            cache = load_cache()
            cache["first_division"] = {
                "post_id": "first456",
                "match_dates": ["2025-10-18"],
                "round": "Regular Season - 8",
                "posted_at": "2025-10-18"
            }
            save_cache(cache)

            final_cache = load_cache()
            assert "premier_division" in final_cache
            assert "first_division" in final_cache
            assert final_cache["premier_division"]["post_id"] == "prem123"
            assert final_cache["first_division"]["post_id"] == "first456"

        finally:
            common.CACHE_FILE = original_cache_file


class TestErrorRecovery:
    """Integration tests for error handling and recovery."""

    @patch('live_updater.update_reddit_post')
    @patch('live_updater.get_league_table')
    @patch('live_updater.get_live_fixtures')
    @patch('live_updater.load_cache')
    def test_api_failure_returns_empty_list(
        self,
        mock_load_cache,
        mock_get_fixtures,
        mock_get_table,
        mock_update_post
    ):
        """Test that API failures are handled by returning empty list."""
        from live_updater import main

        today = datetime.now().date().isoformat()
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "abc123",
                "match_dates": [today],
                "round": "Regular Season - 10",
                "posted_at": today
            }
        }

        mock_get_fixtures.return_value = []

        main()

        assert not mock_update_post.called

    @patch('live_updater.update_reddit_post')
    @patch('live_updater.get_league_table')
    @patch('live_updater.get_live_fixtures')
    @patch('live_updater.load_cache')
    def test_reddit_failure_logged_but_continues(
        self,
        mock_load_cache,
        mock_get_fixtures,
        mock_get_table,
        mock_update_post
    ):
        """Test that Reddit failures don't stop other updates."""
        from live_updater import main

        today = datetime.now().date().isoformat()
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "prem123",
                "match_dates": [today],
                "round": "Regular Season - 10",
                "posted_at": today
            },
            "first_division": {
                "post_id": "first456",
                "match_dates": [today],
                "round": "Regular Season - 8",
                "posted_at": today
            }
        }

        mock_get_fixtures.return_value = [
            {
                "fixture": {
                    "date": f"{today}T18:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                    "status": {"short": "2H", "elapsed": 30}
                },
                "teams": {
                    "home": {"name": "St Patrick's Athl."},
                    "away": {"name": "Shelbourne"}
                },
                "goals": {"home": 2, "away": 1},
                "league": {"id": 357},
                "events": []
            },
            {
                "fixture": {
                    "date": f"{today}T19:45:00+00:00",
                    "venue": {"name": "UCD Bowl"},
                    "status": {"short": "1H", "elapsed": 25}
                },
                "teams": {
                    "home": {"name": "UCD"},
                    "away": {"name": "Athlone"}
                },
                "goals": {"home": 0, "away": 0},
                "league": {"id": 358},
                "events": []
            }
        ]

        mock_get_table.return_value = []

        mock_update_post.side_effect = [False, True]

        main()

        assert mock_update_post.call_count == 2
