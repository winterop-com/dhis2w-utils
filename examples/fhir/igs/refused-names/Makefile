DOCKER_IMAGE := fhir-ig
IG_DIR := ig
TX_SERVER ?= http://tx.fhir.org
# Publisher JVM heap. It needs roughly this much again for metaspace, JVM native memory, and
# the OS, so keep the docker VM at JAVA_HEAP + ~2G or the kernel OOM-kills the build (exit 137).
JAVA_HEAP ?= 4g
# The toolchain uv.lock pins. Override to run a checkout: D2W="uv run --project /path/to/dhis2w-utils d2w"
D2W ?= uv run d2w
# Named volume for the FHIR package cache - the bulk of a cold build's wall clock.
CACHE_VOLUME := fhir-ig-cache
# Where `build` runs the publisher: a directory on the container's own filesystem rather than the
# mounted project. See the comment on that target for why.
BUILD_WORKDIR := /home/publisher/work
# What comes back out of that directory when the publisher is done. The site, the resources SUSHI
# compiled - `validate`, `check-artifacts` and the FHIR endpoint all read those - and the terminology
# and package caches the next build reuses. `temp/` and `template/` stay behind: nothing reads them,
# and they are the bulk of what a build writes.
BUILD_CARRIED_BACK := output fsh-generated input-cache

.PHONY: cache-init help setup upgrade generate validate sushi build refresh clean clean-all

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-12s %s\n", $$1, $$2}'

setup:  ## Build the SUSHI + IG publisher docker image
	docker build -t $(DOCKER_IMAGE) .

upgrade:  ## Rebuild the image from scratch, pulling the latest SUSHI + IG publisher
	docker build --pull --no-cache -t $(DOCKER_IMAGE) .

generate:  ## Regenerate FSH from DHIS2 metadata
	$(D2W) fhir generate

.PHONY: update
update:  ## Update the project to the current d2w: move the toolchain pin, sync, refresh the scaffold-managed files
	uv lock --upgrade
	uv sync
	$(D2W) fhir init --refresh

validate:  ## Check the DHIS2 instance's codes/names for FHIR-safety (writes md/csv/pdf; exit 1 on errors)
	$(D2W) fhir validate

.PHONY: check

check:  ## Scan the artifacts on disk for what aborts the IG publisher (offline, seconds, exit 1 on findings)
# A finding fails this recipe loudly; a toolchain too old to know the command must not. A project
# whose lock pins a dhis2w-fhir without `check-artifacts` (1.8+) would otherwise die here on
# "No such command" and take `build` down with it - on a guide that is perfectly publishable. So
# ask the CLI what it knows first, and when the command is absent, warn with the upgrade named
# and let the build proceed unscanned.
	@if $(D2W) fhir --help 2>/dev/null | grep -q "check-artifacts"; then \
		$(D2W) fhir check-artifacts; \
	else \
		echo "WARNING: the pinned dhis2w-fhir has no 'd2w fhir check-artifacts' (1.8+); skipping the artifact scan. Upgrade: uv lock --upgrade && uv sync"; \
	fi

cache-init:  ## Ensure the shared package-cache volume is writable by the publisher user
	docker run --rm -u root -v $(CACHE_VOLUME):/home/publisher/.fhir --entrypoint sh $(DOCKER_IMAGE) -c "mkdir -p /home/publisher/.fhir/packages && chown -R 1001:1001 /home/publisher/.fhir"

sushi: cache-init  ## Compile FSH to FHIR resources
	docker run --rm -v $$(pwd)/$(IG_DIR):/home/publisher/ig -v $(CACHE_VOLUME):/home/publisher/.fhir \
		$(DOCKER_IMAGE) sushi .

build: cache-init  ## Run the full IG publisher
# The scan first, and a finding stops the build here. A DHIS2 name or code carrying '<' survives every
# pass of the publisher and kills the last one, after every resource has already been rendered - hours
# spent to be told a page failed to parse. Reading the same files the publisher reads answers in
# seconds and names the object. Generation carries the same gate, but a build publishes what is on
# disk: output written before the gate, output from an older toolchain pin, and hand-authored FSH.
	$(MAKE) check
# Then the publisher, run on the container's own disk rather than on the mounted project. Docker on
# macOS reaches a host directory over a network-style filesystem, and the publisher's output pass
# writes tens of thousands of small files one at a time: on a district-scale guide that single pass
# took 341 seconds through the mount and 21 seconds inside the container. So the project is streamed
# in, built there, and the results streamed back - two bulk copies instead of one file at a time.
# Linux mounts a host directory directly and pays none of that; the recipe is the same either way
# because a project that builds one way on one machine should build the same way on the other.
	docker run --rm -v $$(pwd)/$(IG_DIR):/mnt/ig -v $(CACHE_VOLUME):/home/publisher/.fhir \
		$(DOCKER_IMAGE) bash -c 'set -e; \
			rm -rf $(BUILD_WORKDIR); mkdir -p $(BUILD_WORKDIR); \
			tar -C /mnt/ig --exclude=./output --exclude=./temp --exclude=./template -cf - . \
				| tar -C $(BUILD_WORKDIR) -xf -; \
			cd $(BUILD_WORKDIR); \
			status=0; \
			java -Xmx$(JAVA_HEAP) -jar /home/publisher/.ig-publisher/publisher.jar ig.ini -ig . -tx $(TX_SERVER) \
				|| status=$$?; \
			for carried in $(BUILD_CARRIED_BACK); do \
				if [ -d "$(BUILD_WORKDIR)/$$carried" ]; then \
					rm -rf "/mnt/ig/$$carried"; \
					tar -C $(BUILD_WORKDIR) -cf - "$$carried" | tar -C /mnt/ig -xf -; \
				fi; \
			done; \
			exit $$status'

.PHONY: build-bind

build-bind: cache-init  ## Run the publisher straight over the mounted project, no copy in or out
# The same build without the two copies. Worth reaching for when you want to watch output/ fill up
# as it is written, or when a copy is what you suspect. On macOS it is the slower of the two.
	$(MAKE) check
	docker run --rm -v $$(pwd)/$(IG_DIR):/home/publisher/ig -v $(CACHE_VOLUME):/home/publisher/.fhir \
		$(DOCKER_IMAGE) \
		java -Xmx$(JAVA_HEAP) -jar /home/publisher/.ig-publisher/publisher.jar ig.ini -ig . -tx $(TX_SERVER)

.PHONY: serve serve-live

serve:  ## Serve the compiled IG as a FHIR endpoint, with the capture UI at / (run generate + sushi first)
	$(D2W) fhir serve --ui

serve-live:  ## Serve straight from the DHIS2 instance, with the capture UI at / - no compile needed
	$(D2W) fhir serve --live --ui

.PHONY: forward forward-import

forward:  ## Dry-run the capture spool against DHIS2 - validate only, nothing written, nothing moved
	$(D2W) fhir forward

forward-import:  ## Import the capture spool into DHIS2 and file every receipt by what it became
	$(D2W) fhir forward --import

clean:  ## Remove build output (keeps ig/input-cache, the terminology cache the next build reuses)
	rm -rf $(IG_DIR)/fsh-generated $(IG_DIR)/output $(IG_DIR)/temp $(IG_DIR)/template \
		$(IG_DIR)/translations $(IG_DIR)/Requirements-fromNarrative.json

clean-all: clean  ## Also remove the terminology cache and the FHIR package cache volume
	rm -rf $(IG_DIR)/input-cache
	-docker volume rm $(CACHE_VOLUME)

# The caches survive a refresh on purpose. The terminology cache is hours of tx.fhir.org
# round-trips on a large guide, the package cache is re-downloads, and neither can go stale
# under a tooling upgrade - both are keyed by what they hold. `make clean-all` first is the
# deliberate act when you really want them gone.
refresh:  ## Wipe build output, pull latest tooling, regenerate, revalidate, rebuild (keeps the caches)
	$(MAKE) clean
	$(MAKE) upgrade
	$(MAKE) generate
# The leading dash keeps the rebuild going: validate exits 1 on instance code errors by design,
# and a full refresh wants fresh reports out of it, not an abort. The dash rather than --no-fail,
# because --no-fail also drops the red "N error(s) found" line - the one thing worth reading here.
	-$(MAKE) validate
# No sushi step: the publisher runs its own SUSHI over the same FSH, so calling both
# compiles everything twice - the single largest cost in the chain.
	$(MAKE) build
