#!/usr/bin/env bash
# Aggregated analytics queries — `d2w analytics query`. Refreshes of the
# analytics backing tables live under `d2w maintenance refresh ...`
# (see maintenance.sh).
set -euo pipefail

# Aggregated analytics for Penta1 doses across all 4 Sierra Leone districts, last 12 months.
d2w analytics query \
  --dim dx:fClA2Erf6IO\;UOlfIjgN8X6 \
  --dim pe:LAST_12_MONTHS \
  --dim ou:ImspTQPwCqd\;LEVEL-2 \
  --skip-meta

# Same query as raw pre-aggregation rows (/api/analytics/rawData).
d2w analytics query --shape raw \
  --dim dx:fClA2Erf6IO \
  --dim pe:LAST_12_MONTHS \
  --dim ou:ImspTQPwCqd

# DataValueSet envelope (easy to round-trip into dataValueSets import).
d2w analytics query --shape dvs \
  --dim dx:fClA2Erf6IO \
  --dim pe:LAST_12_MONTHS \
  --dim ou:ImspTQPwCqd
