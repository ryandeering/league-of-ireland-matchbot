"""Tests for match data client and data conversion."""

import unittest
from unittest.mock import Mock, patch

import requests

from match_client import (
    MatchDataClient,
    convert_raw_match,
    convert_raw_table,
    convert_match_events,
    extract_score_from_details,
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

    def test_penalty_via_goal_description_key(self):
        """Penalty detected via goalDescriptionKey when isPenalty is None."""
        details = {
            "header": {
                "teams": [
                    {"name": "Derry City", "id": "8338"},
                    {"name": "Dundalk", "id": "8341"},
                ]
            },
            "content": {
                "matchFacts": {
                    "events": {
                        "events": [
                            {
                                "type": "Goal",
                                "time": 90,
                                "isHome": True,
                                "nameStr": "Michael Duffy",
                                "ownGoal": None,
                                "isPenalty": None,
                                "goalDescriptionKey": "penalty",
                            }
                        ]
                    }
                }
            },
        }
        events = convert_match_events(details)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["detail"], "Penalty")
        self.assertEqual(events[0]["player"]["name"], "Michael Duffy")


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
                "scoresStr": "45-15",
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
                "scoresStr": "40-18",
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
                "scoresStr": "35-20",
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

    def test_scores_str_parsing(self):
        """Test that scoresStr is correctly parsed into GF and GA."""
        table = [{"idx": 1, "id": 1, "name": "Team", "played": 5,
                  "wins": 3, "draws": 1, "losses": 1,
                  "scoresStr": "10-4", "goalConDiff": 6, "pts": 10}]
        converted = convert_raw_table(table)
        self.assertEqual(converted[0]["all"]["goals"]["for"], 10)
        self.assertEqual(converted[0]["all"]["goals"]["against"], 4)

    def test_missing_scores_str_defaults_to_zero(self):
        """Row with no scoresStr should default GF/GA to 0."""
        table = [{"idx": 1, "id": 1, "name": "Team", "played": 0,
                  "wins": 0, "draws": 0, "losses": 0,
                  "goalConDiff": 0, "pts": 0}]
        converted = convert_raw_table(table)
        self.assertEqual(converted[0]["all"]["goals"]["for"], 0)
        self.assertEqual(converted[0]["all"]["goals"]["against"], 0)

    def test_zero_zero_scores_str(self):
        """scoresStr '0-0' should parse to GF=0, GA=0."""
        table = [{"idx": 1, "id": 1, "name": "Team", "played": 1,
                  "wins": 0, "draws": 1, "losses": 0,
                  "scoresStr": "0-0", "goalConDiff": 0, "pts": 1}]
        converted = convert_raw_table(table)
        self.assertEqual(converted[0]["all"]["goals"]["for"], 0)
        self.assertEqual(converted[0]["all"]["goals"]["against"], 0)

    def test_high_scoring_scores_str(self):
        """scoresStr with double-digit values should parse correctly."""
        table = [{"idx": 1, "id": 1, "name": "Team", "played": 20,
                  "wins": 15, "draws": 3, "losses": 2,
                  "scoresStr": "45-15", "goalConDiff": 30, "pts": 48}]
        converted = convert_raw_table(table)
        self.assertEqual(converted[0]["all"]["goals"]["for"], 45)
        self.assertEqual(converted[0]["all"]["goals"]["against"], 15)


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

    @patch("match_client.requests.get")
    def test_get_league_table_returns_none_on_request_error(self, mock_get):
        """Test table endpoint errors return None for caller-level fallback logic."""
        mock_get.side_effect = requests.exceptions.RequestException("API down")

        match_client = MatchDataClient()
        table = match_client.get_league_table(126)

        self.assertIsNone(table)


class TestExtractScoreFromDetails(unittest.TestCase):
    """Test score extraction from matchDetails header."""

    def test_extract_scores_from_header(self):
        """Test extracting home/away scores from header teams."""
        details = {
            "header": {
                "teams": [
                    {"name": "Derry City", "score": 2},
                    {"name": "Sligo Rovers", "score": 1},
                ]
            }
        }
        home, away = extract_score_from_details(details)
        self.assertEqual(home, 2)
        self.assertEqual(away, 1)

    def test_extract_scores_zero_zero(self):
        """Test extracting 0-0 scores (not confused with None)."""
        details = {
            "header": {
                "teams": [
                    {"name": "Team A", "score": 0},
                    {"name": "Team B", "score": 0},
                ]
            }
        }
        home, away = extract_score_from_details(details)
        self.assertEqual(home, 0)
        self.assertEqual(away, 0)

    def test_extract_scores_missing_score_key(self):
        """Test returns None when header has no score."""
        details = {
            "header": {
                "teams": [
                    {"name": "Team A"},
                    {"name": "Team B"},
                ]
            }
        }
        home, away = extract_score_from_details(details)
        self.assertIsNone(home)
        self.assertIsNone(away)

    def test_extract_scores_empty_header(self):
        """Test returns None with empty header."""
        details = {"header": {}}
        home, away = extract_score_from_details(details)
        self.assertIsNone(home)
        self.assertIsNone(away)

    def test_extract_scores_no_header(self):
        """Test returns None with missing header."""
        details = {}
        home, away = extract_score_from_details(details)
        self.assertIsNone(home)
        self.assertIsNone(away)

    def test_extract_scores_single_team(self):
        """Test returns None with only one team in header."""
        details = {
            "header": {
                "teams": [{"name": "Team A", "score": 2}]
            }
        }
        home, away = extract_score_from_details(details)
        self.assertIsNone(home)
        self.assertIsNone(away)

    def test_null_league_score_enriched_from_details(self):
        """Regression: league payload null score + matchDetails score = correct render."""
        # Simulate: leagues endpoint returns null scores
        raw_match = {
            "id": "5100791",
            "home": {"id": "8338", "name": "Derry City"},
            "away": {"id": "6361", "name": "Sligo Rovers"},
            "status": {
                "utcTime": "2026-02-06T19:45:00Z",
                "started": True,
                "finished": True,
                "cancelled": False,
                "score": {"home": None, "away": None},
            },
            "_league_id": 126,
        }
        converted = convert_raw_match(raw_match)

        # Scores should be None from leagues endpoint
        self.assertIsNone(converted["goals"]["home"])
        self.assertIsNone(converted["goals"]["away"])

        # matchDetails has the real scores
        details = {
            "header": {
                "teams": [
                    {"name": "Derry City", "score": 2},
                    {"name": "Sligo Rovers", "score": 1},
                ]
            }
        }
        home, away = extract_score_from_details(details)
        self.assertEqual(home, 2)
        self.assertEqual(away, 1)

        # After enrichment, scores should be correct
        converted["goals"]["home"] = home
        converted["goals"]["away"] = away
        from common import get_match_status_display
        score, status = get_match_status_display(converted)
        self.assertEqual(score, "2-1")
        self.assertEqual(status, "FT")


class TestScorerAttribution(unittest.TestCase):
    """Test goal scorer attribution with isHome flag vs name comparison."""

    def test_scorer_attributed_by_ishome_flag(self):
        """Test scorers are attributed using isHome flag, not team name.

        Regression: matchDetails can use different team name variants
        (e.g. "St Patrick's Athl." vs "St. Patrick's Athletic"). The isHome
        flag avoids this mismatch entirely.
        """
        fixture = {
            "teams": {
                "home": {"name": "St Patrick's Athl."},
                "away": {"name": "Shelbourne"},
            },
            "events": [
                {
                    "type": "Goal",
                    "team": {"name": "St. Patrick's Athletic"},  # Different variant!
                    "player": {"name": "Chris Forrester"},
                    "time": {"elapsed": 34},
                    "detail": "Normal Goal",
                    "isHome": True,
                },
                {
                    "type": "Goal",
                    "team": {"name": "Shelbourne FC"},  # Different variant!
                    "player": {"name": "Sean Boyd"},
                    "time": {"elapsed": 67},
                    "detail": "Normal Goal",
                    "isHome": False,
                },
            ],
        }

        scorers = format_live_fixture(fixture)
        # Scorers column should have both goals attributed correctly
        scorers_str = scorers[6]
        self.assertIn("Forrester", scorers_str)
        self.assertIn("Boyd", scorers_str)

    def test_scorer_fallback_to_team_name_when_no_ishome(self):
        """Test scorers fall back to team name comparison when isHome is absent."""
        fixture = {
            "teams": {
                "home": {"name": "Derry City"},
                "away": {"name": "Sligo Rovers"},
            },
            "events": [
                {
                    "type": "Goal",
                    "team": {"name": "Derry City"},
                    "player": {"name": "Will Patching"},
                    "time": {"elapsed": 12},
                    "detail": "Normal Goal",
                    # No isHome key
                },
            ],
        }

        from common import extract_scorers
        scorers = extract_scorers(fixture)
        self.assertEqual(len(scorers["home"]), 1)
        self.assertEqual(scorers["home"][0]["name"], "Will Patching")
        self.assertEqual(len(scorers["away"]), 0)

    def test_scorer_name_mismatch_without_ishome_goes_to_away(self):
        """Test that name mismatch without isHome puts scorer in away bucket."""
        fixture = {
            "teams": {
                "home": {"name": "St Patrick's Athl."},
                "away": {"name": "Shelbourne"},
            },
            "events": [
                {
                    "type": "Goal",
                    "team": {"name": "St. Patrick's Athletic"},  # No match!
                    "player": {"name": "Chris Forrester"},
                    "time": {"elapsed": 34},
                    "detail": "Normal Goal",
                    # No isHome key - name won't match home team
                },
            ],
        }

        from common import extract_scorers
        scorers = extract_scorers(fixture)
        # Without isHome, the name mismatch causes it to go to away
        self.assertEqual(len(scorers["home"]), 0)
        self.assertEqual(len(scorers["away"]), 1)


if __name__ == "__main__":
    unittest.main()
