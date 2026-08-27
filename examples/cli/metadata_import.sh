#!/usr/bin/env bash
# `d2w metadata import` — push a metadata bundle at the instance.
# Run via `uv run bash examples/cli/metadata_import.sh` so the `d2w` entry resolves.
set -euo pipefail

tmp=$(mktemp -d)
trap "rm -rf $tmp" EXIT

# One throwaway indicator type, minted client-side so the bundle owns its identity.
MINTED=$(d2w dev uid)
printf '{"indicatorTypes":[{"id":"%s","name":"Example import type %s","factor":1,"number":false}]}\n' \
    "$MINTED" "$MINTED" > "$tmp/bundle.json"
echo "--- bundle carries indicatorTypes/$MINTED"

echo
echo "--- dry run: DHIS2 validates and preheats, and writes nothing"
d2w metadata import "$tmp/bundle.json" --dry-run

echo
echo "--- the real import"
# --strategy CREATE_AND_UPDATE (the default) creates what is new and overwrites
# what already exists; --atomic-mode ALL rolls the whole bundle back if any one
# object is refused, where NONE commits the objects that survived.
d2w metadata import "$tmp/bundle.json" --strategy CREATE_AND_UPDATE --atomic-mode ALL

echo
echo "--- it landed:"
d2w metadata get indicatorTypes "$MINTED" --fields "id,name,factor"

echo
echo "--- teardown: the same bundle under --strategy DELETE"
d2w metadata import "$tmp/bundle.json" --strategy DELETE
