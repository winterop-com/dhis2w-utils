# dhis2w-ql

`d2ql` — a pipeline query and transform language with an embedded expression language, `d2path`.
Pure engine, no DHIS2 required: it queries any JSON-shaped data — lists of dicts, Pydantic models,
local `.json`/`.ndjson` files — with a pushdown seam for backends that can answer parts of a query
natively.

This package is the language engine alone: tokenizer, recursive-descent parser, Pydantic AST,
expression evaluator, query planner, and execution engine over a source-agnostic `DataSource`
protocol. Its only dependency is `pydantic`. The DHIS2 binding (live `DataSource`, pushdown
compiler, CLI, MCP tools) lives in the `query` plugin in `dhis2w-core`; FHIR is a consumer of the
engine (`d2path` evaluates over any JSON, and the `transform` stage can emit FHIR resources)
rather than a dependency.

## Install

```bash
uv add dhis2w-ql        # or: pip install dhis2w-ql
```

## Quickstart — d2path over your own JSON

`d2path` is the expression layer: path navigation, operators, and ~40 functions with collection
semantics.

```python
from dhis2w_ql import Evaluator, parse_expression

facilities = [
    {"name": "Ngelehun CHC", "level": 4, "tags": ["chc", "rural"]},
    {"name": "Kailahun MCHP", "level": 4, "tags": ["mchp"]},
    {"name": "Bo District", "level": 2, "tags": []},
]

expression = parse_expression("where(level = 4 and tags.count() > 0).name.select(upper())")
print(Evaluator().evaluate(expression, facilities))
# ['NGELEHUN CHC', 'KAILAHUN MCHP']
```

## Quickstart — a full pipeline over in-memory rows

The pipeline layer adds stages (`where`, `select`, `transform`, `order`, paging, `group by`,
`fold`), named definitions, and sinks. `InMemoryBinder` maps resource names to row lists; any
backend can implement the same `DataSource` protocol and advertise which filters/ordering/paging
it can execute natively — the planner pushes that prefix down and runs the rest locally.

```python
import asyncio

from dhis2w_ql import InMemoryBinder, QueryEngine, parse

program = parse("""
facilities
  | where level = 4
  | select name, level
  | order name asc
  | limit 10
""")

engine = QueryEngine(program, InMemoryBinder({"facilities": facilities}))
result = asyncio.run(engine.run_terminal())
print(result.rows)
# [{'name': 'Kailahun MCHP', 'level': 4}, {'name': 'Ngelehun CHC', 'level': 4}]
```

Programs can also read local files directly — `read("facilities.json")` or
`read("events.ndjson")` as the source — and end in a sink (`>> "out.csv"`,
`>> stdout as ndjson`).

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

## Collection semantics in one minute

- Every expression evaluates to a collection; navigation (`a.b`) flattens one level per hop.
- A single-element collection collapses to its scalar in results.
- String functions (`upper()`, `lower()`, `length()`, `trim()`, `toChars()`) operate on a
  singleton focus; map them over a collection with `select(...)` — `name.select(upper())`.
- Comparisons are existential over collections: `tags = "chc"` is true when any element matches.

## Documentation

- [d2ql tutorial](https://winterop-com.github.io/dhis2w-utils/guides/d2ql-tutorial/) and
  [reference](https://winterop-com.github.io/dhis2w-utils/guides/d2ql/)
- [d2path reference](https://winterop-com.github.io/dhis2w-utils/guides/d2path/) and the
  [generated example catalog](https://winterop-com.github.io/dhis2w-utils/query/d2path-examples/)
  — 140 examples covering every function, each parsed and evaluated in CI against this engine
- [Language semantics](https://winterop-com.github.io/dhis2w-utils/query/semantics/) and the
  [cookbook](https://winterop-com.github.io/dhis2w-utils/query/cookbook/)
- Runnable sample programs: [`examples/d2ql/`](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/d2ql)
  in the repository — every file is parse-tested in CI

The curated catalogs ship in the package: `dhis2w_ql.SAMPLES` (sample programs) and
`dhis2w_ql.DOC_EXAMPLES` (the evaluator-verified example catalog behind the docs page).
