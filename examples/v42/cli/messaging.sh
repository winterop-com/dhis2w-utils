#!/usr/bin/env bash
# `dhis2 messaging` — internal-messaging workflow over `/api/messageConversations`.
#
# DHIS2 ships a lightweight internal messaging system with a
# ticket-workflow flavour (priority + status + assign/unassign).
# This script exercises the happy path: send a self-addressed message,
# list + get it, reply, set priority/status + assign, then delete.
set -euo pipefail

# Self-addressed message so the example runs without other users on the
# instance; pull the calling user's UID out of `dhis2 --json system whoami`.
SELF_UID=$(dhis2 --json system whoami | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# ---------------------------------------------------------------------------
# Send + inbox
# ---------------------------------------------------------------------------

CREATE_OUT=$(dhis2 messaging send "Example demo subject" "Hello from the example" --user "$SELF_UID")
CONVO_UID=$(printf '%s' "$CREATE_OUT" | awk '/sent conversation/ { print $3 }')
echo "created conversation $CONVO_UID"

dhis2 messaging list --filter "read:eq:false" | head -8 || true
dhis2 messaging get "$CONVO_UID" | head -15 || true

# ---------------------------------------------------------------------------
# Reply + ticket-workflow knobs
# ---------------------------------------------------------------------------

dhis2 messaging reply "$CONVO_UID" "Follow-up reply"
dhis2 messaging set-priority "$CONVO_UID" HIGH
dhis2 messaging set-status "$CONVO_UID" OPEN
dhis2 messaging assign "$CONVO_UID" "$SELF_UID"

# ---------------------------------------------------------------------------
# Read-state toggle + cleanup
# ---------------------------------------------------------------------------

dhis2 messaging mark-read "$CONVO_UID"
dhis2 messaging unassign "$CONVO_UID"
dhis2 messaging delete "$CONVO_UID"
