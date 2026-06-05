#!/usr/bin/env bash
# `dhis2 metadata categories` — Category authoring (axis of a disaggregation grid).
# Run via `uv run bash examples/v41/cli/categories.sh` so `dhis2` resolves.
set -euo pipefail

# Read paths.
dhis2 metadata list categories --page-size 5
CAT_UID=$(dhis2 --json metadata list categories --page-size 1 | jq -r '.[0].id')
[ -n "$CAT_UID" ] && dhis2 metadata categories get "$CAT_UID"

# Read fixture CategoryOptions to wire on create.
CO_UIDS=$(dhis2 --json metadata list categoryOptions --page-size 2 | jq -r '.[].id' | xargs)
read -ra CO_ARR <<<"$CO_UIDS"

# Create with options wired on save (idempotent on UID — re-running would 409).
# dhis2 metadata categories create \
#     --name "DemoModality" --short-name "DemoMod" \
#     --type DISAGGREGATION \
#     --option "${CO_ARR[0]}" --option "${CO_ARR[1]}"

# Per-item membership edits without re-PUTting the whole category.
# dhis2 metadata categories add-option <CAT_UID> <CO_UID>
# dhis2 metadata categories remove-option <CAT_UID> <CO_UID>

# Partial label rename.
# dhis2 metadata categories rename <CAT_UID> --short-name "Mod"

# Delete (DHIS2 rejects when the category is referenced by a CategoryCombo).
# dhis2 metadata categories delete <CAT_UID> --yes
