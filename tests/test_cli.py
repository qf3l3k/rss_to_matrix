import logging
from argparse import Namespace

from rss_to_matrix import cli, service
from rss_to_matrix.config import AppConfig, ConfigError, FeedConfig
from rss_to_matrix.database import StateError


def _config(tmp_path, *, feeds=None):
    if feeds is None:
        feeds = (
            FeedConfig(
                id="example",
                name="Example",
                url="https://example.test/feed",
                room_id="!room:matrix.test",
            ),
        )
    return AppConfig(
        homeserver="https://matrix.test",
        access_token="token",
        state_db=str(tmp_path / "state.sqlite3"),
        feeds=feeds,
    )


def test_main_loads_config_and_delegates_to_service(monkeypatch, tmp_path):
    config_path = tmp_path / "config.toml"
    config = _config(tmp_path)
    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda: Namespace(command="run", config=config_path, dry_run=True),
    )
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(
        cli,
        "run",
        lambda loaded_config, dry_run: 7 if loaded_config is config and dry_run else 8,
    )

    assert cli.main() == 7


def test_main_reports_configuration_errors(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda: Namespace(
            command="run", config=tmp_path / "missing.toml", dry_run=False
        ),
    )
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _path: (_ for _ in ()).throw(ConfigError("bad value")),
    )

    assert cli.main() == 2
    assert "Configuration error: bad value" in caplog.text


def test_validate_config_does_not_run_service(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    config_path = tmp_path / "config.toml"
    config = _config(tmp_path)
    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda: Namespace(command="validate-config", config=config_path, dry_run=False),
    )
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(
        cli,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("service executed")
        ),
    )

    assert cli.main() == 0
    assert f"Configuration is valid: {config_path}" in caplog.text


def test_main_reports_state_errors_without_traceback(monkeypatch, tmp_path, caplog):
    config = _config(tmp_path)
    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda: Namespace(
            command="run",
            config=tmp_path / "config.toml",
            dry_run=False,
        ),
    )
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(
        cli,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(StateError("bad schema")),
    )

    assert cli.main() == 1
    assert "State error: bad schema" in caplog.text


def test_run_reports_feed_counts(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    feeds = (
        FeedConfig(
            id="on",
            name="On",
            url="https://example.test/on",
            room_id="!room:matrix.test",
        ),
        FeedConfig(
            id="off",
            name="Off",
            url="https://example.test/off",
            room_id="!room:matrix.test",
            enabled=False,
        ),
    )
    monkeypatch.setattr(
        service,
        "process_feed",
        lambda **kwargs: 2 if kwargs["feed"].enabled else 0,
    )

    assert service.run(_config(tmp_path, feeds=feeds), dry_run=True) == 0
    assert "Run complete: posted=2 succeeded=1 failed=0 skipped=1" in caplog.text


def test_run_reuses_and_closes_http_session(monkeypatch, tmp_path):
    session = Namespace(closed=False)
    session.close = lambda: setattr(session, "closed", True)
    client_sessions = []

    def make_client(client_session, _network):
        client_sessions.append(client_session)
        return object()

    monkeypatch.setattr(service.requests, "Session", lambda: session)
    monkeypatch.setattr(service, "FeedClient", make_client)
    monkeypatch.setattr(service, "MatrixClient", make_client)
    monkeypatch.setattr(service, "process_feed", lambda **_kwargs: 0)

    assert service.run(_config(tmp_path)) == 0
    assert client_sessions == [session, session]
    assert session.closed is True


def test_run_continues_after_feed_failure_and_returns_one(
    monkeypatch, tmp_path, caplog
):
    caplog.set_level(logging.INFO)
    feeds = (
        FeedConfig(
            id="broken",
            name="Broken",
            url="https://example.test/broken",
            room_id="!room:matrix.test",
        ),
        FeedConfig(
            id="working",
            name="Working",
            url="https://example.test/working",
            room_id="!room:matrix.test",
        ),
    )
    processed = []

    def process(**kwargs):
        processed.append(kwargs["feed"].id)
        if kwargs["feed"].id == "broken":
            raise RuntimeError("feed unavailable")
        return 3

    monkeypatch.setattr(service, "process_feed", process)

    assert service.run(_config(tmp_path, feeds=feeds)) == 1
    assert processed == ["broken", "working"]
    assert "Feed failed: Broken (broken)" in caplog.text
    assert "Run complete: posted=3 succeeded=1 failed=1 skipped=0" in caplog.text
