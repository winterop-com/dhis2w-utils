#!/usr/bin/env bash
# `dhis2 user` — list, get, invite, reset-password.
# Run via `uv run bash examples/v41/cli/user_administration.sh` so the `dhis2` entry resolves.
set -euo pipefail

# --- reads (safe; pure /api/users GETs) ---------------------------------------

# List users — shares every flag with `dhis2 metadata list`.
dhis2 user list --page-size 5
dhis2 user list --filter "disabled:eq:false" --order "lastLogin:desc" --page-size 5
dhis2 user list --filter "username:like:admin" --fields ":identifiable"

# Fetch by UID or username. Non-UID input is resolved via a
# username-eq filter lookup server-side.
dhis2 user get admin --fields "id,username,displayName,lastLogin"
dhis2 user get M5zQapPyTZI --fields "id,username,authorities"

# The authenticated user's /api/me (authorities, settings, programs).
dhis2 system whoami

# --- writes (hit real DHIS2 state; uncomment on a real instance) --------------

# Create a new user + email an invitation. DHIS2 derives the username from the
# email prefix when --username is omitted.
# dhis2 user invite alice@example.com --first-name Alice --surname Example \
#     --user role abcDEFghiJK --org-unit ImspTQPwCqd

# Re-send an invitation that was already queued but never accepted.
# dhis2 user reinvite <UID>

# Trigger DHIS2's password-reset email for an existing user.
# dhis2 user reset-password <UID>
