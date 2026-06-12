#!/usr/bin/env bash
# `d2w metadata program-rules ...` — tracker business-logic workflows.
#
# DHIS2 program rules fire in response to tracker events: hide/show fields,
# emit warnings/errors, assign calculated values. They're configured via
# `ProgramRule`, `ProgramRuleVariable`, and `ProgramRuleAction` metadata.
# Generic CRUD lives under `d2w metadata list programRules` — this
# sub-app layers the authoring + debugging workflows on top.
set -euo pipefail

# The seeded Child Programme carries rules for immunization workflows.
# Swap the UID below for your own.
CHILD_PROGRAM=IpHINAT79UW

# --- List + inspect ---------------------------------------------------------
# Scoped to one program, ordered by priority, with action counts per rule.

d2w metadata list programRules --filter program.id:eq:"$CHILD_PROGRAM"

# Show one rule with its condition + every action resolved inline.
d2w metadata program-rules get GC4gpdoSD4r

# Same as `show` but raw JSON — useful when piping into jq.
d2w --json metadata program-rules get GC4gpdoSD4r | jq '.programRuleActions'

# --- Authoring support ------------------------------------------------------
# What variables can a rule in this program reference?

d2w metadata program-rules vars-for "$CHILD_PROGRAM"

# Parse-check a condition before saving. DHIS2 doesn't expose a dedicated
# program-rule validator — this command uses the program-indicator parser by
# default, which is stricter on DE references but catches most syntactic
# problems. Read the specific error message to distinguish real problems
# from the `#{variableName}` parser mismatch. The command exits 1 on any
# ERROR status, so guard with `|| true` in pipelines where you want to
# surface but not abort on parser-mismatch errors.

d2w metadata program-rules validate-expression '1 + 1 > 0' --context generic || true

# --- Impact analysis --------------------------------------------------------
# Before renaming or removing a DE, find the program rules that reference it.
# Exits 1 if nothing matches — safe in CI pipelines.

d2w metadata program-rules where-de-is-used vANAXwtLwcT

# d2w metadata program-rules where-de-is-used vANAXwtLwcT \
#   && echo "still referenced — don't delete"

# --- Generic surface (for CRUD) ---------------------------------------------
# The workflow commands above layer on the generic metadata endpoints.
# Raw CRUD stays on `d2w metadata list / get` with the DHIS2 resource name.

d2w metadata list programRules --filter "program.id:eq:$CHILD_PROGRAM" \
    --fields 'id,name,priority,condition'
d2w metadata list programRuleVariables \
    --filter "program.id:eq:$CHILD_PROGRAM" \
    --fields 'id,name,programRuleVariableSourceType,dataElement[id]'
