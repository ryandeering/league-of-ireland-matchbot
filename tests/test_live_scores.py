"""Tests for live score formatting and match status display."""

import unittest
from common import (
    get_match_status_display,
    format_live_fixture,
)


class TestMatchStatusDisplay(unittest.TestCase):
    """Test match status display formatting."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_fixture = {
            "fixture": {
                "status": {
                    "short": "NS",
                    "elapsed": None,
                },
                "date": "2024-10-19T19:45:00+00:00",
                "venue": {"name": "Richmond Park"},
            },
            "goals": {
                "home": None,
                "away": None,
            },
            "teams": {
                "home": {"name": "St Patrick's Athl.", "id": 1},
                "away": {"name": "Shelbourne", "id": 2},
            },
        }

    def test_pre_match_not_started(self):
        """Test pre-match display (NS - not started)."""
        fixture = self.base_fixture.copy()
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "vs")
        self.assertTrue(len(status) > 0)  # Status should be non-empty

    def test_pre_match_tbd(self):
        """Test TBD match status."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "TBD"
        score, _ = get_match_status_display(fixture)
        self.assertEqual(score, "vs")

    def test_first_half(self):
        """Test first half display (1H) - St Pats vs Shelbourne."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "1H"
        fixture["fixture"]["status"]["elapsed"] = 18
        fixture["goals"]["home"] = 1
        fixture["goals"]["away"] = 0
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "1-0")
        self.assertEqual(status, "18'")

    def test_half_time(self):
        """Test half time display (HT) - St Pats vs Shelbourne."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "HT"
        fixture["goals"]["home"] = 1
        fixture["goals"]["away"] = 0
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "1-0")
        self.assertEqual(status, "HT")

    def test_second_half(self):
        """Test second half display (2H) - St Pats vs Shelbourne."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "2H"
        fixture["fixture"]["status"]["elapsed"] = 67
        fixture["goals"]["home"] = 2
        fixture["goals"]["away"] = 1
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-1")
        self.assertEqual(status, "67'")

    def test_extra_time(self):
        """Test extra time display (ET) - St Pats vs Shelbourne."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "ET"
        fixture["goals"]["home"] = 2
        fixture["goals"]["away"] = 2
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-2")
        self.assertEqual(status, "ET")

    def test_penalties(self):
        """Test penalties display (P) - St Pats vs Shelbourne."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "P"
        fixture["goals"]["home"] = 2
        fixture["goals"]["away"] = 2
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-2")
        self.assertEqual(status, "Pens")

    def test_full_time(self):
        """Test full time display (FT) - St Pats vs Shelbourne."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "FT"
        fixture["goals"]["home"] = 2
        fixture["goals"]["away"] = 2
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-2")
        self.assertEqual(status, "FT")

    def test_after_extra_time(self):
        """Test after extra time display (AET) - St Pats vs Shelbourne."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "AET"
        fixture["goals"]["home"] = 3
        fixture["goals"]["away"] = 2
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "3-2")
        self.assertEqual(status, "AET")

    def test_after_penalties(self):
        """Test after penalties display (PEN) - St Pats vs Shelbourne."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "PEN"
        fixture["goals"]["home"] = 2
        fixture["goals"]["away"] = 2
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-2")
        self.assertEqual(status, "Pens")

    def test_unknown_status(self):
        """Test unknown status falls back gracefully."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "UNKNOWN"
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "vs")
        self.assertEqual(status, "UNKNOWN")

    def test_zero_score(self):
        """Test zero goals display - goalless match."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "2H"
        fixture["fixture"]["status"]["elapsed"] = 45
        fixture["goals"]["home"] = 0
        fixture["goals"]["away"] = 0
        score, _ = get_match_status_display(fixture)
        self.assertEqual(score, "0-0")


class TestFormatLiveFixture(unittest.TestCase):
    """Test live fixture formatting."""

    def setUp(self):
        """Set up test fixtures - St Patrick's Athletic vs Shelbourne."""
        self.fixture = {
            "fixture": {
                "status": {
                    "short": "2H",
                    "elapsed": 67,
                },
                "date": "2025-10-20T18:45:00+00:00",
                "venue": {"name": "Richmond Park"},
            },
            "goals": {
                "home": 2,
                "away": 1,
            },
            "teams": {
                "home": {"name": "St Patrick's Athl."},
                "away": {"name": "Shelbourne"},
            },
        }

    def test_format_returns_list_with_seven_elements(self):
        """Test that formatted fixture has all required columns."""
        formatted = format_live_fixture(self.fixture)
        self.assertIsInstance(formatted, list)
        self.assertEqual(len(formatted), 7)  # Home, Score, Away, Venue, Status, Kickoff, Scorers

    def test_format_contains_team_names(self):
        """Test that team names are included."""
        formatted = format_live_fixture(self.fixture)
        self.assertEqual(formatted[0], "St Patrick's Athletic")
        self.assertEqual(formatted[2], "Shelbourne")

    def test_format_contains_score(self):
        """Test that score is included."""
        formatted = format_live_fixture(self.fixture)
        self.assertEqual(formatted[1], "2-1")

    def test_format_contains_venue(self):
        """Test that venue is included."""
        formatted = format_live_fixture(self.fixture)
        self.assertEqual(formatted[3], "Richmond Park")

    def test_format_contains_status(self):
        """Test that status is included."""
        formatted = format_live_fixture(self.fixture)
        self.assertEqual(formatted[4], "67'")

    def test_format_with_shortened_team_names(self):
        """Test that team name normalization works."""
        self.fixture["teams"]["home"]["name"] = "St Patrick's Athl."
        formatted = format_live_fixture(self.fixture)
        self.assertEqual(formatted[0], "St Patrick's Athletic")


class TestMatchStatusEdgeCases(unittest.TestCase):
    """Test edge cases in match status handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_fixture = {
            "fixture": {
                "status": {
                    "short": "1H",
                    "elapsed": 45,
                },
                "date": "2024-10-19T19:45:00+00:00",
                "venue": {"name": "Stadium"},
            },
            "goals": {
                "home": 0,
                "away": 0,
            },
            "teams": {
                "home": {"name": "Team A", "id": 1},
                "away": {"name": "Team B", "id": 2},
            },
        }

    def test_high_scoring_match(self):
        """Test high-scoring match display."""
        fixture = self.base_fixture.copy()
        fixture["goals"]["home"] = 4
        fixture["goals"]["away"] = 3
        score, _ = get_match_status_display(fixture)
        self.assertEqual(score, "4-3")

    def test_late_goal_minute_90(self):
        """Test 90th minute display."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "2H"
        fixture["fixture"]["status"]["elapsed"] = 90
        fixture["goals"]["home"] = 1
        fixture["goals"]["away"] = 1
        _, status = get_match_status_display(fixture)
        self.assertEqual(status, "90'")

    def test_injury_time_minute_95(self):
        """Test injury time display."""
        fixture = self.base_fixture.copy()
        fixture["fixture"]["status"]["short"] = "2H"
        fixture["fixture"]["status"]["elapsed"] = 95
        _, status = get_match_status_display(fixture)
        self.assertEqual(status, "95'")


if __name__ == "__main__":
    unittest.main()
