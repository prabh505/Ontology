# CausaLog developer entry points.
#
# PYTHONHASHSEED is exported for every target that can touch the pipeline: hash
# randomization is a named threat to the determinism guarantee (CONVENTIONS.md §11).
export PYTHONHASHSEED := 0

# The interpreter the venv is built from. Pinned to the version CI uses and the version
# `requires-python` and the mypy/ruff targets declare, so a local run and a CI run cannot
# disagree about the language level.
PYTHON   ?= python3.12

COMPOSE  := docker compose -f deployment/docker-compose.yml
VENV     := backend/.venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help setup up down lint typecheck laws test test-fast bench rebuild-graph reset

help: ## Show this list
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: ## Create the virtualenv, install pinned dependencies, install frontend packages
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e "backend[dev]"
	cd frontend && npm install --no-audit --no-fund

up: ## Start postgres, neo4j, redis, backend, frontend; wait for healthchecks
	$(COMPOSE) up -d --wait
	$(COMPOSE) ps

down: ## Stop the stack, keep volumes
	$(COMPOSE) down

lint: ## ruff + the four law/boundary checks
	$(VENV)/bin/ruff check backend scripts
	$(VENV)/bin/ruff format --check backend scripts
	$(MAKE) laws
	cd frontend && npm run lint

laws: ## The enforcement scripts alone -- each proves itself, then scans (DEF-0001)
	@echo "--- self-tests: every law check must be observed to reject, not just to pass"
	$(PY) scripts/check_law_copies.py --self-test
	$(PY) scripts/check_domain_independence.py --self-test
	$(PY) scripts/check_layers.py --self-test
	$(PY) scripts/check_dependency_policy.py --self-test
	$(PY) scripts/check_governance_consistency.py --self-test
	@echo "--- scans"
	$(PY) scripts/check_law_copies.py
	$(PY) scripts/check_domain_independence.py
	$(PY) scripts/check_layers.py
	$(PY) scripts/check_dependency_policy.py
	$(PY) scripts/check_governance_consistency.py

typecheck: ## mypy --strict over the distribution, tsc --noEmit over the frontend
	cd backend && ../$(VENV)/bin/mypy
	cd frontend && npx tsc --noEmit

test: ## Full test suite with coverage reporting
	cd backend && ../$(VENV)/bin/pytest

test-fast: ## Skip anything marked slow and skip coverage instrumentation
	cd backend && ../$(VENV)/bin/pytest -m "not slow" --no-cov

bench: ## Measure the prd.md §55 performance targets
	@echo "prd.md §55 targets: load <30s, graph <60s, root-cause <3s, counterfactual <5s, recommendation <5s"
	$(PY) scripts/check_determinism.py || true
	@echo "NOT-YET-RUNNABLE: benchmarks land with the orchestration pipeline (P1 exit)."

rebuild-graph: ## Rebuild the Neo4j projection from PostgreSQL alone (ADR-0001)
	@test -n "$(RUN_ID)" || (echo "usage: make rebuild-graph RUN_ID=run:<hash>" && exit 1)
	$(PY) scripts/rebuild_graph.py --run-id "$(RUN_ID)"

reset: ## Destroy local state: containers, volumes, venv, caches, determinism scratch
	$(COMPOSE) down -v --remove-orphans
	rm -rf $(VENV) .determinism backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
	find backend scripts -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf frontend/node_modules frontend/.next
