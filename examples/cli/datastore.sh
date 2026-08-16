#!/usr/bin/env bash
# `d2w datastore` — namespaced key/value access to /api/dataStore (and per-user
# /api/userDataStore via --user). Values are arbitrary JSON. This sets a demo key,
# reads it back, lists it, then deletes the namespace so nothing is left behind.
set -euo pipefail

export DHIS2_URL="${DHIS2_URL:-http://localhost:8080}"

NAMESPACE="dhis2w_utils_demo"
KEY="example"

# Set a value (parsed as JSON; a bare word would be stored as a JSON string instead).
d2w datastore set "$NAMESPACE" "$KEY" '{"hello": "world", "count": 42}'

# Read it back (printed as JSON).
d2w datastore get "$NAMESPACE" "$KEY"

# List keys in the namespace, and all namespaces in the store.
d2w datastore keys "$NAMESPACE"
d2w datastore namespaces

# Clean up — delete the whole demo namespace (--yes skips the confirmation prompt).
d2w datastore delete-namespace "$NAMESPACE" --yes
