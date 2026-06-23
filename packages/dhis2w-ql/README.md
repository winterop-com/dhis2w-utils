# dhis2w-ql

`d2ql` — a pipeline query and transform language with an embedded expression language, `d2path`.

This member is the pure language engine: tokenizer, recursive-descent parser, Pydantic AST,
expression evaluator, query planner, and execution engine over a source-agnostic `DataSource`
protocol. It has no DHIS2 or FHIR runtime dependency — the DHIS2 binding (live `DataSource`,
pushdown compiler, CLI, MCP tools) lives in the `query` plugin in `dhis2w-core`, and FHIR is a
consumer of the engine (`d2path` evaluates over any JSON, and the `transform` stage can emit FHIR
resources) rather than a dependency.

## Language shape

```
define ActiveAggregates:
  dataElements | where domainType = "AGGREGATE"

ActiveAggregates
  | where name ~ "ANC"
  | select id, name, categoryCombo.name as combo
  | transform { code: id, label: name }
  | order name asc
  | limit 20
  >> "elements.csv"
```

- **Expression layer** (`d2path`): path navigation, operators, and functions with collection
  semantics — used inside `where`, `select`, `order`, and `transform`.
- **Pipeline layer**: stages separated by `|`, optionally ending in a `>>` sink.
- **Definitions**: `define NAME: ...` and `define function NAME(args): ...` make a `.d2ql` file
  a reusable library of named queries and helpers.

The pipeline `|` is the stage separator; collection union is the `union()` function (not the `|`
operator) to keep the two unambiguous.
