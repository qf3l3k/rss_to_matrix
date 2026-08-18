# Release Procedure

## Prepare

1. Create `release/X.Y.Z` from the verified `develop` branch.
2. Update `rss_to_matrix.__version__`, the example user agent, and release notes.
3. Confirm configuration and database migrations are documented.
4. Run the complete development-host gate:

   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -e '.[dev]'
   ./scripts/check.sh
   shellcheck scripts/*.sh
   systemd-analyze verify \
     systemd/rss-to-matrix.service \
     systemd/rss-to-matrix.timer
   python -m build
   ```

5. Confirm GitLab CI passes the quality and package jobs.

## End-To-End Verification

Use dedicated development credentials and never a production Matrix room.

1. Copy the production-like config and state database to the development host.
2. Run `validate-config` against that copy.
3. Back up the copied state, then run `--dry-run` with a public RSS and Atom
   feed and inspect ordering, summaries, links, limits, state suppression, and
   any schema migration.
4. Send to an unencrypted Matrix test room and confirm plain-text and formatted
   rendering, transaction retries, rate-limit handling, and deduplication.
5. Run twice and confirm the second run posts no duplicate entries.
6. Rehearse a legacy database migration from a backup and verify that known
   entries remain seen under configured feed IDs.
7. Run `scripts/install.sh` twice on the deployment host fixture and confirm
   config preservation, state backup, timer restoration, and unit hardening.
8. Follow the documented rollback using the generated backup.

## Publish

Only after every automated and end-to-end check passes:

1. Merge the release branch into `main` and back into `develop`.
2. Create an annotated tag from the release commit:

   ```bash
   git tag -a vX.Y.Z -m "RSS to Matrix X.Y.Z"
   git push origin main develop vX.Y.Z
   ```

3. Publish the CI-built artifacts and release notes.
4. Deploy the exact tag with `scripts/install.sh` and inspect the first timer
   invocation in the journal.

## Version 0.1.0 Gate

`v0.1.0` is the first packaged release. Do not create this tag until the Phase
8 branch passes CI and the end-to-end verification above on the development
host.
