.PHONY: setup test test-fast lint check

setup:
	cd backend && uv sync

test:
	cd backend && uv run pytest

test-fast:
	cd backend && uv run pytest -m "not slow"

lint:
	cd backend && uv run ruff check src tests scripts

check: lint test
