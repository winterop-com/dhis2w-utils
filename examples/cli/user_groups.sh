#!/usr/bin/env bash
# `d2w user group` — admin workflows over /api/userGroups.
# Run via `uv run bash examples/cli/user_groups.sh` so `d2w` resolves.
set -euo pipefail

d2w user group list
d2w --json user group list --filter "name:like:Admin" --page-size 5 | jq '.[0]'

# Show the sharing block on a group, then grant a user metadata-write access.
# GROUP_UID=$(d2w --json user group list --page-size 1 | jq -r '.[0].id')
# USER_UID=M5zQapPyTZI
# d2w user group sharing-get "$GROUP_UID"
# d2w user group sharing-grant-user "$GROUP_UID" "$USER_UID" --metadata-write

# Membership edits:
# d2w user group add-member "$GROUP_UID" "$USER_UID"
# d2w user group remove-member "$GROUP_UID" "$USER_UID"

# Create / delete a user group directly (no import bundle needed):
# UG_UID=$(d2w --json user group create --name "Data reviewers" --code DATA_REVIEWERS | jq -r '.response.uid')
# d2w user group add-member "$UG_UID" "$USER_UID"
# d2w user group delete "$UG_UID" --yes
