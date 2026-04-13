.PHONY: help
help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Commands

.PHONY: setup
setup: ## Install dependencies and pre-commit hooks
	@uv sync --all-groups
	@uv run pre-commit install
	@uv run playwright install chromium

.PHONY: lint
lint: ## Run linter
	@echo Running lint...
	@uv run ruff check --fix .
	@echo Done

.PHONY: format
format: ## Run formatter
	@echo Running formatter...
	@uv run ruff format .
	@echo Done

.PHONY: pretty
pretty:  ## Run linter and formatter
	@make format
	@make lint

.PHONY: test
test:  ## Run tests
	@uv run pytest -v -n 4
