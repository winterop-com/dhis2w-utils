#!/usr/bin/env bash
# `dhis2 metadata program-rule ...` — tracker business-logic workflows.
#
# DHIS2 program rules fire in response to tracker events: hide/show fields,
# emit warnings/errors, assign calculated values. They're configured via
# `ProgramRule`, `ProgramRuleVariable`, and `ProgramRuleAction` metadata.
# Generic CRUD lives under `dhis2 metadata list programRules` — this
# sub-app layers the authoring + debugging workflows on top.
set -euo pipefail

# The seeded Child Programme carries rules for immunization workflows.
# Swap the UID below for your own.
CHILD_PROGRAM=IpHINAT79UW

# --- List + inspect ---------------------------------------------------------
# Scoped to one program, ordered by priority, with action counts per rule.

dhis2 metadata list programRules --filter program.id:eq:"$CHILD_PROGRAM"

# Show one rule with its condition + every action resolved inline.
dhis2 metadata program-rule get GC4gpdoSD4r

# Same as `show` but raw JSON — useful when piping into jq.
dhis2 --json metadata program-rule get GC4gpdoSD4r | jq '.programRuleActions'

# --- Authoring support ------------------------------------------------------
# What variables can a rule in this program reference?

dhis2 metadata program-rule vars-for "$CHILD_PROGRAM"

# Parse-check a condition before saving. DHIS2 doesn't expose a dedicated
# program-rule validator — this command uses the program-indicator parser by
# default, which is stricter on DE references but catches most syntactic
# problems. Read the specific error message to distinguish real problems
# from the `#{variableName}` parser mismatch. The command exits 1 on any
# ERROR status, so guard with `|| true` in pipelines where you want to
# surface but not abort on parser-mismatch errors.

dhis2 metadata program-rule validate-expression '1 + 1 > 0' --context generic || true

# --- Impact analysis --------------------------------------------------------
# Before renaming or removing a DE, find the program rules that reference it.
# Exits 1 if nothing matches — safe in CI pipelines.

dhis2 metadata program-rule where-de-is-used vANAXwtLwcT

# dhis2 metadata program-rule where-de-is-used vANAXwtLwcT \
#   && echo "still referenced — don't delete"

# --- Generic surface (for CRUD) ---------------------------------------------
# The workflow commands above layer on the generic metadata endpoints.
# Raw CRUD stays on `dhis2 metadata list / get` with the DHIS2 resource name.

dhis2 metadata list programRules --filter "program.id:eq:$CHILD_PROGRAM" \
    --fields 'id,name,priority,condition'
dhis2 metadata list programRuleVariables \
    --filter "program.id:eq:$CHILD_PROGRAM" \
    --fields 'id,name,programRuleVariableSourceType,dataElement[id]'
