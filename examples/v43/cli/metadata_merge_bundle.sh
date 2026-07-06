#!/usr/bin/env bash
# `d2w metadata merge-bundle` — import a saved bundle file into a target profile.
# The bundle-source variant of `metadata merge`: instead of exporting from
# a source profile, read the bundle from disk. Useful when the bundle came
# from a saved `metadata export`, was hand-crafted, or was produced by a
# non-DHIS2 tool.
# Run via `uv run bash examples/v43/cli/metadata_merge_bundle.sh` so `d2w` resolves.
set -euo pipefail

# 1. Save a small bundle to disk via the existing export verb.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
BUNDLE="$TMP/data-elements.json"

d2w metadata export --resource dataElements --filter dataElements:name:like:Visits \
    --output "$BUNDLE"

# 2. Dry-run preview against the same instance — DHIS2 walks the bundle and
#    reports conflicts + counts without committing (importMode=VALIDATE).
d2w metadata merge-bundle "$DHIS2_PROFILE" "$BUNDLE" --dry-run

# 3. Apply by dropping --dry-run.
# d2w metadata merge-bundle prod "$BUNDLE"

# 4. Restrict the import to a subset of bundle keys — the bundle is filtered
#    to those collections before the POST, so the count summary reports
#    exactly what was written.
# d2w metadata merge-bundle "$DHIS2_PROFILE" "$BUNDLE" -r dataElements --dry-run
