#!/usr/bin/env bash
# Metadata round-trip pipeline: export -> transform with jq -> diff -> import.
#
# Canonical "I want to change a field on every dataElement matching X" workflow.
# Exports a filtered slice, applies a field transform via jq, diffs to confirm
# the scope of the change, imports to land it.
set -euo pipefail

export DHIS2_PROFILE="${DHIS2_PROFILE:-local_basic}"
WORK=/tmp/metadata_round_trip
mkdir -p "$WORK"

echo "=== 1. Export the slice we want to mutate (filter-narrowed)"
d2w metadata export \
    --resource dataElements \
    --filter "dataElements:name:like:Penta" \
    --output "$WORK/original.json"

echo ""
echo "=== 2. Transform: add a shared 'description' prefix to every exported element"
jq '.dataElements |= map(.description = ("[Penta] " + (.description // "no description")))' \
    "$WORK/original.json" > "$WORK/modified.json"

echo ""
echo "=== 3. Diff — shows what would change on re-import"
d2w metadata diff "$WORK/original.json" "$WORK/modified.json" --show-uids

echo ""
echo "=== 4. Dry-run import to confirm DHIS2 accepts the shape"
d2w metadata import "$WORK/modified.json" --dry-run

echo ""
echo "=== 5. Real import"
d2w metadata import "$WORK/modified.json"

echo ""
echo "=== 6. Diff the modified bundle against the live instance"
# `--live` exports only the resource types present in the file and diffs.
# Since our file is a filtered slice (Penta-only), dataElements outside that
# slice appear as "deleted" relative to the file — that's expected.
# What we care about: the Penta elements should all be 'unchanged' now.
# Full diff output — no piping because DHIS2's Rich table renderer +
# `set -o pipefail` trip on SIGPIPE when the downstream consumer (head /
# awk + exit / sed + q) closes stdin early.
d2w metadata diff "$WORK/modified.json" --live --show-uids

echo ""
echo "=== 7. Revert to the original for idempotency"
d2w metadata import "$WORK/original.json"
echo ""
echo "--- done; work files left at $WORK/ for inspection ---"
