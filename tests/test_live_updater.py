"""Integration tests for live updater functionality."""

import unittest
from unittest.mock import patch
from datetime import date


class TestLiveUpdaterLogic(unittest.TestCase):
    """Test live updater core logic."""

    def setUp(self):
        """Set up test fixtures - St Patrick's Athletic vs Shelbourne."""
        self.sample_fixtures = [
            {
                "fixture": {
                    "id": 1,
                    "status": {"short": "1H", "elapsed": 23},
                    "date": "2024-10-19T19:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 357},
                "goals": {"home": 2, "away": 0},  # St Pats leading
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 1},
                    "away": {"name": "Shelbourne", "id": 2},
                },
            },
            {
                "fixture": {
                    "id": 2,
                    "status": {"short": "FT", "elapsed": 90},
                    "date": "2024-10-19T15:00:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 358},
                "goals": {"home": 3, "away": 0},  # St Pats victory
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 3},
                    "away": {"name": "Shelbourne", "id": 4},
                },
            },
        ]

    def test_organize_fixtures_by_league(self):
        """Test organizing fixtures by league ID."""
        fixtures_by_league = {357: [], 358: [], 359: []}

        for fixture in self.sample_fixtures:
            league_id = fixture["league"]["id"]
            if league_id in fixtures_by_league:
                fixtures_by_league[league_id].append(fixture)

        self.assertEqual(len(fixtures_by_league[357]), 1)
        self.assertEqual(len(fixtures_by_league[358]), 1)
        self.assertEqual(len(fixtures_by_league[359]), 0)

    def test_check_if_all_matches_finished(self):
        """Test checking if all matches are finished."""
        # All finished
        all_finished = all(
            f["fixture"]["status"]["short"] == "FT"
            for f in self.sample_fixtures
        )
        self.assertFalse(all_finished)  # One is 1H

        # Update to all finished
        self.sample_fixtures[0]["fixture"]["status"]["short"] = "FT"
        all_finished = all(
            f["fixture"]["status"]["short"] == "FT"
            for f in self.sample_fixtures
        )
        self.assertTrue(all_finished)

    def test_has_matches_on_today(self):
        """Test checking if matches scheduled for today."""
        today = date.today().isoformat()
        cache = {
            "premier_division": {
                "post_id": "test123",
                "match_dates": [today, "2024-10-20"],
                "round": "Regular Season - 32",
            }
        }

        has_matches_today = False
        for competition in ["premier_division", "first_division", "fai_cup"]:
            if competition in cache:
                if today in cache[competition].get("match_dates", []):
                    has_matches_today = True
                    break

        self.assertTrue(has_matches_today)

    def test_no_matches_today(self):
        """Test when no matches scheduled today."""
        cache = {
            "premier_division": {
                "post_id": "test123",
                "match_dates": ["2024-10-20", "2024-10-21"],
                "round": "Regular Season - 32",
            }
        }

        today = date.today().isoformat()
        has_matches_today = False
        for competition in ["premier_division", "first_division", "fai_cup"]:
            if competition in cache:
                if today in cache[competition].get("match_dates", []):
                    has_matches_today = True
                    break

        self.assertFalse(has_matches_today)


class TestLiveUpdaterIntegration(unittest.TestCase):
    """Test live updater integration with external APIs."""

    @patch("live_updater.load_cache")
    @patch("live_updater.get_live_fixtures")
    def test_no_cache_exits_gracefully(
            self, mock_get_fixtures, mock_load_cache):
        """Test that updater exits gracefully with no cached posts."""
        mock_load_cache.return_value = {}
        mock_get_fixtures.return_value = []

        # Import here to avoid import before patch
        from live_updater import main

        # Should not raise error
        main()
        mock_get_fixtures.assert_not_called()

    @patch("live_updater.load_cache")
    @patch("live_updater.get_live_fixtures")
    def test_no_matches_today_exits_early(
        self, mock_get_fixtures, mock_load_cache
    ):
        """Test updater exits when no matches scheduled today."""
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "test123",
                "match_dates": ["2025-10-20"],  # Future date
                "round": "Regular Season - 32",
            }
        }
        mock_get_fixtures.return_value = []

        from live_updater import main

        main()
        mock_get_fixtures.assert_not_called()

    @patch("live_updater.update_reddit_post")
    @patch("live_updater.get_league_table")
    @patch("live_updater.get_live_fixtures")
    @patch("live_updater.load_cache")
    def test_update_premier_division_thread(
        self,
        mock_load_cache,
        mock_get_fixtures,
        mock_get_table,
        mock_update_post,
    ):
        """Test updating Premier Division thread."""
        today = date.today().isoformat()
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "prem_post_123",
                "match_dates": [today],
                "round": "Regular Season - 32",
            }
        }

        mock_fixture = {
            "fixture": {
                "id": 1,
                "status": {"short": "2H", "elapsed": 67},
                "date": "2025-10-20T18:45:00+00:00",
                "venue": {"name": "Richmond Park"},
            },
            "league": {"id": 357},
            "goals": {"home": 2, "away": 1},
            "teams": {
                "home": {"name": "St Patrick's Athl.", "id": 1},
                "away": {"name": "Shelbourne", "id": 2},
            },
        }

        mock_get_fixtures.return_value = [mock_fixture]
        mock_get_table.return_value = []
        mock_update_post.return_value = True

        from live_updater import main

        main()

        # Verify update was called
        self.assertTrue(mock_update_post.called)

    @patch("live_updater.load_cache")
    @patch("live_updater.get_live_fixtures")
    def test_handles_mixed_league_fixtures(
        self, mock_get_fixtures, mock_load_cache
    ):
        """Test handling fixtures from multiple leagues."""
        today = date.today().isoformat()
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "prem_123",
                "match_dates": [today],
                "round": "Regular Season - 32",
            },
            "first_division": {
                "post_id": "first_456",
                "match_dates": [today],
                "round": "Regular Season - 28",
            },
            "fai_cup": {
                "post_id": "cup_789",
                "match_dates": [today],
                "round": "Final",
            },
        }

        fixtures = [
            {
                "fixture": {
                    "status": {"short": "1H", "elapsed": 23},
                    "date": f"{today}T19:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 357},
                "goals": {"home": 2, "away": 0},  # St Pats leading
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 1},
                    "away": {"name": "Shelbourne", "id": 2},
                },
            },
            {
                "fixture": {
                    "status": {"short": "HT", "elapsed": None},
                    "date": f"{today}T15:00:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 358},
                "goals": {"home": 1, "away": 0},  # St Pats winning
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 3},
                    "away": {"name": "Shelbourne", "id": 4},
                },
            },
            {
                "fixture": {
                    "status": {"short": "2H", "elapsed": 67},
                    "date": f"{today}T20:00:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 359},
                "goals": {"home": 3, "away": 1},  # St Pats dominating
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 5},
                    "away": {"name": "Shelbourne", "id": 6},
                },
            },
        ]

        mock_get_fixtures.return_value = fixtures

        # Organize by league
        fixtures_by_league = {357: [], 358: [], 359: []}
        for fixture in fixtures:
            league_id = fixture["league"]["id"]
            if league_id in fixtures_by_league:
                fixtures_by_league[league_id].append(fixture)

        # Verify distribution
        self.assertEqual(len(fixtures_by_league[357]), 1)
        self.assertEqual(len(fixtures_by_league[358]), 1)
        self.assertEqual(len(fixtures_by_league[359]), 1)


class TestLiveUpdaterErrorHandling(unittest.TestCase):
    """Test live updater error handling."""

    @patch("live_updater.load_cache")
    @patch("live_updater.get_live_fixtures")
    def test_handles_empty_live_fixtures(
        self, mock_get_fixtures, mock_load_cache
    ):
        """Test handling when no live fixtures returned."""
        today = date.today().isoformat()
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "test123",
                "match_dates": [today],
                "round": "Regular Season - 32",
            }
        }
        mock_get_fixtures.return_value = []

        from live_updater import main

        # Should handle gracefully
        main()

    @patch("live_updater.update_reddit_post")
    @patch("live_updater.get_league_table")
    @patch("live_updater.get_live_fixtures")
    @patch("live_updater.load_cache")
    def test_continues_after_update_failure(
        self,
        mock_load_cache,
        mock_get_fixtures,
        mock_get_table,
        mock_update_post,
    ):
        """Test updater continues if one post update fails."""
        today = date.today().isoformat()
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "prem_123",
                "match_dates": [today],
                "round": "Regular Season - 32",
            },
            "first_division": {
                "post_id": "first_456",
                "match_dates": [today],
                "round": "Regular Season - 28",
            },
        }

        fixtures = [
            {
                "fixture": {
                    "status": {"short": "1H", "elapsed": 23},
                    "date": f"{today}T19:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 357},
                "goals": {"home": 2, "away": 0},  # St Pats leading
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 1},
                    "away": {"name": "Shelbourne", "id": 2},
                },
            },
            {
                "fixture": {
                    "status": {"short": "HT", "elapsed": None},
                    "date": f"{today}T15:00:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 358},
                "goals": {"home": 1, "away": 0},  # St Pats winning
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 3},
                    "away": {"name": "Shelbourne", "id": 4},
                },
            },
        ]

        mock_get_fixtures.return_value = fixtures
        mock_get_table.return_value = []
        # First call fails, second succeeds
        mock_update_post.side_effect = [False, True]

        from live_updater import main

        # Should complete without raising
        main()

        # Both posts should be attempted
        self.assertEqual(mock_update_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
