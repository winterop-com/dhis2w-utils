#!/usr/bin/env bash
# Outlier detection + tracked-entity analytics — the two remaining /api/analytics surfaces.
# Run via `uv run bash examples/v42/cli/analytics_outlier_tracked_entities.sh`.
set -euo pipefail

# --- Outlier detection -------------------------------------------------------
# Finds data values that deviate from the historical pattern of their series.
# Z_SCORE is the default; MODIFIED_Z_SCORE is more robust when outliers already
# exist in the training data; MIN_MAX uses hard min/max bounds.
# (Upstream DHIS2 quirk: OpenAPI emits `MOD_Z_SCORE` but the server rejects it
# at runtime, accepting `MODIFIED_Z_SCORE` instead. See BUGS.md.)

echo "--- Z-score outliers in Kambia, last 12 months (threshold=2.0)"
d2w analytics outlier-detection \
    --data-set BfMAe6Itzgt \
    --org-unit PMa2VCrupOd \
    --period LAST_12_MONTHS \
    --algorithm Z_SCORE --threshold 2.0 --max-results 5

echo
echo "--- Same query with modified Z-score (robust to existing outliers), descending"
d2w analytics outlier-detection \
    --data-set BfMAe6Itzgt --org-unit PMa2VCrupOd --period LAST_12_MONTHS \
    --algorithm MODIFIED_Z_SCORE --threshold 3.5 --max-results 3 --sort-order DESC

# --- Tracked entity analytics ------------------------------------------------
# Line-lists tracked entities of a given type. The seeded Sierra Leone fixture
# ships one TET "Person (Play)" (uid=nEenWmSyUEp) with 500 enrolled children
# from the Child Programme sample (IpHINAT79UW).

echo
echo "--- list tracked entities of type Person (Play) under Sierra Leone (descendants), first 3"
d2w analytics tracked-entities query nEenWmSyUEp \
    --dimension ou:ImspTQPwCqd --ou-mode DESCENDANTS \
    --page-size 3 --asc created
