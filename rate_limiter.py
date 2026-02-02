"""Simple rate limiting for external API calls.

Uses a minimum interval between requests to be respectful
and avoid potential blocking.
"""

import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_MIN_INTERVAL = 0.2  # 200ms minimum between requests


class RateLimiter:
    """Simple rate limiter with minimum interval between requests."""

    def __init__(self, min_interval: float = DEFAULT_MIN_INTERVAL):
        """Initialize the rate limiter.

        Args:
            min_interval: Minimum seconds between requests (default 0.2)
        """
        self.min_interval = min_interval
        self._last_request_time = 0.0

    def wait(self) -> None:
        """Wait if needed to respect minimum interval."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_time = time.time()

    def get_polling_interval(self) -> int:
        """Get recommended polling interval for live updates.

        Returns:
            Polling interval in seconds (60 = 1 minute)
        """
        return 60  # 1 minute between live score checks


class APIClient:
    """HTTP client with retry mechanism for external API."""

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        rate_limiter: Optional[RateLimiter] = None,
        max_retries: int = 3,
    ):
        """Initialize the API client.

        Args:
            base_url: Base URL for API calls
            headers: Default headers for all requests
            rate_limiter: Optional rate limiter instance
            max_retries: Maximum retry attempts (default 3)
        """
        self.base_url = base_url
        self.headers = headers
        self.rate_limiter = rate_limiter or RateLimiter()
        self.max_retries = max_retries

    def get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        """Make a GET request with automatic retry on failure.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            timeout: Request timeout in seconds

        Returns:
            JSON response as dictionary

        Raises:
            requests.exceptions.RequestException: If all retries fail
        """
        self.rate_limiter.wait()

        url = f"{self.base_url}{endpoint}"
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(
                    "Timeout on attempt %s/%s: %s",
                    attempt,
                    self.max_retries,
                    e
                )
                if attempt < self.max_retries:
                    backoff = 2 ** (attempt - 1)
                    logger.info("Retrying in %s seconds...", backoff)
                    time.sleep(backoff)

            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code

                # Don't retry on 4xx errors (except 429)
                if 400 <= status_code < 500 and status_code != 429:
                    raise

                logger.warning(
                    "HTTP error %s on attempt %s/%s: %s",
                    status_code,
                    attempt,
                    self.max_retries,
                    e
                )

                if attempt < self.max_retries:
                    backoff = 2 ** (attempt - 1)
                    logger.info("Retrying in %s seconds...", backoff)
                    time.sleep(backoff)

            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(
                    "Request error on attempt %s/%s: %s",
                    attempt,
                    self.max_retries,
                    e
                )
                if attempt < self.max_retries:
                    backoff = 2 ** (attempt - 1)
                    logger.info("Retrying in %s seconds...", backoff)
                    time.sleep(backoff)

        raise last_exception or requests.exceptions.RequestException(
            "API call failed after all retries"
        )


# Keep backward compatibility aliases
APIRateLimiter = RateLimiter
