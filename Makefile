.PHONY: help install lint check-examples test test-slow test-contract test-durations coverage frontend-dev build-frontend lint-frontend test-frontend e2e-frontend docs docs-serve docs-build docs-cli docs-mcp docs-d2path build publish-all deps-upgrade clean clean-artifacts dhis2-run dhis2-down dhis2-seed dhis2-versions-check dhis2-versions-bump dhis2-build-e2e-dump dhis2-codegen-all dhis2-codegen-play dhis2-codegen-play-v42 dhis2-codegen-play-v43 verify-examples verify-igs bench-list bench-round bench-bridge bench-general bench-mcp bench-router bench-claude-general bench-claude-mcp bench-claude-bridge bench-validate bench-matrix bench-composite bench-longcontext refresh-setup refresh-and-verify

UV := $(shell command -v uv 2> /dev/null)

# The capture UI. It is the one part of this workspace that needs node, and it is
# deliberately kept out of `make lint` / `make test` so those stay a pure-Python run
# on a machine with no node at all. CI runs these targets in their own workflow,
# .github/workflows/frontend.yml, path-filtered to the package that owns the UI.
FRONTEND_DIR := packages/dhis2w-fhir-serve/frontend
# Where a running `d2w fhir serve` is, for the dev server to proxy FHIR calls to.
# Match `[serve] port` in the project you are serving.
SERVE_TARGET ?= http://127.0.0.1:8080

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
	@echo "  build            Build all workspace wheels (run build-frontend first, or the wheel ships no UI)"
	@echo "  publish-<member> Build + upload one dhis2w-<member> to PyPI (requires UV_PUBLISH_TOKEN env)"
	@echo "                   Members: $(PUBLISHABLE_MEMBERS)"
	@echo "  publish-all      Upload every publishable member in dependency order (same token)"
	@echo "  deps-upgrade     Re-resolve uv.lock to pick up newer versions"
	@echo "  clean            Remove caches, build artifacts, coverage output, and run artifacts"
	@echo "  clean-artifacts  Remove run artifacts alone: reports, screenshots, browser state"
	@echo ""
	@echo "Capture UI (needs node + pnpm; not part of lint/test):"
	@echo "  frontend-dev     Vite dev server, proxying FHIR calls to \$$(SERVE_TARGET) (default :8080)"
	@echo "  build-frontend   Build the React app into dhis2w-fhir-serve's static/ (run before 'make build')"
	@echo "  lint-frontend    oxlint + tsc --noEmit over the frontend"
	@echo "  test-frontend    vitest run over the frontend"
	@echo "  e2e-frontend     Playwright specs against a real 'd2w fhir serve --ui' on :8377"
	@echo "                   (prereqs, not run for you: 'make build-frontend' and"
	@echo "                    'cd $(FRONTEND_DIR) && pnpm exec playwright install chromium')"
	@echo ""
	@echo "Docs:"
	@echo "  docs             Alias for docs-serve"
	@echo "  docs-serve       Serve mkdocs site locally at http://127.0.0.1:8000 (regens CLI ref first)"
	@echo "  docs-build       Build mkdocs site to ./site (regens CLI ref first)"
	@echo "  docs-cli         Regenerate docs/cli-reference.md from the Typer app"
	@echo "  docs-mcp         Regenerate docs/mcp-reference.md from the FastMCP server"
	@echo "  docs-d2path      Regenerate docs/query/d2path-examples.md from the d2path catalog"
	@echo ""
	@echo "DHIS2 local stack:"
	@echo "  dhis2-run        Start the stack, seed auth, stream logs (Ctrl+C tears it down)"
	@echo "  dhis2-seed       (re-)seed PATs + OAuth2 client against an already-running stack"
	@echo "  dhis2-down       Stop the local DHIS2 stack"
	@echo "  dhis2-versions-check  Show whether any pinned DHIS2 minor is behind the latest Docker Hub patch"
	@echo "  dhis2-versions-bump   Rewrite versions.env to the latest patch for each non-held minor (then regenerate codegen)"
	@echo "  dhis2-build-e2e-dump  Wipe + populate a fresh DHIS2 with test data, regenerate infra/\$$(DHIS2_VERSION)/dump.sql.gz"
	@echo "  refresh-setup         Wipe + rebuild e2e dump + seed (no example verify — fast iteration on setup)"
	@echo "  refresh-and-verify    Rebuild dump + seed + refresh analytics + run every example"
	@echo ""
	@echo "Code generation + examples:"
	@echo "  dhis2-codegen-all     Spin up DHIS2 v41/v42/v43 in turn and regenerate each v{N}/ (~40 min; pass VERSIONS=\"v41 v42 v43\" to narrow)"
	@echo "  dhis2-codegen-play    Refresh v42 + v43 generated/ trees against play.im.dhis2.org (no docker)"
	@echo "  verify-examples       Run every non-interactive example + print PASS/FAIL summary"
	@echo "  verify-igs            Refresh, validate, generate + dockerized SUSHI compile every example IG (on demand; needs docker)"
	@echo ""
	@echo "Model testing (local LLMs; reads -> play42, writes -> local_basic; no model defaults):"
	@echo "  bench-list       List the models the backend has installed (pick from these)"
	@echo "  bench-validate   Validate ONE model across both axes: general + bridge (MODEL= required)"
	@echo "  bench-general    Axis 1 — general capability: python+cli+tooling, no DHIS2 (MODELS= required; BENCH_MAX_TOKENS=, BENCH_ORACLE=)"
	@echo "  bench-bridge     Axis 2 — benchmark named models over the bridge: read+write+perf (MODELS= required; BENCH_ORACLE=)"
	@echo "  bench-mcp        Full dhis2-mcp server (~311 tools), read+write (MODELS= required; BENCH_CONTEXT=128K)"
	@echo "  bench-router     Local models over the dhis2w-mcp-router (search+dispatch), read suite at small context (MODELS= required; BENCH_CONTEXT=16K)"
	@echo "  bench-claude-general Cloud Claude on the coding suite: python+cli+tooling, no DHIS2 (MODELS= optional; ambient subscription auth)"
	@echo "  bench-claude-mcp Cloud Claude over full dhis2-mcp via Agent SDK, read suite on play42 (MODELS= optional; ambient subscription auth)"
	@echo "  bench-claude-bridge Cloud Claude over the dhis2_cli bridge: read+write+composite (MODELS= optional; RUNS= composite reps; needs make dhis2-run)"
	@echo "  bench-round      Drive dhis2w-mcp-bridge with one local model (MODEL= required; ROUND=read|write|bench, PROFILE=)"
	@echo "  bench-matrix     Command x model matrix: how each model handles every CLI command (ARGS= to slice)"
	@echo "  bench-composite  Hard multi-object writes (data set+elements, program+stages): no MODELS = oracle; MODELS= drives models (RUNS=3, pass-rate)"
	@echo "  bench-longcontext Needle-in-a-haystack retrieval at increasing lengths (MODELS= required; BENCH_CONTEXT= target, default 256K capped per model)"
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
	@echo ">>> Checking example paths resolve (no per-version tree, no dangling references)"
	@$(UV) run python -u infra/scripts/check_example_paths.py
	@echo ">>> Checking example CLI commands + MCP tool references resolve"
	@$(UV) run python -u infra/scripts/check_example_refs.py

test:
	@echo ">>> Running tests (excluding slow + contract)"
	@$(UV) run pytest -n auto -q -m "not slow and not contract" packages

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
	@$(UV) run pytest -n auto -q -m "not slow and not contract" \
		--cov --cov-report=term-missing --cov-report=xml --cov-fail-under=70 packages

# The reference docs render the canonical v42 surface (CLAUDE.md baseline). Pin the
# version so the output is reproducible everywhere — CI (no profile) and local dev
# (any active profile) alike. The sentinel DHIS2_PROFILE makes profile resolution
# miss, so DHIS2_VERSION wins instead of whatever .dhis2 profile happens to be active.
DOCS_DHIS2_VERSION ?= v42
DOCS_PIN := DHIS2_PROFILE=__docs_no_profile__ DHIS2_VERSION=$(DOCS_DHIS2_VERSION)

docs-cli:
	@echo ">>> Regenerating CLI reference from the Typer app (pinned to $(DOCS_DHIS2_VERSION))"
	@$(DOCS_PIN) $(UV) run typer dhis2w_cli.main utils docs --name d2w --title "CLI reference" --output docs/cli-reference.md
	@echo "    wrote docs/cli-reference.md"

docs-mcp:
	@echo ">>> Regenerating MCP tool reference from the FastMCP server (pinned to $(DOCS_DHIS2_VERSION))"
	@$(DOCS_PIN) $(UV) run python -u infra/scripts/gen_mcp_reference.py

docs-d2path:
	@echo ">>> Regenerating docs/query/d2path-examples.md from the validated d2path catalog"
	@$(UV) run python -u infra/scripts/gen_d2path_examples.py

docs-serve: docs-cli docs-mcp docs-d2path
	@echo ">>> Serving docs at http://127.0.0.1:8000"
	@$(UV) run mkdocs serve

docs-build: docs-cli docs-mcp docs-d2path
	@echo ">>> Building docs site (strict — broken links / missing nav fail the build)"
	@$(UV) run mkdocs build --strict

docs: docs-serve

frontend-dev:
	@echo ">>> Vite dev server; FHIR calls proxy to $(SERVE_TARGET)"
	@echo "    Start the endpoint it talks to first: 'd2w fhir serve' in your IG project"
	@cd $(FRONTEND_DIR) && VITE_SERVE_TARGET=$(SERVE_TARGET) pnpm dev

build-frontend:
	@echo ">>> Building the capture UI into packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/static"
	@cd $(FRONTEND_DIR) && pnpm install --frozen-lockfile && pnpm build

lint-frontend:
	@echo ">>> Linting the capture UI (oxlint)"
	@cd $(FRONTEND_DIR) && pnpm exec oxlint
	@echo ">>> Type-checking the capture UI (tsc)"
	@cd $(FRONTEND_DIR) && pnpm exec tsc -b --force

test-frontend:
	@echo ">>> Running capture UI tests (vitest)"
	@cd $(FRONTEND_DIR) && pnpm exec vitest run

# Boots a real `d2w fhir serve --ui` on 8377 over a fixture IG project the config
# writes from tests/fixture_project.py, so the suite exercises the actual router
# table rather than a mock. Neither prerequisite is run automatically: the build
# writes into the Python package, and downloading a browser is not something a
# test command should do behind your back.
e2e-frontend:
	@echo ">>> Running capture UI browser tests (playwright, chromium, :8377)"
	@echo "    Needs 'make build-frontend' first, and chromium installed once:"
	@echo "    cd $(FRONTEND_DIR) && pnpm exec playwright install chromium"
	@cd $(FRONTEND_DIR) && pnpm exec playwright test

build:
	@echo ">>> Building all workspace wheels"
	@echo "    (the dhis2w-fhir-serve wheel ships whatever 'make build-frontend' last produced)"
	@$(UV) build --all-packages

# Releasing from the terminal. The other path to PyPI is a tag: push vX.Y.Z and
# .github/workflows/pypi-publish.yml builds and uploads every dhis2w-* package
# via Trusted Publishing, which needs no token. These targets need
# UV_PUBLISH_TOKEN and upload from the checkout in front of you.
#
# The publishable workspace members, in dependency order: each one is uploaded
# after everything it imports, so a resolver reading PyPI mid-release never meets
# a package naming a sibling version the index has not seen yet. The two
# workspace-only members — dhis2w-codegen and dhis2w-bench — are absent on
# purpose: they are internal tools with nothing to offer a PyPI consumer.
#
# Names here are the suffix after `dhis2w-`; the targets are `publish-<suffix>`.
PUBLISHABLE_MEMBERS := client ql core browser fhir fhir-engine fhir-serve cli mcp mcp-bridge mcp-router

# `publish-<member>` is deliberately not declared .PHONY: GNU make skips pattern-rule
# search for a phony target, and the pattern rule below is the whole family. Nothing
# in the tree is named `publish-anything`, so there is no file for it to collide with.
#
# One member: build its wheel + sdist and upload that pair alone. The member's
# own artifacts are removed from dist/ first, so a dist/ holding an earlier
# version cannot be uploaded alongside the one just built — `make build` and the
# sibling publish targets all write into the same directory.
publish-%:
	@test -n "$(UV_PUBLISH_TOKEN)" || { \
		echo "UV_PUBLISH_TOKEN is unset — export a PyPI token before publishing dhis2w-$*"; \
		exit 2; \
	}
	@echo ">>> Building dhis2w-$* wheel + sdist"
	@rm -f dist/$(subst -,_,dhis2w-$*)-*.whl dist/$(subst -,_,dhis2w-$*)-*.tar.gz
	@$(UV) build --package dhis2w-$*
	@echo ">>> Uploading dhis2w-$* to PyPI"
	@$(UV) publish dist/$(subst -,_,dhis2w-$*)-*.whl dist/$(subst -,_,dhis2w-$*)-*.tar.gz

publish-all:
	@test -n "$(UV_PUBLISH_TOKEN)" || { \
		echo "UV_PUBLISH_TOKEN is unset — export a PyPI token before publishing"; \
		exit 2; \
	}
	@echo ">>> Publishing every dhis2w-* package in dependency order:"
	@echo "    $(PUBLISHABLE_MEMBERS)"
	@echo "    (the dhis2w-fhir-serve wheel ships whatever 'make build-frontend' last produced)"
	@for member in $(PUBLISHABLE_MEMBERS); do \
		$(MAKE) --no-print-directory publish-$$member || exit 1; \
	done
	@echo ">>> Every member uploaded"

deps-upgrade:
	@echo ">>> Upgrading all resolvable deps (uv lock --upgrade)"
	@$(UV) lock --upgrade
	@echo ">>> Re-syncing workspace with updated lock"
	@$(UV) sync --all-packages --all-extras

dhis2-run:
	@DHIS2_VERSION=$(or $(DHIS2_VERSION),v43) infra/scripts/dhis2_run.sh

dhis2-seed:
	@$(MAKE) -C infra seed

dhis2-down:
	@$(MAKE) -C infra down

dhis2-build-e2e-dump:
	@$(MAKE) -C infra build-e2e-dump DHIS2_VERSION=$(or $(DHIS2_VERSION),v43)

dhis2-versions-check:
	@$(UV) run python infra/scripts/check_version_bumps.py

dhis2-versions-bump:
	@$(UV) run python infra/scripts/check_version_bumps.py --apply

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
	@echo ">>> Running every non-interactive example against profile $${DHIS2_PROFILE:-local_basic} (version resolved from the profile)"
	@if [ -f infra/home/credentials/.env.auth ]; then \
		set -a; . infra/home/credentials/.env.auth; set +a; \
		DHIS2_VERSION=$(DHIS2_VERSION) $(UV) run python -u infra/scripts/verify_examples.py; \
	else \
		echo "    note: infra/home/credentials/.env.auth missing — env-dependent examples (profile_crud.py) will fail"; \
		DHIS2_VERSION=$(DHIS2_VERSION) $(UV) run python -u infra/scripts/verify_examples.py; \
	fi

verify-igs:
	@echo ">>> Verifying every example IG under examples/fhir/igs against profile $${DHIS2_PROFILE:-local_basic}"
	@echo "    refresh, validate, generate, dockerized SUSHI compile - on demand, not part of 'make test'"
	@if [ -f infra/home/credentials/.env.auth ]; then \
		set -a; . infra/home/credentials/.env.auth; set +a; \
		$(UV) run python -u infra/scripts/verify_igs.py; \
	else \
		echo "    note: infra/home/credentials/.env.auth missing - the guides need a reachable DHIS2 instance"; \
		$(UV) run python -u infra/scripts/verify_igs.py; \
	fi

bench-list:
	@echo ">>> Installed models (the backend's view; MODEL_BACKEND= to switch)"
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.backend

bench-round:
	@test -n "$(MODEL)" || { echo "usage: make bench-round MODEL=<key> [ROUND=read|write|bench] [PROFILE=]  (see 'make bench-list')"; exit 2; }
	@echo ">>> Bridge test round: MODEL=$(MODEL) ROUND=$(or $(ROUND),read) PROFILE=$(or $(PROFILE),play42)"
	@echo "    (reads -> play42 readonly; writes -> local_basic. See docs/notes/small-model-bridge.md)"
	@lms server start >/dev/null 2>&1 || true
	@lms ps 2>/dev/null | grep -qF "$(MODEL)" || lms load $(MODEL) --gpu max --ttl 3600 -y
	@$(UV) run python -u -m dhis2w_bench.round \
		--model $(MODEL) \
		--round $(or $(ROUND),read) \
		--profile $(or $(PROFILE),$(if $(filter write,$(ROUND)),local_basic,play42))

bench-bridge:
	@test -n "$(MODELS)" || { echo "usage: make bench-bridge MODELS=\"<key> [<key> ...]\"  (no default; see 'make bench-list')"; exit 2; }
	@echo ">>> Bridge model benchmark: read -> play42 (read-only), write -> local_basic; one model at a time."
	@echo "    The write round needs local_basic up — run 'make dhis2-run' first if it isn't."
	@echo "    Name an oracle with BENCH_ORACLE=<key> to enable the SUSPECT-task check."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.bridge $(MODELS)

bench-general:
	@test -n "$(MODELS)" || { echo "usage: make bench-general MODELS=\"<key> [<key> ...]\"  (no default; see 'make bench-list')"; exit 2; }
	@echo ">>> General-capability benchmark (axis 1: python + cli + tooling; no DHIS2). One model = single test;"
	@echo "    several = side-by-side comparison. BENCH_MAX_TOKENS= tightens the budget; BENCH_ORACLE= sets an oracle."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.general $(MODELS)

bench-mcp:
	@test -n "$(MODELS)" || { echo "usage: make bench-mcp MODELS=\"<key> [<key> ...]\"  (no default; see 'make bench-list')"; exit 2; }
	@echo ">>> Full-MCP benchmark: the model drives the whole dhis2-mcp server (~311 tools) read + write."
	@echo "    Loads each model at BENCH_CONTEXT (default 128K) — the tool payload is ~49k tokens."
	@echo "    Read round = play42 with READ-ONLY tools only (the server has no readonly guard); write = local_basic."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.mcp $(MODELS)

bench-router:
	@test -n "$(MODELS)" || { echo "usage: make bench-router MODELS=\"<key> [<key> ...]\"  (no default; see 'make bench-list')"; exit 2; }
	@echo ">>> Router benchmark: local models drive the full dhis2-mcp surface via the router (search_tools + call_tool)."
	@echo "    Loads each model at BENCH_CONTEXT (default 16K) — the router payload is 2 tools, not the ~49k full surface."
	@echo "    Read suite on play42 with the router read-only. Compare against bench-mcp (full payload) and bench-bridge."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.router $(MODELS)

bench-claude-general:
	@echo ">>> Cloud Claude on the coding suite (python + cli + tooling), the cloud peer of bench-general."
	@echo "    Auth is AMBIENT (logged-in Claude Code subscription) — no API key read or stored; costs subscription budget."
	@echo "    MODELS optional: 'make bench-claude-general MODELS=\"opus sonnet\"' compares; empty = session-default model."
	@$(UV) run python -u -m dhis2w_bench.claude_general $(MODELS)

bench-claude-mcp:
	@echo ">>> Cloud Claude drives the full dhis2-mcp server via the Agent SDK (read suite on play42)."
	@echo "    Auth is AMBIENT (logged-in Claude Code subscription) — no API key read or stored; costs subscription budget."
	@echo "    MODELS optional: 'make bench-claude-mcp MODELS=\"opus sonnet\"' compares; empty = session-default model."
	@$(UV) run python -u -m dhis2w_bench.claude_mcp $(MODELS)

bench-claude-bridge:
	@echo ">>> Cloud Claude drives the dhis2_cli bridge via the Agent SDK: read (play42) + write + composite (local_basic)."
	@echo "    Auth is AMBIENT (logged-in Claude Code subscription) — no API key read or stored; costs subscription budget."
	@echo "    Write + composite rounds need local_basic up (make dhis2-run). MODELS optional; RUNS= repeats the flaky composite."
	@$(UV) run python -u -m dhis2w_bench.claude_bridge $(MODELS) $(if $(RUNS),--runs $(RUNS))

bench-validate:
	@test -n "$(MODEL)" || { echo "usage: make bench-validate MODEL=<key>   (e.g. google/gemma-4-12b-qat)"; exit 2; }
	@echo ">>> Validate $(MODEL) across both axes"
	@echo ">>> Axis 1 — general (python + cli + tooling)"
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.general $(MODEL)
	@echo ">>> Axis 2 — bridge (read + write); write round needs local_basic up (make dhis2-run)"
	@$(UV) run python -u -m dhis2w_bench.bridge $(MODEL)

bench-composite:
	@echo ">>> Composite write-workflow scenarios on local_basic (data set+elements, program+stages)."
	@echo "    No MODELS: run the deterministic oracle. MODELS=\"<key> ...\": drive each model via the bridge."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.composite $(if $(MODELS),--models $(MODELS)) $(if $(RUNS),--runs $(RUNS)) $(ARGS)

bench-longcontext:
	@test -n "$(MODELS)" || { echo "usage: make bench-longcontext MODELS=\"<key> ...\"  (no default; see 'make bench-list')"; exit 2; }
	@echo ">>> Long-context retrieval (needle-in-a-haystack) at increasing lengths; each model loads at min(BENCH_CONTEXT, its max), default target 256k."
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.longcontext $(MODELS)

bench-matrix:
	@echo ">>> CLI command x model matrix (how each roster model handles every command; read-only on play42)"
	@echo "    Streaming + resumable. Slice it: make bench-matrix ARGS=\"--group metadata --models google/gemma-4-12b-qat\""
	@lms server start >/dev/null 2>&1 || true
	@$(UV) run python -u -m dhis2w_bench.matrix $(ARGS)

refresh-setup:
	@echo ">>> [1/2] Rebuilding e2e dump (wipes + reseeds the stack)"
	@$(MAKE) dhis2-build-e2e-dump
	@echo ">>> [2/2] Seeding PATs + OAuth2 client (writes .env.auth)"
	@$(MAKE) -C infra seed
	@echo ">>> Setup complete — run 'make verify-examples' to exercise the example suite"

refresh-and-verify:
	@echo ">>> [1/4] Rebuilding e2e dump (wipes + reseeds the stack)"
	@$(MAKE) dhis2-build-e2e-dump
	@echo ">>> [2/4] Seeding PATs + OAuth2 client (writes .env.auth)"
	@$(MAKE) -C infra seed
	@echo ">>> [3/4] Refreshing analytics tables (the analytics examples read them)"
	@$(MAKE) refresh-analytics
	@echo ">>> [4/4] Verifying every non-interactive example (DHIS2 $(or $(DHIS2_VERSION),v43))"
	@set -a; . infra/home/credentials/.env.auth; set +a; \
		DHIS2_VERSION=$(or $(DHIS2_VERSION),v43) $(UV) run python -u infra/scripts/verify_examples.py

clean: clean-artifacts
	@echo ">>> Cleaning"
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .coverage htmlcov coverage.xml
	@rm -rf .pyright
	@rm -rf dist build site

clean-artifacts:
	@echo ">>> Removing run artifacts (reports, screenshots, browser and property-test state)"
	@rm -rf dhis2-security-*/ reports/dhis2-security-*/
	@rm -rf .hypothesis .playwright-mcp
	@rm -rf packages/dhis2w-fhir-serve/frontend/test-results
	@rm -rf packages/dhis2w-fhir-serve/frontend/playwright-report
	@find . -maxdepth 1 -type f -name "*.png" -delete
	@echo "    the working tree holds no run output; regenerate any of it by re-running its command"

.DEFAULT_GOAL := help
