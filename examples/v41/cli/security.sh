#!/usr/bin/env bash
# Inspect DHIS2 security posture via `d2w security` (read-only).
set -euo pipefail

# Password policy, credential expiry, self-registration, and lockout —
# a focused slice of /api/systemSettings rendered as a table.
d2w security settings

# Same data as a typed JSON object (exactly the security fields, nothing else).
# Pipe into jq for a single value — e.g. the minimum password length:
d2w --json security settings
d2w --json security settings | jq '.minPasswordLength'
