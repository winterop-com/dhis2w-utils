#!/usr/bin/env bash
# d2ql filtering — `where`, boolean logic, matching, membership, comparisons.
#
# Predicates are written in d2path. Simple field comparisons are pushed down to
# DHIS2's `filter=` (fast); anything the server can't express runs locally.
# Use `d2w query explain '<program>'` to see the split.
set -euo pipefail

# Equality — pushed down to `domainType:eq:AGGREGATE`.
d2w query eval 'dataElements | where domainType = "AGGREGATE" | select id, name | limit 5'

# `like` (alias for `~`) — case-insensitive match; pushes down to `ilike`.
d2w query eval 'dataElements | where name like "anc" | select name | limit 5'

# `and` / `or` combine clauses.
d2w query eval 'dataElements | where domainType = "AGGREGATE" and valueType = "NUMBER" | select name | limit 5'
d2w query eval 'dataElements | where name like "ANC" or name like "BCG" | select name | limit 5'

# `in [...]` membership; `!=` negation; numeric comparisons (`>=` `<=` `>` `<`).
d2w query eval 'dataElements | where valueType in ["NUMBER", "INTEGER"] | select name | limit 5'
d2w query eval 'organisationUnits | where level >= 3 | select name, level | limit 5'

# A nested association path filters too (parent/categoryCombo are real DHIS2 paths).
d2w query eval 'dataElements | where categoryCombo.name = "default" | select name | limit 5'

# Inline filter shorthand: `resource[predicate]` is a leading `where`.
d2w query eval 'dataElements[domainType = "AGGREGATE"] | select name | limit 5'

# A predicate the server cannot express (a function) stays local — same result, work just moves.
d2w query explain 'dataElements | where name.substring(0, 3) = "ANC" | select name'
