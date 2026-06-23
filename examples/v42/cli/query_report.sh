#!/usr/bin/env bash
# A *full* d2ql workflow: a multi-definition program file run with `d2w query run`.
#
# Unlike the one-liners in query_eval.sh, this writes a reusable d2ql "library"
# (scalar define + a function + a terminal pipeline) to a file and runs it —
# the way a real report or scheduled job would be kept under version control.
set -euo pipefail

program="$(mktemp /tmp/immunisation-XXXXXX.d2ql)"
cat > "$program" <<'D2QL'
// Immunisation coverage building blocks.
define MinLevel: 2
define function isImmunisation(de): $de.name like "BCG" or $de.name like "measles" or $de.name like "Penta"

// Aggregate immunisation data elements, alphabetised.
dataElements
  | where domainType = "AGGREGATE" and isImmunisation($this)
  | select id, name, valueType
  | order name asc
  | limit 20
D2QL

# 1) Inspect the plan: what is pushed down to DHIS2 vs. evaluated locally.
d2w query explain "$(cat "$program")"

# 2) Run the whole program against the active profile.
d2w query run "$program"

# 3) Run it again, writing the rows to CSV instead of stdout.
d2w query run "$program" --out /tmp/immunisation.csv

# A second program: roll analytics up per data element with `group by`.
rollup="$(mktemp /tmp/rollup-XXXXXX.d2ql)"
cat > "$rollup" <<'D2QL'
analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd")
  | where value > 1000
  | group by dx { total: sum(value), periods: count() }
  | order total desc
D2QL
d2w query run "$rollup"

rm -f "$program" "$rollup"
