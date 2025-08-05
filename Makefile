.PHONY: install sync-bot sync-learnflow run-bot run-learnflow test-bot test-learnflow test-all lint format clean

# Installation commands
install:
	uv sync --all-groups

sync-bot:
	uv sync --package learnflow-bot --all-groups

sync-learnflow:
	uv sync --package learnflow-core --all-groups

# Run commands
run-bot:
	uv run --package learnflow-bot python -m bot

run-learnflow:
	uv run --package learnflow-core python -m learnflow

# Test commands
test-bot:
	uv run --package learnflow-bot --group test pytest bot/

test-learnflow:
	uv run --package learnflow-core --group test pytest learnflow/

test-all: test-bot test-learnflow

# Code quality commands
lint:
	uv run --group dev ruff check .
	uv run --group dev mypy bot/ learnflow/

format:
	uv run --group dev black .
	uv run --group dev ruff format .

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/