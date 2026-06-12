#!/usr/bin/env bash
# OIDC login flow — the CLI path.
# Mirrors examples/client/oidc_login.py but everything happens through
# `d2w profile add` + `d2w profile login`. When DHIS2_USERNAME +
# DHIS2_PASSWORD are available in env, the Playwright helper from
# dhis2w-browser drives the login + consent screens end-to-end so this
# script completes headlessly; otherwise it opens a browser and waits
# for a human click.
set -euo pipefail

# Source the seeded OAuth2 client creds into env.
set -a; source infra/home/credentials/.env.auth; set +a

# Create an oauth2 profile. --from-env pulls the DHIS2_OAUTH_* values
# and stamps them into ~/.config/dhis2/profiles.toml.
d2w profile add local_oidc --auth oauth2 --from-env --default

# Drive the authorization-code + PKCE flow.
if [ -n "${DHIS2_USERNAME:-}" ] && [ -n "${DHIS2_PASSWORD:-}" ]; then
    # Automated — `drive_oauth2_login` spawns `d2w profile login --no-browser`,
    # reads the authorize URL from its stderr, and drives Chromium through the
    # DHIS2 login form + Spring AS consent screen. Tokens persist exactly as
    # they would on the human-driven path. Requires the `[browser]` extra:
    #     uv add 'dhis2w-cli[browser]' && playwright install chromium
    uv run python - <<'PY'
import asyncio
import os
from dhis2w_browser import drive_oauth2_login
asyncio.run(
    drive_oauth2_login(
        "local_oidc",
        username=os.environ["DHIS2_USERNAME"],
        password=os.environ["DHIS2_PASSWORD"],
    )
)
PY
else
    # Interactive — opens your system browser and waits for the human click.
    # Pass --no-browser (or set DHIS2_OAUTH_NO_BROWSER=1) to print the auth URL
    # to stderr for copy-paste into any other browser — handy over SSH.
    d2w profile login local_oidc
fi

# Prove it worked — every subsequent `d2w ...` call reuses the cached
# access token (refreshing silently when near expiry). `--profile/-p` is a
# global flag on the `d2w` root, so it goes BEFORE the subcommand.
d2w profile verify local_oidc
d2w --profile local_oidc system whoami
