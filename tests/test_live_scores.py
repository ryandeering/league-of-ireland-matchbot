"""Tests for live score formatting and match status display."""

import unittest

from models import Fixture, MatchStatus, Team, Venue
from common import (
    get_match_status_display,
    format_live_fixture,
    parse_match_datetime,
    get_fixture_dublin_date,
    filter_weekly_matches,
    apply_fallback_grounds,
)


def _make_fixture(**overrides):
    """Helper to create a Fixture with sensible defaults."""
    defaults = dict(
        id=1,
        date="2024-10-19T19:45:00+00:00",
        status=MatchStatus(short="NS", elapsed=None),
        venue=Venue(name="Richmond Park"),
        home=Team(id=1, name="St Patrick's Athl."),
        away=Team(id=2, name="Shelbourne"),
        home_goals=None,
        away_goals=None,
        league_id=126,
        round="Regular Season - 15",
        events=[],
    )
    defaults.update(overrides)
    return Fixture(**defaults)


class TestMatchStatusDisplay(unittest.TestCase):
    """Test match status display formatting."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_fixture = _make_fixture()

    def test_pre_match_not_started(self):
        """Test pre-match display (NS - not started)."""
        fixture = _make_fixture()
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "vs")
        self.assertEqual(status, "-")

    def test_pre_match_tbd(self):
        """Test TBD match status."""
        fixture = _make_fixture(status=MatchStatus(short="TBD", elapsed=None))
        score, _ = get_match_status_display(fixture)
        self.assertEqual(score, "vs")

    def test_first_half(self):
        """Test first half display (1H) - St Pats vs Shelbourne."""
        fixture = _make_fixture(
            status=MatchStatus(short="1H", elapsed=18),
            home_goals=1,
            away_goals=0,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "1-0")
        self.assertEqual(status, "18'")

    def test_half_time(self):
        """Test half time display (HT) - St Pats vs Shelbourne."""
        fixture = _make_fixture(
            status=MatchStatus(short="HT", elapsed=None),
            home_goals=1,
            away_goals=0,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "1-0")
        self.assertEqual(status, "HT")

    def test_second_half(self):
        """Test second half display (2H) - St Pats vs Shelbourne."""
        fixture = _make_fixture(
            status=MatchStatus(short="2H", elapsed=67),
            home_goals=2,
            away_goals=1,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-1")
        self.assertEqual(status, "67'")

    def test_extra_time(self):
        """Test extra time display (ET) - St Pats vs Shelbourne."""
        fixture = _make_fixture(
            status=MatchStatus(short="ET", elapsed=None),
            home_goals=2,
            away_goals=2,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-2")
        self.assertEqual(status, "ET")

    def test_penalties(self):
        """Test penalties display (P) - St Pats vs Shelbourne."""
        fixture = _make_fixture(
            status=MatchStatus(short="P", elapsed=None),
            home_goals=2,
            away_goals=2,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-2")
        self.assertEqual(status, "Pens")

    def test_full_time(self):
        """Test full time display (FT) - St Pats vs Shelbourne."""
        fixture = _make_fixture(
            status=MatchStatus(short="FT", elapsed=None),
            home_goals=2,
            away_goals=2,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-2")
        self.assertEqual(status, "FT")

    def test_after_extra_time(self):
        """Test after extra time display (AET) - St Pats vs Shelbourne."""
        fixture = _make_fixture(
            status=MatchStatus(short="AET", elapsed=None),
            home_goals=3,
            away_goals=2,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "3-2")
        self.assertEqual(status, "AET")

    def test_after_penalties(self):
        """Test after penalties display (PEN) - St Pats vs Shelbourne."""
        fixture = _make_fixture(
            status=MatchStatus(short="PEN", elapsed=None),
            home_goals=2,
            away_goals=2,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "2-2")
        self.assertEqual(status, "Pens")

    def test_unknown_status(self):
        """Test unknown status falls back gracefully."""
        fixture = _make_fixture(
            status=MatchStatus(short="UNKNOWN", elapsed=None),
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "vs")
        self.assertEqual(status, "UNKNOWN")

    def test_zero_score(self):
        """Test zero goals display - goalless match."""
        fixture = _make_fixture(
            status=MatchStatus(short="2H", elapsed=45),
            home_goals=0,
            away_goals=0,
        )
        score, _ = get_match_status_display(fixture)
        self.assertEqual(score, "0-0")


class TestFormatLiveFixture(unittest.TestCase):
    """Test live fixture formatting."""

    def setUp(self):
        """Set up test fixtures - St Patrick's Athletic vs Shelbourne."""
        self.fixture = _make_fixture(
            date="2025-10-20T18:45:00+00:00",
            status=MatchStatus(short="2H", elapsed=67),
            home_goals=2,
            away_goals=1,
        )

    def test_format_returns_list_with_seven_elements(self):
        """Test that formatted fixture has all required columns."""
        formatted = format_live_fixture(self.fixture)
        self.assertIsInstance(formatted, list)
        self.assertEqual(len(formatted), 7)  # Home, Score, Away, Venue, Status, Kickoff, Scorers

    def test_format_contains_team_names(self):
        """Test that team names are included."""
        formatted = format_live_fixture(self.fixture)
        self.assertEqual(formatted[0], "St. Patrick's Athletic")
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
        fixture = _make_fixture(
            date="2025-10-20T18:45:00+00:00",
            status=MatchStatus(short="2H", elapsed=67),
            home=Team(id=1, name="St Patrick's Athl."),
            home_goals=2,
            away_goals=1,
        )
        formatted = format_live_fixture(fixture)
        self.assertEqual(formatted[0], "St. Patrick's Athletic")


class TestMatchStatusEdgeCases(unittest.TestCase):
    """Test edge cases in match status handling."""

    def test_high_scoring_match(self):
        """Test high-scoring match display."""
        fixture = _make_fixture(
            status=MatchStatus(short="1H", elapsed=45),
            home=Team(id=1, name="Team A"),
            away=Team(id=2, name="Team B"),
            venue=Venue(name="Stadium"),
            home_goals=4,
            away_goals=3,
        )
        score, _ = get_match_status_display(fixture)
        self.assertEqual(score, "4-3")

    def test_late_goal_minute_90(self):
        """Test 90th minute display."""
        fixture = _make_fixture(
            status=MatchStatus(short="2H", elapsed=90),
            home=Team(id=1, name="Team A"),
            away=Team(id=2, name="Team B"),
            venue=Venue(name="Stadium"),
            home_goals=1,
            away_goals=1,
        )
        _, status = get_match_status_display(fixture)
        self.assertEqual(status, "90'")

    def test_injury_time_minute_95(self):
        """Test injury time display."""
        fixture = _make_fixture(
            status=MatchStatus(short="2H", elapsed=95),
            home=Team(id=1, name="Team A"),
            away=Team(id=2, name="Team B"),
            venue=Venue(name="Stadium"),
            home_goals=0,
            away_goals=0,
        )
        _, status = get_match_status_display(fixture)
        self.assertEqual(status, "95'")


class TestNullScoreHandling(unittest.TestCase):
    """Regression tests: null scores must not render as 0-0."""

    def test_null_scores_started_match_shows_vs(self):
        """Started match with null scores should show 'vs', not '0-0'."""
        fixture = _make_fixture(
            date="2025-07-18T19:45:00+00:00",
            status=MatchStatus(short="2H", elapsed=67),
            venue=Venue(name="Stadium"),
            home=Team(id=1, name="Team A"),
            away=Team(id=2, name="Team B"),
            home_goals=None,
            away_goals=None,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "vs")
        self.assertNotEqual(score, "0-0")
        self.assertEqual(status, "67'")

    def test_null_scores_finished_match_shows_vs(self):
        """Finished match with null scores should show 'vs', not '0-0'."""
        fixture = _make_fixture(
            date="2025-07-18T19:45:00+00:00",
            status=MatchStatus(short="FT", elapsed=90),
            venue=Venue(name="Stadium"),
            home=Team(id=1, name="Team A"),
            away=Team(id=2, name="Team B"),
            home_goals=None,
            away_goals=None,
        )
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "vs")
        self.assertEqual(status, "FT")

    def test_null_scores_half_time_shows_vs(self):
        """HT match with null scores should show 'vs', not '0-0'."""
        fixture = _make_fixture(
            date="2025-07-18T19:45:00+00:00",
            status=MatchStatus(short="HT", elapsed=None),
            venue=Venue(name="Stadium"),
            home=Team(id=1, name="Team A"),
            away=Team(id=2, name="Team B"),
            home_goals=None,
            away_goals=None,
        )
        score, _ = get_match_status_display(fixture)
        self.assertEqual(score, "vs")

    def test_zero_zero_score_still_renders(self):
        """Actual 0-0 score (not null) should still display correctly."""
        fixture = _make_fixture(
            date="2025-07-18T19:45:00+00:00",
            status=MatchStatus(short="HT", elapsed=None),
            venue=Venue(name="Stadium"),
            home=Team(id=1, name="Team A"),
            away=Team(id=2, name="Team B"),
            home_goals=0,
            away_goals=0,
        )
        score, _ = get_match_status_display(fixture)
        self.assertEqual(score, "0-0")


class TestCancelledMatchDisplay(unittest.TestCase):
    """Regression tests: cancelled matches must not show a score."""

    def _make_cancelled_fixture(self, home_score=None, away_score=None):
        return _make_fixture(
            date="2026-02-13T19:45:00+00:00",
            status=MatchStatus(short="CANC", elapsed=None),
            venue=Venue(name="Richmond Park"),
            home=Team(id=1, name="St Patrick's Athl."),
            away=Team(id=2, name="Galway United FC"),
            home_goals=home_score,
            away_goals=away_score,
        )

    def test_cancelled_with_null_scores_shows_dash(self):
        """Cancelled match with null scores should show '-'."""
        fixture = self._make_cancelled_fixture(None, None)
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "-")
        self.assertEqual(status, "Cancelled")

    def test_cancelled_with_zero_scores_shows_dash_not_0_0(self):
        """Cancelled match with 0-0 from API should show '-', not '0-0'."""
        fixture = self._make_cancelled_fixture(0, 0)
        score, status = get_match_status_display(fixture)
        self.assertEqual(score, "-")
        self.assertNotEqual(score, "0-0")
        self.assertEqual(status, "Cancelled")

    def test_cancelled_format_live_fixture(self):
        """Cancelled match should show '-' and 'Cancelled' in formatted output."""
        fixture = self._make_cancelled_fixture(0, 0)
        formatted = format_live_fixture(fixture)
        self.assertEqual(formatted[1], "-")        # Score column
        self.assertEqual(formatted[4], "Cancelled") # Status column


class TestFallbackGrounds(unittest.TestCase):
    """Regression tests: missing venues must be filled from league_grounds."""

    def test_tbd_venue_replaced_by_fallback(self):
        """Fixture with TBD venue should get home team's ground."""
        fixtures = [_make_fixture(
            venue=Venue(name="TBD"),
            home=Team(id=1, name="Derry City"),
        )]
        result = apply_fallback_grounds(fixtures)
        self.assertEqual(result[0].venue.name, "Brandywell Stadium")

    def test_empty_venue_replaced_by_fallback(self):
        """Fixture with empty venue should get home team's ground."""
        fixtures = [_make_fixture(
            venue=Venue(name=""),
            home=Team(id=1, name="Shamrock Rovers"),
        )]
        result = apply_fallback_grounds(fixtures)
        self.assertEqual(result[0].venue.name, "Tallaght Stadium")

    def test_api_venue_not_overwritten(self):
        """Fixture with a real venue from the API should not be overwritten."""
        fixtures = [_make_fixture(
            venue=Venue(name="Eamonn Deacy Park"),
            home=Team(id=1, name="Galway United"),
        )]
        result = apply_fallback_grounds(fixtures)
        self.assertEqual(result[0].venue.name, "Eamonn Deacy Park")

    def test_normalised_name_lookup(self):
        """Abbreviated API team names should still resolve via normalisation."""
        fixtures = [_make_fixture(
            venue=Venue(name="TBD"),
            home=Team(id=1, name="St Patrick's Athl."),
        )]
        result = apply_fallback_grounds(fixtures)
        self.assertEqual(result[0].venue.name, "Richmond Park")


class TestDSTTransitions(unittest.TestCase):
    """Test Dublin timezone / DST handling in parse_match_datetime."""

    def test_summer_late_match_crosses_dublin_midnight(self):
        """23:30 UTC during IST (summer) = 00:30 next day in Dublin."""
        result = parse_match_datetime("2025-07-18T23:30:00Z")
        self.assertEqual(result.date().isoformat(), "2025-07-19")
        self.assertEqual(result.strftime("%H:%M"), "00:30")

    def test_winter_late_match_same_day(self):
        """23:30 UTC during GMT (winter) = 23:30 same day in Dublin."""
        result = parse_match_datetime("2025-12-18T23:30:00Z")
        self.assertEqual(result.date().isoformat(), "2025-12-18")
        self.assertEqual(result.strftime("%H:%M"), "23:30")

    def test_summer_normal_kickoff(self):
        """19:45 UTC during IST = 20:45 same day in Dublin."""
        result = parse_match_datetime("2025-07-18T19:45:00Z")
        self.assertEqual(result.date().isoformat(), "2025-07-18")
        self.assertEqual(result.strftime("%H:%M"), "20:45")

    def test_winter_normal_kickoff(self):
        """19:45 UTC during GMT = 19:45 same day in Dublin."""
        result = parse_match_datetime("2026-02-06T19:45:00Z")
        self.assertEqual(result.date().isoformat(), "2026-02-06")
        self.assertEqual(result.strftime("%H:%M"), "19:45")


class TestDublinDateGrouping(unittest.TestCase):
    """Regression tests: date grouping must use Dublin-local date."""

    def test_summer_late_utc_grouped_under_dublin_date(self):
        """A 23:30 UTC match during IST should be grouped under the Dublin date."""
        fixture = _make_fixture(date="2025-07-18T23:30:00Z")
        dublin_date = get_fixture_dublin_date(fixture)
        utc_date = fixture.date[:10]

        self.assertEqual(dublin_date, "2025-07-19")
        self.assertEqual(utc_date, "2025-07-18")
        self.assertNotEqual(dublin_date, utc_date)

    def test_winter_normal_match_same_date(self):
        """Normal winter kickoff should be same date in UTC and Dublin."""
        fixture = _make_fixture(date="2026-02-06T19:45:00Z")
        dublin_date = get_fixture_dublin_date(fixture)
        utc_date = fixture.date[:10]

        self.assertEqual(dublin_date, "2026-02-06")
        self.assertEqual(dublin_date, utc_date)

    def test_empty_date_returns_empty_string(self):
        """Fixture with no date should return empty string."""
        fixture = _make_fixture(date="")
        self.assertEqual(get_fixture_dublin_date(fixture), "")

        fixture_no_date = _make_fixture(date="")
        self.assertEqual(get_fixture_dublin_date(fixture_no_date), "")


class TestWeeklyFiltering(unittest.TestCase):
    """Regression tests for weekly fixture filtering window."""

    def test_excludes_same_weekday_next_week(self):
        """Friday run should not include fixtures on next Friday."""
        run_date = parse_match_datetime("2026-02-13T12:00:00Z").date()
        fixtures = [
            _make_fixture(date="2026-02-13T19:45:00Z"),
            _make_fixture(date="2026-02-19T19:45:00Z"),
            _make_fixture(date="2026-02-20T19:45:00Z"),
        ]

        weekly = filter_weekly_matches(fixtures, run_date)
        dates = sorted({parse_match_datetime(m.date).date().isoformat()
                        for m in weekly})

        self.assertEqual(dates, ["2026-02-13", "2026-02-19"])

    def test_includes_today_and_next_six_days(self):
        """Window includes today and day+6, but excludes day+7."""
        run_date = parse_match_datetime("2026-02-13T12:00:00Z").date()
        fixtures = [
            _make_fixture(date="2026-02-13T10:00:00Z"),  # day 0
            _make_fixture(date="2026-02-19T22:00:00Z"),  # day 6
            _make_fixture(date="2026-02-20T10:00:00Z"),  # day 7
        ]

        weekly = filter_weekly_matches(fixtures, run_date)
        included_dates = {
            parse_match_datetime(m.date).date().isoformat()
            for m in weekly
        }

        self.assertIn("2026-02-13", included_dates)
        self.assertIn("2026-02-19", included_dates)
        self.assertNotIn("2026-02-20", included_dates)


if __name__ == "__main__":
    unittest.main()
