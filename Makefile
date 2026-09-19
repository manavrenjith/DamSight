.PHONY: all setup ingest run-site ensemble surrogate evac precompute demo test lint help

all: help

help:
	@echo "DamSight Makefile Commands:"
	@echo "  make setup        - Install package in editable mode"
	@echo "  make test         - Run test suite"
	@echo "  make lint         - Run code linter"
	@echo "  make ingest       - Ingest terrain and exposure datasets"
	@echo "  make run-site     - Run hydrodynamic simulation for site"
	@echo "  make ensemble     - Run Monte Carlo ensemble"
	@echo "  make surrogate    - Train ML surrogate model"
	@echo "  make evac         - Run evacuation routing analysis"
	@echo "  make precompute   - Generate precomputed demo outputs"
	@echo "  make demo         - Launch API server and web dashboard"

setup:
	python -m pip install -e .

test:
	pytest tests/

lint:
	python -m ruff check src/ tests/ || echo "Lint check finished"

ingest:
	python scripts/run_site.py --site site_a --stage ingest --allow-synthetic

run-site:
	@echo "not implemented yet"

ensemble:
	@echo "not implemented yet"

surrogate:
	@echo "not implemented yet"

evac:
	@echo "not implemented yet"

precompute:
	@echo "not implemented yet"

demo:
	@echo "not implemented yet"
