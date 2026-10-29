"""Deadline.remaining (specs/002-repo-ingest research.md § R7)."""

import pytest

from graphora.ingest.walk import Deadline, LimitExceeded


def test_remaining_counts_down():
    deadline = Deadline(300)
    assert 299 < deadline.remaining() <= 300


def test_remaining_never_negative():
    deadline = Deadline(0)
    assert deadline.remaining() == 0.0
    with pytest.raises(LimitExceeded):
        deadline.check()
