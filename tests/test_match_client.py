"""Tests for match data client and data conversion."""

import unittest
from unittest.mock import Mock, patch

from match_client import (
    MatchDataClient,
    convert_raw_match,
    convert_raw_table,
    convert_match_events,
    LEAGUE_ID_PREMIER,
)
from common import format_live_fixture, get_match_status_display


class TestLiveMatch(unittest.TestCase):
    """Test with a simulated live match scenario."""

    def setUp(self):
        """Set up a live match fixture - Shamrock Rovers vs St Patrick's Athletic."""
        self.live_raw_match = {
            "id": "4567890",
            "round": "15",
            "home": {
                "id": "8073",
                "name": "Shamrock Rovers",
                "shortName": "Shamrock"
            },
            "away": {
                "id": "8085",
                "name": "St Patrick's Athletic",
                "shortName": "St Pats"
            },
            "status": {
                "utcTime": "2025-07-18T19:45:00Z",
                "started": True,
                "finished": False,
                "cancelled": False,
                "score": {
                    "home": 2,
                    "away": 1
                },
                "liveTime": {
                    "short": "67",
                    "long": "67:32"
                }
            },
            "venue": "Tallaght Stadium",
            "_league_id": LEAGUE_ID_PREMIER
        }

        # Match details response (for events)
        self.match_details = {
            "header": {
                "teams": [
                    {"name": "Shamrock Rovers", "id": "8073"},
                    {"name": "St Patrick's Athletic", "id": "8085"}
                ]
            },
            "content": {
                "matchFacts": {
                    "events": {
                        "events": [
                            {
                                "type": "Goal",
                                "time": 23,
                                "isHome": True,
                                "nameStr": "Aaron Greene",
                                "ownGoal": False,
                                "isPenalty": False
                            },
                            {
                                "type": "Goal",
                                "time": 41,
                                "isHome": False,
                                "nameStr": "Eoin Doyle",
                                "ownGoal": False,
                                "isPenalty": True
                            },
                            {
                                "type": "Goal",
                                "time": 62,
                                "isHome": True,
                                "nameStr": "Graham Burke",
                                "ownGoal": False,
                                "isPenalty": False
                            }
                        ]
                    }
                }
            }
        }

    def test_convert_live_match(self):
        """Test converting a live match to api-football format."""
        converted = convert_raw_match(self.live_raw_match)

        # Check structure
        self.assertIn("fixture", converted)
        self.assertIn("teams", converted)
        self.assertIn("goals", converted)
        self.assertIn("league", converted)

        # Check fixture details
        self.assertEqual(converted["fixture"]["id"], 4567890)
        self.assertIn("status", converted["fixture"])

        # Check teams
        self.assertEqual(converted["teams"]["home"]["name"], "Shamrock Rovers")
        self.assertEqual(converted["teams"]["away"]["name"], "St Patrick's Athletic")

        # Check score
        self.assertEqual(converted["goals"]["home"], 2)
        self.assertEqual(converted["goals"]["away"], 1)

    def test_live_match_status_display(self):
        """Test that live match status displays correctly."""
        converted = convert_raw_match(self.live_raw_match)
        score, status = get_match_status_display(converted)

        self.assertEqual(score, "2-1")
        # Status should show minute
        self.assertIn("67", status)

    def test_format_live_fixture(self):
        """Test formatting a live fixture for display."""
        converted = convert_raw_match(self.live_raw_match)
        formatted = format_live_fixture(converted)

        # Should return [home, score, away, venue, status, kickoff, scorers]
        self.assertEqual(len(formatted), 7)
        self.assertEqual(formatted[0], "Shamrock Rovers")
        self.assertEqual(formatted[1], "2-1")
        self.assertEqual(formatted[2], "St Patrick's Athletic")

    def test_convert_match_events(self):
        """Test converting match events (goal scorers)."""
        events = convert_match_events(self.match_details)

        self.assertEqual(len(events), 3)

        # First goal - Aaron Greene 23'
        self.assertEqual(events[0]["type"], "Goal")
        self.assertEqual(events[0]["player"]["name"], "Aaron Greene")
        self.assertEqual(events[0]["time"]["elapsed"], 23)
        self.assertEqual(events[0]["team"]["name"], "Shamrock Rovers")

        # Second goal - Eoin Doyle 41' (pen)
        self.assertEqual(events[1]["player"]["name"], "Eoin Doyle")
        self.assertEqual(events[1]["detail"], "Penalty")
        self.assertEqual(events[1]["team"]["name"], "St Patrick's Athletic")

        # Third goal - Graham Burke 62'
        self.assertEqual(events[2]["player"]["name"], "Graham Burke")
        self.assertEqual(events[2]["time"]["elapsed"], 62)


class TestMatchStatuses(unittest.TestCase):
    """Test different match status scenarios."""

    def _create_match(self, started, finished, score_home, score_away, live_time=None):
        """Helper to create match with specific status."""
        return {
            "id": "123",
            "home": {"id": "1", "name": "Team A"},
            "away": {"id": "2", "name": "Team B"},
            "status": {
                "utcTime": "2025-07-18T19:45:00Z",
                "started": started,
                "finished": finished,
                "cancelled": False,
                "score": {"home": score_home, "away": score_away},
                "liveTime": {"short": live_time} if live_time else {}
            },
            "_league_id": 126
        }

    def test_not_started_match(self):
        """Test match that hasn't started."""
        match = self._create_match(False, False, None, None)
        converted = convert_raw_match(match)
        score, status = get_match_status_display(converted)

        self.assertEqual(score, "vs")
        self.assertEqual(converted["fixture"]["status"]["short"], "NS")

    def test_first_half_match(self):
        """Test match in first half."""
        match = self._create_match(True, False, 1, 0, "23")
        converted = convert_raw_match(match)
        score, status = get_match_status_display(converted)

        self.assertEqual(score, "1-0")
        self.assertIn("23", status)

    def test_half_time_match(self):
        """Test match at half time."""
        match = self._create_match(True, False, 1, 1, "HT")
        converted = convert_raw_match(match)
        score, status = get_match_status_display(converted)

        self.assertEqual(score, "1-1")
        self.assertEqual(status, "HT")

    def test_second_half_match(self):
        """Test match in second half."""
        match = self._create_match(True, False, 2, 1, "78")
        converted = convert_raw_match(match)
        score, status = get_match_status_display(converted)

        self.assertEqual(score, "2-1")
        self.assertIn("78", status)

    def test_finished_match(self):
        """Test finished match."""
        match = self._create_match(True, True, 3, 2, "FT")
        converted = convert_raw_match(match)

        self.assertEqual(converted["fixture"]["status"]["short"], "FT")
        self.assertEqual(converted["goals"]["home"], 3)
        self.assertEqual(converted["goals"]["away"], 2)


class TestLeagueTable(unittest.TestCase):
    """Test league table conversion."""

    def setUp(self):
        """Set up sample league table."""
        self.raw_table = [
            {
                "idx": 1,
                "id": 8073,
                "name": "Shamrock Rovers",
                "played": 20,
                "wins": 15,
                "draws": 3,
                "losses": 2,
                "scoresFor": 45,
                "scoresAgainst": 15,
                "goalConDiff": 30,
                "pts": 48
            },
            {
                "idx": 2,
                "id": 8085,
                "name": "St Patrick's Athletic",
                "played": 20,
                "wins": 14,
                "draws": 4,
                "losses": 2,
                "scoresFor": 40,
                "scoresAgainst": 18,
                "goalConDiff": 22,
                "pts": 46
            },
            {
                "idx": 3,
                "id": 8079,
                "name": "Shelbourne",
                "played": 20,
                "wins": 12,
                "draws": 5,
                "losses": 3,
                "scoresFor": 35,
                "scoresAgainst": 20,
                "goalConDiff": 15,
                "pts": 41
            }
        ]

    def test_convert_table(self):
        """Test converting raw table to api-football format."""
        converted = convert_raw_table(self.raw_table)

        self.assertEqual(len(converted), 3)

        # Check first place
        first = converted[0]
        self.assertEqual(first["rank"], 1)
        self.assertEqual(first["team"]["name"], "Shamrock Rovers")
        self.assertEqual(first["all"]["played"], 20)
        self.assertEqual(first["all"]["win"], 15)
        self.assertEqual(first["all"]["draw"], 3)
        self.assertEqual(first["all"]["lose"], 2)
        self.assertEqual(first["all"]["goals"]["for"], 45)
        self.assertEqual(first["all"]["goals"]["against"], 15)
        self.assertEqual(first["goalsDiff"], 30)
        self.assertEqual(first["points"], 48)

    def test_empty_table(self):
        """Test converting empty table."""
        converted = convert_raw_table([])
        self.assertEqual(converted, [])


class TestMatchDataClientIntegration(unittest.TestCase):
    """Integration tests for match data client (with mocked requests)."""

    @patch("match_client.requests.get")
    def test_get_league_matches(self, mock_get):
        """Test fetching league matches."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "fixtures": {
                "allMatches": [
                    {
                        "id": "123",
                        "home": {"id": "1", "name": "Team A"},
                        "away": {"id": "2", "name": "Team B"},
                        "status": {
                            "utcTime": "2025-07-18T19:45:00Z",
                            "started": False,
                            "finished": False
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        match_client = MatchDataClient()
        data = match_client.get_league_matches(126, tab="fixtures")

        self.assertIn("fixtures", data)
        mock_get.assert_called_once()

    @patch("match_client.requests.get")
    def test_get_match_details(self, mock_get):
        """Test fetching match details."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "header": {"teams": []},
            "content": {"matchFacts": {"events": {"events": []}}}
        }
        mock_get.return_value = mock_response

        match_client = MatchDataClient()
        details = match_client.get_match_details(12345)

        self.assertIn("header", details)
        mock_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
