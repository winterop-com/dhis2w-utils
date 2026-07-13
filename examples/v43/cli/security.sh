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

# Run every check step by step; streams Markdown/plaintext/CSV plus a self-rendering
# HTML bundle (open report.dc.html) to a timestamped folder
# (dhis2-security-<profile>-<timestamp>Z) in the current directory.
d2w security audit

# Choose where the run folder goes and which report formats to write.
d2w security audit --output-dir ./reports --format md,html

# The audit actively tests the well-known default login (admin/district) against
# /api/me by default; a success is a CRITICAL finding. It is a single HTTP Basic
# attempt, never retried. When failed-login lockout is enabled, the audit prints a
# warning first, since one wrong guess counts toward locking the real admin account.
# Disable the active probe to keep the audit strictly read-only:
d2w security audit --no-credential-probe

# The 14 valid --checks keys, in canonical running order:
#   version, transport, settings, authorities, roles, hygiene, credential-probe,
#   guest, apps, sharing, auth-methods, tokens, routes, audit-config
# Pass any comma-separated subset; --skip takes the same keys.

# Run only the probe (skips every other check):
d2w security audit --checks credential-probe

# Run only the version check (EOL line, patch/hotfix currency, security-advisory patch floor):
d2w security audit --checks version

# Run only the instance role audit (ALL-granting and dangerous-authority roles):
d2w security audit --checks roles

# Run only the per-user account hygiene check (stale / never-logged-in / 2FA on privileged accounts):
d2w security audit --checks hygiene

# Treat privileged accounts idle for 180 days (instead of the default 90) as stale:
d2w security audit --checks hygiene --stale-days 180

# Flag active accounts whose password is older than 90 days or never set (default threshold is 365):
d2w security audit --checks hygiene --max-password-age 90

# On v42+, also name each superuser missing 2FA (per-user /api/users/twoFactor read):
d2w security audit --two-factor-detail

# Run only the installed-apps check (side-loaded apps, available App Hub updates, custom JS/CSS injection):
d2w security audit --checks apps

# Run only the anonymous-access (guest) check (endpoints readable without a login, self-registration state):
d2w security audit --checks guest

# Run only the public-metadata sharing check (public-write and externally-accessible objects across the
# data-bearing and exposure-prone metadata types, paged and capped, decoded from each object's sharing block):
d2w security audit --checks sharing

# Bound how many objects the sharing scan inspects before stopping; truncation is reported in the run, not silent:
d2w security audit --checks sharing --max-objects 2000

# Also build the interactive d3 sharing explorer (sharing-explorer.html) into the run folder: an
# offline, self-contained "who can read/write this object, and by what path" reasoning engine over the
# unified access graph (objects + users/roles/groups). --visualize is an alias for --sharing-graph.
d2w security audit --checks sharing --sharing-graph

# The full typed report as JSON on stdout; progress events go to stderr.
d2w --json security audit | jq '.summary'

# Continue an interrupted run from its folder; checks that already finished are skipped.
d2w security audit --resume ./reports/dhis2-security-default-20260613T120000Z

# Re-render an existing run's report files from its JSONL spine without re-scanning.
d2w security report ./reports/dhis2-security-default-20260613T120000Z --format html
