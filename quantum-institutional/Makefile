.PHONY: help install test lint typecheck verify api all
PY ?= python3

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

install:  ## Install dev dependencies
	$(PY) -m pip install -e ".[api,dev]"

test:  ## Run the full suite
	$(PY) -m pytest

lint:  ## Ruff lint + format check
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

typecheck:  ## mypy strict over src/
	$(PY) -m mypy

verify:  ## Vendored Quantum 5.0 artefacts still byte-identical
	cd reference/quantum_5_0 && sha256sum -c MANIFEST.sha256

api:  ## Run the API locally
	$(PY) -m uvicorn quantum_institutional.api.app:app --reload --app-dir src

all: verify lint typecheck test  ## Everything CI runs
