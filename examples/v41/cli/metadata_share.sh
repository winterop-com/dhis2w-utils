#!/usr/bin/env bash
# `d2w metadata share` — bulk-apply a sharing block across many UIDs of one resource.
# Fans out concurrent POSTs to /api/sharing?type=<resource>&id=<uid> via
# client.metadata.apply_sharing_bulk; per-UID failures land in a row-level table.
# Run via `uv run bash examples/v41/cli/metadata_share.sh` so `d2w` resolves.
set -euo pipefail

# Pick the first two data sets — these are the cohort we'll share.
DS_UIDS=$(d2w --json metadata list dataSets --page-size 2 | jq -r '.[].id' | xargs)
read -ra DS_ARR <<<"$DS_UIDS"

# Find a user group to grant access to.
UG_UID=$(d2w --json user group list --page-size 1 | jq -r '.[0].id')

# Dry-run preview — what would be sent if --dry-run is dropped.
d2w metadata share dataSet "${DS_ARR[@]}" \
    --public-access r------- \
    --user-group-access "${UG_UID}:rwrw----" \
    --dry-run

# Apply the sharing block. Same payload, no --dry-run.
# d2w metadata share dataSet "${DS_ARR[@]}" \
#     --public-access r------- \
#     --user-group-access "${UG_UID}:rwrw----"

# Stdin form — pipe a UID list from any source.
# d2w --json metadata list dataSets --filter 'name:like:ANC' \
#     | jq -r '.[].id' \
#     | d2w metadata share dataSet - --public-access -------- --dry-run
