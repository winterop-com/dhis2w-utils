#!/usr/bin/env bash
# `d2w profile add --auth session` — bind a profile to an existing browser login.
# The profile stores the raw Cookie header value (name included, e.g.
# "JSESSIONID=abc123"), and every request sends it verbatim. This is the
# fallback for instances where PAT creation is unavailable (pre-2.38, disabled,
# or 403 for the user); prefer `--auth pat` when the instance supports it.
# Secrets never come via argv: the cookie is read from DHIS2_SESSION_COOKIE or
# prompted with hidden input.
set -euo pipefail

export DHIS2_URL="${DHIS2_URL:-http://localhost:8080}"

# Grab the session cookie from a logged-in browser tab (DevTools > Application >
# Cookies, or a browser extension that reads it for you), then upsert a profile.
# Re-running the same command with a fresh cookie handles rotation/expiry.
DHIS2_SESSION_COOKIE="JSESSIONID=abc123" \
  d2w profile add browser --url "$DHIS2_URL" --auth session --local

# Instances that enforce CSRF on write endpoints also expect the XSRF-TOKEN
# cookie echoed back as an X-XSRF-TOKEN header. Capture it the same way (it's the
# value of the XSRF-TOKEN cookie) and pass it via DHIS2_SESSION_XSRF; it's
# optional and inert when absent, so read-only sessions can skip it entirely.
DHIS2_SESSION_COOKIE="JSESSIONID=abc123" DHIS2_SESSION_XSRF="a1b2c3d4-xsrf" \
  d2w profile add browser --url "$DHIS2_URL" --auth session --local

# The profile acts as whoever owns the browser session. `verify` probes
# /api/me: a 401-flavored failure means the cookie has expired — re-run the
# upsert above with a fresh cookie.
d2w profile verify browser || echo "session expired; re-add with a fresh cookie"

# The stored profile looks like this in .dhis2/profiles.toml (0600). The
# xsrf_token line is present only when DHIS2_SESSION_XSRF was set:
#   [profiles.browser]
#   base_url = "http://localhost:8080"
#   auth = "session"
#   cookie = "JSESSIONID=abc123"
#   xsrf_token = "a1b2c3d4-xsrf"

# Unbind by removing the profile.
d2w profile remove browser --local
