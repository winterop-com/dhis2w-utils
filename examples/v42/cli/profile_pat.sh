#!/usr/bin/env bash
# `dhis2 profile pat create` — provision a Personal Access Token as an admin.
# Secrets never come via argv. Admin creds are read from DHIS2_ADMIN_PAT /
# DHIS2_ADMIN_PASSWORD env vars, or via an interactive prompt (hidden input).
set -euo pipefail

# Export an admin password for this script run so `profile pat create` can use it
# without prompting. In real operator use you'd have this in a sourced env
# file (infra/home/credentials/.env.auth after `make dhis2-seed`).
export DHIS2_ADMIN_PASSWORD="${DHIS2_ADMIN_PASSWORD:-district}"
export DHIS2_URL="${DHIS2_URL:-http://localhost:8080}"

# Create a PAT. The token value is only shown here once — DHIS2 never echoes it
# again. The `--description` helps identify the PAT later in the UI.
dhis2 profile pat create --admin-user admin --description "demo token"

# One-shot capture into an env var so it's available to later tooling without
# ever landing in shell history. --quiet prints only the token value.
FRESH_PAT=$(dhis2 profile pat create --admin-user admin --description "script-captured" -q)
echo "captured PAT length: ${#FRESH_PAT} (prefix: ${FRESH_PAT:0:5}...)"

# The fresh PAT can then drive a profile. `profile add` also reads DHIS2_PAT
# from env so the secret never goes into argv.
# DHIS2_PAT=$FRESH_PAT dhis2 profile add smoketest --url $DHIS2_URL --auth pat
