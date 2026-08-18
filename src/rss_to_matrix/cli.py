import argparse
import logging
from pathlib import Path

from rss_to_matrix.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from rss_to_matrix.database import StateError
from rss_to_matrix.service import run

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post RSS/Atom feed updates into Matrix rooms."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "validate-config"),
        default="run",
        help="Command to execute. Default: run",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config TOML file. Default: {DEFAULT_CONFIG_PATH}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Parse feeds and show messages without posting to Matrix or updating state."
        ),
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    try:
        config = load_config(args.config)
    except ConfigError as error:
        logger.error("Configuration error: %s", error)
        return 2

    if args.command == "validate-config":
        logger.info("Configuration is valid: %s", args.config)
        return 0

    try:
        return run(config, dry_run=args.dry_run)
    except StateError as error:
        logger.error("State error: %s", error)
        return 1
