#!/usr/bin/env bash
# `d2w maintenance predictors run ...` — run DHIS2's predictor engines
# (synthetic data values generated from historical data). CRUD on the
# predictors themselves stays on the generic `d2w metadata list predictors`.
#
# Validation-rule runs (a different engine that returns violations) live in
# the sibling `validation_rules.sh`.
#
# Usage:
#   ./examples/v41/cli/predictors.sh
set -euo pipefail

# The workspace seeds two BCG-dose predictors + a PredictorGroup:
#   PrdAvgBCG01  — avg(#{s46m5MS0hxu.Prlt0C1RF0s}) over 3 monthly samples
#   PrdSumBCG01  — sum(#{s46m5MS0hxu.Prlt0C1RF0s}) over 3 monthly samples
#   PdGImmun001  — group wrapping both
# Seeded 2024 data covers Jan–Dec 2024 at the facility level, so any
# run window inside 2024 produces real predictions.

# Run every predictor on the instance:
d2w maintenance predictors run \
    --start-date 2024-04-01 --end-date 2024-06-30

# Run one predictor by UID:
d2w maintenance predictors run \
    --predictor PrdSumBCG01 \
    --start-date 2024-04-01 --end-date 2024-04-30

# Run a PredictorGroup:
d2w maintenance predictors run \
    --group PdGImmun001 \
    --start-date 2024-04-01 --end-date 2024-06-30

# --- CRUD on predictors ----------------------------------------------------
# Stays on the generic metadata surface — no special plugin:
d2w metadata list predictors --fields 'id,name,generator,sequentialSampleCount'
