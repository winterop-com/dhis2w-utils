#!/usr/bin/env bash
# d2ql aggregate data — `group by`, the analytics source, and the dataValues source.
#
# `group by <key> { name: agg, ... }` groups rows and reduces each group with
# aggregate functions (sum/avg/min/max/count). It works over ANY source:
# metadata, analytics, or raw data values.
set -euo pipefail

# group by over metadata: data elements per value type.
d2w query eval 'dataElements | group by valueType { n: count() } | order n desc'

# group by over metadata with a nested key.
d2w query eval 'programs | group by programType { n: count() } | order n desc'

# analytics(...) source: aggregated values from /api/analytics, keyed by dimension.
d2w query eval 'analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd") | select dx, pe, value | limit 8'

# analytics + filter + roll up per data element.
d2w query eval 'analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd") | where value > 1000 | group by dx { total: sum(value), periods: count() } | order total desc'

# analytics reshaped into a per-month time series.
d2w query eval 'analytics(dx: "fbfJHSPpUQD", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd") | transform { month: pe, anc1: value } | order month asc'

# dataValues(...) source: raw aggregate values from /api/dataValueSets.
d2w query eval 'dataValues(dataSet: "BfMAe6Itzgt", period: "202401", orgUnit: "ImspTQPwCqd") | transform { de: dataElement, ou: orgUnit, v: value } | limit 8'
