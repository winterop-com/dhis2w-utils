#!/usr/bin/env bash
# `dhis2 metadata share` — bulk-apply a sharing block across many UIDs of one resource.
# Fans out concurrent POSTs to /api/sharing?type=<resource>&id=<uid> via
# client.metadata.apply_sharing_bulk; per-UID failures land in a row-level table.
# Run via `uv run bash examples/v42/cli/metadata_share.sh` so `dhis2` resolves.
set -euo pipefail

# Pick the first two data sets — these are the cohort we'll share.
DS_UIDS=$(dhis2 --json metadata list dataSets --page-size 2 | jq -r '.[].id' | xargs)
read -ra DS_ARR <<<"$DS_UIDS"

# Find a user group to grant access to.
UG_UID=$(dhis2 --json user group list --page-size 1 | jq -r '.[0].id')

# Dry-run preview — what would be sent if --dry-run is dropped.
dhis2 metadata share dataSet "${DS_ARR[@]}" \
    --public-access r------- \
    --user-group-access "${UG_UID}:rwrw----" \
    --dry-run

# Apply the sharing block. Same payload, no --dry-run.
# dhis2 metadata share dataSet "${DS_ARR[@]}" \
#     --public-access r------- \
#     --user-group-access "${UG_UID}:rwrw----"

# Stdin form — pipe a UID list from any source.
# dhis2 --json metadata list dataSets --filter 'name:like:ANC' \
#     | jq -r '.[].id' \
#     | dhis2 metadata share dataSet - --public-access -------- --dry-run
