# RSS to Matrix Deployment

## Goal

Deploy `rss-to-matrix` as a native Debian systemd oneshot service. The service
polls configured RSS/Atom feeds, records seen entries in SQLite, and posts new
entries to selected unencrypted Matrix rooms.

Target environment used in these examples:

```text
Homeserver: https://matrix.example.com
Bot user:   @rss-bot:matrix.example.com
Runtime:    /opt/rss-to-matrix/.venv
Config:     /etc/rss-to-matrix/config.toml
State:      /var/lib/rss-to-matrix/state.sqlite3
Service:    rss-to-matrix.service
Timer:      rss-to-matrix.timer
```

## Important Packaging Change

The legacy release was a single executable script copied to:

```text
/usr/local/bin/rss-to-matrix
```

The current application is an installable Python package. Do not copy
`src/rss-to-matrix` to `/usr/local/bin`, and do not install Poetry. The project
is installed into a dedicated virtual environment, which generates the command:

```text
/opt/rss-to-matrix/.venv/bin/rss-to-matrix
```

The systemd unit invokes that command directly:

```ini
ExecStartPre=/opt/rss-to-matrix/.venv/bin/rss-to-matrix validate-config --config /etc/rss-to-matrix/config.toml
ExecStart=/opt/rss-to-matrix/.venv/bin/rss-to-matrix --config /etc/rss-to-matrix/config.toml
```

The program performs one polling run and exits. `rss-to-matrix.timer` starts it
every ten minutes. It is not a continuously running `Type=simple` daemon.

## 1. Prepare Matrix

Create a private, unencrypted Matrix room and invite the bot:

```text
@rss-bot:matrix.example.com
```

Copy the internal room ID from Element:

```text
Room settings -> Advanced -> Internal room ID
```

The value must include the leading `!` and homeserver, for example:

```text
!AbCdEfGhIjKlMnOpQr:matrix.example.com
```

If the bot account does not exist, create it on the Synapse host:

```bash
sudo register_new_matrix_user \
  -k "$(sudo cat /etc/matrix-synapse/registration_shared_secret.txt)" \
  http://127.0.0.1:8008
```

Create a non-admin user named `rss-bot`, log in once, and join the RSS room.

Obtain an access token:

```bash
curl -s -X POST "https://matrix.example.com/_matrix/client/v3/login" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "m.login.password",
    "identifier": {
      "type": "m.id.user",
      "user": "rss-bot"
    },
    "password": "BOT_PASSWORD_HERE",
    "initial_device_display_name": "rss-to-matrix"
  }'
```

Store only the returned `access_token` in the application config. Do not store
the bot password there.

## 2. Install Prerequisites

```bash
sudo apt update
sudo apt install -y git python3 python3-venv curl
```

Keep a deployment checkout so later upgrades can use the same installer:

```bash
sudo git clone REPOSITORY_URL /opt/rss-to-matrix-source
sudo git -C /opt/rss-to-matrix-source log --oneline -5
```

Check out a reviewed release tag or commit rather than deploying an arbitrary
moving branch.

## 3. Back Up a Legacy Installation

If `/usr/local/bin/rss-to-matrix` is currently deployed, stop polling before
changing files:

```bash
sudo systemctl stop rss-to-matrix.timer rss-to-matrix.service
sudo install -m 600 \
  /etc/rss-to-matrix/config.toml \
  ./config.toml.pre-package-backup
sudo install -m 600 \
  /var/lib/rss-to-matrix/state.sqlite3 \
  ./state.sqlite3.pre-package-backup
```

The state backup is mandatory for rollback to `v0.0.0-legacy`. That version
cannot read the new schema after migration.

Before the first packaged run, add a stable unique `id` to every existing feed
without changing its `name`. The migration maps legacy state to IDs by exact
feed-name match. For example:

```toml
[[feed]]
id = "example-feed"
name = "Example Feed" # Keep the legacy name for the migration.
url = "https://feeds.example.com/rss.xml"
room_id = "!ROOM_ID:matrix.example.com"
```

The legacy SQLite database at `/var/lib/rss-to-matrix/state.sqlite3` is migrated
automatically to schema version 2. The original table is retained as
`seen_entries_legacy_v1` for inspection.

## 4. Install the Package and Units

Run the repository installer as root:

```bash
cd /opt/rss-to-matrix-source
sudo ./scripts/install.sh
```

The installer is idempotent. It:

- creates the `rss-to-matrix` system user and group;
- creates `/opt/rss-to-matrix/.venv`;
- installs or upgrades the package with pip;
- creates `/etc/rss-to-matrix/config.toml` only when it is absent;
- preserves an existing config and repairs its ownership and mode;
- backs up an existing state database before upgrading;
- installs the supplied systemd service and timer units;
- restores the timer only if it was active before a successful upgrade.

It does not enable a timer on a new installation.

The source checkout and runtime are intentionally separate:

```text
/opt/rss-to-matrix-source       deployment checkout
/opt/rss-to-matrix/.venv        installed runtime and command
/etc/rss-to-matrix/config.toml  operator-managed secrets/config
/var/lib/rss-to-matrix          service-owned state and backups
```

## 5. Configure the Application

Edit the installed configuration:

```bash
sudo nano /etc/rss-to-matrix/config.toml
```

Current configuration example:

```toml
homeserver = "https://matrix.example.com"
access_token = "PASTE_BOT_ACCESS_TOKEN_HERE"
state_db = "/var/lib/rss-to-matrix/state.sqlite3"

[network]
connect_timeout_seconds = 5
read_timeout_seconds = 20
max_attempts = 5
retry_backoff_seconds = 1
max_retry_delay_seconds = 60
user_agent = "rss-to-matrix/0.1.0"

[[feed]]
id = "example-feed"
name = "Example Feed"
url = "https://feeds.example.com/rss.xml"
room_id = "!PASTE_ROOM_ID_HERE:matrix.example.com"
enabled = true
max_entries_per_run = 3
post_delay_seconds = 5
summary_max_chars = 500
```

Required top-level fields are `homeserver` and `access_token`. Every feed needs
`id`, `name`, `url`, and `room_id`. Feed IDs must be unique and stable; display
names may be changed after the legacy migration.

The config must remain readable by the service account but not other users:

```bash
sudo chown root:rss-to-matrix /etc/rss-to-matrix/config.toml
sudo chmod 640 /etc/rss-to-matrix/config.toml
```

This application does not currently expose Prometheus metrics. Settings such as
`prometheus_port`, `slo_time_to_run`, `feed_path`, `interval`, `[[bridge]]`, and
message templates belong to a different application and are not accepted here.

## 6. Validate and Test Manually

Validate without accessing SQLite, feeds, or Matrix:

```bash
sudo -u rss-to-matrix \
  /opt/rss-to-matrix/.venv/bin/rss-to-matrix \
  validate-config \
  --config /etc/rss-to-matrix/config.toml
```

Perform a dry run:

```bash
sudo -u rss-to-matrix \
  HOME=/var/lib/rss-to-matrix \
  /opt/rss-to-matrix/.venv/bin/rss-to-matrix \
  --config /etc/rss-to-matrix/config.toml \
  --dry-run
```

Dry-run mode does not send Matrix messages or mark entries as seen. It does open
the configured SQLite database and may initialize or migrate the schema. Use a
database backup when testing a legacy migration.

Perform one real run only after checking dry-run output:

```bash
sudo -u rss-to-matrix \
  HOME=/var/lib/rss-to-matrix \
  /opt/rss-to-matrix/.venv/bin/rss-to-matrix \
  --config /etc/rss-to-matrix/config.toml
```

On the first run, only the newest `max_entries_per_run` entries are considered.
The setting is a latest-only window, not an eventual historical queue.

## 7. Enable systemd Scheduling

The installer deploys a hardened `Type=oneshot` service with configuration
validation in `ExecStartPre` and a nine-minute timeout.

Run and inspect the service once:

```bash
sudo systemctl start rss-to-matrix.service
sudo systemctl status rss-to-matrix.service
sudo journalctl -u rss-to-matrix.service -n 100 --no-pager
```

A successful oneshot service normally becomes `inactive (dead)` after exiting;
the command status should show a successful result.

Enable the timer only after the manual run succeeds:

```bash
sudo systemctl enable --now rss-to-matrix.timer
systemctl list-timers | grep rss-to-matrix
```

The timer runs on ten-minute wall-clock boundaries with up to 30 seconds of
jitter and catches up one missed invocation after downtime.

Follow logs:

```bash
sudo journalctl -u rss-to-matrix.service -f
```

## 8. Remove the Legacy Launcher

After the packaged command, manual run, service, and timer have all been
verified, remove the obsolete copied script:

```bash
sudo rm -f /usr/local/bin/rss-to-matrix
hash -r
```

Do not replace it with a symlink. systemd and operator commands should use the
virtualenv command directly so the interpreter and dependencies cannot drift.

Confirm the deployed unit uses the new path:

```bash
systemctl cat rss-to-matrix.service
```

## 9. Add or Change Feeds

Edit the config, validate it, then trigger a oneshot run:

```bash
sudo nano /etc/rss-to-matrix/config.toml
sudo -u rss-to-matrix \
  /opt/rss-to-matrix/.venv/bin/rss-to-matrix validate-config
sudo systemctl start rss-to-matrix.service
sudo journalctl -u rss-to-matrix.service -n 100 --no-pager
```

Changing a feed `name` preserves state. Changing its `id` creates a new state
identity and can repost entries from the current delivery window.

## 10. Back Up

Stop writes and back up config and state:

```bash
sudo systemctl stop rss-to-matrix.timer rss-to-matrix.service
sudo install -m 600 \
  /etc/rss-to-matrix/config.toml \
  /srv/backups/rss-to-matrix-config.toml
sudo install -m 600 \
  /var/lib/rss-to-matrix/state.sqlite3 \
  /srv/backups/rss-to-matrix-state.sqlite3
sudo systemctl start rss-to-matrix.timer
```

Encrypt off-host backups because the config contains a Matrix access token. The
virtualenv and systemd units are reproducible from a pinned release.

## 11. Upgrade

Check out a reviewed release or commit and rerun the installer:

```bash
cd /opt/rss-to-matrix-source
sudo git -C /opt/rss-to-matrix-source fetch --tags
sudo git -C /opt/rss-to-matrix-source checkout RELEASE_OR_COMMIT
sudo ./scripts/install.sh
```

If the timer was active, the installer stops polling, waits for the service,
creates a timestamped state backup, upgrades the virtualenv and units, reloads
systemd, and restarts the timer. Existing configuration is not overwritten.

After upgrading:

```bash
sudo -u rss-to-matrix \
  /opt/rss-to-matrix/.venv/bin/rss-to-matrix validate-config
sudo systemctl start rss-to-matrix.service
sudo journalctl -u rss-to-matrix.service -n 100 --no-pager
```

## 12. Roll Back

For packaged releases, stop polling, restore the matching config/state backup,
check out the previous release, and rerun its installer:

```bash
sudo systemctl stop rss-to-matrix.timer rss-to-matrix.service
sudo install -m 640 -o root -g rss-to-matrix \
  /srv/backups/rss-to-matrix-config.toml \
  /etc/rss-to-matrix/config.toml
sudo install -m 640 -o rss-to-matrix -g rss-to-matrix \
  /srv/backups/rss-to-matrix-state.sqlite3 \
  /var/lib/rss-to-matrix/state.sqlite3
cd /opt/rss-to-matrix-source
sudo git -C /opt/rss-to-matrix-source checkout PREVIOUS_RELEASE_OR_COMMIT
sudo ./scripts/install.sh
sudo systemctl start rss-to-matrix.service
sudo systemctl start rss-to-matrix.timer
```

Rolling back to `v0.0.0-legacy` requires its archived manual installation and a
pre-migration database backup. Do not point the legacy script at schema version
2.

## 13. Troubleshooting

### Configuration validation fails

```bash
sudo -u rss-to-matrix \
  /opt/rss-to-matrix/.venv/bin/rss-to-matrix validate-config
```

Check required fields, unique feed IDs, URL schemes, internal room IDs, numeric
ranges, config ownership, and TOML syntax.

### Bot does not post

```bash
sudo journalctl -u rss-to-matrix.service -n 200 --no-pager
```

Check that the token is valid, the bot joined the room, the room ID begins with
`!`, the room is unencrypted, the feed URL is reachable, and the entry is not
already recorded in SQLite.

### Permission denied

```bash
sudo ls -ld /opt/rss-to-matrix /etc/rss-to-matrix /var/lib/rss-to-matrix
sudo ls -l /etc/rss-to-matrix/config.toml
```

Expected ownership:

```text
/opt/rss-to-matrix                  root:root
/etc/rss-to-matrix                 root:rss-to-matrix
/etc/rss-to-matrix/config.toml     root:rss-to-matrix mode 0640
/var/lib/rss-to-matrix             rss-to-matrix:rss-to-matrix
```

### Service shows inactive after a run

That is expected for a successful oneshot. Inspect its result and journal, then
check that `rss-to-matrix.timer` is active.

### Too many messages

Reduce `max_entries_per_run`, test in a dedicated room, and keep the SQLite
state persistent. Deleting or changing `state_db`, or changing a feed ID, can
make entries appear unseen again.

## 14. Operational Checklist

- [ ] Private unencrypted Matrix room created.
- [ ] `rss-bot` created, invited, and joined.
- [ ] Internal room ID copied.
- [ ] Bot access token generated and stored only in protected config.
- [ ] Legacy config and SQLite state backed up.
- [ ] Stable unique ID added to every feed.
- [ ] `scripts/install.sh` completed successfully.
- [ ] Config validation passed.
- [ ] Dry run inspected.
- [ ] Real oneshot run succeeded.
- [ ] SQLite legacy migration verified without duplicate posts.
- [ ] systemd service uses `/opt/rss-to-matrix/.venv/bin/rss-to-matrix`.
- [ ] Timer enabled and next run visible in `systemctl list-timers`.
- [ ] Obsolete `/usr/local/bin/rss-to-matrix` removed after verification.
- [ ] Config and state backups stored securely.
