#!/usr/bin/env bash
# `d2w dev codegen` — regenerate the typed client from a DHIS2 instance.
# Three subcommands, two source-of-truth paths.
set -euo pipefail

export DHIS2_URL="${DHIS2_URL:-http://localhost:8080}"
export DHIS2_USERNAME="${DHIS2_USERNAME:-admin}"
export DHIS2_PASSWORD="${DHIS2_PASSWORD:-district}"

# --- /api/schemas path (metadata resources) -----------------------------------

# Online: hit a live instance and write generated/v{N}/schemas/ + enums.py +
# resources.py + schemas_manifest.json. Version is derived from /api/system/info.
# The example writes into a scratch directory: pointed at the committed tree
# (the default), this command rewrites source the repository pins - which is the
# real maintenance flow, not a batch pass's business.
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
d2w dev codegen generate --url "$DHIS2_URL" --username "$DHIS2_USERNAME" --password "$DHIS2_PASSWORD" \
    --output-root "$OUT"
ls "$OUT"

# Offline: re-run the emitter against every committed schemas_manifest.json.
# Useful after touching templates or the mapping logic — no network needed.
d2w dev codegen rebuild --output-root "$OUT"

# Offline, single version:
d2w dev codegen rebuild --manifest packages/dhis2w-client/src/dhis2w_client/generated/v42/schemas_manifest.json \
    --output-root "$OUT"

# --- /api/openapi.json path (instance-side shapes) ----------------------------

# Offline: regenerate generated/v{N}/oas/ from each committed openapi.json.
# Covers every `components/schemas` entry — WebMessage envelopes, tracker
# read/write, DataValue, AuthScheme leaves, DataIntegrity*, SystemInfo, etc.
d2w dev codegen oas-rebuild --output-root "$OUT"

# Offline, single version — useful when iterating on oas_emit.py / its templates.
d2w dev codegen oas-rebuild --version v42 --output-root "$OUT"
