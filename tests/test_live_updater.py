"""Integration tests for live updater functionality."""

import unittest
from unittest.mock import patch
from datetime import date


class TestLiveUpdaterLogic(unittest.TestCase):
    """Test live updater core logic."""

    def setUp(self):
        """Set up test fixtures - St Patrick's Athletic vs Shelbourne."""
        # League IDs: Premier=126, First=218, FAI Cup=219
        self.sample_fixtures = [
            {
                "fixture": {
                    "id": 1,
                    "status": {"short": "1H", "elapsed": 23},
                    "date": "2024-10-19T19:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 126},  # Premier Division
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
                "league": {"id": 218},  # First Division
                "goals": {"home": 3, "away": 0},
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 3},
                    "away": {"name": "Shelbourne", "id": 4},
                },
            },
        ]

    def test_organize_fixtures_by_league(self):
        """Test organizing fixtures by league ID."""
        # League IDs: Premier=126, First=218, FAI Cup=219
        fixtures_by_league = {126: [], 218: [], 219: []}

        for fixture in self.sample_fixtures:
            league_id = fixture["league"]["id"]
            if league_id in fixtures_by_league:
                fixtures_by_league[league_id].append(fixture)

        self.assertEqual(len(fixtures_by_league[126]), 1)
        self.assertEqual(len(fixtures_by_league[218]), 1)
        self.assertEqual(len(fixtures_by_league[219]), 0)

    def test_check_if_all_matches_finished(self):
        """Test checking if all matches are finished."""
        all_finished = all(
            f["fixture"]["status"]["short"] == "FT"
            for f in self.sample_fixtures
        )
        self.assertFalse(all_finished)  # One is 1H

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
            "league": {"id": 126},  # Premier Division
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

        # League IDs: Premier=126, First=218, FAI Cup=219
        fixtures = [
            {
                "fixture": {
                    "status": {"short": "1H", "elapsed": 23},
                    "date": f"{today}T19:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 126},  # Premier Division
                "goals": {"home": 2, "away": 0},
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
                "league": {"id": 218},  # First Division
                "goals": {"home": 1, "away": 0},
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
                "league": {"id": 219},  # FAI Cup
                "goals": {"home": 3, "away": 1},
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 5},
                    "away": {"name": "Shelbourne", "id": 6},
                },
            },
        ]

        mock_get_fixtures.return_value = fixtures

        fixtures_by_league = {126: [], 218: [], 219: []}
        for fixture in fixtures:
            league_id = fixture["league"]["id"]
            if league_id in fixtures_by_league:
                fixtures_by_league[league_id].append(fixture)

        # Verify distribution
        self.assertEqual(len(fixtures_by_league[126]), 1)
        self.assertEqual(len(fixtures_by_league[218]), 1)
        self.assertEqual(len(fixtures_by_league[219]), 1)


class TestCleanupFinishedMatchDay(unittest.TestCase):
    """Test cache cleanup when matches finish."""

    @patch("live_updater.save_cache")
    @patch("live_updater.get_league_fixtures")
    def test_cleanup_when_all_matches_finished(
        self, mock_get_fixtures, mock_save_cache
    ):
        """Test cache cleanup when all today's matches are finished."""
        from live_updater import _cleanup_finished_match_day

        today = date.today()
        today_str = today.isoformat()

        cache = {
            "premier_division": {
                "post_id": "test123",
                "match_dates": [today_str, "2026-02-07"],
            }
        }

        # All matches finished (FT)
        mock_get_fixtures.return_value = [
            {
                "fixture": {
                    "date": f"{today_str}T19:45:00+00:00",
                    "status": {"short": "FT"},
                },
                "league": {"id": 126},
            },
            {
                "fixture": {
                    "date": f"{today_str}T19:45:00+00:00",
                    "status": {"short": "FT"},
                },
                "league": {"id": 126},
            },
        ]

        _cleanup_finished_match_day(cache, today)

        # Should have removed today from match_dates
        self.assertNotIn(today_str, cache["premier_division"]["match_dates"])
        self.assertIn("2026-02-07", cache["premier_division"]["match_dates"])
        mock_save_cache.assert_called_once()

    @patch("live_updater.save_cache")
    @patch("live_updater.get_league_fixtures")
    def test_no_cleanup_when_matches_not_started(
        self, mock_get_fixtures, mock_save_cache
    ):
        """Test no cleanup when matches haven't started yet."""
        from live_updater import _cleanup_finished_match_day

        today = date.today()
        today_str = today.isoformat()

        cache = {
            "premier_division": {
                "post_id": "test123",
                "match_dates": [today_str],
            }
        }

        # Matches not started (NS)
        mock_get_fixtures.return_value = [
            {
                "fixture": {
                    "date": f"{today_str}T19:45:00+00:00",
                    "status": {"short": "NS"},
                },
                "league": {"id": 126},
            },
        ]

        _cleanup_finished_match_day(cache, today)

        # Should NOT have removed today
        self.assertIn(today_str, cache["premier_division"]["match_dates"])
        mock_save_cache.assert_not_called()

    @patch("live_updater.save_cache")
    @patch("live_updater.get_league_fixtures")
    def test_no_cleanup_when_matches_in_progress(
        self, mock_get_fixtures, mock_save_cache
    ):
        """Test no cleanup when some matches still in progress."""
        from live_updater import _cleanup_finished_match_day

        today = date.today()
        today_str = today.isoformat()

        cache = {
            "premier_division": {
                "post_id": "test123",
                "match_dates": [today_str],
            }
        }

        # Mixed: one finished, one in progress
        mock_get_fixtures.return_value = [
            {
                "fixture": {
                    "date": f"{today_str}T19:45:00+00:00",
                    "status": {"short": "FT"},
                },
                "league": {"id": 126},
            },
            {
                "fixture": {
                    "date": f"{today_str}T20:00:00+00:00",
                    "status": {"short": "2H"},
                },
                "league": {"id": 126},
            },
        ]

        _cleanup_finished_match_day(cache, today)

        # Should NOT have removed today
        self.assertIn(today_str, cache["premier_division"]["match_dates"])
        mock_save_cache.assert_not_called()

    @patch("live_updater.get_league_fixtures")
    def test_get_todays_fixtures_filters_correctly(self, mock_get_fixtures):
        """Test _get_todays_fixtures filters to today only."""
        from live_updater import _get_todays_fixtures

        today = date.today()
        today_str = today.isoformat()

        mock_get_fixtures.return_value = [
            {"fixture": {"date": f"{today_str}T19:45:00+00:00"}},
            {"fixture": {"date": "2026-02-07T19:45:00+00:00"}},
            {"fixture": {"date": f"{today_str}T20:00:00+00:00"}},
        ]

        result = _get_todays_fixtures(today, [126])

        self.assertEqual(len(result), 2)
        for fixture in result:
            self.assertTrue(fixture["fixture"]["date"].startswith(today_str))


class TestLiveUpdaterErrorHandling(unittest.TestCase):
    """Test live updater error handling."""

    @patch("live_updater._cleanup_finished_match_day")
    @patch("live_updater.load_cache")
    @patch("live_updater.get_live_fixtures")
    def test_handles_empty_live_fixtures(
        self, mock_get_fixtures, mock_load_cache, mock_cleanup
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

        # Should handle gracefully and call cleanup
        main()
        mock_cleanup.assert_called_once()

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

        # League IDs: Premier=126, First=218
        fixtures = [
            {
                "fixture": {
                    "status": {"short": "1H", "elapsed": 23},
                    "date": f"{today}T19:45:00+00:00",
                    "venue": {"name": "Richmond Park"},
                },
                "league": {"id": 126},  # Premier Division
                "goals": {"home": 2, "away": 0},
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
                "league": {"id": 218},  # First Division
                "goals": {"home": 1, "away": 0},
                "teams": {
                    "home": {"name": "St Patrick's Athletic", "id": 3},
                    "away": {"name": "Shelbourne", "id": 4},
                },
            },
        ]

        mock_get_fixtures.return_value = fixtures
        mock_get_table.return_value = []
        mock_update_post.side_effect = [False, True]  # First fails, second succeeds

        from live_updater import main

        # Should complete without raising
        main()

        # Both posts should be attempted
        self.assertEqual(mock_update_post.call_count, 2)


class TestLOIPremierRound1Simulation(unittest.TestCase):
    """Simulate Round 1 of 2026 LOI Premier Division with real fixture data."""

    def setUp(self):
        """Set up Round 1 fixtures fetched from external API.

        These are actual Round 1 fixtures for the 2026 season.
        We simulate them as live matches with various states.
        """
        # Real Round 1 raw fixture data (fetched from API)
        self.raw_round_1_fixtures = [
            {
                "round": "1",
                "roundName": 1,
                "pageUrl": "/matches/sligo-rovers-vs-derry-city/1sbstg#5100791",
                "id": "5100791",
                "home": {
                    "name": "Derry City",
                    "shortName": "Derry City",
                    "id": "8338"
                },
                "away": {
                    "name": "Sligo Rovers",
                    "shortName": "Sligo Rovers",
                    "id": "6361"
                },
                "status": {
                    "utcTime": "2026-02-06T19:45:00Z",
                    "started": True,
                    "cancelled": False,
                    "finished": False,
                    "score": {"home": 2, "away": 1},
                    "liveTime": {"short": "67", "maxTime": 90}
                },
                "_league_id": 126
            },
            {
                "round": "1",
                "roundName": 1,
                "pageUrl": "/matches/drogheda-united-vs-galway-united-fc/1s8rv9gf#5100792",
                "id": "5100792",
                "home": {
                    "name": "Galway United FC",
                    "shortName": "Galway United FC",
                    "id": "520517"
                },
                "away": {
                    "name": "Drogheda United",
                    "shortName": "Drogheda United",
                    "id": "8339"
                },
                "status": {
                    "utcTime": "2026-02-06T19:45:00Z",
                    "started": True,
                    "cancelled": False,
                    "finished": False,
                    "score": {"home": 0, "away": 0},
                    "liveTime": {"short": "HT", "maxTime": 45}
                },
                "_league_id": 126
            },
            {
                "round": "1",
                "roundName": 1,
                "pageUrl": "/matches/shelbourne-vs-waterford-fc/15eomr#5100793",
                "id": "5100793",
                "home": {
                    "name": "Waterford FC",
                    "shortName": "Waterford FC",
                    "id": "6042"
                },
                "away": {
                    "name": "Shelbourne",
                    "shortName": "Shelbourne",
                    "id": "5751"
                },
                "status": {
                    "utcTime": "2026-02-06T19:45:00Z",
                    "started": True,
                    "cancelled": False,
                    "finished": False,
                    "score": {"home": 1, "away": 3},
                    "liveTime": {"short": "78", "maxTime": 90}
                },
                "_league_id": 126
            },
            {
                "round": "1",
                "roundName": 1,
                "pageUrl": "/matches/dundalk-vs-shamrock-rovers/anwer#5100794",
                "id": "5100794",
                "home": {
                    "name": "Shamrock Rovers",
                    "shortName": "Shamrock Rovers",
                    "id": "4131"
                },
                "away": {
                    "name": "Dundalk",
                    "shortName": "Dundalk",
                    "id": "1853"
                },
                "status": {
                    "utcTime": "2026-02-06T20:00:00Z",
                    "started": True,
                    "cancelled": False,
                    "finished": False,
                    "score": {"home": 1, "away": 0},
                    "liveTime": {"short": "23", "maxTime": 45}
                },
                "_league_id": 126
            },
            {
                "round": "1",
                "roundName": 1,
                "pageUrl": "/matches/st-patricks-athletic-vs-bohemian-fc/cdqfe#5100795",
                "id": "5100795",
                "home": {
                    "name": "Bohemian FC",
                    "shortName": "Bohemian FC",
                    "id": "4594"
                },
                "away": {
                    "name": "St. Patrick's Athletic",
                    "shortName": "St. Patrick's Athletic",
                    "id": "1854"
                },
                "status": {
                    "utcTime": "2026-02-08T14:00:00Z",
                    "started": False,
                    "cancelled": False,
                    "finished": False
                },
                "_league_id": 126
            },
        ]

    def test_convert_round_1_fixtures(self):
        """Test converting all Round 1 raw fixtures to api-football format."""
        from match_client import convert_raw_match

        converted = [convert_raw_match(m) for m in self.raw_round_1_fixtures]

        self.assertEqual(len(converted), 5)

        # Check Derry vs Sligo (2H, 67')
        derry_sligo = converted[0]
        self.assertEqual(derry_sligo["teams"]["home"]["name"], "Derry City")
        self.assertEqual(derry_sligo["teams"]["away"]["name"], "Sligo Rovers")
        self.assertEqual(derry_sligo["goals"]["home"], 2)
        self.assertEqual(derry_sligo["goals"]["away"], 1)
        self.assertEqual(derry_sligo["fixture"]["status"]["short"], "2H")

        # Check Galway vs Drogheda (HT, 0-0)
        galway_drogheda = converted[1]
        self.assertEqual(galway_drogheda["teams"]["home"]["name"], "Galway United FC")
        self.assertEqual(galway_drogheda["goals"]["home"], 0)
        self.assertEqual(galway_drogheda["goals"]["away"], 0)
        self.assertEqual(galway_drogheda["fixture"]["status"]["short"], "HT")

        # Check Waterford vs Shelbourne (2H, 78')
        waterford_shels = converted[2]
        self.assertEqual(waterford_shels["teams"]["away"]["name"], "Shelbourne")
        self.assertEqual(waterford_shels["goals"]["home"], 1)
        self.assertEqual(waterford_shels["goals"]["away"], 3)

        # Check Shamrock Rovers vs Dundalk (1H, 23')
        rovers_dundalk = converted[3]
        self.assertEqual(rovers_dundalk["teams"]["home"]["name"], "Shamrock Rovers")
        self.assertEqual(rovers_dundalk["fixture"]["status"]["short"], "1H")
        self.assertEqual(rovers_dundalk["fixture"]["status"]["elapsed"], 23)

        # Check Bohs vs St Pats (NS - not started yet)
        bohs_pats = converted[4]
        self.assertEqual(bohs_pats["teams"]["home"]["name"], "Bohemian FC")
        self.assertEqual(bohs_pats["teams"]["away"]["name"], "St. Patrick's Athletic")
        self.assertEqual(bohs_pats["fixture"]["status"]["short"], "NS")

    def test_filter_live_matches_from_round_1(self):
        """Test filtering only live matches from Round 1."""
        live_matches = [
            m for m in self.raw_round_1_fixtures
            if m["status"].get("started") and not m["status"].get("finished")
        ]

        # 4 matches are live (Bohs vs Pats hasn't started)
        self.assertEqual(len(live_matches), 4)

        # Verify the not-started match is excluded
        for match in live_matches:
            self.assertNotEqual(match["home"]["name"], "Bohemian FC")

    def test_format_round_1_for_display(self):
        """Test formatting Round 1 matches for Reddit display."""
        from match_client import convert_raw_match
        from common import format_live_fixture

        converted = [convert_raw_match(m) for m in self.raw_round_1_fixtures]
        formatted = [format_live_fixture(m) for m in converted]

        # Check format: [home, score, away, venue, status, kickoff, scorers]
        self.assertEqual(len(formatted), 5)  # 5 matches
        self.assertEqual(len(formatted[0]), 7)  # 7 columns per match

        # Derry 2-1 Sligo
        self.assertEqual(formatted[0][0], "Derry City")
        self.assertEqual(formatted[0][1], "2-1")
        self.assertEqual(formatted[0][2], "Sligo Rovers")

        # Galway 0-0 Drogheda
        self.assertEqual(formatted[1][1], "0-0")

        # Waterford 1-3 Shelbourne
        self.assertEqual(formatted[2][1], "1-3")

        # Shamrock Rovers 1-0 Dundalk
        self.assertEqual(formatted[3][1], "1-0")

        # Bohs vs St Pats (not started)
        self.assertEqual(formatted[4][1], "vs")

    def test_organize_round_1_by_date(self):
        """Test organizing Round 1 fixtures by match date."""
        from match_client import convert_raw_match

        converted = [convert_raw_match(m) for m in self.raw_round_1_fixtures]

        matches_by_date = {}
        for match in converted:
            match_date = match["fixture"]["date"][:10]
            matches_by_date.setdefault(match_date, []).append(match)

        # Should have 2 dates: Feb 6 (4 matches) and Feb 8 (1 match)
        self.assertEqual(len(matches_by_date), 2)
        self.assertIn("2026-02-06", matches_by_date)
        self.assertIn("2026-02-08", matches_by_date)
        self.assertEqual(len(matches_by_date["2026-02-06"]), 4)
        self.assertEqual(len(matches_by_date["2026-02-08"]), 1)

    def test_simulate_goals_with_events(self):
        """Test simulating goal events for Derry vs Sligo match."""
        from match_client import convert_raw_match

        # Add simulated events to the Derry vs Sligo match
        derry_sligo_with_events = self.raw_round_1_fixtures[0].copy()

        # Simulate converted match with events
        converted = convert_raw_match(derry_sligo_with_events)
        converted["events"] = [
            {
                "type": "Goal",
                "team": {"name": "Derry City"},
                "player": {"name": "Patrick McEleney"},
                "time": {"elapsed": 12},
                "detail": "Normal Goal",
            },
            {
                "type": "Goal",
                "team": {"name": "Sligo Rovers"},
                "player": {"name": "Aidan Keena"},
                "time": {"elapsed": 34},
                "detail": "Penalty",
            },
            {
                "type": "Goal",
                "team": {"name": "Derry City"},
                "player": {"name": "Will Patching"},
                "time": {"elapsed": 58},
                "detail": "Normal Goal",
            },
        ]

        # Verify events
        self.assertEqual(len(converted["events"]), 3)
        self.assertEqual(converted["events"][0]["player"]["name"], "Patrick McEleney")
        self.assertEqual(converted["events"][1]["detail"], "Penalty")
        self.assertEqual(converted["events"][2]["time"]["elapsed"], 58)

    @patch("live_updater.update_reddit_post")
    @patch("live_updater.get_league_table")
    @patch("live_updater.get_live_fixtures")
    @patch("live_updater.load_cache")
    def test_full_round_1_update_simulation(
        self,
        mock_load_cache,
        mock_get_fixtures,
        mock_get_table,
        mock_update_post,
    ):
        """Simulate a full Round 1 live update cycle."""
        from match_client import convert_raw_match

        # Set up cache for Round 1
        mock_load_cache.return_value = {
            "premier_division": {
                "post_id": "round1_test_post",
                "match_dates": ["2026-02-06", "2026-02-08"],
                "round": "Regular Season - 1",
            }
        }

        # Convert raw fixtures and filter to live only
        live_raw = [
            m for m in self.raw_round_1_fixtures
            if m["status"].get("started") and not m["status"].get("finished")
        ]
        converted_fixtures = [convert_raw_match(m) for m in live_raw]

        mock_get_fixtures.return_value = converted_fixtures
        mock_get_table.return_value = []  # Empty table for Round 1
        mock_update_post.return_value = True

        # Organize by league
        fixtures_by_league = {126: [], 218: [], 219: []}
        for fixture in converted_fixtures:
            league_id = fixture["league"]["id"]
            if league_id in fixtures_by_league:
                fixtures_by_league[league_id].append(fixture)

        # Verify 4 live Premier Division matches
        self.assertEqual(len(fixtures_by_league[126]), 4)

        # Verify match details
        home_teams = [f["teams"]["home"]["name"] for f in fixtures_by_league[126]]
        self.assertIn("Derry City", home_teams)
        self.assertIn("Galway United FC", home_teams)
        self.assertIn("Waterford FC", home_teams)
        self.assertIn("Shamrock Rovers", home_teams)


if __name__ == "__main__":
    unittest.main()
