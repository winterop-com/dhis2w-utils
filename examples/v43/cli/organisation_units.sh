#!/usr/bin/env bash
# Organisation-unit surface under `dhis2 metadata`: four canonical
# sub-apps matching DHIS2's resource paths 1:1 —
#
#   dhis2 metadata organisation-units           /api/organisationUnits
#   dhis2 metadata organisation-unit-groups     /api/organisationUnitGroups
#   dhis2 metadata organisation-unit-group-sets /api/organisationUnitGroupSets
#   dhis2 metadata organisation-unit-levels     /api/organisationUnitLevels
#
# Sierra Leone is the seeded hierarchy; `ImspTQPwCqd` is the country root.
set -euo pipefail

ROOT_UID=ImspTQPwCqd

# ---------------------------------------------------------------------------
# Hierarchy reads
# ---------------------------------------------------------------------------

# Top-level roots — level 1 on every instance is the country root(s).
dhis2 metadata list organisationUnits --filter level:eq:1

# Walk a bounded-depth subtree. Indentation mirrors hierarchyLevel.
dhis2 metadata organisation-units tree "$ROOT_UID" --max-depth 2 | head -40 || true

# Inspect one OU.
dhis2 metadata organisation-units get "$ROOT_UID"

# ---------------------------------------------------------------------------
# Levels — give every depth a human label
# ---------------------------------------------------------------------------

dhis2 metadata list organisationUnitLevels

# `--by-level` resolves the numeric depth to the underlying UID row so
# "level 2" is a stable handle across instances.
dhis2 metadata organisation-unit-levels rename 2 --by-level --name "Province"

# ---------------------------------------------------------------------------
# Groups — CXw2yu5fodb is the "Public" seeded group
# ---------------------------------------------------------------------------

dhis2 metadata list organisationUnitGroups | head -10 || true
dhis2 metadata organisation-unit-groups get CXw2yu5fodb
dhis2 metadata organisation-unit-groups members CXw2yu5fodb --page-size 5

# ---------------------------------------------------------------------------
# Group sets — Bpx0589u8y0 is "Facility Ownership" (seeded)
# ---------------------------------------------------------------------------

dhis2 metadata list organisationUnitGroupSets | head -10 || true
dhis2 metadata organisation-unit-group-sets get Bpx0589u8y0

# ---------------------------------------------------------------------------
# Create / membership / delete round-trip
# ---------------------------------------------------------------------------
# Create an empty group, wire it into a fresh group set, then clean up.

GROUP_OUT=$(dhis2 --json metadata organisation-unit-groups create \
    --name "Example demo group" --short-name "Demo" --color "#3388ff")
GROUP_UID=$(printf '%s' "$GROUP_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

GROUP_SET_OUT=$(dhis2 --json metadata organisation-unit-group-sets create \
    --name "Example demo dimension" --short-name "DemoDim")
GROUP_SET_UID=$(printf '%s' "$GROUP_SET_OUT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

dhis2 metadata organisation-unit-group-sets add-groups "$GROUP_SET_UID" --group "$GROUP_UID"
dhis2 metadata organisation-unit-group-sets get "$GROUP_SET_UID"

dhis2 metadata organisation-unit-group-sets remove-groups "$GROUP_SET_UID" --group "$GROUP_UID"
dhis2 metadata organisation-unit-group-sets delete "$GROUP_SET_UID" --yes
dhis2 metadata organisation-unit-groups delete "$GROUP_UID" --yes
