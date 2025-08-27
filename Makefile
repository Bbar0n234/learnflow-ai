.PHONY: install sync-bot sync-learnflow sync-artifacts run-bot run-learnflow test-bot test-learnflow test-artifacts test-all lint format clean dev-services ruff-check ruff-fix ruff-format ruff-check-bot ruff-fix-bot ruff-format-bot ruff-check-learnflow ruff-fix-learnflow ruff-format-learnflow ruff-check-artifacts ruff-fix-artifacts ruff-format-artifacts mypy-bot mypy-learnflow mypy-artifacts fix-bot fix-learnflow fix-artifacts

# Installation commands
install:
	uv sync --all-groups

sync-bot:
	uv sync --package learnflow-bot --all-groups

sync-learnflow:
	uv sync --package learnflow-core --all-groups

sync-artifacts:
	uv sync --package artifacts-service --all-groups

# Run commands
run-bot:
	uv run --package learnflow-bot python -m bot

run-learnflow:
	uv run --package learnflow-core python -m learnflow

run-artifacts:
	uv run --package artifacts-service python -m artifacts-service

# Test commands
test-bot:
	uv run --package learnflow-bot --group test pytest bot/

test-learnflow:
	uv run --package learnflow-core --group test pytest learnflow/

test-artifacts:
	uv run --package artifacts-service --group test pytest artifacts-service/

test-all: test-bot test-learnflow test-artifacts

# Ruff commands for bot service only
ruff-check-bot:
	uv run --package learnflow-bot --group dev ruff check bot/

ruff-fix-bot:
	uv run --package learnflow-bot --group dev ruff check bot/ --fix

ruff-format-bot:
	uv run --package learnflow-bot --group dev ruff format bot/

# Ruff commands for learnflow service only
ruff-check-learnflow:
	uv run --package learnflow-core --group dev ruff check learnflow/

ruff-fix-learnflow:
	uv run --package learnflow-core --group dev ruff check learnflow/ --fix

ruff-format-learnflow:
	uv run --package learnflow-core --group dev ruff format learnflow/

# Ruff commands for artifacts-service only
ruff-check-artifacts:
	uv run --package artifacts-service --group dev ruff check artifacts-service/

ruff-fix-artifacts:
	uv run --package artifacts-service --group dev ruff check artifacts-service/ --fix

ruff-format-artifacts:
	uv run --package artifacts-service --group dev ruff format artifacts-service/

# MyPy commands for each service
mypy-bot:
	uv run --package learnflow-bot --group dev mypy bot/

mypy-learnflow:
	uv run --package learnflow-core --group dev mypy learnflow/

mypy-artifacts:
	uv run --package artifacts-service --group dev mypy artifacts-service/

# Full fix commands (ruff fix + format + mypy) for each service
fix-bot:
	uv run --package learnflow-bot --group dev ruff check bot/ --fix
	uv run --package learnflow-bot --group dev ruff format bot/
	uv run --package learnflow-bot --group dev mypy bot/

fix-learnflow:
	uv run --package learnflow-core --group dev ruff check learnflow/ --fix
	uv run --package learnflow-core --group dev ruff format learnflow/
	uv run --package learnflow-core --group dev mypy learnflow/

fix-artifacts:
	uv run --package artifacts-service --group dev ruff check artifacts-service/ --fix
	uv run --package artifacts-service --group dev ruff format artifacts-service/
	uv run --package artifacts-service --group dev mypy artifacts-service/

# Docker commands
dev-services:
	docker compose down -v && docker compose up --build bot graph artifacts-service web-ui postgres prompt-config-service

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/