"""Rate limiting and retry mechanism for API calls."""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class APIRateLimiter:
    """Manages API rate limiting with daily and per-minute constraints."""

    def __init__(
        self,
        daily_limit: int = 100,
        per_minute_limit: int = 10,
        max_retries: int = 3,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_recovery_time: int = 300,
    ):
        """
        Initialize the API rate limiter.

        Args:
            daily_limit: Maximum API calls per day (default 100)
            per_minute_limit: Maximum API calls per minute (default 10)
            max_retries: Maximum retry attempts for failed calls (default 3)
            circuit_breaker_threshold: Failures before circuit opens (5)
            circuit_breaker_recovery_time: Seconds until circuit closes (300)
        """
        self.daily_limit = daily_limit
        self.per_minute_limit = per_minute_limit
        self.max_retries = max_retries
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_recovery_time = circuit_breaker_recovery_time

        self.daily_calls = 0
        self.daily_reset_time = datetime.now()
        self.minute_calls = []
        self.consecutive_failures = 0
        self.circuit_open_time: Optional[datetime] = None
        self.stats_file = "api_stats.json"

        self._load_daily_stats()

    def _load_daily_stats(self) -> None:
        """Load daily call statistics from file."""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, "r", encoding="utf-8") as f:
                    stats = json.load(f)
                    last_reset = datetime.fromisoformat(
                        stats.get("reset_time")
                    )
                    now = datetime.now()

                    # Check if stats are from today
                    if last_reset.date() == now.date():
                        self.daily_calls = stats.get("daily_calls", 0)
                        self.daily_reset_time = last_reset
            except (json.JSONDecodeError, ValueError, OSError) as e:
                logger.warning("Could not load API stats: %s", e)
                self.daily_calls = 0
                self.daily_reset_time = datetime.now()

    def _save_daily_stats(self) -> None:
        """Save daily call statistics to file."""
        try:
            stats = {
                "daily_calls": self.daily_calls,
                "reset_time": self.daily_reset_time.isoformat(),
                "timestamp": datetime.now().isoformat(),
            }
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(stats, f)
        except OSError as e:
            logger.warning("Could not save API stats: %s", e)

    def _reset_daily_if_needed(self) -> None:
        """Reset daily counter if a new day has started."""
        now = datetime.now()
        if now.date() > self.daily_reset_time.date():
            self.daily_calls = 0
            self.daily_reset_time = now
            self._save_daily_stats()

    def check_daily_limit(self) -> bool:
        """
        Check if daily limit has been reached.

        Returns:
            True if limit not reached, False if limit exceeded
        """
        self._reset_daily_if_needed()
        return self.daily_calls < self.daily_limit

    def check_per_minute_limit(self) -> bool:
        """
        Check if per-minute limit has been reached.

        Returns:
            True if limit not reached, False if limit exceeded
        """
        now = datetime.now()
        # Remove calls older than 1 minute
        self.minute_calls = [
            call_time for call_time in self.minute_calls
            if (now - call_time).total_seconds() < 60
        ]
        return len(self.minute_calls) < self.per_minute_limit

    def is_circuit_open(self) -> bool:
        """
        Check if circuit breaker is open.

        Returns:
            True if circuit is open, False otherwise
        """
        if self.circuit_open_time is None:
            return False

        elapsed = (datetime.now() - self.circuit_open_time).total_seconds()
        if elapsed > self.circuit_breaker_recovery_time:
            self.circuit_open_time = None
            self.consecutive_failures = 0
            return False

        return True

    def can_make_call(self) -> bool:
        """
        Determine if an API call can be made.

        Returns:
            True if call is allowed, False otherwise
        """
        return (
            self.check_daily_limit()
            and self.check_per_minute_limit()
            and not self.is_circuit_open()
        )

    def record_call(self) -> None:
        """Record a successful API call."""
        self.daily_calls += 1
        self.minute_calls.append(datetime.now())
        self.consecutive_failures = 0
        self._save_daily_stats()

    def record_failure(self) -> None:
        """Record an API call failure."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.circuit_breaker_threshold:
            self.circuit_open_time = datetime.now()

    def get_polling_interval(self) -> int:
        """
        Calculate adaptive polling interval based on remaining daily budget.

        Returns:
            Polling interval in seconds (300, 600, or 900)
        """
        self._reset_daily_if_needed()
        remaining_calls = self.daily_limit - self.daily_calls

        # Conservative estimate: 6 hours of active matches (6 calls per hour)
        if remaining_calls > 36:  # 6 hours * 6 calls
            return 300  # 5 minutes
        if remaining_calls > 18:  # 3 hours * 6 calls
            return 600  # 10 minutes
        return 900  # 15 minutes

    def get_backoff_time(self, attempt: int) -> int:
        """
        Calculate exponential backoff time for retry attempts.

        Args:
            attempt: Current retry attempt number (1-based)

        Returns:
            Backoff time in seconds (2^(n-1): 1s, 2s, 4s, 8s...)
        """
        return 2 ** (attempt - 1)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current rate limiter statistics.

        Returns:
            Dictionary with current stats
        """
        self._reset_daily_if_needed()
        return {
            "daily_calls": self.daily_calls,
            "daily_limit": self.daily_limit,
            "remaining_daily": self.daily_limit - self.daily_calls,
            "per_minute_calls": len(self.minute_calls),
            "per_minute_limit": self.per_minute_limit,
            "circuit_open": self.is_circuit_open(),
            "consecutive_failures": self.consecutive_failures,
            "polling_interval": self.get_polling_interval(),
        }


class APIClient:
    """HTTP client with retry mechanism and rate limiting."""

    def __init__(
        self,
        base_url: str,
        headers: Dict[str, str],
        rate_limiter: APIRateLimiter,
    ):
        """
        Initialize the API client.

        Args:
            base_url: Base URL for API calls
            headers: Default headers for all requests
            rate_limiter: Rate limiter instance
        """
        self.base_url = base_url
        self.headers = headers
        self.rate_limiter = rate_limiter

    def call_with_retry(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """
        Make an API call with automatic retry on failure (exponential backoff).

        Args:
            endpoint: API endpoint path
            params: Query parameters
            timeout: Request timeout in seconds

        Returns:
            JSON response as dictionary

        Raises:
            requests.exceptions.RequestException: If all retries fail or
                circuit breaker is open
        """
        if not self.rate_limiter.can_make_call():
            stats = self.rate_limiter.get_stats()
            if self.rate_limiter.is_circuit_open():
                recovery_time = (
                    self.rate_limiter.circuit_breaker_recovery_time
                )
                raise requests.exceptions.ConnectionError(
                    f"Circuit breaker is open. "
                    f"Failures: {stats['consecutive_failures']}. "
                    f"Retry in {recovery_time}s"
                )
            if not self.rate_limiter.check_daily_limit():
                raise requests.exceptions.RequestException(
                    f"Daily API limit reached: "
                    f"{stats['daily_calls']}/{stats['daily_limit']}"
                )
            raise requests.exceptions.RequestException(
                "Per-minute rate limit exceeded"
            )

        url = f"{self.base_url}{endpoint}"
        last_exception = None

        for attempt in range(1, self.rate_limiter.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                self.rate_limiter.record_call()
                return response.json()

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(
                    "Timeout on attempt %s/%s: %s",
                    attempt,
                    self.rate_limiter.max_retries,
                    e
                )
                if attempt < self.rate_limiter.max_retries:
                    backoff = self.rate_limiter.get_backoff_time(attempt)
                    logger.info("Retrying in %s seconds...", backoff)
                    time.sleep(backoff)

            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code

                # Don't retry on 4xx errors (except 429 and 503)
                if 400 <= status_code < 500 and status_code not in (429, 503):
                    self.rate_limiter.record_failure()
                    raise

                logger.warning(
                    "HTTP error %s on attempt %s/%s: %s",
                    status_code,
                    attempt,
                    self.rate_limiter.max_retries,
                    e
                )

                if attempt < self.rate_limiter.max_retries:
                    backoff = self.rate_limiter.get_backoff_time(attempt)
                    logger.info("Retrying in %s seconds...", backoff)
                    time.sleep(backoff)
                else:
                    self.rate_limiter.record_failure()

            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(
                    "Request error on attempt %s/%s: %s",
                    attempt,
                    self.rate_limiter.max_retries,
                    e
                )
                if attempt < self.rate_limiter.max_retries:
                    backoff = self.rate_limiter.get_backoff_time(attempt)
                    logger.info("Retrying in %s seconds...", backoff)
                    time.sleep(backoff)
                else:
                    self.rate_limiter.record_failure()

        self.rate_limiter.record_failure()
        raise last_exception or requests.exceptions.RequestException(
            "API call failed after all retries"
        )
