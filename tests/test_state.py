import hashlib
import sqlite3
from types import SimpleNamespace

import pytest

from rss_to_matrix.config import FeedConfig
from rss_to_matrix.database import (
    LEGACY_TABLE,
    SCHEMA_VERSION,
    StateError,
    already_seen,
    init_db,
    mark_seen,
)
from rss_to_matrix.feeds import entry_identity


def _feed(feed_id="example", name="Example"):
    return FeedConfig(
        id=feed_id,
        name=name,
        url="https://example.test/feed",
        room_id="!room:matrix.test",
    )


def _create_legacy_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE seen_entries (
            feed_name TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            first_seen INTEGER NOT NULL,
            PRIMARY KEY (feed_name, entry_id)
        )
        """
    )
    conn.executemany(
        "INSERT INTO seen_entries(feed_name, entry_id, first_seen) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_entry_identity_uses_first_available_stable_field():
    entry = SimpleNamespace(id="entry-id", guid="guid", link="link", title="title")

    assert entry_identity(entry) == hashlib.sha256(b"entry-id").hexdigest()


def test_seen_entry_round_trip_and_feed_id_isolation(tmp_path):
    conn = init_db(str(tmp_path / "state" / "state.sqlite3"))
    try:
        assert not already_seen(conn, "feed-a", "entry")

        mark_seen(conn, "feed-a", "entry")

        assert already_seen(conn, "feed-a", "entry")
        assert not already_seen(conn, "feed-b", "entry")
    finally:
        conn.close()


def test_fresh_database_records_current_schema_version(tmp_path):
    conn = init_db(str(tmp_path / "state.sqlite3"))
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(seen_entries)")}
    finally:
        conn.close()

    assert version == SCHEMA_VERSION
    assert "feed_id" in columns
    assert "feed_name" not in columns


def test_legacy_database_migrates_seen_entries_to_feed_id(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    _create_legacy_db(db_path, [("Example", "entry-1", 123)])

    conn = init_db(str(db_path), [_feed(feed_id="stable-id", name="Example")])
    try:
        assert already_seen(conn, "stable-id", "entry-1")
        assert conn.execute(
            f"SELECT first_seen FROM {LEGACY_TABLE} WHERE entry_id = 'entry-1'"
        ).fetchone() == (123,)
        assert conn.execute("SELECT version FROM schema_version").fetchone() == (
            SCHEMA_VERSION,
        )
    finally:
        conn.close()


def test_legacy_name_shared_by_feeds_is_migrated_to_each_id(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    _create_legacy_db(db_path, [("Shared", "entry-1", 123)])
    feeds = [_feed("first", "Shared"), _feed("second", "Shared")]

    conn = init_db(str(db_path), feeds)
    try:
        assert already_seen(conn, "first", "entry-1")
        assert already_seen(conn, "second", "entry-1")
    finally:
        conn.close()


def test_legacy_table_is_not_reapplied_after_migration(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    _create_legacy_db(db_path, [("Example", "entry-1", 123)])
    conn = init_db(str(db_path), [_feed("original-id", "Example")])
    conn.close()

    conn = init_db(str(db_path), [_feed("changed-id", "Example")])
    try:
        assert already_seen(conn, "original-id", "entry-1")
        assert not already_seen(conn, "changed-id", "entry-1")
    finally:
        conn.close()


def test_display_name_change_preserves_state_but_id_change_does_not(tmp_path):
    db_path = str(tmp_path / "state.sqlite3")
    conn = init_db(db_path, [_feed("stable-id", "Old name")])
    mark_seen(conn, "stable-id", "entry-1")
    conn.close()

    conn = init_db(db_path, [_feed("stable-id", "New name")])
    try:
        assert already_seen(conn, "stable-id", "entry-1")
        assert not already_seen(conn, "different-id", "entry-1")
    finally:
        conn.close()


def test_newer_database_schema_is_rejected(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute(
        "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION + 1,)
    )
    conn.commit()
    conn.close()

    with pytest.raises(StateError, match="newer than supported"):
        init_db(str(db_path))
