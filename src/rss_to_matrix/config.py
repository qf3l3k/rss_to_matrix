import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from rss_to_matrix import __version__

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path("/etc/rss-to-matrix/config.toml")
DEFAULT_STATE_DB = "/var/lib/rss-to-matrix/state.sqlite3"
DEFAULT_USER_AGENT = f"rss-to-matrix/{__version__}"
FEED_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ConfigError(ValueError):
    """An operator-correctable configuration error."""


@dataclass(frozen=True, slots=True)
class FeedConfig:
    id: str
    name: str
    url: str
    room_id: str
    enabled: bool = True
    max_entries_per_run: int = 5
    post_delay_seconds: float = 3.0
    summary_max_chars: int = 500


@dataclass(frozen=True, slots=True)
class NetworkConfig:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 20.0
    max_attempts: int = 5
    retry_backoff_seconds: float = 1.0
    max_retry_delay_seconds: float = 60.0
    user_agent: str = DEFAULT_USER_AGENT


@dataclass(frozen=True, slots=True)
class AppConfig:
    homeserver: str
    access_token: str
    state_db: str
    feeds: tuple[FeedConfig, ...]
    network: NetworkConfig = NetworkConfig()


def _required_string(data: Mapping[str, Any], key: str, location: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{location}.{key} must be a non-empty string")
    return value.strip()


def _optional_bool(
    data: Mapping[str, Any], key: str, default: bool, location: str
) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{location}.{key} must be a boolean")
    return value


def _optional_int(
    data: Mapping[str, Any], key: str, default: int, minimum: int, location: str
) -> int:
    value = data.get(key, default)
    if type(value) is not int or value < minimum:
        raise ConfigError(f"{location}.{key} must be an integer >= {minimum}")
    return value


def _optional_number(
    data: Mapping[str, Any], key: str, default: float, minimum: float, location: str
) -> float:
    value = data.get(key, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value < minimum
    ):
        raise ConfigError(f"{location}.{key} must be a number >= {minimum:g}")
    return float(value)


def _http_url(value: str, location: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{location} must be an absolute HTTP or HTTPS URL")
    return value


def _parse_feed(raw: Any, index: int) -> FeedConfig:
    location = f"feed[{index}]"
    if not isinstance(raw, Mapping):
        raise ConfigError(f"{location} must be a TOML table")

    feed_id = _required_string(raw, "id", location)
    if not FEED_ID_PATTERN.fullmatch(feed_id):
        raise ConfigError(
            f"{location}.id must contain only letters, digits, '.', '_' or '-' "
            "and must start with a letter or digit"
        )

    room_id = _required_string(raw, "room_id", location)
    if not room_id.startswith("!") or ":" not in room_id:
        raise ConfigError(f"{location}.room_id must be an internal Matrix room ID")

    return FeedConfig(
        id=feed_id,
        name=_required_string(raw, "name", location),
        url=_http_url(_required_string(raw, "url", location), f"{location}.url"),
        room_id=room_id,
        enabled=_optional_bool(raw, "enabled", True, location),
        max_entries_per_run=_optional_int(raw, "max_entries_per_run", 5, 1, location),
        post_delay_seconds=_optional_number(
            raw, "post_delay_seconds", 3.0, 0.0, location
        ),
        summary_max_chars=_optional_int(raw, "summary_max_chars", 500, 0, location),
    )


def _parse_network(raw: Any) -> NetworkConfig:
    location = "network"
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ConfigError("config.network must be a TOML table")

    return NetworkConfig(
        connect_timeout_seconds=_optional_number(
            raw, "connect_timeout_seconds", 5.0, 0.001, location
        ),
        read_timeout_seconds=_optional_number(
            raw, "read_timeout_seconds", 20.0, 0.001, location
        ),
        max_attempts=_optional_int(raw, "max_attempts", 5, 1, location),
        retry_backoff_seconds=_optional_number(
            raw, "retry_backoff_seconds", 1.0, 0.0, location
        ),
        max_retry_delay_seconds=_optional_number(
            raw, "max_retry_delay_seconds", 60.0, 0.0, location
        ),
        user_agent=(
            _required_string(raw, "user_agent", location)
            if "user_agent" in raw
            else DEFAULT_USER_AGENT
        ),
    )


def parse_config(raw: Any) -> AppConfig:
    if not isinstance(raw, Mapping):
        raise ConfigError("configuration root must be a TOML table")

    homeserver = _http_url(
        _required_string(raw, "homeserver", "config"), "config.homeserver"
    )
    access_token = _required_string(raw, "access_token", "config")
    state_db = raw.get("state_db", DEFAULT_STATE_DB)
    if not isinstance(state_db, str) or not state_db.strip():
        raise ConfigError("config.state_db must be a non-empty string")

    raw_feeds = raw.get("feed")
    if not isinstance(raw_feeds, list) or not raw_feeds:
        raise ConfigError("config.feed must contain at least one feed table")

    feeds = tuple(_parse_feed(feed, index) for index, feed in enumerate(raw_feeds))
    feed_ids = [feed.id for feed in feeds]
    duplicate_ids = sorted(
        feed_id for feed_id in set(feed_ids) if feed_ids.count(feed_id) > 1
    )
    if duplicate_ids:
        raise ConfigError(f"duplicate feed id(s): {', '.join(duplicate_ids)}")

    return AppConfig(
        homeserver=homeserver,
        access_token=access_token,
        state_db=state_db.strip(),
        feeds=feeds,
        network=_parse_network(raw.get("network")),
    )


def load_config(config_path: Path) -> AppConfig:
    try:
        with config_path.open("rb") as config_file:
            raw = tomllib.load(config_file)
    except FileNotFoundError as error:
        raise ConfigError(f"Config file not found: {config_path}") from error
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Cannot load config {config_path}: {error}") from error

    return parse_config(raw)
