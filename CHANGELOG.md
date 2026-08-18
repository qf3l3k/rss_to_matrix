# Changelog

## 0.1.0 - 2026-07-14

First packaged release.

### Added

- Typed TOML configuration with validation and a `validate-config` command.
- Dedicated RSS and Matrix clients with timeouts, bounded retries, and a shared
  HTTP session.
- Per-feed failure isolation, structured logging, run summaries, and dry-run
  support.
- Versioned SQLite state keyed by stable feed IDs, including migration from the
  legacy name-keyed schema.
- Hardened systemd service and timer units with an idempotent installer,
  upgrade backups, and rollback documentation.
- Characterization, configuration, HTTP-client, processing, and state-migration
  tests with lint, typing, coverage, packaging, and GitLab CI gates.

### Changed

- Replaced the single-file implementation with the installable
  `rss_to_matrix` package and console entry point.

### Upgrade Notes

- Add a stable, unique `id` to every configured feed before upgrading.
- Preserve existing feed display names for the first run so legacy seen state
  can be mapped to the new IDs.
- Back up `/etc/rss-to-matrix/config.toml` and the SQLite state database before
  deployment. The installer creates a timestamped state backup automatically.
