#!/usr/bin/env bash
# `d2w metadata export` — pull a metadata bundle off the instance.
# Run via `uv run bash examples/cli/metadata_export.sh` so the `d2w` entry resolves.
set -euo pipefail

tmp=$(mktemp -d)
trap "rm -rf $tmp" EXIT

echo "--- a narrow slice: dataElements + indicatorTypes"
# `:owner` is the default field selector and the lossless one — every field the
# object owns, so the bundle re-imports into another instance unchanged.
d2w metadata export \
    --resource dataElements \
    --resource indicatorTypes \
    --fields ":owner" \
    --output "$tmp/slice.json"

echo
echo "--- what came back:"
python3 -c "import json; d=json.load(open('$tmp/slice.json')); [print(f'  {k}: {len(v)}') for k,v in d.items() if isinstance(v, list)]"

echo
echo "--- the full catalog: no --resource means every type DHIS2 exports by default"
d2w metadata export --output "$tmp/full.json"
python3 -c "import json; d=json.load(open('$tmp/full.json')); print(f'full bundle: {sum(len(v) for v in d.values() if isinstance(v, list))} objects across {sum(1 for v in d.values() if isinstance(v, list))} resource types')"

# Per-resource filters and the dangling-reference warning are their own story:
# see examples/cli/metadata_export_filter.sh.
