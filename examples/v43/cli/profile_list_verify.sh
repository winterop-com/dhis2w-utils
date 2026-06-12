#!/usr/bin/env bash
# Profile management: list, verify, show.
# The script prefers a basic-auth profile (fewest moving parts) — stored PATs
# can expire, and OAuth2 tokens invalidate every time DHIS2's AS rotates its
# client (e.g. after a stack restart). `d2w profile verify` is the right
# command to catch either kind of staleness.
# `add` / `remove` / `login` / `bootstrap` are shown as commented-out examples at the bottom.
set -euo pipefail

# List every profile the CLI can see across project + global TOML files.
d2w profile list

# Pick a basic-auth profile; fall back to PAT if that's all we have.
PROFILE=$(d2w --json profile list | jq -r '.[] | select(.auth == "basic") | .name' | awk 'NR==1{print;exit}')
if [ -z "$PROFILE" ]; then
  PROFILE=$(d2w --json profile list | jq -r '.[] | select(.auth == "pat") | .name' | awk 'NR==1{print;exit}')
fi
if [ -z "$PROFILE" ]; then
  echo "no pat/basic profile configured — add one with \`d2w profile add <name> --auth basic ...\`" >&2
  exit 0
fi

# Probe it — GET /api/system/info + /api/me.
d2w profile verify "$PROFILE"

# Show the profile (secrets redacted).
d2w profile show "$PROFILE"

# Other profile commands (not run by default). Secrets never come via argv —
# pass through env vars (DHIS2_PAT / DHIS2_PASSWORD / DHIS2_OAUTH_CLIENT_SECRET)
# or enter them at the interactive prompt.
# DHIS2_PASSWORD=System123 d2w profile add dev --url https://play.im.dhis2.org/dev --auth basic --username system
# d2w profile default dev
# d2w profile rename dev play-dev
# d2w profile remove play-dev
# d2w profile login local_oidc           # run the OAuth2 flow for an existing oauth2 profile
# d2w profile bootstrap demo --auth pat --url $DHIS2_URL   # one-shot: create PAT + save profile
