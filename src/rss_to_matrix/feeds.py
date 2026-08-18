import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

import feedparser
import requests

from rss_to_matrix.config import NetworkConfig

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
logger = logging.getLogger(__name__)


class FeedFetchError(RuntimeError):
    """A feed could not be retrieved after applying the retry policy."""


class FeedClient:
    def __init__(
        self,
        session: requests.Session,
        config: NetworkConfig,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session
        self._config = config
        self._sleep = sleep

    def fetch(self, url: str) -> Any:
        for attempt in range(1, self._config.max_attempts + 1):
            try:
                response = self._session.get(
                    url,
                    headers={"User-Agent": self._config.user_agent},
                    timeout=(
                        self._config.connect_timeout_seconds,
                        self._config.read_timeout_seconds,
                    ),
                )
            except (requests.ConnectionError, requests.Timeout) as error:
                if attempt == self._config.max_attempts:
                    raise FeedFetchError(
                        f"Feed request failed after {attempt} attempts: {error}"
                    ) from error
                delay = self._retry_delay(attempt)
                logger.warning(
                    "Feed request failed (%s); retrying in %.1fs (%d/%d)",
                    error,
                    delay,
                    attempt,
                    self._config.max_attempts,
                )
                self._sleep(delay)
                continue

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == self._config.max_attempts:
                    raise FeedFetchError(
                        f"Feed request failed after {attempt} attempts: "
                        f"HTTP {response.status_code}"
                    )
                delay = self._response_delay(response, attempt)
                logger.warning(
                    "Feed request returned HTTP %d; retrying in %.1fs (%d/%d)",
                    response.status_code,
                    delay,
                    attempt,
                    self._config.max_attempts,
                )
                self._sleep(delay)
                continue

            if not 200 <= response.status_code < 300:
                raise FeedFetchError(
                    f"Feed request failed: HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

            return feedparser.parse(response.content)

        raise AssertionError("feed retry loop exhausted unexpectedly")

    def _retry_delay(self, attempt: int) -> float:
        delay = self._config.retry_backoff_seconds * (2.0 ** (attempt - 1))
        return min(delay, self._config.max_retry_delay_seconds)

    def _response_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(
                    max(float(retry_after), 0.0),
                    self._config.max_retry_delay_seconds,
                )
            except ValueError:
                pass
        return self._retry_delay(attempt)


def entry_identity(entry: Any) -> str:
    """Build a stable identity, preferring an RSS/Atom ID, GUID, or link."""
    raw = (
        getattr(entry, "id", None)
        or getattr(entry, "guid", None)
        or getattr(entry, "link", None)
        or getattr(entry, "title", None)
        or repr(entry)
    )
    return hashlib.sha256(str(raw).encode("utf-8")).hexdigest()
