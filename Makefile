.PHONY: install dev test test-unit test-graph lint format up down clean

install:
	uv sync

dev:
	uv run uvicorn investment_agent.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v

test-unit:
	uv run pytest tests/unit -v

test-graph:
	uv run pytest tests/graph -v

test-integration:
	uv run pytest tests/integration -v

lint:
	uv run ruff check src tests
	uv run mypy src

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

up:
	docker compose up -d

down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
