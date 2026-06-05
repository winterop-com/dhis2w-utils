#!/usr/bin/env bash
# Inspect DHIS2 security posture via `dhis2 security` (read-only).
set -euo pipefail

# Password policy, credential expiry, self-registration, and lockout —
# a focused slice of /api/systemSettings rendered as a table.
dhis2 security settings

# Same data as a typed JSON object (exactly the security fields, nothing else).
# Pipe into jq for a single value — e.g. the minimum password length:
dhis2 --json security settings
dhis2 --json security settings | jq '.minPasswordLength'
