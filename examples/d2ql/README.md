# d2ql example programs

Standalone, version-agnostic **d2ql** programs — one query each, with a `//` comment explaining it.
A d2ql program is the same text regardless of the DHIS2 major, so these live here once (not under
`examples/v41|v42|v43`), and the per-version `cli/query_run.sh` runners execute them.

Files are grouped by a name prefix: `metadata-*`, `orgunits-*`, `analytics-*`, `datavalues-*`,
`fhir-*`, `geojson-*`, `export-*`, `sink-*`, `library-*`.

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
| `metadata-group-members.d2ql` | "join": group → its member data elements (nested association) |
| `metadata-dataset-elements.d2ql` | "join": data set → elements via `dataSetElements.dataElement` |
| `metadata-validation-rules.d2ql`, `metadata-tracked-entity-attributes.d2ql` | more resources |

**`orgunits-*`** — the org hierarchy

| File | Shows |
|------|-------|
| `orgunits-per-level.d2ql` | hierarchy rollup with `group by` |
| `orgunits-with-parent.d2ql` | nested association navigation (`parent.name`) |
| `orgunits-with-children.d2ql` | "join": org unit → parent + immediate children |
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
| `datavalues-by-dataset.d2ql` | `dataValues(...)` source (`/api/dataValueSets`) |
| `datavalues-date-window.d2ql` | `dataValues(...)` with `startDate`/`endDate` + `children` |
| `datavalues-with-children.d2ql` | `dataValues(...)` over an org unit subtree (`children: true`) |
| `datavalues-by-group.d2ql` | `dataValues(...)` selected by `dataElementGroup` instead of dataset |

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

**`export-*`** — write results to a file with a `>>` sink (format follows the extension)

| File | Shows |
|------|-------|
| `export-json.d2ql` | rows → a JSON array file (`.json`) |
| `export-ndjson.d2ql` | rows → newline-delimited JSON (`.ndjson`), one object per line |
| `export-csv.d2ql` | an analytics rollup → CSV (`.csv`) |
| `export-fhir-bundle.d2ql` | a FHIR Observation Bundle → a JSON file |
| `export-stdout.d2ql` | the explicit `>> stdout` print sink (same as omitting the sink) |

(`geojson-*` and `fhir-bundle-*` also write files when they end in a `>>` sink.)

**`sink-*`** — control output format independently of destination (`as <format>` / bare-format shorthand)

| File | Shows |
|------|-------|
| `sink-stdout-json.d2ql` | `>> json` — JSON array to stdout (bare-keyword shorthand) |
| `sink-stdout-ndjson.d2ql` | `>> ndjson` — newline-delimited JSON to stdout |
| `sink-stdout-csv.d2ql` | `>> csv` — CSV to stdout (escapes wide tables) |
| `sink-stdout-as.d2ql` | `>> stdout as ndjson` — the explicit long form |
| `sink-file-as-override.d2ql` | `>> "file.txt" as csv` — `as` overrides the extension |

**`geojson-*` / `library-*`**

| File | Shows |
|------|-------|
| `geojson-districts.d2ql` | per-row GeoJSON Feature, file sink |
| `geojson-featurecollection.d2ql` | `transform` + `fold` into one FeatureCollection |
| `library-immunisation.d2ql` | a full library: scalar define + function + named query |
