#!/usr/bin/env bash
# `d2w user role` — admin workflows over /api/userRoles.
# Run via `uv run bash examples/cli/user_roles.sh` so `d2w` resolves.
set -euo pipefail

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
# USER_UID=M5zQapPyTZI
# d2w user role add-user "$ROLE_UID" "$USER_UID"
# d2w user role remove-user "$ROLE_UID" "$USER_UID"
