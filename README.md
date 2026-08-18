# RSS to Matrix

A small self-hosted RSS/Atom notifier for Matrix rooms.

`rss-to-matrix` polls configured feeds, records seen entries in SQLite, strips
noisy feed HTML, and posts clean messages through the Matrix Client API. It is
designed for native Debian/systemd deployment without Docker or Poetry.

Python 3.10 or newer is supported. Version `0.1.0` is the first packaged
release; the original single-file implementation is preserved as
`v0.0.0-legacy` and on the `legacy-single-file` branch.

## Features

- RSS and Atom parsing with configurable entry and summary limits.
- Per-feed Matrix room routing and enable/disable controls.
- Plain-text and sanitized HTML Matrix messages.
- SQLite deduplication keyed by stable feed IDs.
- Automatic migration from the legacy name-keyed SQLite schema.
- Explicit HTTP timeouts, bounded retries, and Synapse rate-limit handling.
- Per-feed failure isolation, structured logging, and run summaries.
- Configuration validation and dry-run modes.
- Hardened systemd oneshot service with a ten-minute timer.
- Idempotent installation and upgrade script with state backups.
- Tests, strict typing, coverage enforcement, packaging, and GitLab CI.

## How It Runs

The packaged command is installed inside a dedicated virtual environment:

```text
/opt/rss-to-matrix/.venv/bin/rss-to-matrix
```

The application performs one polling run and exits. systemd starts it on a
timer; it is not a continuously running daemon. The legacy copied command at
`/usr/local/bin/rss-to-matrix` is no longer used.

For installation, migration from the single-file version, systemd operation,
backup, upgrade, rollback, and troubleshooting, follow
[DEPLOYMENT.md](DEPLOYMENT.md).

## Quick Start

On a Debian system with `git`, `python3`, and `python3-venv` installed:

```bash
git clone REPOSITORY_URL rss-to-matrix
cd rss-to-matrix
sudo ./scripts/install.sh
sudo nano /etc/rss-to-matrix/config.toml
sudo -u rss-to-matrix \
  /opt/rss-to-matrix/.venv/bin/rss-to-matrix validate-config
sudo systemctl start rss-to-matrix.service
sudo systemctl enable --now rss-to-matrix.timer
```

Use a dedicated Matrix bot account in a private, unencrypted room. Do not enable
the timer until configuration validation and one manual service run succeed.

## Configuration

```toml
homeserver = "https://matrix.example.com"
access_token = "PASTE_BOT_ACCESS_TOKEN_HERE"
state_db = "/var/lib/rss-to-matrix/state.sqlite3"

[[feed]]
id = "example-news"
name = "Example News"
url = "https://feeds.example.com/news.xml"
room_id = "!PASTE_ROOM_ID_HERE:matrix.example.com"
enabled = true
max_entries_per_run = 3
post_delay_seconds = 5
summary_max_chars = 500
```

The complete example, including network timeout and retry settings, is in
[`config/config.example.toml`](config/config.example.toml).

Required application fields:

- `homeserver`: absolute HTTP or HTTPS Matrix homeserver URL.
- `access_token`: token for the dedicated Matrix bot account.
- `state_db`: optional SQLite path; defaults to the deployed state location.

Required feed fields:

- `id`: unique permanent identity used for deduplication.
- `name`: display name included in messages.
- `url`: absolute HTTP or HTTPS RSS/Atom URL.
- `room_id`: internal Matrix room ID beginning with `!`.

Changing a display name preserves state. Changing a feed ID creates a new state
identity and may repost entries from the current delivery window.

## Commands

Validate configuration without accessing SQLite, RSS, or Matrix:

```bash
rss-to-matrix validate-config --config ./config.toml
```

Preview messages without sending or marking entries as seen:

```bash
rss-to-matrix --config ./config.toml --dry-run
```

Dry-run mode still opens the configured SQLite database for deduplication and
may initialize or migrate its schema.

Run one normal polling cycle:

```bash
rss-to-matrix --config ./config.toml
```

## Delivery Behavior

`max_entries_per_run` is a latest-only delivery window, not an eventual queue.
On the first run, only the newest entries within that window are posted. Later
runs check the same window for unseen entries, preventing a new or long-offline
feed from flooding a room.

One feed failure does not block later feeds. A run returns `1` if any enabled
feed failed, `2` for configuration errors, and `0` when processing succeeds.

## Development

Install the development dependencies and run the complete Python quality gate:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
./scripts/check.sh
```

Additional project documentation:

- [Deployment and migration](DEPLOYMENT.md)
- [Development notes](docs/development.md)
- [Release procedure](docs/release.md)
- [Roadmap](ROADMAP.md)
- [Changelog](CHANGELOG.md)

## Security

The configuration contains a Matrix access token. Keep it readable only by root
and the `rss-to-matrix` service group, use a dedicated non-admin bot, and keep
deployment backups encrypted when stored off-host.

## License

This project is distributed under the terms in [LICENSE](LICENSE).
