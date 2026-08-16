#!/usr/bin/env bash
# `d2w metadata categories` — Category authoring (axis of a disaggregation grid).
# Run via `uv run bash examples/cli/categories.sh` so `d2w` resolves.
set -euo pipefail

# Read paths.
d2w metadata list categories --page-size 5
CAT_UID=$(d2w --json metadata list categories --page-size 1 | jq -r '.[0].id')
[ -n "$CAT_UID" ] && d2w metadata categories get "$CAT_UID"

# Read fixture CategoryOptions to wire on create.
CO_UIDS=$(d2w --json metadata list categoryOptions --page-size 2 | jq -r '.[].id' | xargs)
read -ra CO_ARR <<<"$CO_UIDS"

# Create with options wired on save (idempotent on UID — re-running would 409).
# d2w metadata categories create \
#     --name "DemoModality" --short-name "DemoMod" \
#     --type DISAGGREGATION \
#     --option "${CO_ARR[0]}" --option "${CO_ARR[1]}"

# Per-item membership edits without re-PUTting the whole category.
# d2w metadata categories add-option <CAT_UID> <CO_UID>
# d2w metadata categories remove-option <CAT_UID> <CO_UID>

# Partial label rename.
# d2w metadata categories rename <CAT_UID> --short-name "Mod"

# Delete (DHIS2 rejects when the category is referenced by a CategoryCombo).
# d2w metadata categories delete <CAT_UID> --yes
