#!/usr/bin/env bash
# `d2w browser map screenshot` — capture one or more saved Maps as PNGs
# via the DHIS2 Maps app. Chrome drives the render so the output matches
# what a user sees in the Maps viewer.
#
# Requires the `[browser]` extra:
#     uv add 'dhis2w-cli[browser]'
#     playwright install chromium
set -euo pipefail

# Seeded thematic choropleths shipped with the e2e dump.
DOSES_MAP=y3jLMnZTV6i
IMMUNIZATION_MAP=iKgbemGaDUh

OUT=/tmp/map-screenshots
rm -rf "$OUT"

d2w browser map screenshot \
    --output-dir "$OUT" \
    --only "$DOSES_MAP" --only "$IMMUNIZATION_MAP"

ls "$OUT/"*/ | head
