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

# My effective authorities from /api/me/authorization, categorised by the
# dangerous-authority taxonomy (superuser, user management, SQL views, ...).
d2w security authorities

# JSON for scripting; e.g. fail a CI check when the integration account holds ALL:
d2w --json security authorities | jq '.is_superuser'
