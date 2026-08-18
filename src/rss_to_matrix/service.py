import logging
import sqlite3
import time
from dataclasses import dataclass

import requests

from rss_to_matrix.config import AppConfig, FeedConfig
from rss_to_matrix.database import already_seen, init_db, mark_seen
from rss_to_matrix.feeds import FeedClient, entry_identity
from rss_to_matrix.formatting import format_entry
from rss_to_matrix.matrix import MatrixClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunSummary:
    posted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0


def process_feed(
    conn: sqlite3.Connection,
    homeserver: str,
    access_token: str,
    feed: FeedConfig,
    feed_client: FeedClient,
    matrix_client: MatrixClient,
    dry_run: bool = False,
) -> int:
    if not feed.enabled:
        logger.info("Skipping disabled feed: %s", feed.name)
        return 0

    logger.info("Checking feed: %s <%s>", feed.name, feed.url)
    parsed = feed_client.fetch(feed.url)
    if parsed.bozo:
        logger.warning("Feed parse issue for %s: %s", feed.name, parsed.bozo_exception)

    entries = list(parsed.entries)
    if not entries:
        logger.info("Feed %s: no entries found", feed.name)
        return 0

    # Feedparser conventionally returns newest first; Matrix should read oldest first.
    entries.reverse()

    # Preserve the legacy flood limit, especially for a feed's first run.
    entries = entries[-feed.max_entries_per_run :]
    pending_entries = []
    for entry in entries:
        entry_id = entry_identity(entry)
        if already_seen(conn, feed.id, entry_id):
            continue
        pending_entries.append((entry, entry_id))

    for index, (entry, entry_id) in enumerate(pending_entries):
        body, formatted_body = format_entry(
            feed_name=feed.name,
            entry=entry,
            summary_max_chars=feed.summary_max_chars,
        )
        matrix_client.send(
            homeserver=homeserver,
            access_token=access_token,
            room_id=feed.room_id,
            body=body,
            formatted_body=formatted_body,
            dry_run=dry_run,
        )
        if not dry_run:
            mark_seen(conn, feed.id, entry_id)

        if not dry_run and index < len(pending_entries) - 1:
            time.sleep(feed.post_delay_seconds)

    posted = len(pending_entries)
    logger.info("Feed %s: posted %d new entries", feed.name, posted)
    return posted


def run(config: AppConfig, dry_run: bool = False) -> int:
    conn = init_db(config.state_db, config.feeds)
    session = requests.Session()
    feed_client = FeedClient(session, config.network)
    matrix_client = MatrixClient(session, config.network)
    posted = 0
    succeeded = 0
    failed = 0
    skipped = 0
    try:
        for feed in config.feeds:
            if not feed.enabled:
                skipped += 1
                logger.info("Skipping disabled feed: %s", feed.name)
                continue

            try:
                posted += process_feed(
                    conn=conn,
                    homeserver=config.homeserver,
                    access_token=config.access_token,
                    feed=feed,
                    feed_client=feed_client,
                    matrix_client=matrix_client,
                    dry_run=dry_run,
                )
                succeeded += 1
            except Exception:
                failed += 1
                logger.exception("Feed failed: %s (%s)", feed.name, feed.id)
    finally:
        session.close()
        conn.close()

    summary = RunSummary(
        posted=posted,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
    )
    logger.info(
        "Run complete: posted=%d succeeded=%d failed=%d skipped=%d",
        summary.posted,
        summary.succeeded,
        summary.failed,
        summary.skipped,
    )
    return summary.exit_code
