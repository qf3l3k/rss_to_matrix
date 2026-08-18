from types import SimpleNamespace

import requests

from rss_to_matrix.config import NetworkConfig
from rss_to_matrix.matrix import MatrixClient, MatrixSendError


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def put(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(status, *, text="", headers=None, json_body=None):
    def json():
        if isinstance(json_body, Exception):
            raise json_body
        return json_body or {}

    return SimpleNamespace(
        status_code=status,
        text=text,
        headers=headers or {},
        json=json,
    )


def _send(client):
    client.send(
        "https://matrix.test",
        "secret",
        "!room:matrix.test",
        "body",
        "<b>body</b>",
    )


def test_matrix_client_retries_with_stable_transaction_id_and_timeout():
    session = FakeSession([requests.ConnectionError("down"), _response(200)])
    sleeps = []
    client = MatrixClient(
        session,
        NetworkConfig(
            connect_timeout_seconds=2,
            read_timeout_seconds=9,
            max_attempts=2,
        ),
        sleep=sleeps.append,
        transaction_id=lambda: "stable-txn",
    )

    _send(client)

    assert len(session.calls) == 2
    assert all(call[0].endswith("/stable-txn") for call in session.calls)
    assert session.calls[0][1]["timeout"] == (2, 9)
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer secret"
    assert sleeps == [1]


def test_matrix_client_honors_and_caps_matrix_rate_limit():
    session = FakeSession(
        [_response(429, json_body={"retry_after_ms": 120_000}), _response(200)]
    )
    sleeps = []
    client = MatrixClient(
        session,
        NetworkConfig(max_attempts=2, max_retry_delay_seconds=10),
        sleep=sleeps.append,
    )

    _send(client)

    assert sleeps == [10]


def test_matrix_client_retries_selected_server_errors_only():
    session = FakeSession([_response(500), _response(200)])
    client = MatrixClient(session, NetworkConfig(max_attempts=2), sleep=lambda _: None)

    _send(client)

    assert len(session.calls) == 2


def test_matrix_client_fails_permanent_error_without_retry():
    session = FakeSession([_response(403, text="forbidden")])

    try:
        _send(MatrixClient(session, NetworkConfig()))
    except MatrixSendError as error:
        assert "HTTP 403: forbidden" in str(error)
    else:
        raise AssertionError("MatrixSendError was not raised")

    assert len(session.calls) == 1
