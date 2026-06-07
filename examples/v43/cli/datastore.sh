#!/usr/bin/env bash
# `dhis2 datastore` — namespaced key/value access to /api/dataStore (and per-user
# /api/userDataStore via --user). Values are arbitrary JSON. This sets a demo key,
# reads it back, lists it, then deletes the namespace so nothing is left behind.
set -euo pipefail

export DHIS2_URL="${DHIS2_URL:-http://localhost:8080}"

NAMESPACE="dhis2w_utils_demo"
KEY="example"

# Set a value (parsed as JSON; a bare word would be stored as a JSON string instead).
dhis2 datastore set "$NAMESPACE" "$KEY" '{"hello": "world", "count": 42}'

# Read it back (printed as JSON).
dhis2 datastore get "$NAMESPACE" "$KEY"

# List keys in the namespace, and all namespaces in the store.
dhis2 datastore keys "$NAMESPACE"
dhis2 datastore namespaces

# Clean up — delete the whole demo namespace (--yes skips the confirmation prompt).
dhis2 datastore delete-namespace "$NAMESPACE" --yes
