#!/usr/bin/env bash
# `d2w user` — list, get, invite, reset-password.
# Run via `uv run bash examples/v42/cli/user_administration.sh` so the `d2w` entry resolves.
set -euo pipefail

# --- reads (safe; pure /api/users GETs) ---------------------------------------

# List users — shares every flag with `d2w metadata list`.
d2w user list --page-size 5
d2w user list --filter "disabled:eq:false" --order "lastLogin:desc" --page-size 5
d2w user list --filter "username:like:admin" --fields ":identifiable"

# Fetch by UID or username. Non-UID input is resolved via a
# username-eq filter lookup server-side.
d2w user get admin --fields "id,username,displayName,lastLogin"
d2w user get M5zQapPyTZI --fields "id,username,authorities"

# The authenticated user's /api/me (authorities, settings, programs).
d2w system whoami

# --- writes (hit real DHIS2 state; uncomment on a real instance) --------------

# Create a new user + email an invitation. DHIS2 derives the username from the
# email prefix when --username is omitted.
# d2w user invite alice@example.com --first-name Alice --surname Example \
#     --user role abcDEFghiJK --org-unit ImspTQPwCqd

# Re-send an invitation that was already queued but never accepted.
# d2w user reinvite <UID>

# Trigger DHIS2's password-reset email for an existing user.
# d2w user reset-password <UID>
