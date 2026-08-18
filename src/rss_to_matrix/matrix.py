import logging
import time
from collections.abc import Callable
from urllib.parse import quote

import requests

from rss_to_matrix.config import NetworkConfig

RETRYABLE_STATUS_CODES = {408, 500, 502, 503, 504}
logger = logging.getLogger(__name__)


class MatrixSendError(RuntimeError):
    """A Matrix message could not be delivered."""


class MatrixClient:
    def __init__(
        self,
        session: requests.Session,
        config: NetworkConfig,
        sleep: Callable[[float], None] = time.sleep,
        transaction_id: Callable[[], str] = lambda: str(time.time_ns()),
    ) -> None:
        self._session = session
        self._config = config
        self._sleep = sleep
        self._transaction_id = transaction_id

    def send(
        self,
        homeserver: str,
        access_token: str,
        room_id: str,
        body: str,
        formatted_body: str,
        dry_run: bool = False,
    ) -> None:
        if dry_run:
            logger.info("DRY RUN: would send Matrix message:\n%s", body)
            return

        txn_id = self._transaction_id()
        url = (
            f"{homeserver.rstrip('/')}"
            f"/_matrix/client/v3/rooms/"
            f"{quote(room_id, safe='')}"
            f"/send/m.room.message/{txn_id}"
        )
        payload = {
            "msgtype": "m.text",
            "body": body,
            "format": "org.matrix.custom.html",
            "formatted_body": formatted_body,
        }

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                response = self._session.put(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "User-Agent": self._config.user_agent,
                    },
                    json=payload,
                    timeout=(
                        self._config.connect_timeout_seconds,
                        self._config.read_timeout_seconds,
                    ),
                )
            except (requests.ConnectionError, requests.Timeout) as error:
                if attempt == self._config.max_attempts:
                    raise MatrixSendError(
                        f"Matrix send failed after {attempt} attempts: {error}"
                    ) from error
                delay = self._retry_delay(attempt)
                logger.warning(
                    "Matrix send failed (%s); retrying in %.1fs (%d/%d)",
                    error,
                    delay,
                    attempt,
                    self._config.max_attempts,
                )
                self._sleep(delay)
                continue

            if 200 <= response.status_code < 300:
                return

            if (
                response.status_code == 429
                or response.status_code in RETRYABLE_STATUS_CODES
            ):
                if attempt == self._config.max_attempts:
                    raise MatrixSendError(
                        f"Matrix send failed after {attempt} attempts: "
                        f"HTTP {response.status_code}"
                    )
                delay = self._response_delay(response, attempt)
                logger.warning(
                    "Matrix send returned HTTP %d; retrying in %.1fs (%d/%d)",
                    response.status_code,
                    delay,
                    attempt,
                    self._config.max_attempts,
                )
                self._sleep(delay)
                continue

            raise MatrixSendError(
                f"Matrix send failed: HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        raise AssertionError("Matrix retry loop exhausted unexpectedly")

    def _retry_delay(self, attempt: int) -> float:
        delay = self._config.retry_backoff_seconds * (2.0 ** (attempt - 1))
        return min(delay, self._config.max_retry_delay_seconds)

    def _response_delay(self, response: requests.Response, attempt: int) -> float:
        if response.status_code == 429:
            try:
                retry_after_ms = float(response.json().get("retry_after_ms"))
                return min(
                    max(retry_after_ms / 1000.0, 0.0),
                    self._config.max_retry_delay_seconds,
                )
            except (AttributeError, TypeError, ValueError):
                pass

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
