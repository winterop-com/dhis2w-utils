#!/usr/bin/env bash
# `d2w browser viz screenshot` — capture one or more Visualizations as
# PNGs via the DHIS2 Data Visualizer app. Chrome drives every render so
# the output matches the dashboard UI byte-for-byte.
#
# Requires the `[browser]` extra:
#     uv add 'dhis2w-cli[browser]'
#     playwright install chromium
set -euo pipefail

OUT=/tmp/viz-screenshots
rm -rf "$OUT"

# Capture three saved vizes (LINE, PIVOT_TABLE, SINGLE_VALUE) from the
# committed seed. --only can repeat.
d2w browser viz screenshot \
    --output-dir "$OUT" \
    --only Qyuliufvfjl \
    --only FXFCkALrbsC \
    --only DNRhUsVbTgT

ls "$OUT/"*/ | head

# Capture every visualization on the instance — useful for a full audit
# pass when reviewing a new seed or after a bulk viz refactor.
# d2w browser viz screenshot --output-dir "$OUT"

# Skip the info banner / trim for cleaner PNGs going into a report.
# d2w browser viz screenshot --output-dir "$OUT" --only Qyuliufvfjl --no-banner --no-trim

# Run headful (useful for debugging plateau or selector issues).
# d2w browser viz screenshot --output-dir "$OUT" --only Qyuliufvfjl --headful
