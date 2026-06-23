# d2ql example programs

Standalone, version-agnostic **d2ql** programs — one query each, with a `//` comment explaining it.
A d2ql program is the same text regardless of the DHIS2 major, so these live here once (not under
`examples/v41|v42|v43`), and the per-version `cli/query_run.sh` runners execute them.

Files are grouped by a name prefix: `metadata-*`, `orgunits-*`, `analytics-*`, `datavalues-*`,
`fhir-*`, `geojson-*`, `library-*`.

## Run one

```bash
d2w query run examples/d2ql/orgunits-per-level.d2ql
d2w --profile play42 --json query run examples/d2ql/analytics-rollup.d2ql
```

## Inspect one (no server needed)

```bash
d2w query ast "$(cat examples/d2ql/library-immunisation.d2ql)"   # parse tree
d2w query explain "$(cat examples/d2ql/metadata-anc-elements.d2ql)" # pushdown vs local
```

## Load one from Python

```python
from dhis2w_ql import parse

library = parse(open("examples/d2ql/library-immunisation.d2ql").read())
print([d.name for d in library.definitions])           # ['MinLevel', 'isImmunisation', 'Aggregates']
print([s.kind for s in library.terminal.stages])       # ['where', 'select', 'order', 'limit']
```

## The programs

**`metadata-*`** — explore the data dictionary

| File | Shows |
|------|-------|
| `metadata-elements-by-value-type.d2ql` | `group by` + `count` |
| `metadata-anc-elements.d2ql` | `where` + `and` + `like`, `select`, `order` |
| `metadata-aggregation-types.d2ql` | `group by` an enum field |
| `metadata-indicators.d2ql` | nested ref projection (`indicatorType.name`) |
| `metadata-data-sets.d2ql`, `metadata-programs.d2ql`, `metadata-constants.d2ql` | simple projections |
| `metadata-categories.d2ql`, `metadata-category-combos.d2ql` | repeating association → list |
| `metadata-option-sets.d2ql`, `metadata-legend-sets.d2ql`, `metadata-indicator-groups.d2ql` | nested association lists |
| `metadata-validation-rules.d2ql`, `metadata-tracked-entity-attributes.d2ql` | more resources |

**`orgunits-*`** — the org hierarchy

| File | Shows |
|------|-------|
| `orgunits-per-level.d2ql` | hierarchy rollup with `group by` |
| `orgunits-with-parent.d2ql` | nested association navigation (`parent.name`) |
| `orgunits-groups.d2ql` | organisation unit groups |

**`analytics-*` / `datavalues-*`** — aggregate data

| File | Shows |
|------|-------|
| `analytics-time-series.d2ql` | `analytics(...)` reshaped per month |
| `analytics-rollup.d2ql` | `analytics(...)` + filter + `group by` |
| `analytics-anc-coverage.d2ql` | multi-`dx` analytics line listing |
| `datavalues-by-dataset.d2ql` | `dataValues(...)` source (`/api/dataValueSets`) |

**`fhir-*` / `geojson-*` / `library-*`** — transform + fold

| File | Shows |
|------|-------|
| `library-immunisation.d2ql` | a full library: scalar define + function + named query |
| `fhir-observations.d2ql` | FHIR Observation emit via `transform` (array of resources) |
| `fhir-bundle.d2ql` | a *proper* FHIR Bundle: `define function` + `transform` + `fold` |
| `fhir-codesystem.d2ql` | `fold` an option set's options into a FHIR CodeSystem |
| `geojson-districts.d2ql` | per-row GeoJSON Feature, file sink |
| `geojson-featurecollection.d2ql` | `transform` + `fold` into one FeatureCollection |
