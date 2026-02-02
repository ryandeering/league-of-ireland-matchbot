"""Tests for rate limiting and retry mechanism."""

import unittest
from unittest.mock import Mock, patch

import requests

from common import extract_scorers
from rate_limiter import APIClient, RateLimiter


class TestRateLimiter(unittest.TestCase):
    """Tests for RateLimiter class."""

    def setUp(self):
        """Set up test fixtures."""
        self.rate_limiter = RateLimiter(min_interval=0.1)

    def test_initialization(self):
        """Test RateLimiter initializes with correct defaults."""
        limiter = RateLimiter()
        self.assertEqual(limiter.min_interval, 0.2)

    def test_wait_enforces_interval(self):
        """Test wait enforces minimum interval between calls."""
        import time

        self.rate_limiter.wait()
        start = time.time()
        self.rate_limiter.wait()
        elapsed = time.time() - start

        # Should have waited at least min_interval
        self.assertGreaterEqual(elapsed, 0.09)  # Allow small tolerance

    def test_get_polling_interval(self):
        """Test get_polling_interval returns expected value."""
        interval = self.rate_limiter.get_polling_interval()
        self.assertEqual(interval, 60)  # 1 minute between checks


class TestAPIClient(unittest.TestCase):
    """Tests for APIClient class."""

    def setUp(self):
        """Set up test fixtures."""
        self.rate_limiter = RateLimiter(min_interval=0.01)
        self.api_client = APIClient(
            base_url="https://api.example.com",
            headers={"User-Agent": "Mozilla/5.0"},
            rate_limiter=self.rate_limiter,
            max_retries=3,
        )

    def test_api_client_initialization(self):
        """Test APIClient initializes correctly."""
        self.assertEqual(self.api_client.base_url, "https://api.example.com")
        self.assertEqual(
            self.api_client.headers,
            {"User-Agent": "Mozilla/5.0"},
        )
        self.assertIsNotNone(self.api_client.rate_limiter)

    @patch("rate_limiter.requests.get")
    def test_get_success_on_first_attempt(self, mock_get):
        """Test get succeeds on first attempt."""
        mock_response = Mock()
        mock_response.json.return_value = {"response": [{"id": 1}]}
        mock_get.return_value = mock_response

        result = self.api_client.get("/leagues", params={"id": 126})

        self.assertEqual(result, {"response": [{"id": 1}]})
        mock_get.assert_called_once()

    @patch("rate_limiter.requests.get")
    def test_get_retries_on_timeout(self, mock_get):
        """Test get retries on timeout."""
        mock_get.side_effect = [
            requests.exceptions.Timeout("Connection timeout"),
            requests.exceptions.Timeout("Connection timeout"),
            Mock(json=lambda: {"response": [{"id": 1}]}),
        ]

        result = self.api_client.get("/leagues", params={"id": 126}, timeout=5)

        self.assertEqual(result, {"response": [{"id": 1}]})
        self.assertEqual(mock_get.call_count, 3)

    @patch("rate_limiter.requests.get")
    @patch("rate_limiter.time.sleep")
    def test_get_uses_exponential_backoff(self, mock_sleep, mock_get):
        """Test get uses exponential backoff."""
        mock_get.side_effect = [
            requests.exceptions.Timeout("Timeout"),
            requests.exceptions.Timeout("Timeout"),
            Mock(json=lambda: {"response": []}),
        ]

        self.api_client.get("/leagues", params={})

        # Should sleep with exponential backoff: 1s, then 2s
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    @patch("rate_limiter.requests.get")
    def test_get_fails_after_max_retries(self, mock_get):
        """Test get raises after max retries."""
        mock_get.side_effect = requests.exceptions.Timeout("Timeout")

        with self.assertRaises(requests.exceptions.Timeout):
            self.api_client.get("/leagues", params={})

        # Should attempt max_retries times (3)
        self.assertEqual(mock_get.call_count, 3)

    @patch("rate_limiter.requests.get")
    def test_get_raises_on_400_error(self, mock_get):
        """Test get raises immediately on 400 error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError(
                response=Mock(status_code=400)
            )
        )
        mock_response.status_code = 400
        mock_get.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            self.api_client.get("/leagues", params={})

        # Should not retry on 4xx errors
        self.assertEqual(mock_get.call_count, 1)

    @patch("rate_limiter.requests.get")
    def test_get_retries_on_429_error(self, mock_get):
        """Test get retries on 429 (rate limit) error."""
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

        result = self.api_client.get("/leagues", params={})

        self.assertEqual(result, {"response": []})
        self.assertEqual(mock_get.call_count, 2)


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


if __name__ == "__main__":
    unittest.main()
