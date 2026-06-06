#!/usr/bin/env bash
# Describe a generated type's fields via `dhis2 schema <type>` (offline; no server call).
set -euo pipefail

# The field shape of a metadata type, from the OpenAPI-derived models (the preferred source).
# Output reflects the ACTIVE version tree (profile.version / DHIS2_VERSION), so the same
# command against a v41 vs a v43 profile can differ.
dhis2 schema dataElement

# Plural wire names resolve to the singular class; --json emits a typed object.
dhis2 --json schema dataElements | jq '{name, source, version, field_count}'

# Instance-side shapes work too (not just metadata) — e.g. the web-message envelope.
dhis2 schema WebMessage

# Read the /api/schemas-derived tree instead of OpenAPI (richer field descriptions today).
dhis2 schema dataElement --source schemas
