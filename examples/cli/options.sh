#!/usr/bin/env bash
# OptionSet + Option workflows via `d2w metadata`.
# Two layers: the generic list/get surface (works for every resource) and
# the workflow-specific `metadata option-sets get / find / sync` commands.
set -euo pipefail

# --- Workflow commands (d2w metadata option-sets) ----------------------------
# Show one OptionSet with its options resolved inline. Accepts a UID or
# the set's business code — whichever you happen to have in hand.

d2w metadata option-sets get VACCINE_TYPE
d2w --json metadata option-sets get OsVaccType1

# Pinpoint a single option inside a set by code (or by display name):
d2w metadata option-sets find --set VACCINE_TYPE --code BCG
d2w metadata option-sets find --set OsVaccType1 --name Measles

# Idempotent bulk sync from a JSON spec file. Spec is an array of
# `{code, name, sort_order?}` objects. `--dry-run` prints the diff
# without touching DHIS2; `--remove-missing` deletes options whose
# code isn't in the spec (off by default — safer for partial refreshes).

cat > /tmp/vaccine-spec.json <<'JSON'
[
  {"code": "BCG", "name": "BCG"},
  {"code": "MEASLES", "name": "Measles vaccine"},
  {"code": "POLIO", "name": "Polio"},
  {"code": "DPT", "name": "DPT"},
  {"code": "HEPB", "name": "Hepatitis B"},
  {"code": "HPV", "name": "HPV vaccine"}
]
JSON

d2w metadata option-sets sync VACCINE_TYPE /tmp/vaccine-spec.json --dry-run
d2w metadata option-sets sync VACCINE_TYPE /tmp/vaccine-spec.json

# Rollback to the original 5 options — remove HPV with --remove-missing,
# restore MEASLES to its original name:
cat > /tmp/vaccine-rollback.json <<'JSON'
[
  {"code": "BCG", "name": "BCG"},
  {"code": "MEASLES", "name": "Measles"},
  {"code": "POLIO", "name": "Polio"},
  {"code": "DPT", "name": "DPT"},
  {"code": "HEPB", "name": "Hepatitis B"}
]
JSON
d2w metadata option-sets sync VACCINE_TYPE /tmp/vaccine-rollback.json --remove-missing

# --- External-system code mapping (Attribute values) ----------------------
# DHIS2 lets you attach arbitrary typed key-value pairs to any metadata
# resource via Attributes + AttributeValues. The seed fixture wires a
# SNOMED_CODE Attribute onto every vaccine option — exactly the shape
# external integrations use for ICD-10 / SNOMED / LOINC code mapping.

# Read one attribute value by Option UID + attribute business code:
d2w metadata attributes get options OptVacBCG01 SNOMED_CODE

# Reverse lookup — given an external code, find the DHIS2 Option.
# THE integration killer: external system hands you a SNOMED code, you
# return the DHIS2 Option UID it maps to.
d2w metadata attributes find options SNOMED_CODE 386661006                    # measles vaccine immunisation

# Misses exit 1 with a stderr hint — safe in pipelines:
# d2w metadata attributes find options SNOMED_CODE 999999999

# Set / replace an attribute value — read-merge-write, idempotent:
d2w metadata attributes set options OptVacBCG01 SNOMED_CODE TESTING-XYZ
d2w metadata attributes get options OptVacBCG01 SNOMED_CODE   # → TESTING-XYZ
d2w metadata attributes set options OptVacBCG01 SNOMED_CODE 77656005   # restore

# --- Generic metadata surface (works for every resource) -------------------

d2w metadata list optionSets --fields 'id,code,name,valueType'
d2w metadata list optionSets \
    --filter 'code:eq:VACCINE_TYPE' \
    --fields 'id,code,name,valueType,options[id,code,name,sortOrder]'

# Every option in one set (server-side filter + sort-order):
d2w metadata list options \
    --filter 'optionSet.id:eq:OsVaccType1' \
    --order 'sortOrder:asc' \
    --fields 'id,code,name,sortOrder'

# Export a set as a metadata bundle — useful for moving between instances:
d2w metadata export \
    --resource optionSets \
    --resource options \
    --filter 'optionSets:code:eq:VACCINE_TYPE' \
    --output /tmp/vaccine-type.json

# d2w metadata import /tmp/vaccine-type.json --dry-run

# Create an OptionSet directly (no hand-written import bundle needed), then add
# its options with `options sync`, then delete it.
# OS_UID=$(d2w --json metadata option-sets create --name "Vaccine type" --value-type TEXT --code VACCINE_TYPE | jq -r '.response.uid')
# d2w metadata option-sets sync "$OS_UID" /tmp/vaccine-options.json
# d2w metadata option-sets delete "$OS_UID" --yes
