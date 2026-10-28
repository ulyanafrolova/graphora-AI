"""The suite runs offline: any network connection fails the test (002 research § R10)."""

from __future__ import annotations

import urllib.request

import pytest


def test_network_access_fails() -> None:
    with pytest.raises(AssertionError, match="network access in tests"):
        urllib.request.urlopen("https://example.com")
