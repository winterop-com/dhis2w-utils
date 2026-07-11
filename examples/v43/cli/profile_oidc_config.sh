#!/usr/bin/env bash
# `d2w profile oidc-config` — populate an OAuth2 profile by discovering DHIS2's OIDC endpoints.
# Run via `uv run bash examples/v43/cli/profile_oidc_config.sh` after bringing up the seeded local stack.
set -euo pipefail

# Option 1 — pass the DHIS2 base URL. The command appends /.well-known/openid-configuration
# itself, validates the response, and writes a profile with auth=oauth2 + the client creds.
d2w profile oidc-config http://localhost:8080 \
    --name example_oidc_discovered \
    --client-id dhis2-utils-local \
    --client-secret dhis2-utils-local-secret-do-not-use-in-prod \
    --local

# Option 2 — same idea, but pass the full discovery URL (accepted as-is):
# d2w profile oidc-config http://localhost:8080/.well-known/openid-configuration \
#     --name example_oidc_discovered \
#     --client-id dhis2-utils-local --client-secret ...

# Verify the saved profile round-trips against DHIS2.
d2w profile verify example_oidc_discovered || true

# Clean up the demo profile.
d2w profile remove example_oidc_discovered --yes
