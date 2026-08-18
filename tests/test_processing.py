from types import SimpleNamespace

from rss_to_matrix import service
from rss_to_matrix.config import FeedConfig
from rss_to_matrix.database import already_seen, init_db
from rss_to_matrix.feeds import entry_identity


def _entry(number: int):
    return SimpleNamespace(
        id=f"entry-{number}",
        title=f"Entry {number}",
        link=f"https://example.test/{number}",
        summary="Summary",
    )


def _feed(**overrides):
    values = {
        "id": "example",
        "name": "Example",
        "url": "https://example.test/feed",
        "room_id": "!room:example.test",
        "post_delay_seconds": 0,
    }
    values.update(overrides)
    return FeedConfig(**values)


def _parsed(entries):
    return SimpleNamespace(bozo=False, entries=entries)


def _clients(entries, sent):
    feed_client = SimpleNamespace(fetch=lambda _url: _parsed(entries))
    matrix_client = SimpleNamespace(send=lambda **kwargs: sent.append(kwargs))
    return feed_client, matrix_client


def test_process_feed_posts_oldest_first_with_limit(monkeypatch, tmp_path):
    # Feedparser conventionally returns newest entries first.
    sent = []
    feed_client, matrix_client = _clients([_entry(3), _entry(2), _entry(1)], sent)
    sleeps = []
    monkeypatch.setattr(service.time, "sleep", sleeps.append)
    conn = init_db(str(tmp_path / "state.sqlite3"))

    try:
        count = service.process_feed(
            conn,
            "https://matrix.test",
            "token",
            _feed(max_entries_per_run=2),
            feed_client,
            matrix_client,
        )
    finally:
        conn.close()

    assert count == 2
    assert [call["body"].splitlines()[0] for call in sent] == [
        "[Example] Entry 2",
        "[Example] Entry 3",
    ]
    assert sleeps == [0]


def test_process_feed_dry_run_does_not_update_state_or_sleep(monkeypatch, tmp_path):
    entry = _entry(1)
    sent = []
    feed_client, matrix_client = _clients([entry], sent)
    monkeypatch.setattr(
        service.time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(AssertionError("sleep called")),
    )
    conn = init_db(str(tmp_path / "state.sqlite3"))

    try:
        count = service.process_feed(
            conn,
            "https://matrix.test",
            "token",
            _feed(),
            feed_client,
            matrix_client,
            dry_run=True,
        )
        assert not already_seen(conn, "example", entry_identity(entry))
    finally:
        conn.close()

    assert count == 1
    assert sent[0]["dry_run"] is True


def test_process_feed_skips_disabled_feed(monkeypatch, tmp_path):
    feed_client = SimpleNamespace(
        fetch=lambda _url: (_ for _ in ()).throw(AssertionError("feed fetched"))
    )
    matrix_client = SimpleNamespace(send=lambda **_kwargs: None)
    conn = init_db(str(tmp_path / "state.sqlite3"))
    try:
        assert (
            service.process_feed(
                conn,
                "https://matrix.test",
                "token",
                _feed(enabled=False),
                feed_client,
                matrix_client,
            )
            == 0
        )
    finally:
        conn.close()


def test_zero_entry_limit_currently_selects_all_entries(monkeypatch, tmp_path):
    """Characterize the known -0 slice defect before configuration validation."""
    sent = []
    feed_client, matrix_client = _clients([_entry(2), _entry(1)], sent)
    monkeypatch.setattr(service.time, "sleep", lambda _seconds: None)
    conn = init_db(str(tmp_path / "state.sqlite3"))
    try:
        count = service.process_feed(
            conn,
            "https://matrix.test",
            "token",
            _feed(max_entries_per_run=0),
            feed_client,
            matrix_client,
        )
    finally:
        conn.close()

    assert count == 2
    assert len(sent) == 2
