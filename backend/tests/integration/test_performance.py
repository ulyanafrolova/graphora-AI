"""SC-005: about 1,000 Python files are analyzed in under 30 seconds."""

import time

import pytest

from conftest import run_analyze


@pytest.mark.slow
def test_thousand_files_under_30s(tmp_path):
    for p in range(10):
        pkg = tmp_path / f"pkg{p}"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        for m in range(100):
            imports = "\n".join(f"from pkg{(p + k) % 10} import mod{(m + k) % 100}" for k in (1, 2, 3))
            (pkg / f"mod{m}.py").write_text(f"{imports}\n\n\nclass C{m}:\n    def run(self):\n        return {m}\n")

    start = time.monotonic()
    code, out, err = run_analyze(tmp_path)
    elapsed = time.monotonic() - start

    assert code == 0, err
    assert "analyzed 1010 files, 3000 edges (0 unresolved)" in err
    assert elapsed < 30, f"took {elapsed:.1f}s"
