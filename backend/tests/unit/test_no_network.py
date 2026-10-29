"""Network guard in conftest (specs/002-repo-ingest research.md § R10)."""

import urllib.request

import pytest


def test_network_access_fails():
    with pytest.raises(AssertionError, match="network access in tests"):
        urllib.request.urlopen("https://example.com")