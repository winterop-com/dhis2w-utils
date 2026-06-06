#!/usr/bin/env bash
# Describe a generated type's fields via `dhis2 schema <type>`.
set -euo pipefail

# The DHIS2 major is auto-detected from the connected server (/api/system/info,
# SNAPSHOT-safe), then the matching generated models are introspected. So the same
# command against a v41 vs a v43 profile shows that version's shape automatically —
# no version pin needed. Fields come from the OpenAPI-derived models (preferred source).
dhis2 schema dataElement

# Plural wire names resolve to the singular class; --json emits a typed object.
dhis2 --json schema dataElements | jq '{name, source, version, field_count}'

# Instance-side shapes work too (not just metadata) — e.g. the web-message envelope.
dhis2 schema WebMessage

# Read the /api/schemas-derived tree instead of OpenAPI (richer field descriptions today).
dhis2 schema dataElement --source schemas
