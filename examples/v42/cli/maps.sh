#!/usr/bin/env bash
# `dhis2 metadata maps ...` — thematic choropleth authoring via REST.
#
# A DHIS2 Map is a viewport (longitude, latitude, zoom) plus an ordered
# list of layers. Thematic (choropleth) is the most common layer type
# and is what `dhis2 metadata maps create` builds from flags. Multi-layer
# maps (thematic + boundary + facility) need raw construction from the
# library side.
#
# The browser-driven screenshot capture lives in the sibling
# `map_screenshot.sh` — it needs the `[browser]` extra + Chromium and
# is skipped from the default verify-examples run (opt in via
# `verify_examples.py --include-browser`).
set -euo pipefail

# Seeded thematic choropleths shipped with the e2e dump.
DOSES_MAP=y3jLMnZTV6i
IMMUNIZATION_MAP=iKgbemGaDUh

# ---------------------------------------------------------------------------
# List + inspect
# ---------------------------------------------------------------------------

dhis2 metadata list maps
dhis2 metadata maps get "$DOSES_MAP"

# ---------------------------------------------------------------------------
# Create from flags
# ---------------------------------------------------------------------------

dhis2 metadata maps create \
    --name "Demo: first doses given 2024 choropleth" \
    --de I78gJm4KBo7 \
    --pe 2024 \
    --ou ImspTQPwCqd \
    --ou-level 2 \
    --longitude 15 \
    --latitude 64.5 \
    --zoom 4 \
    --classes 5 \
    --color-low '#eff3ff' \
    --color-high '#08519c' \
    --uid MapCliDem01

# Clone it with a new name.
dhis2 metadata maps clone MapCliDem01 \
    --new-name "Demo: first doses given (clone)" \
    --new-uid MapCliCln01

# ---------------------------------------------------------------------------
# Clean up
# ---------------------------------------------------------------------------

dhis2 metadata maps delete MapCliDem01 -y
dhis2 metadata maps delete MapCliCln01 -y
