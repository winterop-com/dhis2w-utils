#!/usr/bin/env bash
# `d2w messaging` — internal-messaging workflow over `/api/messageConversations`.
#
# DHIS2 ships a lightweight internal messaging system with a
# ticket-workflow flavour (priority + status + assign/unassign).
# This script exercises the happy path: send a self-addressed message,
# list + get it, reply, set priority/status + assign, then delete.
set -euo pipefail

# Self-addressed message so the example runs without other users on the
# instance; pull the calling user's UID out of `d2w --json system whoami`.
SELF_UID=$(d2w --json system whoami | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# ---------------------------------------------------------------------------
# Send + inbox
# ---------------------------------------------------------------------------

CREATE_OUT=$(d2w messaging send "Example demo subject" "Hello from the example" --user "$SELF_UID")
CONVO_UID=$(printf '%s' "$CREATE_OUT" | awk '/sent conversation/ { print $3 }')
echo "created conversation $CONVO_UID"

d2w messaging list --filter "read:eq:false" | head -8 || true
d2w messaging get "$CONVO_UID" | head -15 || true

# ---------------------------------------------------------------------------
# Reply + ticket-workflow knobs
# ---------------------------------------------------------------------------

d2w messaging reply "$CONVO_UID" "Follow-up reply"
d2w messaging set-priority "$CONVO_UID" HIGH
d2w messaging set-status "$CONVO_UID" OPEN
d2w messaging assign "$CONVO_UID" "$SELF_UID"

# ---------------------------------------------------------------------------
# Read-state toggle + cleanup
# ---------------------------------------------------------------------------

d2w messaging mark-read "$CONVO_UID"
d2w messaging unassign "$CONVO_UID"
d2w messaging delete "$CONVO_UID"
