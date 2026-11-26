.PHONY: setup test test-fast lint check db db-down web web-build web-test e2e

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

web:
	cd frontend && npm run dev

web-build:
	cd frontend && npm ci && npm run build

web-test:
	cd frontend && npm run lint && npm run typecheck && npm test

e2e:
	cd frontend && npm run build && npx playwright test
