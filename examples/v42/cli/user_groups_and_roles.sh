#!/usr/bin/env bash
# `dhis2 user-group` + `dhis2 user-role` — admin workflows.
# Run via `uv run bash examples/v42/cli/user_groups_and_roles.sh` so `dhis2` resolves.
set -euo pipefail

# --- user-group ---------------------------------------------------------------

dhis2 user-group list
dhis2 --json user-group list --filter "name:like:Admin" --page-size 5 | jq '.[0]'

# Show the sharing block on a group, then grant a user metadata-write access.
# GROUP_UID=$(dhis2 --json user-group list --page-size 1 | jq -r '.[0].id')
# USER_UID=M5zQapPyTZI
# dhis2 user-group sharing-get "$GROUP_UID"
# dhis2 user-group sharing-grant-user "$GROUP_UID" "$USER_UID" --metadata-write

# Membership edits:
# dhis2 user-group add-member "$GROUP_UID" "$USER_UID"
# dhis2 user-group remove-member "$GROUP_UID" "$USER_UID"

# --- user-role ----------------------------------------------------------------

dhis2 user-role list

# Authorities carried by the Superuser role (seeded fixture has it).
ROLE_UID=$(dhis2 --json user-role list --page-size 1 | jq -r '.[0].id')
if [ -n "$ROLE_UID" ] && [ "$ROLE_UID" != "null" ]; then
  echo ">>> first 10 authorities on role $ROLE_UID:"
  AUTHS=$(dhis2 user-role authority-list "$ROLE_UID")
  echo "$AUTHS" | awk 'NR<=10'
  echo "... (full list via \`dhis2 user-role authority-list $ROLE_UID\`)"
fi

# Grant / revoke a role on a user:
# dhis2 user-role add-user "$ROLE_UID" "$USER_UID"
# dhis2 user-role remove-user "$ROLE_UID" "$USER_UID"

# Create / delete a user group directly (no import bundle needed):
# UG_UID=$(dhis2 --json user-group create --name "Data reviewers" --code DATA_REVIEWERS | jq -r '.response.uid')
# dhis2 user-group add-member "$UG_UID" "$USER_UID"
# dhis2 user-group delete "$UG_UID" --yes
