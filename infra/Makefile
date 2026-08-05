.PHONY: help versions pull build up up-fresh up-seeded down clean status logs ps pat seed profile wait build-e2e-dump
.DEFAULT_GOAL := help

DHIS2_VERSION  ?= v43
DHIS2_URL      ?= http://localhost:8080
DHIS2_USER     ?= admin
DHIS2_PASS     ?= district
# Resolve the pinned Docker tag from versions.env (`DHIS2_V41=2.41.8.1` etc.).
# DHIS2_VERSION is the vXX key (v41 | v42 | v43); a dotted tag (e.g. "2.43.0.0")
# bypasses the lookup. An invalid value yields an empty tag and a hard error.
DHIS2_IMAGE_TAG := $(shell scripts/_resolve_image_tag.sh $(DHIS2_VERSION))
ifeq ($(strip $(DHIS2_IMAGE_TAG)),)
$(error DHIS2_VERSION '$(DHIS2_VERSION)' is invalid — use the vXX form (e.g. v43) or a full dotted tag; see scripts/_resolve_image_tag.sh)
endif
COMPOSE        := DHIS2_VERSION=$(DHIS2_VERSION) DHIS2_IMAGE_TAG=$(DHIS2_IMAGE_TAG) docker compose -f compose.yml -f compose.pgadmin.yml

help: ## show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

versions: ## list DHIS2 images available on Docker Hub (pick one for `make up DHIS2_VERSION=...`)
	@cd .. && uv run python infra/scripts/list_versions.py

pull: ## pull the selected DHIS2 version (default: 43)
	@echo ">>> Pulling dhis2/core:$(DHIS2_IMAGE_TAG)"
	@$(COMPOSE) pull

build: ## build supporting images (postgres + glowroot-installer)
	@echo ">>> Building supporting images"
	@$(COMPOSE) build

up: ## start the base stack in the background (keeps volumes; refuses a different major than the volume holds)
	@echo ">>> Starting DHIS2 $(DHIS2_VERSION) + pgAdmin"
	@scripts/_check_volume_major.sh $(DHIS2_VERSION)
	@$(COMPOSE) up -d --remove-orphans

up-fresh: ## wipe volumes + logs, then start the base stack (always pulls the pinned image fresh)
	@echo ">>> Fresh start for DHIS2 $(DHIS2_VERSION)"
	@rm -rf home/logs/*
	@$(COMPOSE) down -v
	@printf '%s' "$(DHIS2_VERSION)" > home/.volume-major
	# `--pull always` so codegen + e2e-dump builds always regenerate against the
	# exact registry image for the pin, never a stale local cache.
	@$(COMPOSE) up -d --pull always --remove-orphans

down: ## stop the stack (keeps volumes)
	@echo ">>> Stopping stack"
	@$(COMPOSE) down

clean: ## nuke everything — stop, remove volumes, wipe runtime data
	@echo ">>> Wiping stack + volumes + logs"
	@$(COMPOSE) down -v --remove-orphans
	@rm -f home/.volume-major
	@rm -rf home/logs/* home/glowroot

ps: ## show container state
	@$(COMPOSE) ps

status: ## show container state + DHIS2 reachability
	@$(COMPOSE) ps
	@echo "---"
	@cd .. && uv run python -c "import httpx, sys; r=httpx.get('$(DHIS2_URL)/dhis-web-login/', timeout=3.0, follow_redirects=True); print(f'DHIS2 login page: HTTP {r.status_code}')" 2>&1 || echo "DHIS2 not reachable at $(DHIS2_URL)"

logs: ## follow DHIS2 + postgres logs
	@$(COMPOSE) logs -f dhis2 postgresql

pat: ## mint a single PAT via `d2w browser pat` (Playwright) against the running instance
	@cd .. && uv run d2w browser pat --url $(DHIS2_URL) --username $(DHIS2_USER) --password $(DHIS2_PASS) --headless

wait: ## block until DHIS2 responds at /api/me (uses seed_auth's readiness probe)
	@cd .. && uv run --with bcrypt python -c "import asyncio; from infra.scripts.seed_auth import wait_for_ready; asyncio.run(wait_for_ready('$(DHIS2_URL)', '$(DHIS2_USER)', '$(DHIS2_PASS)'))"

seed: ## seed standard PAT variations + OAuth2 client into the running stack
	@cd .. && uv run --with bcrypt python infra/scripts/seed_auth.py --url $(DHIS2_URL) --username $(DHIS2_USER) --password $(DHIS2_PASS)

profile: ## write project-scoped `local_basic` Basic-auth profile to <repo>/.dhis2/profiles.toml
	@echo ">>> Writing local_basic profile (DHIS2 $(DHIS2_VERSION))"
	@cd .. && DHIS2_PASSWORD=$(DHIS2_PASS) uv run d2w profile add local_basic --local --auth basic --url $(DHIS2_URL) --username $(DHIS2_USER) --version $(DHIS2_VERSION) --default

up-seeded: ## up + wait + seed + profile — one-shot "I want a DHIS2 with auth ready"
	@$(MAKE) up
	@$(MAKE) wait
	@$(MAKE) seed
	@$(MAKE) profile

build-e2e-dump: ## populate a fresh DHIS2 with test metadata + data + analytics, then dump to infra/$(DHIS2_VERSION)/dump.sql.gz
	@echo ">>> Building e2e dump for DHIS2 $(DHIS2_VERSION) — this WIPES any existing volume state"
	@$(MAKE) up-fresh
	@$(MAKE) wait
	@cd .. && DHIS2_VERSION=$(DHIS2_VERSION) uv run --with bcrypt python infra/scripts/build_e2e_dump.py --url $(DHIS2_URL) --username $(DHIS2_USER) --password $(DHIS2_PASS) --dhis2-version $(DHIS2_VERSION)
