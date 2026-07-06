# Language semantics

This page is the precise reference for how d2ql and d2path behave — the rules that the
[tutorial](../guides/d2ql-tutorial.md) and [reference](../guides/d2ql.md) lean on. Read it when a
program does something you didn't expect.

## The two layers

- **d2ql** is the pipeline layer: a source, `|`-separated stages, an optional `>>` sink, and
  top-level `define`s.
- **d2path** is the expression layer used *inside* stages (`where`, `select`, `transform`, `order`,
  `group by`, `fold`). Every value in d2path is a collection (a list); see
  [d2path → Collection semantics](../guides/d2path.md#collection-semantics).

The `|` character only ever separates pipeline stages. Collection union is the `union()` function,
never `|`, so the two layers never collide on it.

## Focus modes

A d2path expression always evaluates against a **focus**. Which focus is in play depends on the
stage — there are three modes:

| Mode | Where | Focus is… | Variables |
|------|-------|-----------|-----------|
| **Row** | `where`, `select`, `transform`, `order` | one row at a time | `$this` (the row), `$index` (its position) |
| **Group** | the `{ … }` of `group by` | the rows in one bucket | aggregations (`sum(value)`) run over the bucket |
| **Whole-stream** | the `{ … }` of `fold` | all rows at once | `$rows` (the whole stream) |

So `value` means different things by mode: a field of the current row (row mode), the set of `value`s
in the bucket (`sum(value)` in group mode), and is not meaningful bare in fold (use `$rows`).

### Focus variables

| Variable | Resolves to | Valid in |
|----------|-------------|----------|
| `$this` | the current row (row mode) or current item (inside a collection method like `.where(…)`) | row-mode stages, method bodies, and a `define function` body (a helper sees the caller's `$this`/`$index`) |
| `$index` | the current row's zero-based position | row-mode stages. In `order` comparators it is fixed to `0` (position is meaningless while sorting) |
| `$rows` | the entire row stream | `fold` only |
| `$Name` | a scalar `define`'s value (`define Min: 3` → `$Min`) | anywhere; resolves scalar defines only, not query defines |
| `$param` | a `define function`'s argument | that function's body |

## Sources and name resolution

A source is one of: a **resource** (a bare identifier like `dataElements`), a **named query** (a
`define`d pipeline used by name), a **call source** (`analytics(…)` / `dataValues(…)`), a **file**
(`read("…")`), or a bare **expression**.

**Resolution priority for a bare identifier** is: a **bound resource first**, then a `define`. So if
the instance exposes a `dataElements` resource, a `define dataElements: …` would be shadowed — name
your defines distinctly. An identifier that matches neither is an error.

### `name(...)` — two call forms

`name(...)` is disambiguated by its arguments, not a reserved list:

- **Named arguments** (`key: value`) → a **call source**: `analytics(dx: "…", pe: "…", ou: "…")`,
  `dataValues(dataSet: "…", period: "…", orgUnit: "…")`. For `analytics(...)`, args split into a
  known analytics-**option** set (`aggregationType`, `outputIdScheme`, `includeNumDen`, `skipMeta`,
  `startDate`/`endDate`, …, plus `filter`) routed to query params, and **dimensions** (everything
  else: `dx`/`pe`/`ou`/`co`/UIDs) — the camelCase option names never collide with dimension keys.
- **Positional arguments or none** → a **d2path function call** (an expression source):
  `today()`, `iif(active, 1, 0)`, a user `define function`.

This is why `define Today: today()` is a scalar define (an expression), not a call source.

### `define` — two kinds

`define NAME: <body>` is a **query define** when the body is a pipeline (`define A: dataElements |
where …`) and a **scalar define** when the body is an expression (`define Min: 3`, `define Today:
today()`). The parser decides by the body's first tokens: a bare identifier / named-arg call /
`read(...)` begins a pipeline source; anything that continues into an expression (a member `.`, an
operator, an infix keyword, or a positional call) is a scalar expression. Use a query define as a
source; reference a scalar define as `$NAME`.

**Definition rules.** Names must be unique — a duplicate `define`/`define function` name is rejected,
not silently overwritten. A `define function` may not reuse a built-in function name (`upper`, `sum`,
…), since the built-in would shadow it, and its parameters must be distinct (`f(x, x)` is rejected).
A definition or function that references itself, directly or through a cycle (`define A: B` /
`define B: A`, or `define function f(x): f($x)`), is rejected as recursive rather than recursing until
it crashes. A `define function` body sees the caller's `$this`/`$index`, so helpers can read the
current row without taking it as a parameter.

## `select` vs `transform`

Both project each row, but differ in output shape and naming:

- **`select e1, e2 as alias, …`** produces a flat object. Each column is named by its `as` alias, or
  derived from the expression: a bare name or a member uses the last segment (`categoryCombo.name` →
  `name`), and anything else becomes `column1`, `column2`, … **If two columns derive the same name
  the program is rejected** — add an alias. Use `select` for tabular output.
- **`transform { … }`** produces an arbitrary object you spell out in full — nested objects, arrays,
  computed fields. Keys are exactly what you write. Use `transform` to build foreign shapes (FHIR,
  GeoJSON) or anything non-tabular. A duplicate key in any object literal (`{ id: id, id: name }`) is
  rejected at parse time, so a repeated key never silently overwrites.

`group by key { … }` names the key column with the same derivation rule (`group by
categoryCombo.name` → key column `name`; a computed key → `column1`); alias by grouping on a
`transform`ed field if you need a specific name. The key name must not collide with an aggregation
name (the program is rejected if it does).

## Operators

Precedence, lowest to highest:

| Tier | Operators |
|------|-----------|
| implication | `implies` |
| or | `or`, `xor` |
| and | `and` |
| equality / match | `=`, `!=`, `~`, `!~`, `like` |
| relational | `<`, `<=`, `>`, `>=`, `in`, `contains`, `is` |
| additive | `+`, `-` |
| multiplicative | `*`, `/`, `div` (integer divide), `mod` |
| unary | prefix `-`, `+` |
| postfix | `.member`, `[index]`, `["key"]`, `.method(...)` |

Notes:

- **`like` and `~` are the same operator** — `like` is the readable spelling, normalised to `~` in
  the AST. There is no symbolic operator for `not`; use the `not()` function or `!=` / `!~`.
- **`contains` is both** an infix operator (`tags contains "x"`) and a method (`name.contains("x")`).
- **`implies` is right-associative:** `a implies b implies c` is `a implies (b implies c)`. Every
  other binary operator is left-associative.
- Comparisons are **existential** over collections (see d2path): `items.qty > 2` is true if any
  collected `qty` exceeds 2.

### String matching

`like` / `~` is **case-insensitive substring** matching — *not* SQL `LIKE` (no `%`/`_` wildcards) and
*not* a regular expression. For full regex use the [`matches(regex)`](../guides/d2path.md#matchesregex)
function. For prefix/suffix use `startsWith` / `endsWith`.

### `null`, missing, and presence

A missing field and an explicit JSON `null` both evaluate to the empty collection, so `field = null`
matches nothing. Test presence with `field.exists()` and absence with `field.empty()` — see
[d2path → Presence and absence](../guides/d2path.md#presence-and-absence-there-is-no-null).

## `[]` is overloaded by position

- **At a source**, `resource[predicate]` is an inline filter: `dataElements[domainType =
  "AGGREGATE"]` is shorthand for `dataElements | where domainType = "AGGREGATE"`.
- **In an expression**, `collection[n]` is integer indexing (`coding[0]`) and `node["key"]` is
  member access by key (see below).

## Field names that aren't identifiers

Member access (`a.b`) accepts identifiers and reserved words only. To reach a field whose name has
hyphens, spaces, or a leading digit (e.g. a FHIR extension key), use a **string subscript** — `[...]`
is integer indexing when given a number and member-access-by-key when given a string:

```text
extension["us-core-race"]      # nested awkward key
items["bad name"].v            # then keep navigating
$this["code-x"]                # a top-level awkward key on the current row
```

## Pushdown — the equivalence it does and doesn't promise

d2ql pushes a leading run of `where` filters, then `order`, then paging, to DHIS2's list endpoint and
runs the rest locally; `d2w query explain` shows the split. The operators are mapped so a pushed
filter selects the same rows as the same filter evaluated locally: `=`→`eq`, `!=`→`ne`,
`~`→`ilike` (both case-insensitive substring), `<`/`<=`/`>`/`>=`→`lt`/`le`/`gt`/`ge`, `in`→`in`. An
audit against the demo server confirmed pushed and local agree for literal values across these
operators (including `!=` over rows where the field is absent).

Four corners are handled or called out explicitly:

- **`~` with `%` or `_`:** DHIS2 `ilike` treats these as SQL wildcards, but d2path `~` is a *literal*
  case-insensitive substring. A `~` value containing `%`/`_` is therefore **kept local** (not pushed)
  so the result matches the literal meaning. `explain` shows it as a local `where`.
- **Values containing `:` `,` `[` `]`:** DHIS2's `property:operator:value` filter syntax has no
  escaping for its own structural characters, so a value like `"a:b,c"` would render as a broken
  clause and silently return wrong rows. Any comparison (or `in` member) whose value contains one of
  these characters is **kept local**; `explain` shows it as a local `where`.
- **Server-side value validation:** DHIS2 validates a pushed filter's value, so an invalid value
  (e.g. an enum in the wrong case like `domainType = "aggregate"`) raises a `400` where local
  evaluation would simply return no rows. Use the exact value DHIS2 expects.
- **Date / datetime comparisons:** when pushed, DHIS2's date semantics apply (correct). The local
  fallback compares values as-is, and a date/datetime field does not compare against a bare string
  literal — so a date comparison that is *not* pushed can under-match. Pin date handling is tracked
  with date-literal support (`@2026-06-23`).

`explain` always tells you exactly what ran where.

## Libraries

A `.d2ql` file is a self-contained library of `define`s and a terminal pipeline; run a specific
definition with `--define <name>`. There is no cross-file `import`/`export` or versioning — a
"library" is one file, shared by copying or running it directly.

Every rule on this page is asserted in `packages/dhis2w-ql/tests/test_semantics.py`, so the spec and
the implementation cannot drift apart silently.

## See also

- [d2ql tutorial](../guides/d2ql-tutorial.md) · [d2ql reference](../guides/d2ql.md) ·
  [d2path](../guides/d2path.md) · [Cookbook](cookbook.md)
