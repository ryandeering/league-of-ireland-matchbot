"""Tests for rate limiting and retry mechanism."""

import json
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import requests

from common import extract_scorers, format_scorers_inline
from rate_limiter import APIClient, APIRateLimiter


class TestAPIRateLimiter(unittest.TestCase):
    """Tests for APIRateLimiter class."""

    def setUp(self):
        """Set up test fixtures."""
        # Clean up stats file before each test
        if os.path.exists("api_stats.json"):
            os.remove("api_stats.json")
        self.rate_limiter = APIRateLimiter(
            daily_limit=10,
            per_minute_limit=10,
            max_retries=3,
            circuit_breaker_threshold=3,
            circuit_breaker_recovery_time=60,
        )

    def tearDown(self):
        """Clean up after tests."""
        if os.path.exists("api_stats.json"):
            os.remove("api_stats.json")

    def test_initialization(self):
        """Test APIRateLimiter initializes with correct defaults."""
        limiter = APIRateLimiter()
        self.assertEqual(limiter.daily_limit, 100)
        self.assertEqual(limiter.per_minute_limit, 10)
        self.assertEqual(limiter.max_retries, 3)
        self.assertEqual(limiter.circuit_breaker_threshold, 5)

    def test_check_daily_limit_initially_true(self):
        """Test daily limit check returns True initially."""
        self.assertTrue(self.rate_limiter.check_daily_limit())

    def test_check_daily_limit_exceeded(self):
        """Test daily limit check returns False when exceeded."""
        self.rate_limiter.daily_calls = 10
        self.assertFalse(self.rate_limiter.check_daily_limit())

    def test_check_per_minute_limit_initially_true(self):
        """Test per-minute limit check returns True initially."""
        self.assertTrue(self.rate_limiter.check_per_minute_limit())

    def test_check_per_minute_limit_exceeded(self):
        """Test per-minute limit check returns False when exceeded."""
        # per_minute_limit is 10, so add 10 timestamps to exceed it
        now = datetime.now()
        self.rate_limiter.minute_calls = [now for _ in range(10)]
        self.assertFalse(self.rate_limiter.check_per_minute_limit())

    def test_check_per_minute_limit_clears_old_calls(self):
        """Test per-minute limit removes calls older than 1 minute."""
        old_time = datetime.now() - timedelta(seconds=61)
        new_time = datetime.now()

        self.rate_limiter.minute_calls = [old_time, new_time]
        self.rate_limiter.check_per_minute_limit()

        # Old call should be removed
        self.assertEqual(len(self.rate_limiter.minute_calls), 1)
        self.assertEqual(self.rate_limiter.minute_calls[0], new_time)

    def test_can_make_call_when_all_limits_ok(self):
        """Test can_make_call returns True when all limits are OK."""
        self.assertTrue(self.rate_limiter.can_make_call())

    def test_can_make_call_when_daily_limit_exceeded(self):
        """Test can_make_call returns False when daily limit exceeded."""
        self.rate_limiter.daily_calls = 10
        self.assertFalse(self.rate_limiter.can_make_call())

    def test_can_make_call_when_per_minute_limit_exceeded(self):
        """Test can_make_call returns False when per-minute limit exceeded."""
        # per_minute_limit is 10, so add 10 timestamps to exceed it
        now = datetime.now()
        self.rate_limiter.minute_calls = [now for _ in range(10)]
        self.assertFalse(self.rate_limiter.can_make_call())

    def test_can_make_call_when_circuit_open(self):
        """Test can_make_call returns False when circuit is open."""
        self.rate_limiter.circuit_open_time = datetime.now()
        self.assertFalse(self.rate_limiter.can_make_call())

    def test_record_call_increments_daily(self):
        """Test record_call increments daily counter."""
        self.assertEqual(self.rate_limiter.daily_calls, 0)
        self.rate_limiter.record_call()
        self.assertEqual(self.rate_limiter.daily_calls, 1)

    def test_record_call_adds_minute_timestamp(self):
        """Test record_call adds current time to minute calls."""
        self.assertEqual(len(self.rate_limiter.minute_calls), 0)
        self.rate_limiter.record_call()
        self.assertEqual(len(self.rate_limiter.minute_calls), 1)

    def test_record_call_resets_consecutive_failures(self):
        """Test record_call resets consecutive failures counter."""
        self.rate_limiter.consecutive_failures = 3
        self.rate_limiter.record_call()
        self.assertEqual(self.rate_limiter.consecutive_failures, 0)

    def test_record_failure_increments_counter(self):
        """Test record_failure increments consecutive failures."""
        self.assertEqual(self.rate_limiter.consecutive_failures, 0)
        self.rate_limiter.record_failure()
        self.assertEqual(self.rate_limiter.consecutive_failures, 1)

    def test_record_failure_opens_circuit_at_threshold(self):
        """Test record_failure opens circuit at threshold."""
        self.rate_limiter.consecutive_failures = 2
        self.rate_limiter.record_failure()
        self.assertIsNotNone(self.rate_limiter.circuit_open_time)

    def test_is_circuit_open_returns_false_initially(self):
        """Test is_circuit_open returns False initially."""
        self.assertFalse(self.rate_limiter.is_circuit_open())

    def test_is_circuit_open_returns_true_when_open(self):
        """Test is_circuit_open returns True when circuit is open."""
        self.rate_limiter.circuit_open_time = datetime.now()
        self.assertTrue(self.rate_limiter.is_circuit_open())

    def test_is_circuit_open_auto_recovers_after_timeout(self):
        """Test circuit breaker auto-recovers after timeout."""
        old_time = datetime.now() - timedelta(seconds=61)
        self.rate_limiter.circuit_open_time = old_time
        self.assertFalse(self.rate_limiter.is_circuit_open())

    def test_get_polling_interval_5_min_when_plenty_budget(self):
        """Test polling interval is 5 min with plenty of budget."""
        # Test with 100 daily limit: remaining > 36 calls = 5 min
        limiter = APIRateLimiter(daily_limit=100)
        limiter.daily_calls = 50
        interval = limiter.get_polling_interval()
        self.assertEqual(interval, 300)

    def test_get_polling_interval_10_min_when_medium_budget(self):
        """Test polling interval is 10 min with medium budget."""
        # Test with 100 daily limit: 18 < remaining <= 36 = 10 min
        limiter = APIRateLimiter(daily_limit=100)
        limiter.daily_calls = 70
        interval = limiter.get_polling_interval()
        self.assertEqual(interval, 600)

    def test_get_polling_interval_15_min_when_low_budget(self):
        """Test polling interval is 15 min with low budget."""
        # Test with 100 daily limit: remaining <= 18 = 15 min
        limiter = APIRateLimiter(daily_limit=100)
        limiter.daily_calls = 85
        interval = limiter.get_polling_interval()
        self.assertEqual(interval, 900)

    def test_get_backoff_time_exponential(self):
        """Test get_backoff_time uses exponential backoff."""
        # Exponential: 2^(n-1)
        self.assertEqual(self.rate_limiter.get_backoff_time(1), 1)
        self.assertEqual(self.rate_limiter.get_backoff_time(2), 2)
        self.assertEqual(self.rate_limiter.get_backoff_time(3), 4)
        self.assertEqual(self.rate_limiter.get_backoff_time(4), 8)

    def test_get_stats_returns_dict(self):
        """Test get_stats returns dictionary with all info."""
        stats = self.rate_limiter.get_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn("daily_calls", stats)
        self.assertIn("daily_limit", stats)
        self.assertIn("remaining_daily", stats)
        self.assertIn("per_minute_calls", stats)
        self.assertIn("circuit_open", stats)
        self.assertIn("polling_interval", stats)

    def test_stats_file_persistence(self):
        """Test daily stats are persisted to file."""
        # record_call internally calls _save_daily_stats()
        self.rate_limiter.record_call()

        self.assertTrue(os.path.exists("api_stats.json"))

    def test_stats_file_loading(self):
        """Test daily stats are loaded from file."""
        # Create stats file
        stats = {
            "daily_calls": 7,
            "reset_time": datetime.now().isoformat(),
            "timestamp": datetime.now().isoformat(),
        }
        with open("api_stats.json", "w", encoding="utf-8") as f:
            json.dump(stats, f)

        # Create new limiter and check it loads stats
        limiter = APIRateLimiter()
        self.assertEqual(limiter.daily_calls, 7)


class TestAPIClient(unittest.TestCase):
    """Tests for APIClient class."""

    def setUp(self):
        """Set up test fixtures."""
        if os.path.exists("api_stats.json"):
            os.remove("api_stats.json")
        self.rate_limiter = APIRateLimiter(daily_limit=10, per_minute_limit=10)
        self.api_client = APIClient(
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer token"},
            rate_limiter=self.rate_limiter,
        )

    def tearDown(self):
        """Clean up after tests."""
        if os.path.exists("api_stats.json"):
            os.remove("api_stats.json")

    def test_api_client_initialization(self):
        """Test APIClient initializes correctly."""
        self.assertEqual(self.api_client.base_url, "https://api.example.com")
        self.assertEqual(
            self.api_client.headers,
            {"Authorization": "Bearer token"},
        )
        self.assertIsNotNone(self.api_client.rate_limiter)

    @patch("rate_limiter.requests.get")
    def test_call_with_retry_success_on_first_attempt(self, mock_get):
        """Test call_with_retry succeeds on first attempt."""
        mock_response = Mock()
        mock_response.json.return_value = {"response": [{"id": 1}]}
        mock_get.return_value = mock_response

        result = self.api_client.call_with_retry(
            "/fixtures", params={"live": "357"})

        self.assertEqual(result, {"response": [{"id": 1}]})
        self.assertEqual(self.rate_limiter.daily_calls, 1)
        mock_get.assert_called_once()

    @patch("rate_limiter.requests.get")
    def test_call_with_retry_retries_on_timeout(self, mock_get):
        """Test call_with_retry retries on timeout."""
        mock_get.side_effect = [
            requests.exceptions.Timeout("Connection timeout"),
            requests.exceptions.Timeout("Connection timeout"),
            Mock(json=lambda: {"response": [{"id": 1}]}),
        ]

        result = self.api_client.call_with_retry(
            "/fixtures", params={"live": "357"}, timeout=5
        )

        self.assertEqual(result, {"response": [{"id": 1}]})
        self.assertEqual(mock_get.call_count, 3)

    @patch("rate_limiter.requests.get")
    @patch("rate_limiter.time.sleep")
    def test_call_with_retry_uses_exponential_backoff(
            self, mock_sleep, mock_get):
        """Test call_with_retry uses exponential backoff."""
        mock_get.side_effect = [
            requests.exceptions.Timeout("Timeout"),
            requests.exceptions.Timeout("Timeout"),
            Mock(json=lambda: {"response": []}),
        ]

        self.api_client.call_with_retry("/fixtures", params={})

        # Should sleep with exponential backoff: 1s, then 2s
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch("rate_limiter.requests.get")
    def test_call_with_retry_fails_after_max_retries(self, mock_get):
        """Test call_with_retry raises after max retries."""
        mock_get.side_effect = requests.exceptions.Timeout("Timeout")

        with self.assertRaises(requests.exceptions.Timeout):
            self.api_client.call_with_retry("/fixtures", params={})

        # Should attempt max_retries times (default 3)
        self.assertEqual(mock_get.call_count, 3)

    @patch("rate_limiter.requests.get")
    def test_call_with_retry_raises_on_400_error(self, mock_get):
        """Test call_with_retry raises immediately on 400 error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError(
                response=Mock(status_code=400)
            )
        )
        mock_response.status_code = 400
        mock_get.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            self.api_client.call_with_retry(
                "/fixtures", params={})

        # Should not retry on 4xx errors
        self.assertEqual(mock_get.call_count, 1)

    @patch("rate_limiter.requests.get")
    def test_call_with_retry_retries_on_429_error(self, mock_get):
        """Test call_with_retry retries on 429 (rate limit) error."""
        error_response = Mock(status_code=429)
        mock_get.side_effect = [
            Mock(
                raise_for_status=Mock(
                    side_effect=requests.exceptions.HTTPError(
                        response=error_response
                    )
                )
            ),
            Mock(json=lambda: {"response": []}),
        ]

        result = self.api_client.call_with_retry("/fixtures", params={})

        self.assertEqual(result, {"response": []})
        self.assertEqual(mock_get.call_count, 2)

    def test_call_with_retry_raises_when_circuit_open(self):
        """Test call_with_retry raises when circuit breaker is open."""
        self.rate_limiter.circuit_open_time = datetime.now()

        with self.assertRaises(requests.exceptions.ConnectionError):
            self.api_client.call_with_retry("/fixtures", params={})

    def test_call_with_retry_raises_when_daily_limit_exceeded(self):
        """Test call_with_retry raises when daily limit exceeded."""
        self.rate_limiter.daily_calls = 10

        with self.assertRaises(requests.exceptions.RequestException):
            self.api_client.call_with_retry("/fixtures", params={})

    def test_call_with_retry_raises_when_per_minute_limit_exceeded(self):
        """Test call_with_retry raises when per-minute limit exceeded."""
        self.rate_limiter.minute_calls = [datetime.now(), datetime.now()]

        with self.assertRaises(requests.exceptions.RequestException):
            self.api_client.call_with_retry("/fixtures", params={})

    @patch("rate_limiter.requests.get")
    def test_call_with_retry_records_call_on_success(self, mock_get):
        """Test call_with_retry records successful call."""
        mock_response = Mock()
        mock_response.json.return_value = {"response": []}
        mock_get.return_value = mock_response

        self.api_client.call_with_retry("/fixtures", params={})

        stats = self.rate_limiter.get_stats()
        self.assertEqual(stats["daily_calls"], 1)
        self.assertEqual(stats["consecutive_failures"], 0)

    @patch("rate_limiter.requests.get")
    def test_call_with_retry_records_failure_on_final_error(self, mock_get):
        """Test call_with_retry records failure after all retries fail."""
        mock_get.side_effect = requests.exceptions.Timeout("Timeout")

        with self.assertRaises(requests.exceptions.Timeout):
            self.api_client.call_with_retry("/fixtures", params={})

        self.assertGreater(self.rate_limiter.consecutive_failures, 0)


class TestScorerExtraction(unittest.TestCase):
    """Tests for scorer extraction functions."""

    def test_extract_scorers_from_fixture_with_events(self):
        """Test extract_scorers with fixture containing goal events."""
        fixture = {
            "teams": {
                "home": {"name": "St Patrick's Athl."},
                "away": {"name": "Shelbourne"},
            },
            "events": [
                {
                    "type": "Goal",
                    "team": {"name": "St Patrick's Athl."},
                    "player": {"name": "John Smith"},
                    "time": {"elapsed": 25},
                    "detail": None,
                },
                {
                    "type": "Goal",
                    "team": {"name": "Shelbourne"},
                    "player": {"name": "Jane Doe"},
                    "time": {"elapsed": 45},
                    "detail": "Penalty",
                },
                {
                    "type": "Card",
                    "team": {"name": "St Patrick's Athl."},
                    "player": {"name": "Bob Wilson"},
                    "time": {"elapsed": 30},
                    "detail": "Yellow Card",
                },
            ],
        }

        scorers = extract_scorers(fixture)

        self.assertEqual(len(scorers["home"]), 1)
        self.assertEqual(len(scorers["away"]), 1)
        self.assertEqual(scorers["home"][0]["name"], "John Smith")
        self.assertEqual(scorers["home"][0]["minute"], 25)
        self.assertFalse(scorers["home"][0]["penalty"])
        self.assertEqual(scorers["away"][0]["name"], "Jane Doe")
        self.assertTrue(scorers["away"][0]["penalty"])

    def test_extract_scorers_own_goal(self):
        """Test extract_scorers identifies own goals."""

        fixture = {
            "teams": {
                "home": {"name": "Team A"},
                "away": {"name": "Team B"},
            },
            "events": [
                {
                    "type": "Goal",
                    "team": {"name": "Team A"},
                    "player": {"name": "Own Goal Player"},
                    "time": {"elapsed": 50},
                    "detail": "Own Goal",
                },
            ],
        }

        scorers = extract_scorers(fixture)

        self.assertTrue(scorers["home"][0]["own_goal"])

    def test_extract_scorers_no_events(self):
        """Test extract_scorers handles fixture with no events."""

        fixture = {
            "teams": {
                "home": {"name": "Team A"},
                "away": {"name": "Team B"},
            },
        }

        scorers = extract_scorers(fixture)

        self.assertEqual(len(scorers["home"]), 0)
        self.assertEqual(len(scorers["away"]), 0)

    def test_format_scorers_inline_with_goals(self):
        """Test format_scorers_inline formats goals as inline string."""

        fixture = {
            "teams": {
                "home": {"name": "St Patrick's Athl."},
                "away": {"name": "Shelbourne"},
            },
            "events": [
                {
                    "type": "Goal",
                    "team": {"name": "St Patrick's Athl."},
                    "player": {"name": "John Smith"},
                    "time": {"elapsed": 25},
                    "detail": None,
                },
                {
                    "type": "Goal",
                    "team": {"name": "St Patrick's Athl."},
                    "player": {"name": "Jane Brown"},
                    "time": {"elapsed": 67},
                    "detail": "Penalty",
                },
            ],
        }

        inline = format_scorers_inline(fixture)

        # Should contain both team names
        self.assertIn("**St Patrick's Athletic:**", inline)
        # Should contain scorers with minutes
        self.assertIn("John Smith (25')", inline)
        self.assertIn("Jane Brown (P 67')", inline)
        # Should use pipe separator (no away team in this example)
        self.assertNotIn(" | ", inline)

    def test_format_scorers_inline_with_both_teams(self):
        """Test format_scorers_inline with goals from both teams."""

        fixture = {
            "teams": {
                "home": {"name": "St Patrick's Athl."},
                "away": {"name": "Shelbourne"},
            },
            "events": [
                {
                    "type": "Goal",
                    "team": {"name": "St Patrick's Athl."},
                    "player": {"name": "John Smith"},
                    "time": {"elapsed": 25},
                    "detail": None,
                },
                {
                    "type": "Goal",
                    "team": {"name": "Shelbourne"},
                    "player": {"name": "Bob Wilson"},
                    "time": {"elapsed": 45},
                    "detail": None,
                },
            ],
        }

        inline = format_scorers_inline(fixture)

        # Should contain pipe separator between teams
        self.assertIn(" | ", inline)
        self.assertIn("**St Patrick's Athletic:** John Smith (25')", inline)
        self.assertIn("**Shelbourne:** Bob Wilson (45')", inline)

    def test_format_scorers_inline_no_goals(self):
        """Test format_scorers_inline returns empty string with no goals."""

        fixture = {
            "teams": {
                "home": {"name": "Team A"},
                "away": {"name": "Team B"},
            },
        }

        inline = format_scorers_inline(fixture)

        self.assertEqual(inline, "")


if __name__ == "__main__":
    unittest.main()
