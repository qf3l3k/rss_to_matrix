import logging
from types import SimpleNamespace

from rss_to_matrix.config import NetworkConfig
from rss_to_matrix.formatting import format_entry, strip_html
from rss_to_matrix.matrix import MatrixClient


def test_strip_html_normalizes_markup_and_entities():
    source = "<style>hidden</style><p>Hello&nbsp; world</p><div>Next<br>line</div>"

    assert strip_html(source) == "Hello world\nNext\nline"


def test_format_entry_builds_plain_and_safe_html_bodies():
    entry = SimpleNamespace(
        title="News <b>& more</b>",
        link="https://example.test/article?a=1&b=2",
        summary="<p>First line</p><p>Second line</p>",
    )

    body, formatted_body = format_entry("Feed & Co", entry)

    assert body == (
        "[Feed & Co] News & more\n\n"
        "https://example.test/article?a=1&b=2\n\n"
        "First line\nSecond line"
    )
    assert formatted_body == (
        "<strong>[Feed &amp; Co]</strong> "
        '<a href="https://example.test/article?a=1&amp;b=2">News &amp; more</a>'
        "<br><br>First line<br>Second line"
    )


def test_format_entry_truncates_summary():
    entry = SimpleNamespace(title="Title", summary="1234567890")

    body, formatted_body = format_entry("Feed", entry, 8)

    assert body.endswith("12345...")
    assert formatted_body.endswith("12345...")


def test_matrix_client_dry_run_does_not_call_http(caplog):
    caplog.set_level(logging.INFO)
    session = SimpleNamespace(
        put=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("HTTP called"))
    )
    client = MatrixClient(session, NetworkConfig())

    client.send(
        "https://matrix.test",
        "token",
        "!room:test",
        "body",
        "<b>body</b>",
        dry_run=True,
    )

    assert "DRY RUN: would send Matrix message:\nbody" in caplog.text
