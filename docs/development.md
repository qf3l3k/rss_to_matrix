# Development Notes

## Local dry run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'

cp config/config.example.toml ./config.toml
# Edit config.toml and set state_db = "./state.sqlite3".
rss-to-matrix --config ./config.toml --dry-run
```

## Development checks

Run the characterization tests and static checks:

```bash
./scripts/check.sh
```

This checks formatting, lint, strict typing, tests, branch coverage, and the
configured coverage floor. GitLab CI repeats the gate with a runner-provided
Python 3.10 or newer and builds the release distributions.

## GitLab Runner Requirements

GitLab always executes jobs on a registered runner using a fresh checkout in
`CI_PROJECT_DIR`; it does not execute the repository on the GitLab server or on
the developer workstation.

A Docker or Kubernetes executor is recommended. It must be able to pull the
declared `python:3.13-slim` image and reach the Python package index (or a
configured internal mirror). If the runner has tags, add the matching tags to
`.gitlab-ci.yml` so GitLab cannot select an incompatible runner.

A shell executor ignores the YAML `image` key. To use one, provide Python 3.10
or newer as `python3`, its venv support, and network access to the dependency
index. `scripts/ci-bootstrap.sh` validates the minimum interpreter version,
creates `.ci-venv` inside the checkout, and installs all runtime and development
dependencies before each job.

This pipeline verifies compatibility with the runner's installed version. An
exact Python 3.10 compatibility job requires a Docker/Kubernetes executor or a
separately tagged runner that provides Python 3.10.

The first lines of a GitLab job log identify the runner and executor. A failure
before `ci-bootstrap.sh` normally indicates checkout, runner, or image-pull
configuration rather than application code.

Validate deployment artifacts on a systemd-based development host:

```bash
shellcheck scripts/install.sh
systemd-analyze verify \
  systemd/rss-to-matrix.service \
  systemd/rss-to-matrix.timer
```

The suite began with characterization tests for the legacy implementation and
now also covers typed configuration, HTTP policy, orchestration, migrations,
and packaging metadata. The zero-entry-limit characterization remains as an
explicit record of behavior rejected by configuration validation.

## Current CLI contract

- A successful run returns exit code `0`.
- Missing files and invalid configuration, including a configuration with no
  feeds, return exit code `2` with a concise error message.
- A run where any enabled feed fails returns exit code `1` after attempting all
  remaining feeds.
- `--dry-run` reads feeds and renders messages without posting to Matrix or
  marking entries as seen. It may initialize or migrate the configured SQLite
  database before reading deduplication state.

## Future Work

Potential features and engineering improvements are tracked in
[ROADMAP.md](../ROADMAP.md).
