"""Limit messages for the CLI (unchanged) and the API (specs/010-end-to-end-pipeline tasks T006)."""

import pytest

from graphora.ingest.walk import LimitExceeded
from graphora.pipeline.messages import limit_message

CASES = [
    ("files", 5000, 5001,
     "file limit exceeded: at least 5001 files > --max-files 5000",
     "file limit exceeded: at least 5001 files > max_files 5000"),
    ("bytes", 10, 11,
     "size limit exceeded: at least 11 bytes > --max-bytes 10",
     "size limit exceeded: at least 11 bytes > max_bytes 10"),
    ("seconds", 300, 300.4,
     "time limit exceeded: 300.4s > --max-seconds 300",
     "time limit exceeded: 300.4s > max_seconds 300"),
    ("archive_bytes", 100, 101,
     "archive size limit exceeded: at least 101 bytes > --max-archive-bytes 100",
     "archive size limit exceeded: at least 101 bytes > max_archive_bytes 100"),
    ("extract_bytes", 100, 101,
     "extracted size limit exceeded: at least 101 bytes > --max-extract-bytes 100",
     "extracted size limit exceeded: at least 101 bytes > max_extract_bytes 100"),
    ("entries", 20000, 20001,
     "entry limit exceeded: at least 20001 entries > --max-entries 20000",
     "entry limit exceeded: at least 20001 entries > max_entries 20000"),
]


@pytest.mark.parametrize("limit,value,observed,cli,api", CASES)
def test_messages(limit, value, observed, cli, api):
    exc = LimitExceeded(limit, value, observed)
    assert limit_message(exc, "cli") == cli
    assert limit_message(exc, "api") == api
