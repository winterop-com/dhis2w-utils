#!/usr/bin/env bash
# `dhis2 metadata legend-sets ...` — LegendSet authoring + application.
#
# A DHIS2 LegendSet is an ordered list of `Legend` entries, each a
# colour (`#RRGGBB`) + display name assigned to a numeric range
# `[startValue, endValue)`. Visualizations and maps reference a
# LegendSet by UID; at render time DHIS2 colours each cell by which
# legend its value falls into. The workspace seeds `LsDoseBand1`
# with four colour ranges tuned to 2024 monthly dose totals (red <
# 2k, amber 2-5k, yellow 5-10k, green 10k+) and attaches it to two
# single-DE column charts on the Immunization dashboard.
set -euo pipefail

# ---------------------------------------------------------------------------
# List + show
# ---------------------------------------------------------------------------

dhis2 metadata list legendSets | head -20
dhis2 metadata legend-sets get LsDoseBand1

# ---------------------------------------------------------------------------
# Create a fresh legend set + read it back
# ---------------------------------------------------------------------------
# Each `--legend start:end:color[:name]` defines one legend (colour
# range). `start` must be strictly less than `end`; `color` is a
# `#RRGGBB` hex string; `name` is optional (auto-generated from the
# numeric range when omitted).

dhis2 metadata legend-sets create \
    --name "Ad-hoc coverage" \
    --code "AD_HOC_COVERAGE_DEMO" \
    --legend '0:50:#d73027:Low coverage' \
    --legend '50:80:#fdae61:Medium coverage' \
    --legend '80:120:#1a9850:High coverage' | tee /tmp/legend-set-create.txt

# Pick the UID out of the create output for the subsequent show/delete.
NEW_UID=$(awk '/created legendSet/ { print $3 }' /tmp/legend-set-create.txt)
dhis2 metadata legend-sets get "$NEW_UID"

# ---------------------------------------------------------------------------
# Clone + delete
# ---------------------------------------------------------------------------
# Cloning duplicates the legends with fresh UIDs on the set + each
# child. Useful for forking a base set into a monochrome /
# alternate-palette variant without rebuilding the legends by hand.

dhis2 metadata legend-sets clone "$NEW_UID" --new-name "Ad-hoc coverage (clone)" | tee /tmp/legend-set-clone.txt
CLONE_UID=$(awk '/cloned/ { print $4 }' /tmp/legend-set-clone.txt)

dhis2 metadata legend-sets delete "$CLONE_UID" --yes
dhis2 metadata legend-sets delete "$NEW_UID" --yes
