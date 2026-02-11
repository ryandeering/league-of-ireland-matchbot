"""Tests for FAI Cup fixture and round helpers."""

import unittest
from unittest.mock import patch

from fai_cup import (
    get_current_round,
    get_matches_for_cup,
    get_matches_for_round,
    get_round_display_name,
)


class TestFAICupFixtures(unittest.TestCase):
    """Test FAI Cup fixture processing."""

    @patch("fai_cup.client.get_league_matches")
    def test_get_matches_for_cup_deduplicates_fixtures(self, mock_get_league_matches):
        """Test fixtures/results are deduplicated with results data taking priority."""
        mock_get_league_matches.side_effect = [
            {
                "fixtures": {
                    "allMatches": [
                        {
                            "id": "100",
                            "round": "Quarter-finals",
                            "home": {"id": "1", "name": "Team A"},
                            "away": {"id": "2", "name": "Team B"},
                            "status": {
                                "utcTime": "2025-08-01T18:45:00Z",
                                "started": True,
                                "finished": False,
                                "cancelled": False,
                                "score": {"home": 1, "away": 0},
                                "liveTime": {"short": "88", "maxTime": 90},
                            },
                        }
                    ]
                }
            },
            {
                "fixtures": {
                    "allMatches": [
                        {
                            "id": "100",
                            "round": "Quarter-finals",
                            "home": {"id": "1", "name": "Team A"},
                            "away": {"id": "2", "name": "Team B"},
                            "status": {
                                "utcTime": "2025-08-01T18:45:00Z",
                                "started": True,
                                "finished": True,
                                "cancelled": False,
                                "score": {"home": 2, "away": 1},
                                "liveTime": {"short": "FT", "maxTime": 90},
                            },
                        }
                    ]
                }
            },
        ]

        matches = get_matches_for_cup()

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["fixture"]["id"], 100)
        self.assertEqual(matches[0]["fixture"]["status"]["short"], "FT")
        self.assertEqual(matches[0]["goals"]["home"], 2)
        self.assertEqual(matches[0]["goals"]["away"], 1)


class TestFAICupRounds(unittest.TestCase):
    """Test current round detection logic."""

    def test_get_current_round_fallback_uses_latest_match_date(self):
        """Test fallback round uses the latest match by date, not list order."""
        matches = [
            {
                "fixture": {"date": "2025-10-01T19:45:00+00:00"},
                "league": {"round": "FAI Cup - Final"},
            },
            {
                "fixture": {"date": "2025-08-15T19:45:00+00:00"},
                "league": {"round": "FAI Cup - Semi-finals"},
            },
        ]

        round_name = get_current_round(matches)
        self.assertEqual(round_name, "Final")


class TestFAICupRoundFiltering(unittest.TestCase):
    """Test round filtering uses exact match, not substring."""

    def test_round_1_does_not_match_round_10(self):
        """Regression: round '1' must not match round '10' or '11'.

        Previous code used 'in' for substring matching, so 'Round 1'
        would match 'Round 10', 'Round 11', etc.
        """
        matches = [
            {
                "fixture": {"date": "2025-06-01T19:45:00+00:00"},
                "league": {"round": "Regular Season - 1"},
            },
            {
                "fixture": {"date": "2025-07-01T19:45:00+00:00"},
                "league": {"round": "Regular Season - 10"},
            },
            {
                "fixture": {"date": "2025-07-15T19:45:00+00:00"},
                "league": {"round": "Regular Season - 11"},
            },
        ]

        round_1 = get_matches_for_round(matches, "1")
        self.assertEqual(len(round_1), 1)
        self.assertEqual(round_1[0]["league"]["round"], "Regular Season - 1")

    def test_round_2_does_not_match_round_12_or_21(self):
        """Test round '2' doesn't match '12', '20', '21', '22'."""
        matches = [
            {"fixture": {"date": "2025-06-01T19:45:00+00:00"},
             "league": {"round": "Regular Season - 2"}},
            {"fixture": {"date": "2025-07-01T19:45:00+00:00"},
             "league": {"round": "Regular Season - 12"}},
            {"fixture": {"date": "2025-08-01T19:45:00+00:00"},
             "league": {"round": "Regular Season - 20"}},
            {"fixture": {"date": "2025-08-15T19:45:00+00:00"},
             "league": {"round": "Regular Season - 21"}},
            {"fixture": {"date": "2025-09-01T19:45:00+00:00"},
             "league": {"round": "Regular Season - 22"}},
        ]

        round_2 = get_matches_for_round(matches, "2")
        self.assertEqual(len(round_2), 1)
        self.assertEqual(round_2[0]["league"]["round"], "Regular Season - 2")

    def test_named_round_exact_match(self):
        """Test named rounds like 'Semi-finals' use exact match."""
        matches = [
            {"fixture": {"date": "2025-08-01T19:45:00+00:00"},
             "league": {"round": "FAI Cup - Semi-finals"}},
            {"fixture": {"date": "2025-09-01T19:45:00+00:00"},
             "league": {"round": "FAI Cup - Final"}},
        ]

        semis = get_matches_for_round(matches, "Semi-finals")
        self.assertEqual(len(semis), 1)
        self.assertEqual(semis[0]["league"]["round"], "FAI Cup - Semi-finals")

        final = get_matches_for_round(matches, "Final")
        self.assertEqual(len(final), 1)
        self.assertEqual(final[0]["league"]["round"], "FAI Cup - Final")

    def test_empty_round_returns_empty(self):
        """Test that empty current_round returns no matches."""
        matches = [
            {"fixture": {"date": "2025-08-01T19:45:00+00:00"},
             "league": {"round": "FAI Cup - Semi-finals"}},
        ]

        result = get_matches_for_round(matches, "")
        self.assertEqual(result, [])


class TestFAICupRoundDisplay(unittest.TestCase):
    """Test display-friendly labels for API round keys."""

    def test_fraction_rounds_map_to_knockout_labels(self):
        """FotMob FAI Cup keys should map to readable knockout names."""
        self.assertEqual(get_round_display_name("1/4"), "Quarter-finals")
        self.assertEqual(get_round_display_name("1/2"), "Semi-finals")
        self.assertEqual(get_round_display_name("final"), "Final")

    def test_mapping_is_case_insensitive(self):
        """Upper/lowercase API values should still map correctly."""
        self.assertEqual(get_round_display_name("FINAL"), "Final")
        self.assertEqual(get_round_display_name("1/4"), "Quarter-finals")

    def test_unknown_round_falls_back_to_extracted_name(self):
        """Unexpected round strings should still return usable text."""
        self.assertEqual(
            get_round_display_name("FAI Cup - Preliminary Round"),
            "Preliminary Round",
        )


if __name__ == "__main__":
    unittest.main()
