#!/usr/bin/env bash
# d2ql projection + transform — picking columns vs. building new shapes.
#
# `select` picks/renames columns. `transform` builds an arbitrary object per row
# (nested objects, arrays, computed values) — the tool for reshaping and for
# emitting foreign formats like FHIR. Both use d2path expressions for values.
set -euo pipefail

# select: a flat row of chosen fields, including a nested association.
d2w query eval 'dataElements | select id, name, categoryCombo.name as combo | limit 5'

# select with a computed column (call a d2path function).
d2w query eval 'dataElements | select name, name.upper() as upper | limit 5'

# transform: rename and compute into a fresh object.
d2w query eval 'dataElements | transform { code: id, label: name, aggregate: domainType = "AGGREGATE" } | limit 5'

# transform: nested objects and arrays.
d2w query eval 'dataElements | transform { id: id, meta: { type: domainType, value: valueType }, tags: [domainType, valueType] } | limit 3'

# transform: emit a FHIR Observation shape (transform is generic — nothing FHIR-specific in d2ql).
d2w query eval 'dataElements | where domainType = "AGGREGATE" | transform { resourceType: "Observation", status: "final", code: { coding: [ { system: "dhis2", code: id, display: name } ] } } | limit 2'

# transform: map data elements to terminology-style concepts.
d2w query eval 'dataElements | transform { system: "dhis2-dataElements", code: id, display: name } | limit 5'
