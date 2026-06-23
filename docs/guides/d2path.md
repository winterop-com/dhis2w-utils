# d2path — the path + expression language

d2path is the expression language embedded in [d2ql](d2ql.md). It navigates and computes over a
node — a DHIS2 wire model or any JSON document (a FHIR resource, a fixture) — and is used inside
every `where`, `select`, `order`, and `transform`. It is a documented FHIRPath/JSONPath-compatible
subset, so the same expressions that work against FHIR JSON work against DHIS2 models.

Evaluate one against a local document with the CLI (no profile needed):

```bash
d2w query d2path 'name.where(use = "official").family' --input patient.json
```

## Collection semantics

Every expression evaluates to a **collection** (a list). A single value is a one-element
collection, and "no value" is the empty collection. Navigation flattens: `name.given` gathers the
`given` values across every `name`. This is what makes chaining uniform — `where`, `select`,
`first()`, and friends all take and return collections.

```
name.given                    -> ["Ada", "Lovelace", "Countess"]
name.given.first()            -> ["Ada"]
name.given.count()            -> [3]
doesNotExist                  -> []           (missing navigates to empty)
```

## Navigation

- Member access: `categoryCombo.name`, `code.coding.system`
- Indexing: `name[0]`, `dataSetElements[1]`
- Against a FHIR resource, a leading type name resolves to the resource itself, so
  `Patient.name.family` works as written.

## Operators

| Category | Operators |
|----------|-----------|
| Equality | `=` `!=` |
| Match (case-insensitive substring / loose) | `~` `!~` |
| Comparison | `<` `<=` `>` `>=` |
| Membership | `in [a, b]`, `contains` |
| Boolean | `and` `or` `xor` `implies` |
| Arithmetic | `+` `-` `*` `/` `div` `mod` (and `+` concatenates strings) |
| Type test | `is Integer` / `is String` / `is Boolean` / `is Decimal` |

`~` is the case-insensitive "like" operator (`name ~ "anc"`); in d2ql it pushes down to DHIS2
`ilike`. Membership uses array-literal syntax: `valueType in ["NUMBER", "INTEGER"]`. `is` takes a
type name (a bare identifier, e.g. `value is Integer`).

**Comparisons over collections are existential.** Because navigation flattens, a comparison or
match operator against a repeated field is true when **any** value matches — `name.given =
"Lovelace"` is true when `given` is `["Ada", "Lovelace"]`. `!=`/`!~` are the negation ("no value
matches"). Use `contains` / `in` when you want explicit membership semantics.

## Functions

Filtering and projection: `where(expr)`, `select(expr)`, `exists([expr])`, `all(expr)`, `empty()`,
`iif(cond, then, else)`.

Subsetting: `first()`, `last()`, `tail()`, `skip(n)`, `take(n)`, `count()`, `distinct()`,
`isDistinct()`, `union(other)`, `combine(other)`, `not()`.

Strings: `upper()`, `lower()`, `length()`, `trim()`, `startsWith(s)`, `endsWith(s)`, `contains(s)`,
`substring(start[, len])`, `indexOf(s)`, `replace(a, b)`, `matches(regex)`, `split(sep)`,
`join([sep])`.

Math / aggregate: `sum()`, `min()`, `max()`, `avg()`, `abs()`, `round([n])`.

Conversion / temporal: `toInteger()`, `toDecimal()`, `toString()`, `today()`, `now()`.

## Variables

- `$this` — the current row inside a `where`/`select`/`transform` stage.
- `$index` — the current row's position.
- `$name` — a scalar `define`, or a `define function` parameter.

## Examples

```
name.where(use = "official").given.first()        official first name
telecom.where(system = "phone").value              all phone numbers
code.coding.where(system = "http://loinc.org").code   the LOINC code
active = true and gender = "female"                a compound predicate
identifier.where(system = "national").value.first()   first national id
name.given.join(" ")                               join a collection to a string
```

## Relationship to FHIRPath

d2path implements a compatible subset of FHIRPath's navigation, operators, and core functions, with
collection semantics matching the spec. It is not a full FHIRPath/CQL implementation — it is the
expression layer d2ql needs, designed to read the same against FHIR JSON and DHIS2 models. One
deliberate difference: the `|` character is the d2ql pipeline separator, so collection union is the
`union()` function rather than the `|` operator.

## See also

- [d2ql](d2ql.md) — the pipeline language that embeds d2path.
- API reference: [`dhis2w_ql`](../api/query.md).
