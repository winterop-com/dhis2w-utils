#!/usr/bin/env bash
# `d2w query` — run d2ql programs and d2path expressions over DHIS2 metadata.
#
# d2ql is a pipeline language (source | where | select | transform | order |
# limit >> sink); d2path is the embedded FHIRPath/JSONPath-compatible
# expression language used inside each stage.
set -euo pipefail

# --- Parse a program to its AST (offline — no server needed) ---------------
d2w query ast 'dataElements | where domainType = "AGGREGATE" | select id, name | limit 5'

# --- Run a query against the active profile --------------------------------
d2w query eval 'dataElements | where domainType = "AGGREGATE" | select id, name as label | limit 5'

# --- Show what is pushed down to DHIS2 vs. evaluated locally ---------------
d2w query explain 'dataElements | where name ~ "ANC" | transform { code: id } | limit 5'

# --- Reshape rows and write CSV --------------------------------------------
d2w query eval 'dataElements | transform { code: id, label: name } | limit 5 >> "/tmp/d2ql-elements.csv"'

# --- Aggregate: roll up analytics values per data element ------------------
d2w query eval 'analytics(dx: "fbfJHSPpUQD;cYeuwXTCPkU", pe: "LAST_12_MONTHS", ou: "ImspTQPwCqd") | aggregate by dx { total: sum(value) } | order total desc'
