# Makefile

define HELP_MESSAGE
firmware

# Installing

1. Create/Update Conda env and install dev deps: `make setup`
2. Activate the environment: `conda activate firmware`

# Running Tests

1. Run autoformatting: `make format`
2. Run static checks: `make static-checks`
3. Run unit tests: `make test`

endef
export HELP_MESSAGE

all:
	@echo "$$HELP_MESSAGE"
.PHONY: all

# ------------------------ #
#        PyPI Build        #
# ------------------------ #

build-for-pypi:
	@pip install --verbose build wheel twine
	@python -m build --sdist --wheel --outdir dist/ .
	@twine upload dist/*
.PHONY: build-for-pypi

push-to-pypi: build-for-pypi
	@twine upload dist/*
.PHONY: push-to-pypi

# ------------------------ #
#       Static Checks      #
# ------------------------ #

py-files := $(shell find . -name '*.py')

format:
	@ruff format $(py-files)
	@ruff check --fix $(py-files)
.PHONY: format

static-checks:
	@ruff check $(py-files)
	@mypy --install-types --non-interactive $(py-files)
.PHONY: lint

# ------------------------ #
#        Unit tests        #
# ------------------------ #

test:
	python -m pytest
.PHONY: test

# ------------------------ #
#     Conda Environment    #
# ------------------------ #

ENV ?= firmware

conda-create:
	bash scripts/setup-conda.sh $(ENV)
.PHONY: conda-create

conda-update:
	bash scripts/setup-conda.sh $(ENV)
.PHONY: conda-update

install-dev:
	@pip install -e .[dev]
.PHONY: install-dev

setup: conda-create
.PHONY: setup
