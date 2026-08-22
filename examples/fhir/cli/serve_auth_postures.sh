#!/usr/bin/env bash
# d2w fhir serve --auth — the four postures a facade takes towards the caller at its door.
# Needs the serve extra: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# Every facade here runs `--live`, so there is no SUSHI compile and no docker; every request is a
# read or a capture, so nothing is written to DHIS2.
set -euo pipefail

# `[serve] auth` takes four values, and each answers a different question about the caller:
#
#   none    serve everybody. Loopback only unless the project says otherwise.
#   token   a static bearer token this deployment issued, out of D2W_FHIR_SERVE_TOKENS.
#   dhis2   the caller's own DHIS2 credentials, checked against the instance this run reads.
#   jwt     a token from the OpenID Connect issuer named in [serve.jwt], verified against its keys.
#
# `[serve] auth_scope` is the second half of the same decision - how much of the surface the posture
# covers. `write` guards the capture address and leaves reads open; `all` guards everything but
# /metadata, which stays open so a client can read the posture it has to meet.

# A free loopback port, so a facade this script starts never collides with one already listening.
pick_port() {
    local candidate
    for candidate in $(seq 8130 8199); do
        if ! (exec 3<>"/dev/tcp/127.0.0.1/${candidate}") 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    echo "no free port between 8130 and 8199" >&2
    return 1
}
PORT="${FHIR_AUTH_PORT:-$(pick_port)}"
BASE="http://127.0.0.1:${PORT}"

# One event program for the capture half, one tracked entity type for the register half, and the
# registry capped at level 2 so each `--live` startup stays quick.
d2w fhir init demo-serve-auth --id dhis2.fhir.serveauthdemo \
    --canonical http://example.org/fhir/serve-auth-demo \
    --publisher "Demo Org" --event-program EVTsupVis01 --max-level 2
cd demo-serve-auth

cat >>fhir.toml <<'TOML'

[serve.tracked_entities]
tracked_entity_types = ["nEenWmSyUEp"]
TOML

start_facade() {
    d2w fhir serve --live --no-ui --port "$PORT" "$@" >facade.log 2>&1 &
    SERVER_PID=$!
    trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
    for _ in $(seq 1 90); do
        if [ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/metadata")" = "200" ]; then
            return 0
        fi
        sleep 1
    done
    echo "the facade did not answer ${BASE}/metadata within 90s:" >&2
    tail -20 facade.log >&2
    return 1
}

stop_facade() {
    kill "$SERVER_PID" 2>/dev/null || true
    trap - EXIT
    wait "$SERVER_PID" 2>/dev/null || true
}

status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

# --- none: the posture an absent key is not ------------------------------------------------------
# A project that has never written `auth` is served on loopback and refused anywhere else, naming
# the line to write. An absent key is nobody's decision; `auth = "none"` written out is somebody's,
# and passes this check. The refusal costs no connection - the posture is settled before the store
# is built - so this run neither reads DHIS2 nor binds the interface it is refusing.
d2w fhir serve --live --host 0.0.0.0 --port "$PORT" \
    || echo "the bind was refused - who reaches this facade and who it answers are one decision"

# --- token: one shared secret, handed to whoever integrates --------------------------------------
# The tokens come from the environment and never from fhir.toml, which is a file projects commit.
# Comma-separated for several clients; rotating them is replacing the variable and restarting.
export D2W_FHIR_SERVE_TOKENS='a-long-random-value,another-for-the-second-client'
start_facade --auth token --auth-scope all

# `all` closes the whole surface except /metadata, so a client can read what it has to present.
echo "token posture, no credential:   $(status "${BASE}/Questionnaire")"
echo "token posture, wrong token:     $(status -H 'Authorization: Bearer nope' "${BASE}/Questionnaire")"
echo "token posture, issued token:    $(status -H 'Authorization: Bearer a-long-random-value' "${BASE}/Questionnaire")"
echo "token posture, /metadata:       $(status "${BASE}/metadata")"

# A refusal says what to present rather than only that something was missing.
curl -s -D- -o /dev/null "${BASE}/Questionnaire" | grep -i '^www-authenticate'
stop_facade

# --- dhis2: the accounts the clerks already have -------------------------------------------------
# The credentials are the caller's own, not this project's: the facade checks each one by reading
# /api/me on the instance as them. This takes them from the environment the way any caller would
# have them; `make verify-examples` sources infra/home/credentials/.env.auth, which carries both.
start_facade --auth dhis2

# The scope is the default `write`, so the published guide stays open to everybody.
echo "dhis2 posture, guide read:      $(status "${BASE}/Questionnaire")"

# A register read is the exception the scope does not cover: it is answered under the caller's own
# credentials, so with none presented there is nobody to answer as and the read is a 401 - not an
# answer given as the facade's own profile.
echo "dhis2 posture, register anon:   $(status "${BASE}/Patient?_count=1")"
echo "dhis2 posture, wrong password:  $(status -u "${DHIS2_USERNAME}:not-the-password" "${BASE}/Patient?_count=1")"
echo "dhis2 posture, register as you: $(status -u "${DHIS2_USERNAME}:${DHIS2_PASSWORD}" "${BASE}/Patient?_count=1")"

# What DHIS2 hides it hides: the search runs on the instance under that caller's sharing,
# organisation unit scopes, and access levels, and this server applies no rule of its own.
curl -s -u "${DHIS2_USERNAME}:${DHIS2_PASSWORD}" "${BASE}/Patient?_count=1" | head -c 120
echo

# A DHIS2 personal access token is the same posture without a password on the wire.
echo "dhis2 posture, ApiToken:        $(status -H "Authorization: ApiToken ${DHIS2_PAT}" "${BASE}/Patient?_count=1")"

# The challenge names `xBasic`, and that is not a typo. A browser meeting `WWW-Authenticate: Basic`
# on a request a page made opens its own credential dialog and leaves the request pending, so the
# capture screen would hang on Submit instead of rendering the refusal. What callers send is
# unchanged: HTTP Basic, exactly as the two lines above send it.
curl -s -D- -o /dev/null "${BASE}/Patient?_count=1" | grep -i '^www-authenticate'

# Capture is guarded under `write` too, and the username the facade validated lands on the receipt -
# which is what makes a spool listing say who filled each form in. Nothing reaches DHIS2: a capture
# writes a receipt to the spool, and `d2w fhir forward` is the command that drains it.
d2w fhir generate load-set --per-target 1
echo "dhis2 posture, capture anon:    $(status -X POST "${BASE}/QuestionnaireResponse" \
    -H 'Content-Type: application/fhir+json' --data-binary @load/EVTsupVis01-example-1.json)"
echo "dhis2 posture, capture as you:  $(status -u "${DHIS2_USERNAME}:${DHIS2_PASSWORD}" \
    -X POST "${BASE}/QuestionnaireResponse" \
    -H 'Content-Type: application/fhir+json' --data-binary @load/EVTsupVis01-example-1.json)"
stop_facade

d2w fhir spool --details

# --- jwt: the identity provider the organisation already runs ------------------------------------
# This posture asks nobody anything: it verifies what the issuer signed, against the keys that
# issuer publishes. So it needs no instance - and it needs the issuer, which is a property of the
# deployment rather than of one invocation and therefore has no flag. Stating the posture without
# naming one is refused before anything starts.
d2w fhir serve --live --auth jwt --port "$PORT" \
    || echo "the posture was refused - a verifier with no issuer trusts everything or nothing"

# Named, it is two lines. `audience` is what the token must be addressed to, `username_claim` is
# which claim becomes the name on a receipt, and `forward_bearer` is whether the register is read
# under the caller's token as well - off unless the instance trusts the same issuer.
cat >>fhir.toml <<'TOML'

[serve.jwt]
issuer = "https://idp.example.org/realms/health"
audience = "d2w-fhir-serve"
username_claim = "preferred_username"
forward_bearer = false
TOML

# `oauth2` is not a fifth value, and that is current rather than an oversight: DHIS2 2.43.1's own
# authorization server answers 500 for any client its API creates (BUGS.md 96), so a project could
# state it and nothing would answer. See docs/fhir/301-serving.md for the whole table.

cd .. && rm -rf demo-serve-auth
