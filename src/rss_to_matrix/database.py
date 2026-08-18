import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

from rss_to_matrix.config import FeedConfig

SCHEMA_VERSION = 2
LEGACY_TABLE = "seen_entries_legacy_v1"


class StateError(RuntimeError):
    """The state database schema cannot be used safely."""


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _schema_version(conn: sqlite3.Connection) -> int | None:
    if not _table_exists(conn, "schema_version"):
        return None
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    return int(row[0]) if row is not None else None


def _create_v2_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_entries (
            feed_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            first_seen INTEGER NOT NULL,
            PRIMARY KEY (feed_id, entry_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
        """
    )
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))


def _migrate_v1_table(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, LEGACY_TABLE):
        raise StateError("Cannot migrate state: both legacy state tables already exist")
    conn.execute(f"ALTER TABLE seen_entries RENAME TO {LEGACY_TABLE}")


def _backfill_legacy_entries(
    conn: sqlite3.Connection, feeds: Iterable[FeedConfig]
) -> None:
    if not _table_exists(conn, LEGACY_TABLE):
        return

    for feed in feeds:
        conn.execute(
            f"""
            INSERT OR IGNORE INTO seen_entries(feed_id, entry_id, first_seen)
            SELECT ?, entry_id, first_seen
            FROM {LEGACY_TABLE}
            WHERE feed_name = ?
            """,
            (feed.id, feed.name),
        )


def _initialize_schema(conn: sqlite3.Connection, feeds: Iterable[FeedConfig]) -> None:
    version = _schema_version(conn)
    if version is not None and version > SCHEMA_VERSION:
        raise StateError(
            f"State schema version {version} is newer than supported "
            f"version {SCHEMA_VERSION}"
        )

    migrated_from_v1 = False
    if _table_exists(conn, "seen_entries"):
        columns = _table_columns(conn, "seen_entries")
        if "feed_name" in columns and "feed_id" not in columns:
            _migrate_v1_table(conn)
            migrated_from_v1 = True
        elif "feed_id" not in columns:
            raise StateError("State table has an unrecognized schema")

    _create_v2_tables(conn)
    if migrated_from_v1:
        _backfill_legacy_entries(conn, feeds)


def init_db(db_path: str, feeds: Iterable[FeedConfig] = ()) -> sqlite3.Connection:
    db_file = Path(db_path)
    try:
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
    except (OSError, sqlite3.Error) as error:
        raise StateError(f"Cannot open state database {db_path}: {error}") from error

    try:
        conn.execute("BEGIN IMMEDIATE")
        _initialize_schema(conn, feeds)
        conn.commit()
    except StateError:
        conn.rollback()
        conn.close()
        raise
    except sqlite3.Error as error:
        conn.rollback()
        conn.close()
        raise StateError(
            f"Cannot initialize state database {db_path}: {error}"
        ) from error
    except Exception:
        conn.rollback()
        conn.close()
        raise
    return conn


def already_seen(conn: sqlite3.Connection, feed_id: str, entry_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM seen_entries WHERE feed_id = ? AND entry_id = ?",
        (feed_id, entry_id),
    ).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, feed_id: str, entry_id: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO seen_entries(feed_id, entry_id, first_seen)
        VALUES (?, ?, ?)
        """,
        (feed_id, entry_id, int(time.time())),
    )
    conn.commit()
