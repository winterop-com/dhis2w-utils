#!/usr/bin/env bash
# `d2w maintenance validation ...` — validate expressions, run the validation
# engine, browse persisted results. CRUD on the rules themselves stays on the
# generic `d2w metadata list validationRules` surface.
#
# Predictor runs (the synthetic-data-value engine) live in the sibling
# `predictors.sh` — same plugin namespace, different engine.
#
# Usage:
#   ./examples/cli/validation_rules.sh
set -euo pipefail

# --- Expression validation --------------------------------------------------
# Parse-check any DHIS2 expression + render a human description. Useful as a
# pre-save gate before creating a VR or indicator.

d2w maintenance validation validate-expression '#{fClA2Erf6IO}'
d2w maintenance validation validate-expression '#{noSuchDeUid}'

# Per-context parsers: validation-rule / indicator / predictor / program-indicator.
# Each has a different allowed-reference set on the DHIS2 side.
d2w maintenance validation validate-expression '#{fClA2Erf6IO} > 0' --context validation-rule

# --- Validation analysis ----------------------------------------------------
# Evaluate validation rules on an org-unit subtree for a date range. Returns
# violations (cells where the rule evaluates to `false`). Synchronous — no
# `--watch`. `--persist` writes violations to /api/validationResults for
# later inspection; `--notification` fires configured notification templates.
#
# The workspace seeds two BCG validation rules + a ValidationRuleGroup:
#   VrBCGPos001  — BCG <1y must be > 0 (catches legitimate zero-dose months)
#   VrBCGInf001  — BCG <1y == BCG >1y (sentinel — produces reliable violations)
#   VrGImmun001  — group wrapping both

# Run one group against the Sierra Leone root OU (walks the full sub-tree):
d2w maintenance validation run ImspTQPwCqd \
    --start-date 2024-04-01 --end-date 2024-06-30 \
    --group VrGImmun001 --max-results 10

# Run every rule on the instance (no --group):
# d2w maintenance validation run ImspTQPwCqd \
#     --start-date 2024-04-01 --end-date 2024-06-30 --max-results 5

# --- Persisted validation results -------------------------------------------
# Persist the sentinel rule's violations, then browse them via
# /api/validationResults:
d2w maintenance validation run ImspTQPwCqd \
    --start-date 2024-04-01 --end-date 2024-04-30 \
    --group VrGImmun001 --persist --max-results 5

d2w maintenance validation result list --ou ImspTQPwCqd --pe 202404

# Bulk-delete by filter (at least one filter required — can't wipe the whole
# table accidentally):
# d2w maintenance validation result delete --pe 202404

# --- CRUD on validation rules ----------------------------------------------
# Stays on the generic metadata surface — no special plugin:
d2w metadata list validationRules --fields 'id,name,leftSide,rightSide'
