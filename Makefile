.PHONY: install dev test lint build clean

install:  ## Install the package
	pip install .

dev:  ## Install in editable mode with dev dependencies
	pip install -e ".[dev,pdf]"

test:  ## Run tests
	pytest tests/ -v --tb=short

lint:  ## Run linters
	flake8 bjam_toolbox --max-line-length=120
	black --check bjam_toolbox

format:  ## Auto-format code
	black bjam_toolbox

build:  ## Build sdist and wheel
	python -m build

clean:  ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info bjam_toolbox.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
