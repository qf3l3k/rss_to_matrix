from pathlib import Path

import pytest

from rss_to_matrix.config import (
    ConfigError,
    FeedConfig,
    NetworkConfig,
    load_config,
    parse_config,
)


def _raw_config():
    return {
        "homeserver": "https://matrix.test",
        "access_token": "token",
        "feed": [
            {
                "id": "example-feed",
                "name": "Example",
                "url": "https://example.test/feed",
                "room_id": "!room:matrix.test",
            }
        ],
    }


def test_parse_config_applies_defaults():
    config = parse_config(_raw_config())

    assert config.homeserver == "https://matrix.test"
    assert config.state_db == "/var/lib/rss-to-matrix/state.sqlite3"
    assert config.feeds == (
        FeedConfig(
            id="example-feed",
            name="Example",
            url="https://example.test/feed",
            room_id="!room:matrix.test",
        ),
    )
    assert config.network == NetworkConfig()


def test_load_config_reads_and_validates_toml(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
homeserver = "https://matrix.test"
access_token = "token"

[[feed]]
id = "example-feed"
name = "Example"
url = "https://example.test/feed"
room_id = "!room:matrix.test"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.feeds[0].id == "example-feed"


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("homeserver",), "matrix.test", "absolute HTTP or HTTPS URL"),
        (("feed", 0, "id"), "bad id", "must contain only"),
        (("feed", 0, "url"), "ftp://example.test/feed", "absolute HTTP"),
        (("feed", 0, "room_id"), "#room:matrix.test", "internal Matrix room ID"),
        (("feed", 0, "enabled"), "true", "must be a boolean"),
        (("feed", 0, "max_entries_per_run"), 0, "integer >= 1"),
        (("feed", 0, "post_delay_seconds"), -1, "number >= 0"),
        (("feed", 0, "summary_max_chars"), -1, "integer >= 0"),
        (("network", "connect_timeout_seconds"), 0, "number >= 0.001"),
        (("network", "read_timeout_seconds"), 0, "number >= 0.001"),
        (("network", "max_attempts"), 0, "integer >= 1"),
        (("network", "retry_backoff_seconds"), -1, "number >= 0"),
        (("network", "max_retry_delay_seconds"), -1, "number >= 0"),
    ],
)
def test_parse_config_rejects_invalid_values(path, value, message):
    raw = _raw_config()
    raw["network"] = {}
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ConfigError, match=message):
        parse_config(raw)


def test_parse_config_requires_at_least_one_feed():
    raw = _raw_config()
    raw["feed"] = []

    with pytest.raises(ConfigError, match="at least one feed"):
        parse_config(raw)


def test_parse_config_rejects_duplicate_feed_ids():
    raw = _raw_config()
    raw["feed"].append(dict(raw["feed"][0]))

    with pytest.raises(ConfigError, match="duplicate feed id.*example-feed"):
        parse_config(raw)


def test_parse_config_reads_network_policy():
    raw = _raw_config()
    raw["network"] = {
        "connect_timeout_seconds": 2,
        "read_timeout_seconds": 8,
        "max_attempts": 3,
        "retry_backoff_seconds": 0.5,
        "max_retry_delay_seconds": 15,
        "user_agent": "custom-agent/1",
    }

    assert parse_config(raw).network == NetworkConfig(
        connect_timeout_seconds=2,
        read_timeout_seconds=8,
        max_attempts=3,
        retry_backoff_seconds=0.5,
        max_retry_delay_seconds=15,
        user_agent="custom-agent/1",
    )


def test_load_config_wraps_missing_file(tmp_path: Path):
    config_path = tmp_path / "missing.toml"

    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(config_path)
