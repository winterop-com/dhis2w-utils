#!/usr/bin/env bash
# `d2w user-group` + `d2w user-role` — admin workflows.
# Run via `uv run bash examples/v41/cli/user_groups_and_roles.sh` so `d2w` resolves.
set -euo pipefail

# --- user group ---------------------------------------------------------------

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

# --- user role ----------------------------------------------------------------

d2w user role list

# Authorities carried by the Superuser role (seeded fixture has it).
ROLE_UID=$(d2w --json user role list --page-size 1 | jq -r '.[0].id')
if [ -n "$ROLE_UID" ] && [ "$ROLE_UID" != "null" ]; then
  echo ">>> first 10 authorities on role $ROLE_UID:"
  AUTHS=$(d2w user role authority-list "$ROLE_UID")
  echo "$AUTHS" | awk 'NR<=10'
  echo "... (full list via \`d2w user role authority-list $ROLE_UID\`)"
fi

# Grant / revoke a role on a user:
# d2w user role add-user "$ROLE_UID" "$USER_UID"
# d2w user role remove-user "$ROLE_UID" "$USER_UID"

# Create / delete a user group directly (no import bundle needed):
# UG_UID=$(d2w --json user group create --name "Data reviewers" --code DATA_REVIEWERS | jq -r '.response.uid')
# d2w user group add-member "$UG_UID" "$USER_UID"
# d2w user group delete "$UG_UID" --yes
