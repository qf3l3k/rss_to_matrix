from types import SimpleNamespace

import requests

from rss_to_matrix import feeds
from rss_to_matrix.config import NetworkConfig
from rss_to_matrix.feeds import FeedClient, FeedFetchError


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(status=200, *, content=b"feed", text="", headers=None):
    return SimpleNamespace(
        status_code=status,
        content=content,
        text=text,
        headers=headers or {},
    )


def test_feed_client_fetches_with_headers_timeouts_and_parses_content(monkeypatch):
    session = FakeSession([_response(content=b"rss bytes")])
    parsed = object()
    monkeypatch.setattr(feeds.feedparser, "parse", lambda content: parsed)
    config = NetworkConfig(
        connect_timeout_seconds=2,
        read_timeout_seconds=7,
        user_agent="rss-agent/test",
    )

    result = FeedClient(session, config).fetch("https://example.test/feed")

    assert result is parsed
    assert session.calls == [
        (
            "https://example.test/feed",
            {
                "headers": {"User-Agent": "rss-agent/test"},
                "timeout": (2, 7),
            },
        )
    ]


def test_feed_client_retries_transient_errors_with_bounded_backoff():
    session = FakeSession(
        [requests.Timeout("slow"), _response(status=503), _response()]
    )
    sleeps = []
    config = NetworkConfig(
        max_attempts=3,
        retry_backoff_seconds=4,
        max_retry_delay_seconds=5,
    )

    FeedClient(session, config, sleep=sleeps.append).fetch("https://example.test/feed")

    assert sleeps == [4, 5]
    assert len(session.calls) == 3


def test_feed_client_caps_server_retry_after():
    session = FakeSession(
        [_response(status=429, headers={"Retry-After": "600"}), _response()]
    )
    sleeps = []

    FeedClient(
        session,
        NetworkConfig(max_attempts=2, max_retry_delay_seconds=30),
        sleep=sleeps.append,
    ).fetch("https://example.test/feed")

    assert sleeps == [30]


def test_feed_client_does_not_retry_permanent_http_error():
    session = FakeSession([_response(status=404, text="missing")])

    try:
        FeedClient(session, NetworkConfig()).fetch("https://example.test/feed")
    except FeedFetchError as error:
        assert "HTTP 404: missing" in str(error)
    else:
        raise AssertionError("FeedFetchError was not raised")

    assert len(session.calls) == 1
