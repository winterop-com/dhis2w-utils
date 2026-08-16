#!/usr/bin/env bash
# Per-resource filters on `d2w metadata export` — narrow the bundle to just
# the objects you care about, and see which references are left dangling so
# you know whether the slice will round-trip.
set -euo pipefail

echo "--- 1. All dataElements with Penta in the name (filtered export)"
uv run d2w metadata export \
    --resource dataElements \
    --filter "dataElements:name:like:Penta" \
    --output /tmp/penta_elements.json

echo ""
echo "--- 2. Same but broadened — pull the categoryCombos + optionSets the warning pointed at"
uv run d2w metadata export \
    --resource dataElements \
    --resource categoryCombos \
    --resource optionSets \
    --filter "dataElements:name:like:Penta" \
    --output /tmp/penta_with_refs.json

echo ""
echo "--- 3. Per-resource fields: :owner for dataElements, :identifiable for the heavy categoryCombos collection"
uv run d2w metadata export \
    --resource dataElements --resource categoryCombos \
    --resource-fields "dataElements::owner" \
    --resource-fields "categoryCombos::identifiable" \
    --output /tmp/mixed_fields.json

echo ""
echo "--- 4. Skip the reference check when you know the slice is intentionally partial"
uv run d2w metadata export \
    --resource dataElements \
    --filter "dataElements:valueType:eq:TEXT" \
    --no-check-references \
    --output /tmp/text_only.json

echo ""
echo "--- 5. Multiple resources + multiple filters in one call"
uv run d2w metadata export \
    --resource dataElements --resource indicators \
    --filter "dataElements:name:like:Penta" \
    --filter "indicators:code:like:HIV_" \
    --output /tmp/mixed_slice.json
