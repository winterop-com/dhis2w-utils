#!/usr/bin/env bash
# `d2w metadata list` — page through any metadata collection.
#
# Opens with `d2w metadata type list` because that answers the question every
# other line here depends on: which resource names this instance accepts.
set -euo pipefail

# What DHIS2 metadata types does this instance expose?
d2w metadata type list

# Default 50 rows, server-side page 1. `list` is also aliased as `ls`.
d2w metadata list dataElements --page-size 10

# Fields preset — `:identifiable` expands to `id,name,code,created,lastUpdated,displayName`.
# Other presets: `:nameable` (adds description), `:owner` (everything owned by the user), `:all`.
d2w metadata list dataElements --fields ":identifiable" --page-size 5

# Filter with the `property:operator:value` syntax. Repeat --filter for AND;
# pass --root-junction OR to OR them.
d2w metadata list dataElements \
  --filter "name:like:Penta" \
  --filter "code:eq:DE_PENTA1" \
  --root-junction OR \
  --fields "id,name,code"

# Order repeatable — later clauses tie-break.
d2w metadata list organisationUnits \
  --order "level:asc" --order "name:asc" \
  --fields "id,name,level" \
  --page-size 5

# --all streams every server-side page (paging=true + page=1,2,...).
# Useful for dumping a full catalog without knowing the total count upfront.
d2w --json metadata list indicators --all --fields ":identifiable" | jq 'length as $n | "\($n) indicators"'
