.PHONY: help install lint test test-slow test-contract test-durations coverage docs docs-serve docs-build docs-cli docs-mcp build publish-client deps-upgrade clean dhis2-run dhis2-down dhis2-seed dhis2-build-e2e-dump dhis2-codegen-all dhis2-codegen-play dhis2-codegen-play-v42 dhis2-codegen-play-v43 verify-examples bridge-round bridge-bench cli-matrix composite-scenarios refresh-setup refresh-and-verify

UV := $(shell command -v uv 2> /dev/null)

# Silence Material for MkDocs' "Currently unlicensed" / MkDocs 2.0 build notice.
# https://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/
export NO_MKDOCS_2_WARNING := 1

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install          Sync workspace deps (all members, dev group included)"
	@echo "  lint             Run ruff format + ruff check + mypy + pyright"
	@echo "  test             Run tests (excludes slow)"
	@echo "  test-slow        Run slow tests only"
	@echo "  test-contract    Run live-schema contract tests against play.im.dhis2.org"
	@echo "  test-durations   Show 20 slowest tests"
	@echo "  coverage         Run tests with coverage reporting"
	@echo "  docs             Alias for docs-serve"
	@echo "  docs-serve       Serve mkdocs site locally at http://127.0.0.1:8000 (regens CLI ref first)"
	@echo "  docs-build       Build mkdocs site to ./site (regens CLI ref first)"
	@echo "  docs-cli         Regenerate docs/cli-reference.md from the Typer app"
	@echo "  docs-mcp         Regenerate docs/mcp-reference.md from the FastMCP server"
	@echo "  build            Build all workspace wheels"
	@echo "  publish-client   Upload dhis2w-client wheel to PyPI (requires UV_PUBLISH_TOKEN env)"
	@echo "  deps-upgrade     Re-resolve uv.lock to pick up newer versions"
	@echo ""
	@echo "  dhis2-run        Start the stack, seed auth, stream logs (Ctrl+C tears it down)"
	@echo "  dhis2-seed       (re-)seed PATs + OAuth2 client against an already-running stack"
	@echo "  dhis2-down       Stop the local DHIS2 stack"
	@echo "  dhis2-build-e2e-dump  Wipe + populate a fresh DHIS2 with test data, regenerate infra/v\$$(DHIS2_VERSION)/dump.sql.gz"
	@echo "  dhis2-codegen-all     Spin up DHIS2 41/42/43 in turn and regenerate each v{N}/ (~40 min; pass VERSIONS=\"41 42 43\" to narrow)"
	@echo "  dhis2-codegen-play    Refresh v42 + v43 generated/ trees against play.im.dhis2.org (no docker)"
	@echo "  verify-examples       Run every non-interactive example + print PASS/FAIL summary"
	@echo "  bridge-round          Drive dhis2w-mcp-bridge with a local LM Studio model (MODEL=, ROUND=read|write|bench, PROFILE=)"
	@echo "  bridge-bench          Benchmark the model roster over the bridge: read+write+perf (MODELS= to override)"
	@echo "  cli-matrix            Command x model matrix: how each roster model handles every CLI command (ARGS= to slice)"
	@echo "  composite-scenarios   Run composite write workflows (data set+elements, program+stages) oracle-style"
	@echo "  refresh-setup         Wipe + rebuild e2e dump + seed (no example verify — fast iteration on setup)"
	@echo "  refresh-and-verify    Rebuild dump + seed + run every example (turns the PR #125 ritual into one command)"
	@echo ""
	@echo "  For niche targets (versions, wait, status, logs, pat) use 'make -C infra help'."
	@echo ""
	@echo "  clean            Remove caches, build artifacts, coverage output"

install:
	@echo ">>> Syncing workspace"
	@$(UV) sync --all-packages --all-extras

lint:
	@echo ">>> Running linter"
	@$(UV) run ruff format .
	@$(UV) run ruff check . --fix
	@echo ">>> Running type checkers"
	@$(UV) run mypy --explicit-package-bases packages examples infra/scripts
	@$(UV) run pyright

test:
	@echo ">>> Running tests (excluding slow + contract)"
	@$(UV) run pytest -q -m "not slow and not contract" packages

test-contract:
	@echo ">>> Running live-schema contract tests against play.im.dhis2.org"
	@$(UV) run pytest -v -m contract packages

test-upstream-bugs:
	@echo ">>> Running upstream-bug regression tests (paired with BUGS.md entries)"
	@$(UV) run pytest -v -m upstream_bug packages

test-slow:
	@echo ">>> Running slow tests"
	@if [ -f infra/home/credentials/.env.auth ]; then \
		set -a; . infra/home/credentials/.env.auth; set +a; \
		$(UV) run pytest -v -m slow packages; \
	else \
		echo "    (no infra/home/credentials/.env.auth — integration tests that need it will skip; run 'make dhis2-run' first to populate it)"; \
		$(UV) run pytest -v -m slow packages; \
	fi

test-durations:
	@echo ">>> Running tests with 20 slowest"
	@$(UV) run pytest -q -m "not slow and not contract" --durations=20 packages

coverage:
	@echo ">>> Running tests with coverage"
	@$(UV) run coverage run -m pytest -q -m "not slow and not contract" packages
	@$(UV) run coverage report --fail-under=70
	@$(UV) run coverage xml

docs-cli:
	@echo ">>> Regenerating CLI reference from the Typer app"
	@$(UV) run typer dhis2w_cli.main utils docs --name dhis2 --title "CLI reference" --output docs/cli-reference.md
	@echo "    wrote docs/cli-reference.md"

docs-mcp:
	@echo ">>> Regenerating MCP tool reference from the FastMCP server"
	@$(UV) run python infra/scripts/gen_mcp_reference.py

docs-serve: docs-cli docs-mcp
	@echo ">>> Serving docs at http://127.0.0.1:8000"
	@$(UV) run mkdocs serve

docs-build: docs-cli docs-mcp
	@echo ">>> Building docs site (strict — broken links / missing nav fail the build)"
	@$(UV) run mkdocs build --strict

docs: docs-serve

build:
	@echo ">>> Building all workspace wheels"
	@$(UV) build --all-packages

publish-client:
	@echo ">>> Building dhis2w-client wheel"
	@$(UV) build --package dhis2w-client
	@echo ">>> Publishing dhis2w-client to PyPI (dry-run, set PUBLISH=1 + UV_PUBLISH_TOKEN to actually upload)"
	@if [ "$(PUBLISH)" = "1" ]; then \
		$(UV) publish dist/dhis2w_client-*.whl dist/dhis2w_client-*.tar.gz; \
	else \
		echo "    (skipped upload; run 'make publish-client PUBLISH=1' to push)"; \
	fi
	@echo ""
	@echo "Note: 'make publish-client' is for local emergencies only. The canonical flow"
	@echo "is to tag vX.Y.Z and push — .github/workflows/pypi-publish.yml builds and"
	@echo "uploads every dhis2w-* package via PyPI Trusted Publishing (no token needed)."

deps-upgrade:
	@echo ">>> Upgrading all resolvable deps (uv lock --upgrade)"
	@$(UV) lock --upgrade
	@echo ">>> Re-syncing workspace with updated lock"
	@$(UV) sync --all-packages --all-extras

dhis2-run:
	@DHIS2_VERSION=$(or $(DHIS2_VERSION),43) infra/scripts/dhis2_run.sh

dhis2-seed:
	@$(MAKE) -C infra seed

dhis2-down:
	@$(MAKE) -C infra down

dhis2-build-e2e-dump:
	@$(MAKE) -C infra build-e2e-dump DHIS2_VERSION=$(or $(DHIS2_VERSION),43)

dhis2-codegen-all:
	@infra/scripts/codegen_all_versions.sh $(VERSIONS)

dhis2-codegen-play-v42:
	@echo ">>> Refreshing generated/v42 from play.im.dhis2.org/dev-2-42"
	@$(UV) run dhis2 dev codegen generate --url https://play.im.dhis2.org/dev-2-42 --username admin --password district

dhis2-codegen-play-v43:
	@echo ">>> Refreshing generated/v43 from play.im.dhis2.org/dev-2-43"
	@$(UV) run dhis2 dev codegen generate --url https://play.im.dhis2.org/dev-2-43 --username admin --password district

dhis2-codegen-play: dhis2-codegen-play-v42 dhis2-codegen-play-v43

refresh-analytics:
	@echo ">>> Refreshing analytics tables (blocks until ANALYTICS_TABLE task completes)"
	@if [ -f infra/home/credentials/.env.auth ]; then \
		set -a; . infra/home/credentials/.env.auth; set +a; \
		$(UV) run dhis2 maintenance refresh analytics --watch --timeout 600; \
	else \
		$(UV) run dhis2 maintenance refresh analytics --watch --timeout 600; \
	fi

verify-examples:
	@echo ">>> Running every non-interactive example against profile $${DHIS2_PROFILE:-local_basic} (DHIS2 v$(or $(DHIS2_VERSION),42))"
	@if [ -f infra/home/credentials/.env.auth ]; then \
		set -a; . infra/home/credentials/.env.auth; set +a; \
		DHIS2_VERSION=$(or $(DHIS2_VERSION),42) $(UV) run python infra/scripts/verify_examples.py; \
	else \
		echo "    note: infra/home/credentials/.env.auth missing — env-dependent examples (profile_crud.py) will fail"; \
		DHIS2_VERSION=$(or $(DHIS2_VERSION),42) $(UV) run python infra/scripts/verify_examples.py; \
	fi

bridge-round:
	@echo ">>> Bridge test round: MODEL=$(or $(MODEL),google/gemma-4-12b-qat) ROUND=$(or $(ROUND),read) PROFILE=$(or $(PROFILE),play42)"
	@echo "    (reads -> play42 readonly; writes -> local_basic. See docs/notes/small-model-bridge.md)"
	@lms server start >/dev/null 2>&1 || true
	@lms ps 2>/dev/null | grep -qF "$(or $(MODEL),google/gemma-4-12b-qat)" \
		|| lms load $(or $(MODEL),google/gemma-4-12b-qat) --gpu max --ttl 3600 -y
	@$(UV) run python infra/scripts/bridge_round.py \
		--model $(or $(MODEL),google/gemma-4-12b-qat) \
		--round $(or $(ROUND),read) \
		--profile $(or $(PROFILE),$(if $(filter write,$(ROUND)),local_basic,play42))

bridge-bench:
	@echo ">>> Bridge model benchmark (roster in infra/scripts/bench_bridge_models.py)"
	@echo "    reads -> play42 (read-only), writes -> local_basic; loads/unloads each model itself."
	@echo "    Override the roster: make bridge-bench MODELS=\"qwen2.5-7b-instruct google/gemma-4-e4b\""
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python infra/scripts/bench_bridge_models.py $(MODELS)

composite-scenarios:
	@echo ">>> Composite write-workflow scenarios (oracle: create -> verify -> cleanup on local_basic)"
	@$(UV) run python infra/scripts/composite_scenarios.py $(ARGS)

cli-matrix:
	@echo ">>> CLI command x model matrix (how each roster model handles every command; read-only on play42)"
	@echo "    Streaming + resumable. Slice it: make cli-matrix ARGS=\"--group metadata --models google/gemma-4-12b-qat\""
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python infra/scripts/cli_matrix.py $(ARGS)

refresh-setup:
	@echo ">>> [1/2] Rebuilding e2e dump (wipes + reseeds the stack)"
	@$(MAKE) dhis2-build-e2e-dump
	@echo ">>> [2/2] Seeding PATs + OAuth2 client (writes .env.auth)"
	@$(MAKE) -C infra seed
	@echo ">>> Setup complete — run 'make verify-examples' to exercise the example suite"

refresh-and-verify:
	@echo ">>> [1/3] Rebuilding e2e dump (wipes + reseeds the stack)"
	@$(MAKE) dhis2-build-e2e-dump
	@echo ">>> [2/3] Seeding PATs + OAuth2 client (writes .env.auth)"
	@$(MAKE) -C infra seed
	@echo ">>> [3/3] Verifying every non-interactive example (DHIS2 v$(or $(DHIS2_VERSION),42))"
	@set -a; . infra/home/credentials/.env.auth; set +a; \
		DHIS2_VERSION=$(or $(DHIS2_VERSION),42) $(UV) run python infra/scripts/verify_examples.py

clean:
	@echo ">>> Cleaning"
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .coverage htmlcov coverage.xml
	@rm -rf .pyright
	@rm -rf dist build site

.DEFAULT_GOAL := help
