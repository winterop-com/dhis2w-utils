# d2ql example programs

Standalone, version-agnostic **d2ql** programs — one query each, with a `//` comment explaining it.
A d2ql program is the same text regardless of the DHIS2 major, so these live here once (not under
`examples/v41|v42|v43`), and the per-version `cli/query_run.sh` runners execute them.

## Run one

```bash
d2w query run examples/d2ql/org-units-per-level.d2ql
d2w --profile play42 --json query run examples/d2ql/analytics-rollup.d2ql
```

## Inspect one (no server needed)

```bash
d2w query ast "$(cat examples/d2ql/immunisation-library.d2ql)"      # parse tree
d2w query explain "$(cat examples/d2ql/anc-aggregate-elements.d2ql)" # pushdown vs local
```

## Load one from Python

```python
from dhis2w_ql import parse

library = parse(open("examples/d2ql/immunisation-library.d2ql").read())
print([d.name for d in library.definitions])           # ['MinLevel', 'isImmunisation', 'Aggregates']
print([s.kind for s in library.terminal.stages])       # ['where', 'select', 'order', 'limit']
```

## The programs

| File | Shows |
|------|-------|
| `data-elements-by-value-type.d2ql` | `group by` + `count` over metadata |
| `anc-aggregate-elements.d2ql` | `where` + `and` + `like`, `select`, `order` |
| `org-units-per-level.d2ql` | hierarchy rollup with `group by` |
| `districts-with-parent.d2ql` | nested association navigation (`parent.name`) |
| `immunisation-library.d2ql` | a full library: scalar define + function + named query |
| `analytics-time-series.d2ql` | `analytics(...)` source reshaped per month |
| `analytics-rollup.d2ql` | `analytics(...)` + filter + `group by` |
| `districts-geojson.d2ql` | GeoJSON Feature export with a file sink |
| `data-elements-to-fhir.d2ql` | FHIR Observation emit via `transform` |
| `indicators-with-type.d2ql` | nested ref projection |
| `option-sets-with-options.d2ql` | collecting a repeating association into a list |
| `aggregate-data-values.d2ql` | `dataValues(...)` source (`/api/dataValueSets`) |
