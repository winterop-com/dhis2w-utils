# Query language (`dhis2w_ql`)

`dhis2w_ql` is the engine behind [d2ql](../guides/d2ql.md) and [d2path](../guides/d2path.md): a
pipeline query/transform language with an embedded FHIRPath/JSONPath-compatible expression
language. It is a pure, dependency-light package (pydantic only) — the DHIS2 binding (data sources,
pushdown compiler, CLI, MCP) lives in the `query` plugin in `dhis2w-core`.

## When to reach for it

- Parse a d2ql program or d2path expression to a typed AST (`parse`, `parse_pipeline`,
  `parse_expression`).
- Evaluate d2path over your own data (`Evaluator`) — DHIS2 models, FHIR JSON, fixtures.
- Run a parsed program against any source via the engine (`QueryEngine` + a `ResourceBinder`); split
  pushdown from local work with `plan_pipeline`.
- Browse or generate examples (`SAMPLES`, `generate`).

## Worked example — evaluate d2path over JSON

```python
from dhis2w_ql import Evaluator, parse_expression

patient = {"name": [{"use": "official", "given": ["Ada"], "family": "King"}]}
result = Evaluator().evaluate(parse_expression('name.where(use = "official").family'), [patient])
assert result == ["King"]
```

## Worked example — run a program over an in-memory source

```python
import asyncio

from dhis2w_ql import InMemoryBinder, QueryEngine, parse

rows = [{"id": "a1", "name": "ANC", "domainType": "AGGREGATE"}]
engine = QueryEngine(parse('dataElements | where domainType = "AGGREGATE" | transform { code: id }'),
                     InMemoryBinder({"dataElements": rows}))
print(asyncio.run(engine.run_terminal()).rows)  # [{'code': 'a1'}]
```

## Reference

::: dhis2w_ql
