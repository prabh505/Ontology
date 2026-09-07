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
.PHONY: help setup doctor up down verify lint typecheck laws test test-fast bench import recommend \
        events rules root-cause migrate migrate-down migrate-status rebuild-graph \
        verify-projection reset

help: ## Show this list
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: ## Create the virtualenv, install pinned dependencies, install frontend packages
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e "backend[dev]"
	cd frontend && npm install --no-audit --no-fund

doctor: ## Check the container runtime and host ports before starting anything
	$(PYTHON) scripts/check_stack_preflight.py

# `doctor` first, deliberately. Without it the dominant failure is Neo4j being OOM-killed
# during startup, which surfaces as `exit 137` -- an exit code that reads like a
# configuration error and is not one. The preflight names the cause and the remedy instead.
# It uses $(PYTHON), not the venv, so `make up` works before `make setup` has ever run.
up: doctor ## Start postgres, neo4j, redis, backend, frontend; wait for healthchecks
	$(COMPOSE) up -d --wait
	$(COMPOSE) ps

down: ## Stop the stack, keep volumes
	$(COMPOSE) down

verify: lint typecheck test ## Every repository gate, in one command

lint: ## ruff + every law/boundary check, frontend included
	$(VENV)/bin/ruff check backend scripts
	$(VENV)/bin/ruff format --check backend scripts
	$(MAKE) laws
	cd frontend && npm run lint

laws: ## The enforcement scripts alone -- each proves itself, then scans (DEF-0001)
	@echo "--- self-tests: every law check must be observed to reject, not just to pass"
	$(PY) scripts/check_law_copies.py --self-test
	$(PY) scripts/check_domain_independence.py --self-test
	$(PY) scripts/check_confidence_is_a_vector.py --self-test
	$(PY) scripts/check_layers.py --self-test
	$(PY) scripts/check_dependency_policy.py --self-test
	$(PY) scripts/check_governance_consistency.py --self-test
	$(PY) scripts/check_metrics_are_declared.py --self-test
	$(PY) scripts/check_migration_pairs.py --self-test
	$(PY) scripts/check_rule_pack.py --self-test
	$(PY) scripts/check_projection_drift.py --self-test
	$(PY) scripts/export_ontology_schema.py --self-test
	@echo "--- scans"
	$(PY) scripts/check_law_copies.py
	$(PY) scripts/check_domain_independence.py
	$(PY) scripts/check_confidence_is_a_vector.py
	$(PY) scripts/check_layers.py
	$(PY) scripts/check_dependency_policy.py
	$(PY) scripts/check_governance_consistency.py
	$(PY) scripts/check_migration_pairs.py
# Exit 2 = NOT-RUNNABLE while a domain has no rule pack, and the script says which. The
# DataCo pack exists, so this is a real scan today; the tolerance is here for a domain
# onboarded before its rule pack is written (docs/ontology.md §4 step 10).
	$(PY) scripts/check_rule_pack.py --dataset dataco --no-write || test $$? -eq 2
# The exit-2 tolerance that stood here is GONE, as its own comment instructed: it was for
# "while every reasoning package is scaffold", and the scan now covers 84 files across five
# packages including modules 11 and 12. A tolerated exit code outlives its reason silently,
# so it is removed in the commit that made it unnecessary rather than left to be found.
	$(PY) scripts/check_metrics_are_declared.py
	$(PY) scripts/export_ontology_schema.py --check

typecheck: ## mypy --strict over the distribution, tsc --noEmit over the frontend
	cd backend && ../$(VENV)/bin/mypy
	cd frontend && npx tsc --noEmit

test: ## Full test suite with coverage reporting
	cd backend && ../$(VENV)/bin/pytest

test-fast: ## Skip anything marked slow and skip coverage instrumentation
	cd backend && ../$(VENV)/bin/pytest -m "not slow" --no-cov

import: ## Import a dataset: pin it, validate the mapping, measure it, write the report
	@test -n "$(DATASET)" || (echo "usage: make import DATASET=dataco [PROPOSE=1]" && exit 1)
	$(PY) scripts/import_dataset.py --dataset "$(DATASET)" $(if $(PROPOSE),--propose)

events: ## Expand a clean layer into entities and events; write both reports
	@test -n "$(DATASET)" || (echo "usage: make events DATASET=dataco [EVENTS=path/to/events.jsonl]" && exit 1)
	$(PY) scripts/build_event_log.py --dataset "$(DATASET)" $(if $(EVENTS),--write-events "$(EVENTS)")

rules: ## Check a domain's rule pack against its ontology and write the coverage report
	@test -n "$(DATASET)" || (echo "usage: make rules DATASET=dataco" && exit 1)
	$(PY) scripts/check_rule_pack.py --dataset "$(DATASET)"

root-cause: ## Run modules 11 and 12 and the pattern miner; write both standings' reports
	@test -n "$(DATASET)" || (echo "usage: make root-cause DATASET=dataco [ROWS=150]" && exit 1)
	$(PY) scripts/analyze_root_causes.py --dataset "$(DATASET)" $(if $(ROWS),--rows "$(ROWS)")

counterfactual: ## Run module 13 on prd.md §11's worked example; write both standings' reports
	@test -n "$(DATASET)" || (echo "usage: make counterfactual DATASET=dataco [ROWS=150]" && exit 1)
	$(PY) scripts/simulate_counterfactuals.py --dataset "$(DATASET)" $(if $(ROWS),--rows "$(ROWS)")

recommend: ## Run module 14; write both standings' recommendation reports
	@test -n "$(DATASET)" || (echo "usage: make recommend DATASET=dataco [ROWS=150]" && exit 1)
	$(PY) scripts/recommend_interventions.py --dataset "$(DATASET)" $(if $(ROWS),--rows "$(ROWS)")

bench: ## Measure the prd.md §55 performance targets
	@echo "prd.md §55 targets: load <30s, graph <60s, root-cause <3s, counterfactual <5s, recommendation <5s"
	$(PY) scripts/check_determinism.py || true
# The root-cause budget is REAL as of modules 11 and 12. It is measured over a graph built
# at the scale of the committed bounded run, which is 150 rows of 180,519 -- the test prints
# that gap beside its number rather than letting the figure be read as a dataset-scale one
# (OQ-023). `-s` is deliberate: a benchmark whose number nobody can read is one nobody reads.
	cd backend && ../$(VENV)/bin/pytest tests/integration/test_root_cause_budget.py -q -s --no-cov
# The counterfactual budget is REAL as of module 13, and is measured over a graph built at
# the same slice scale for the same reason: the committed promoted graph has zero edges, so
# a query over it would pass on having no work to do (R-22).
	cd backend && ../$(VENV)/bin/pytest tests/integration/test_counterfactual_budget.py -q -s --no-cov
# The recommendation budget is REAL as of module 14, at the same slice scale and with the
# same caveat. It is the widest of the three: a recommendation run simulates once per
# candidate and again per multi-node set, so the pack's declared caps are what keep it
# inside the budget rather than an implementation detail -- the test prints them.
	cd backend && ../$(VENV)/bin/pytest tests/integration/test_recommendation_budget.py -q -s --no-cov
	@echo "STILL NOT-RUNNABLE: the load and graph budgets."

# `make up` deliberately does NOT migrate. The PostgreSQL init directory applies *.sql
# without writing the migration ledger, which leaves a schema that exists and a ledger that
# says nothing has been applied -- and the disagreement stays invisible until a later
# migration fails on an object it did not create (ADR-0033).
migrate: ## Apply pending migrations (TARGET=NNNN to stop at one)
	$(PY) scripts/migrate.py $(if $(TARGET),--target $(TARGET))

migrate-down: ## Reverse migrations back to TARGET (required; 0000 empties the schema)
	@test -n "$(TARGET)" || (echo "usage: make migrate-down TARGET=NNNN (0000 = empty)" && exit 1)
	$(PY) scripts/migrate.py --down --target "$(TARGET)"

migrate-status: ## Show which migrations are applied and which are pending
	$(PY) scripts/migrate.py --status

rebuild-graph: ## Rebuild the Neo4j projection from PostgreSQL alone (ADR-0001)
	@test -n "$(RUN_ID)" || (echo "usage: make rebuild-graph RUN_ID=run:<hash>" && exit 1)
	$(PY) scripts/rebuild_graph.py --run-id "$(RUN_ID)"

verify-projection: ## Report drift between the facts and the derived graph, without repairing
	@test -n "$(RUN_ID)" || (echo "usage: make verify-projection RUN_ID=run:<hash>" && exit 1)
	$(PY) scripts/check_projection_drift.py --run-id "$(RUN_ID)"

reset: ## Destroy local state: containers, volumes, venv, caches, determinism scratch
	$(COMPOSE) down -v --remove-orphans
	rm -rf $(VENV) .determinism backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
	find backend scripts -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf frontend/node_modules frontend/.next
