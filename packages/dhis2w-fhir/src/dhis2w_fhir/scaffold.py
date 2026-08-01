"""Scaffold file contents for `d2w fhir init` - a complete dockerized SUSHI IG project."""

from __future__ import annotations

from datetime import UTC, datetime

from dhis2w_fhir.models import InitOptions, ScaffoldFile

_FHIR_TOML_TEMPLATE = """# fhir.toml - configuration for `d2w fhir generate` (scaffolded by `d2w fhir init`).
# Only the essentials live here; every available option is documented in fhir.toml.example.

# profile = "myserver"              # optional: DHIS2 profile to read metadata from

[ig]
id = "{ig_id}"
canonical = "{canonical}"
name = "{name}"
title = "{title}"
publisher = "{publisher}"
"""

_FHIR_TOML_EXAMPLE = """# fhir.toml.example - every option `d2w fhir generate` understands, with its default.
# Copy what you need into fhir.toml; omitted options keep these defaults.

# DHIS2 profile to read metadata from. Explicit `-p` / `DHIS2_PROFILE` wins over this.
# profile = "myserver"

[ig]
id = "{ig_id}"
canonical = "{canonical}"
name = "{name}"
title = "{title}"
publisher = "{publisher}"

[generate]
# Base URI for DHIS2 identifier systems in aliases.fsh ($DHIS2-OU etc).
identifier_system_base = "http://dhis2.org/fhir"
# Concept code source for option sets: "uid" (option UID, DHIS2 code as property)
# or "code" (DHIS2 code when FHIR-valid, UID as property; invalid codes fall back).
concept_code_source = "uid"

[generate.naming]
# Tokens composing FSH artifact names; ids derive from the kebab of each non-empty token.
# Defaults read by context: D2OSSexCS / d2-os-sex-cs, D2OULevelCS / d2-ou-level-cs.
prefix = "D2"                       # "" drops the prefix (profiles keep a D2 token:
                                    # a profile cannot share its parent resource's name)
option_set = "OS"                   # e.g. "OptionSet"; "" drops the token
org_unit = "OU"                     # must stay non-empty (e.g. "OrgUnit")

[generate.option_sets]
include_names = []                  # exact optionSet names to include (empty = all)
include_ids = []                    # optionSet UIDs to include (empty = all)

[generate.org_units]
root = ""                           # organisation unit root UID (empty = entire tree)
max_level = 0                       # 0 = no level cap
terminology = false                 # also emit the org-unit CodeSystem/ValueSet
                                    # with level/parent/dhis2-code properties
"""

_SUSHI_CONFIG_TEMPLATE = """id: {ig_id}
canonical: {canonical}
name: {name}
title: {title}
description: {title}, generated from DHIS2 metadata by d2w fhir.
status: draft
version: 0.1.0
fhirVersion: 4.0.1
copyrightYear: {year}+
releaseLabel: ci-build
license: CC0-1.0
publisher:
  name: {publisher}
  url: {canonical}

menu:
  Home: index.html
  Artifacts: artifacts.html
"""

_IG_INI_TEMPLATE = """[IG]
ig = fsh-generated/resources/ImplementationGuide-{ig_id}.json
template = fhir2.base.template
"""

_ALIASES_FSH = """// Shared FSH aliases: DHIS2 identifier systems and HL7 terminologies.
// The DHIS2 base URI is a local convention, not a registered FHIR NamingSystem.

Alias: $DHIS2-OU = {identifier_system_base}/id/org-unit
Alias: $DHIS2-OU-CODE = {identifier_system_base}/id/org-unit-code
Alias: $V2-0203 = http://terminology.hl7.org/CodeSystem/v2-0203
"""

_INDEX_MD_TEMPLATE = """# {title}

This Implementation Guide is generated from DHIS2 metadata with `d2w fhir`.

- Option sets are represented as CodeSystem/ValueSet pairs under Terminology.
- Organisation units are represented as Organization instances (with Location
  instances where the source has Point geometry).

See the Artifacts page for the full list.
"""

_IGNORE_WARNINGS = """== Suppressed Messages ==
"""

_MAKEFILE = """DOCKER_IMAGE := fhir-ig
IG_DIR := ig
TX_SERVER ?= n/a

.PHONY: help setup upgrade generate sushi build clean clean-all

help:  ## Show available targets
\t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-12s %s\\n", $$1, $$2}'

setup:  ## Build the SUSHI + IG publisher docker image
\tdocker build -t $(DOCKER_IMAGE) .

upgrade:  ## Rebuild the image from scratch, pulling the latest SUSHI + IG publisher
\tdocker build --pull --no-cache -t $(DOCKER_IMAGE) .

generate:  ## Regenerate FSH from DHIS2 metadata
\td2w fhir generate all

sushi:  ## Compile FSH to FHIR resources
\tdocker run --rm -v $$(pwd)/$(IG_DIR):/home/publisher/ig $(DOCKER_IMAGE) sushi .

build:  ## Run the full IG publisher
\tdocker run --rm -v $$(pwd)/$(IG_DIR):/home/publisher/ig $(DOCKER_IMAGE) \\
\t\tjava -Xmx4g -jar /home/publisher/.ig-publisher/publisher.jar ig.ini -ig . -tx $(TX_SERVER)

clean:  ## Remove build output
\trm -rf $(IG_DIR)/fsh-generated $(IG_DIR)/output $(IG_DIR)/temp $(IG_DIR)/template

clean-all: clean  ## Remove build output and the package cache
\trm -rf $(IG_DIR)/input-cache
"""

_DOCKERFILE = """FROM ghcr.io/fhir/ig-publisher-localdev
RUN mkdir -p /home/publisher/.ig-publisher && \\
    curl -L -o /home/publisher/.ig-publisher/publisher.jar \\
    "https://github.com/HL7/fhir-ig-publisher/releases/latest/download/publisher.jar"
RUN npm install -g fsh-sushi
WORKDIR /home/publisher/ig
"""

_GITIGNORE = """ig/fsh-generated/
ig/output/
ig/temp/
ig/template/
ig/input-cache/
"""


def build_scaffold_files(options: InitOptions) -> list[ScaffoldFile]:
    """Build every file `d2w fhir init` writes, path-relative to the project root."""
    identity = {
        "ig_id": options.ig_id,
        "canonical": options.canonical,
        "name": options.name,
        "title": options.title,
        "publisher": options.publisher,
    }
    return [
        ScaffoldFile(relative_path="fhir.toml", content=_FHIR_TOML_TEMPLATE.format(**identity)),
        ScaffoldFile(relative_path="fhir.toml.example", content=_FHIR_TOML_EXAMPLE.format(**identity)),
        ScaffoldFile(
            relative_path="ig/sushi-config.yaml",
            content=_SUSHI_CONFIG_TEMPLATE.format(
                ig_id=options.ig_id,
                canonical=options.canonical,
                name=options.name,
                title=options.title,
                publisher=options.publisher,
                year=datetime.now(tz=UTC).year,
            ),
        ),
        ScaffoldFile(relative_path="ig/ig.ini", content=_IG_INI_TEMPLATE.format(ig_id=options.ig_id)),
        ScaffoldFile(
            relative_path="ig/input/fsh/aliases.fsh",
            content=_ALIASES_FSH.format(identifier_system_base="http://dhis2.org/fhir"),
        ),
        ScaffoldFile(
            relative_path="ig/input/pagecontent/index.md",
            content=_INDEX_MD_TEMPLATE.format(title=options.title),
        ),
        ScaffoldFile(relative_path="ig/input/ignoreWarnings.txt", content=_IGNORE_WARNINGS),
        ScaffoldFile(relative_path="Makefile", content=_MAKEFILE),
        ScaffoldFile(relative_path="Dockerfile", content=_DOCKERFILE),
        ScaffoldFile(relative_path=".gitignore", content=_GITIGNORE),
    ]
