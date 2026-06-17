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

# Run every check step by step; streams a Markdown/plaintext/CSV/HTML report to
# a timestamped folder (dhis2-security-<profile>-<timestamp>Z) in the current directory.
d2w security audit

# Choose where the run folder goes and which report formats to write.
d2w security audit --output-dir ./reports --format md,html

# The full typed report as JSON on stdout; progress events go to stderr.
d2w --json security audit | jq '.summary'

# Continue an interrupted run from its folder; checks that already finished are skipped.
d2w security audit --resume ./reports/dhis2-security-default-20260613T120000Z

# Re-render an existing run's report files from its JSONL spine without re-scanning.
d2w security report ./reports/dhis2-security-default-20260613T120000Z --format html
