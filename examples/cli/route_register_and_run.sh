#!/usr/bin/env bash
# `d2w route` — register + run integration routes for every upstream auth type.
#
# DHIS2 routes proxy external URLs through DHIS2 so UI-side apps + agents can
# call third-party services without CORS + without exposing upstream
# credentials to the browser.
#
# Auth types DHIS2 supports on the route's `auth` field:
#
#   (none)                     no upstream auth — DHIS2 forwards as-is
#   http-basic                 Authorization: Basic base64(user:pw)
#   api-token                  Authorization: Bearer <token>
#   api-headers                arbitrary custom header (e.g. X-Api-Key)
#   api-query-params           URL query-string param (e.g. ?api_key=...)
#   oauth2-client-credentials  OAuth2 Client Credentials grant — DHIS2 POSTs
#                              to upstream tokenUri with client_id/secret,
#                              caches the access token. For machine-to-machine
#                              when upstream is another DHIS2 or any OAuth2 RS.
#
# For interactive use run `d2w route create` (no args) — a wizard walks through
# code/name/url/auth-type + hidden-input prompts for secrets. This script
# demonstrates each type non-interactively via `--file spec.json`.
set -euo pipefail

# Scratch dir for route specs. chmod 0700 so plaintext secrets don't leak to
# other users on the box. Cleaned up on exit.
SCRATCH=$(mktemp -d)
chmod 0700 "$SCRATCH"
trap 'rm -rf "$SCRATCH"' EXIT


add_route() {
  # Prints the created route UID (and only the UID) to stdout.
  # Diagnostics go to stderr so callers can `uid=$(add_route ...)` cleanly.
  local label="$1" spec="$2"
  local spec_file="$SCRATCH/${label}.json"
  printf '%s\n' "$spec" > "$spec_file"
  chmod 0600 "$spec_file"
  echo "  $label: creating..." >&2
  local response uid
  response=$(d2w --json route create --file "$spec_file")
  uid=$(printf '%s' "$response" | jq -r '.response.uid')
  echo "    uid=$uid" >&2
  printf '%s' "$uid"
}

# Delete every route whose code starts with `EX_`. We match by prefix instead
# of tracking UIDs through the script because the uid-capturing subshells
# don't propagate to the parent array.
purge_examples() {
  d2w --json route list --fields id,code \
    | jq -r '.[] | select(.code // "" | startswith("EX_")) | "\(.id)\t\(.code)"' \
    | while IFS=$'\t' read -r uid code; do
        d2w route delete "$uid" --yes >/dev/null
        echo "    deleted $code ($uid)" >&2
      done
}

# Remove any EX_* routes left behind by a prior interrupted run. Idempotent.
purge_examples

# ---- none ---------------------------------------------------------------------
echo ">>> none (no auth)"
uid_none=$(add_route NONE '{"code":"EX_NONE","name":"ex none","url":"https://httpbin.org/get"}')
d2w route run "$uid_none" | jq -r '"    response keys: \(keys | join(", "))"'

# ---- http-basic ---------------------------------------------------------------
# httpbin's /basic-auth/{user}/{pass} 200s when the Authorization header matches.
echo ">>> http-basic (Authorization: Basic ...)"
uid_basic=$(add_route HTTP_BASIC '{
  "code": "EX_BASIC",
  "name": "ex http-basic",
  "url": "https://httpbin.org/basic-auth/foo/bar",
  "auth": {"type": "http-basic", "username": "foo", "password": "bar"}
}')
d2w route run "$uid_basic" | jq -r '"    authenticated: \(.authenticated // false)  user: \(.user // "-")"'

# ---- api-token ----------------------------------------------------------------
# DHIS2 sends `Authorization: ApiToken <value>` upstream — a DHIS2-specific
# scheme, NOT the OAuth2 `Bearer` scheme. So we verify via /headers (shows
# what reached the target) rather than /bearer (which requires the standard
# `Bearer` scheme).
echo ">>> api-token (Authorization: ApiToken ..., non-standard scheme)"
uid_token=$(add_route API_TOKEN '{
  "code": "EX_APITOKEN",
  "name": "ex api-token",
  "url": "https://httpbin.org/headers",
  "auth": {"type": "api-token", "token": "example-token-not-a-real-secret"}
}')
d2w route run "$uid_token" | jq -r '"    Authorization header reaching upstream: \(.headers.Authorization)"'

# ---- api-headers --------------------------------------------------------------
# httpbin's /headers echoes the upstream request headers — we can see our
# custom X-Api-Key reach the target.
echo ">>> api-headers (custom header)"
uid_hdr=$(add_route API_HEADERS '{
  "code": "EX_APIHDR",
  "name": "ex api-headers",
  "url": "https://httpbin.org/headers",
  "auth": {"type": "api-headers", "headers": {"X-Api-Key": "deadbeef"}}
}')
d2w route run "$uid_hdr" | jq -r '"    X-Api-Key echoed: \(.headers["X-Api-Key"])"'

# ---- api-query-params ---------------------------------------------------------
# httpbin's /get echoes the query-string it received. DHIS2 appends our
# `api_key=...` to every upstream call.
echo ">>> api-query-params"
uid_q=$(add_route API_QUERY '{
  "code": "EX_APIQUERY",
  "name": "ex api-query-params",
  "url": "https://httpbin.org/get",
  "auth": {"type": "api-query-params", "queryParams": {"api_key": "qparam-value"}}
}')
d2w route run "$uid_q" | jq -c '"    query-param echoed: \(.args)"'

# ---- oauth2-client-credentials -----------------------------------------------
# DHIS2 POSTs to tokenUri first, then uses the returned access_token on the
# upstream call. We register the route here (validates the config) but skip
# `route run` because this example points at a placeholder tokenUri — to make
# `run` succeed you'd need a real OAuth2 AS that accepts client_credentials
# (could be another DHIS2 with client_credentials grant registered).
echo ">>> oauth2-client-credentials (config only — placeholder upstream)"
uid_oauth2=$(add_route OAUTH2_CC '{
  "code": "EX_OAUTH2CC",
  "name": "ex oauth2-client-credentials",
  "url": "https://example.invalid/api/",
  "auth": {
    "type": "oauth2-client-credentials",
    "tokenUri": "https://auth.example.invalid/oauth2/token",
    "clientId": "example-client",
    "clientSecret": "example-secret",
    "scopes": "ALL"
  }
}')
echo "    registered (skipping 'route run' — placeholder tokenUri)"

# ---- teardown -----------------------------------------------------------------
echo
echo ">>> cleanup (removes any EX_* route)"
purge_examples
