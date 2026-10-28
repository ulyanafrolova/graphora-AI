import pytest

from graphora.detect.languages import DETECTED_ONLY_EXTENSIONS, MARKER_FILES, classify


@pytest.mark.parametrize("ext, language", sorted(DETECTED_ONLY_EXTENSIONS.items()))
def test_detected_only(ext, language):
    assert classify(f"dir/file{ext}") == (language, "detected_only")


def test_detected_only_table_matches_data_model():
    assert DETECTED_ONLY_EXTENSIONS == {
        ".vue": "vue", ".svelte": "svelte", ".astro": "astro",
        ".go": "go", ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".rs": "rust", ".cs": "csharp",
        ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".rb": "ruby", ".php": "php",
        ".swift": "swift", ".scala": "scala", ".sh": "shell",
    }


@pytest.mark.parametrize("path", ["a.py", "pkg/b.pyi"])
def test_python_analyzed(path):
    assert classify(path) == ("python", "analyzed")


@pytest.mark.parametrize("path", ["a.ts", "a.tsx", "a.mts", "a.cts", "types/x.d.ts"])
def test_typescript_analyzed(path):
    assert classify(path) == ("typescript", "analyzed")


@pytest.mark.parametrize("path", ["a.js", "a.jsx", "a.mjs", "a.cjs"])
def test_javascript_analyzed(path):
    assert classify(path) == ("javascript", "analyzed")


def test_jsconfig_marker():
    assert MARKER_FILES["jsconfig.json"] == "javascript"
    assert classify("web/jsconfig.json") == ("javascript", "not_code")


@pytest.mark.parametrize("path", ["README.md", "config.yaml", "Makefile", ".env"])
def test_not_code(path):
    assert classify(path) == (None, "not_code")


@pytest.mark.parametrize("name", sorted(MARKER_FILES))
def test_markers(name):
    expected_status = "analyzed" if name == "setup.py" else "not_code"
    assert classify(f"sub/{name}") == (MARKER_FILES[name], expected_status)
