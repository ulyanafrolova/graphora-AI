"""Language and coverage status per file (001 data-model.md § CoverageFile, 003 data-model.md § Coverage)."""

from __future__ import annotations

from graphora.graph.model import Status

ANALYZED_EXTENSIONS = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}

DETECTED_ONLY_EXTENSIONS = {
    ".vue": "vue",
    ".svelte": "svelte",
    ".astro": "astro",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rs": "rust",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
}

MARKER_FILES = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "package.json": "typescript",
    "tsconfig.json": "typescript",
    "jsconfig.json": "javascript",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "java",
    "build.gradle": "java",
}


def _extension(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""


def classify(path: str) -> tuple[str | None, Status]:
    name = path.rsplit("/", 1)[-1]
    ext = _extension(name)
    if ext in ANALYZED_EXTENSIONS:
        return ANALYZED_EXTENSIONS[ext], "analyzed"
    if name in MARKER_FILES:
        return MARKER_FILES[name], "not_code"
    if ext in DETECTED_ONLY_EXTENSIONS:
        return DETECTED_ONLY_EXTENSIONS[ext], "detected_only"
    return None, "not_code"
