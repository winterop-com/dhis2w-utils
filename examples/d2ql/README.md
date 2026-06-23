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

## Inspect one

```bash
# Parse tree — offline, no profile or server needed.
d2w query ast "$(cat examples/d2ql/library-immunisation.d2ql)"

# Pushdown vs. local split — needs the active profile (it checks the instance's
# resource catalog), so it connects to DHIS2.
d2w --profile play42 query explain "$(cat examples/d2ql/metadata-anc-elements.d2ql)"
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
| `analytics-named-output.d2ql` | `outputIdScheme: "NAME"` → readable dx/pe/ou names |
| `analytics-indicator-numden.d2ql` | indicator with `includeNumDen: true` (numerator/denominator/factor) |
| `analytics-aggregation-override.d2ql` | `aggregationType: "AVERAGE"` over the year |
| `analytics-coc-breakdown.d2ql` | category-option-combo (`co`) breakdown |
| `analytics-orgunit-level.d2ql` | `ou: "LEVEL-2;…"` rolled up per district |
| `analytics-date-window.d2ql` | `startDate`/`endDate` window instead of a relative period |
| `analytics-multi-period.d2ql` | multiple explicit periods × multiple `dx` |
| `analytics-multi-orgunit.d2ql` | several districts compared with `group by` |
| `analytics-export-csv.d2ql` | analytics rollup written to a CSV sink |
| `datavalues-by-dataset.d2ql` | `dataValues(...)` source (`/api/dataValueSets`) |

**`fhir-*`** — map DHIS2 metadata to FHIR (named `fhir-<source>-<resource>`)

| File | Shows |
|------|-------|
| `fhir-de-observations.d2ql` | data elements → Observation resources (an array) |
| `fhir-bundle-de.d2ql` | data elements → a proper FHIR Bundle (`define function` + `transform` + `fold`) |
| `fhir-de-codesystem.d2ql` | data elements → one CodeSystem of concepts |
| `fhir-optionset-codesystem.d2ql` | one option set → a CodeSystem |
| `fhir-optionset-valueset.d2ql` | one option set → a ValueSet |
| `fhir-bundle-optionset.d2ql` | many option sets → a Bundle of CodeSystems |
| `fhir-dataset-questionnaire.d2ql` | one data set → a Questionnaire (elements → items) |
| `fhir-bundle-dataset.d2ql` | many data sets → a Bundle of Questionnaires |
| `fhir-bundle-analytics.d2ql` | analytics values → a Bundle of Observations |

**`geojson-*` / `library-*`**

| File | Shows |
|------|-------|
| `geojson-districts.d2ql` | per-row GeoJSON Feature, file sink |
| `geojson-featurecollection.d2ql` | `transform` + `fold` into one FeatureCollection |
| `library-immunisation.d2ql` | a full library: scalar define + function + named query |
