# School Summary — common development tasks.
# Requires GNU make, uv (backend) and npm (frontend).

BACKEND  := backend
FRONTEND := frontend
UV       := uv --project $(BACKEND)
NPM      := npm --prefix $(FRONTEND)
PORT     ?= 8000

.DEFAULT_GOAL := help

.PHONY: help install install-backend install-frontend lock \
        dev dev-backend dev-frontend \
        test test-backend test-frontend coverage \
        lint lint-backend lint-frontend format format-check typecheck check \
        build build-frontend docker-build docker-up docker-down docker-logs \
        clean

## ── Setup ────────────────────────────────────────────────────────────

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install backend and frontend dependencies

install-backend: ## Sync backend virtualenv from uv.lock
	$(UV) sync

install-frontend: ## Install frontend node modules
	$(NPM) install

lock: ## Refresh backend uv.lock
	$(UV) lock

## ── Run ──────────────────────────────────────────────────────────────

dev-backend: ## Run backend dev server with reload (PORT=8000)
	$(UV) run uvicorn app.main:app --reload --port $(PORT) --app-dir $(BACKEND)

dev-frontend: ## Run frontend dev server
	$(NPM) run dev

dev: ## Hint for running both dev servers
	@echo "Run 'make dev-backend' and 'make dev-frontend' in two terminals."

## ── Test ─────────────────────────────────────────────────────────────

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend test suite
	$(UV) run pytest

test-frontend: ## Run frontend test suite (vitest; no specs yet)
	$(NPM) run test -- --run --passWithNoTests

coverage: ## Backend tests with HTML coverage report
	$(UV) run pytest --cov=app --cov-report=html --cov-report=term

## ── Quality ──────────────────────────────────────────────────────────

lint: lint-backend lint-frontend ## Lint backend and frontend

lint-backend: ## Ruff lint of the backend
	$(UV) run ruff check $(BACKEND)

lint-frontend: typecheck ## Type-check the frontend (no eslint configured)

typecheck: ## Vue/TypeScript type check
	$(NPM) exec vue-tsc -- --noEmit -p $(FRONTEND)/tsconfig.json

# Note: the backend has never been ruff-formatted — `make format` rewrites
# most files. It is deliberately not part of `make check`.
format: ## Format backend code with ruff
	$(UV) run ruff format $(BACKEND)

format-check: ## Check backend formatting without writing
	$(UV) run ruff format --check $(BACKEND)

check: lint test ## Lint then test everything

## ── Build & Docker ───────────────────────────────────────────────────

build: build-frontend ## Build production assets

build-frontend: ## Build the frontend bundle
	$(NPM) run build

docker-build: ## Build both container images
	docker compose build

docker-up: ## Start the stack in the background
	docker compose up -d --build

docker-down: ## Stop the stack
	docker compose down

docker-logs: ## Follow container logs
	docker compose logs -f

## ── Housekeeping ─────────────────────────────────────────────────────

clean: ## Remove caches and build output
	rm -rf $(FRONTEND)/dist $(BACKEND)/htmlcov $(BACKEND)/.coverage \
	       $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} +
