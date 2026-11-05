.PHONY: setup test test-fast lint check db db-down

TEST_DB_HINT = graphora: GRAPHORA_TEST_DATABASE_URL is not set; store tests will fail. Run `make db` and \
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test, or run \
`cd backend && uv run pytest -m "not db"`.

setup:
	cd backend && uv sync

test:
	@if [ -z "$$GRAPHORA_TEST_DATABASE_URL" ]; then echo '$(TEST_DB_HINT)'; fi
	cd backend && uv run pytest

test-fast:
	@if [ -z "$$GRAPHORA_TEST_DATABASE_URL" ]; then echo '$(TEST_DB_HINT)'; fi
	cd backend && uv run pytest -m "not slow"

lint:
	cd backend && uv run ruff check src tests scripts

check: lint test

db:
	docker compose up -d --wait postgres

db-down:
	docker compose down
