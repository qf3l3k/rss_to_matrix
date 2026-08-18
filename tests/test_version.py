from rss_to_matrix import __version__
from rss_to_matrix.config import DEFAULT_USER_AGENT


def test_version_and_default_user_agent_are_aligned():
    assert __version__ == "0.1.0"
    assert f"rss-to-matrix/{__version__}" == DEFAULT_USER_AGENT
