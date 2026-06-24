# Query language

**d2ql** is a query and transform language for DHIS2. Instead of stitching together endpoint-specific
parameters (`filter=`, analytics `dx`/`pe`/`ou`, tracker params) and reshaping the JSON yourself, you
write one readable pipeline:

```
dataElements
  | where domainType = "AGGREGATE" and name like "ANC"
  | select id, name, categoryCombo.name as combo
  | transform { code: id, label: name }
  | order name asc
  | limit 20
  >> "elements.csv"
```

It is two languages working together:

- **d2ql** — the pipeline: a **source** (`dataElements`, `analytics(...)`, a file, a named query)
  feeding **stages** (`where`, `select`, `transform`, `order`, `limit`, `count`, `group by`, `fold`)
  and optionally a **sink** (`>>`). `define` / `define function` make a `.d2ql` file a reusable
  library.
- **[d2path](../guides/d2path.md)** — the small expression language used inside every stage:
  path navigation, operators, and functions (`categoryCombo.name`, `name.upper()`, `value > 100`).

## Why

- **One surface for metadata and aggregate data.** Query data elements, indicators, org units,
  analytics, and data values the same way, and reshape the result in the same breath.
- **Fast by default.** Simple filters, ordering, and paging are pushed down to DHIS2; only what the
  server can't express runs locally. `d2w query explain '<program>'` shows the split.
- **Speaks FHIR and GeoJSON.** `transform` + `fold` turn DHIS2 metadata into FHIR Bundles,
  CodeSystems, ValueSets, Questionnaires, or GeoJSON FeatureCollections — nothing FHIR-specific is
  baked into the language; it's just object construction.
- **Available everywhere the toolkit is.** The same engine backs the CLI (`d2w query …`), the MCP
  tools (`query_eval` / `query_explain` / `query_d2path`), and the Python API (`dhis2w_ql`).

## Try it

```bash
# run a query against the active profile
d2w query eval 'dataElements | where domainType = "AGGREGATE" | select id, name | limit 10'

# run a saved program (or use `eval --file` / `-f`)
d2w query run examples/d2ql/analytics-rollup.d2ql
d2w query eval --file examples/d2ql/analytics-rollup.d2ql

# inspect parsing (offline) or the pushdown plan — inline or `--file`
d2w query ast     'dataElements | select id, name | limit 5'
d2w query explain -f examples/d2ql/metadata-anc-elements.d2ql
```

## Where to start

| If you want to… | Go to |
|------------------|-------|
| Learn by doing, step by step | [d2ql tutorial](../guides/d2ql-tutorial.md) |
| Look up a stage, source, or sink | [d2ql reference](../guides/d2ql.md) |
| Look up an operator or function | [d2path](../guides/d2path.md) |
| Copy a working recipe (FHIR, GeoJSON, reports) | [Cookbook](cookbook.md) |
| Use it from Python | [`dhis2w_ql` API](../api/query.md) |

Aggregate data sources (`analytics(...)`, `dataValues(...)`) are covered; event/tracker sources are
on the [roadmap](../roadmap.md).
