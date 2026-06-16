.PHONY: help install lint check-examples test test-slow test-contract test-durations coverage docs docs-serve docs-build docs-cli docs-mcp build publish-client deps-upgrade clean dhis2-run dhis2-down dhis2-seed dhis2-build-e2e-dump dhis2-codegen-all dhis2-codegen-play dhis2-codegen-play-v42 dhis2-codegen-play-v43 verify-examples bench-list bench-round bench-bridge bench-general bench-mcp bench-validate bench-matrix bench-composite refresh-setup refresh-and-verify

UV := $(shell command -v uv 2> /dev/null)

# Silence Material for MkDocs' "Currently unlicensed" / MkDocs 2.0 build notice.
# https://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/
export NO_MKDOCS_2_WARNING := 1

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Development:"
	@echo "  install          Sync workspace deps (all members, dev group included)"
	@echo "  lint             Run ruff format + ruff check + mypy + pyright"
	@echo "  test             Run tests (excludes slow)"
	@echo "  test-slow        Run slow tests only"
	@echo "  test-contract    Run live-schema contract tests against play.im.dhis2.org"
	@echo "  test-durations   Show 20 slowest tests"
	@echo "  coverage         Run tests with coverage reporting"
	@echo "  build            Build all workspace wheels"
	@echo "  publish-client   Upload dhis2w-client wheel to PyPI (requires UV_PUBLISH_TOKEN env)"
	@echo "  deps-upgrade     Re-resolve uv.lock to pick up newer versions"
	@echo "  clean            Remove caches, build artifacts, coverage output"
	@echo ""
	@echo "Docs:"
	@echo "  docs             Alias for docs-serve"
	@echo "  docs-serve       Serve mkdocs site locally at http://127.0.0.1:8000 (regens CLI ref first)"
	@echo "  docs-build       Build mkdocs site to ./site (regens CLI ref first)"
	@echo "  docs-cli         Regenerate docs/cli-reference.md from the Typer app"
	@echo "  docs-mcp         Regenerate docs/mcp-reference.md from the FastMCP server"
	@echo ""
	@echo "DHIS2 local stack:"
	@echo "  dhis2-run        Start the stack, seed auth, stream logs (Ctrl+C tears it down)"
	@echo "  dhis2-seed       (re-)seed PATs + OAuth2 client against an already-running stack"
	@echo "  dhis2-down       Stop the local DHIS2 stack"
	@echo "  dhis2-build-e2e-dump  Wipe + populate a fresh DHIS2 with test data, regenerate infra/v\$$(DHIS2_VERSION)/dump.sql.gz"
	@echo "  refresh-setup         Wipe + rebuild e2e dump + seed (no example verify — fast iteration on setup)"
	@echo "  refresh-and-verify    Rebuild dump + seed + run every example (turns the PR #125 ritual into one command)"
	@echo ""
	@echo "Code generation + examples:"
	@echo "  dhis2-codegen-all     Spin up DHIS2 41/42/43 in turn and regenerate each v{N}/ (~40 min; pass VERSIONS=\"41 42 43\" to narrow)"
	@echo "  dhis2-codegen-play    Refresh v42 + v43 generated/ trees against play.im.dhis2.org (no docker)"
	@echo "  verify-examples       Run every non-interactive example + print PASS/FAIL summary"
	@echo ""
	@echo "Model testing (local LLMs; reads -> play42, writes -> local_basic; no model defaults):"
	@echo "  bench-list       List the models the backend has installed (pick from these)"
	@echo "  bench-validate   Validate ONE model across both axes: general + bridge (MODEL= required)"
	@echo "  bench-general    Axis 1 — general capability: python+cli+tooling, no DHIS2 (MODELS= required; BENCH_MAX_TOKENS=, BENCH_CHAMPION=)"
	@echo "  bench-bridge     Axis 2 — benchmark named models over the bridge: read+write+perf (MODELS= required; BENCH_CHAMPION=)"
	@echo "  bench-mcp        Full dhis2-mcp server (~311 tools), read+write (MODELS= required; BENCH_CONTEXT=128K)"
	@echo "  bench-round      Drive dhis2w-mcp-bridge with one local model (MODEL= required; ROUND=read|write|bench, PROFILE=)"
	@echo "  bench-matrix     Command x model matrix: how each model handles every CLI command (ARGS= to slice)"
	@echo "  bench-composite  Run composite write workflows (data set+elements, program+stages) oracle-style"
	@echo ""
	@echo "  For niche targets (versions, wait, status, logs, pat) use 'make -C infra help'."

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

check-examples:
	@echo ">>> Checking per-version example sync (v42 baseline -> v41 + v43)"
	@$(UV) run python -u infra/scripts/check_examples_sync.py
	@echo ">>> Checking example CLI commands + MCP tool references resolve"
	@$(UV) run python -u infra/scripts/check_example_refs.py

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
	@$(UV) run typer dhis2w_cli.main utils docs --name d2w --title "CLI reference" --output docs/cli-reference.md
	@echo "    wrote docs/cli-reference.md"

docs-mcp:
	@echo ">>> Regenerating MCP tool reference from the FastMCP server"
	@$(UV) run python -u infra/scripts/gen_mcp_reference.py

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
	@$(UV) run d2w dev codegen generate --url https://play.im.dhis2.org/dev-2-42 --username admin --password district

dhis2-codegen-play-v43:
	@echo ">>> Refreshing generated/v43 from play.im.dhis2.org/dev-2-43"
	@$(UV) run d2w dev codegen generate --url https://play.im.dhis2.org/dev-2-43 --username admin --password district

dhis2-codegen-play: dhis2-codegen-play-v42 dhis2-codegen-play-v43

refresh-analytics:
	@echo ">>> Refreshing analytics tables (blocks until ANALYTICS_TABLE task completes)"
	@if [ -f infra/home/credentials/.env.auth ]; then \
		set -a; . infra/home/credentials/.env.auth; set +a; \
		$(UV) run d2w maintenance refresh analytics --watch --timeout 600; \
	else \
		$(UV) run d2w maintenance refresh analytics --watch --timeout 600; \
	fi

verify-examples:
	@echo ">>> Running every non-interactive example against profile $${DHIS2_PROFILE:-local_basic} (DHIS2 v$(or $(DHIS2_VERSION),42))"
	@if [ -f infra/home/credentials/.env.auth ]; then \
		set -a; . infra/home/credentials/.env.auth; set +a; \
		DHIS2_VERSION=$(or $(DHIS2_VERSION),42) $(UV) run python -u infra/scripts/verify_examples.py; \
	else \
		echo "    note: infra/home/credentials/.env.auth missing — env-dependent examples (profile_crud.py) will fail"; \
		DHIS2_VERSION=$(or $(DHIS2_VERSION),42) $(UV) run python -u infra/scripts/verify_examples.py; \
	fi

bench-list:
	@echo ">>> Installed models (the backend's view; MODEL_BACKEND= to switch)"
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u infra/scripts/_model_backend.py

bench-round:
	@test -n "$(MODEL)" || { echo "usage: make bench-round MODEL=<key> [ROUND=read|write|bench] [PROFILE=]  (see 'make bench-list')"; exit 2; }
	@echo ">>> Bridge test round: MODEL=$(MODEL) ROUND=$(or $(ROUND),read) PROFILE=$(or $(PROFILE),play42)"
	@echo "    (reads -> play42 readonly; writes -> local_basic. See docs/notes/small-model-bridge.md)"
	@lms server start >/dev/null 2>&1 || true
	@lms ps 2>/dev/null | grep -qF "$(MODEL)" || lms load $(MODEL) --gpu max --ttl 3600 -y
	@$(UV) run python -u infra/scripts/bridge_round.py \
		--model $(MODEL) \
		--round $(or $(ROUND),read) \
		--profile $(or $(PROFILE),$(if $(filter write,$(ROUND)),local_basic,play42))

bench-bridge:
	@test -n "$(MODELS)" || { echo "usage: make bench-bridge MODELS=\"<key> [<key> ...]\"  (no default; see 'make bench-list')"; exit 2; }
	@echo ">>> Bridge model benchmark: read -> play42 (read-only), write -> local_basic; one model at a time."
	@echo "    The write round needs local_basic up — run 'make dhis2-run' first if it isn't."
	@echo "    Name an oracle with BENCH_CHAMPION=<key> to enable the SUSPECT-task check."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u infra/scripts/bench_bridge_models.py $(MODELS)

bench-general:
	@test -n "$(MODELS)" || { echo "usage: make bench-general MODELS=\"<key> [<key> ...]\"  (no default; see 'make bench-list')"; exit 2; }
	@echo ">>> General-capability benchmark (axis 1: python + cli + tooling; no DHIS2). One model = single test;"
	@echo "    several = side-by-side comparison. BENCH_MAX_TOKENS= tightens the budget; BENCH_CHAMPION= sets an oracle."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u infra/scripts/bench_general_models.py $(MODELS)

bench-mcp:
	@test -n "$(MODELS)" || { echo "usage: make bench-mcp MODELS=\"<key> [<key> ...]\"  (no default; see 'make bench-list')"; exit 2; }
	@echo ">>> Full-MCP benchmark: the model drives the whole dhis2-mcp server (~311 tools) read + write."
	@echo "    Loads each model at BENCH_CONTEXT (default 128K) — the tool payload is ~49k tokens."
	@echo "    Read round = play42 with READ-ONLY tools only (the server has no readonly guard); write = local_basic."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u infra/scripts/bench_mcp_models.py $(MODELS)

bench-validate:
	@test -n "$(MODEL)" || { echo "usage: make bench-validate MODEL=<key>   (e.g. google/gemma-4-12b-qat)"; exit 2; }
	@echo ">>> Validate $(MODEL) across both axes"
	@echo ">>> Axis 1 — general (python + cli + tooling)"
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u infra/scripts/bench_general_models.py $(MODEL)
	@echo ">>> Axis 2 — bridge (read + write); write round needs local_basic up (make dhis2-run)"
	@$(UV) run python -u infra/scripts/bench_bridge_models.py $(MODEL)

bench-composite:
	@echo ">>> Composite write-workflow scenarios (oracle: create -> verify -> cleanup on local_basic)"
	@$(UV) run python -u infra/scripts/composite_scenarios.py $(ARGS)

bench-matrix:
	@echo ">>> CLI command x model matrix (how each roster model handles every command; read-only on play42)"
	@echo "    Streaming + resumable. Slice it: make bench-matrix ARGS=\"--group metadata --models google/gemma-4-12b-qat\""
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u infra/scripts/cli_matrix.py $(ARGS)

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
		DHIS2_VERSION=$(or $(DHIS2_VERSION),42) $(UV) run python -u infra/scripts/verify_examples.py

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
