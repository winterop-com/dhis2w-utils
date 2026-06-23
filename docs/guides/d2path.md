# d2path

**d2path** is the expression language used inside every d2ql stage (`where`, `select`, `transform`,
`order`, `group by`, `fold`). It navigates and computes over data with dotted path navigation,
operators, and functions, and works the same whether the data is a DHIS2 wire model or any plain
JSON document (so it can read and emit JSON like FHIR resources too).

Try any expression standalone against a JSON file:

```bash
echo '{"name":"ANC 1st visit"}' > patient.json
d2w query d2path 'name.upper()' --input patient.json     # => ["ANC 1ST VISIT"]
```

## Collection semantics

**Every expression evaluates to a list** — there are no scalars under the hood. A single value is a
one-item list, a missing path is the empty list `[]`. Navigation *flattens*: `items.qty` walks into
every `items` element and collects each `qty`.

This is why comparisons are *existential*: `items.qty > 2` is true if **any** collected `qty` exceeds
2. The CLI/engine `collapse`s a one-item list to that item when building output, so `name.upper()`
shows as `"ANC"`, not `["ANC"]`, in a `select`.

## Presence and absence — there is no `= null`

A missing field and an explicit JSON `null` both evaluate to the **empty collection** `[]`. There is
therefore no useful `field = null`: comparing against the empty collection yields
empty (treated as false), so `where deleted = null` matches nothing and is never pushed down. Test
presence and absence with functions instead:

```text
where field.exists()    # keep rows where the field is present (non-null)
where field.empty()     # keep rows where the field is absent or null
```

`null` is still a writable literal (e.g. `transform { note: null }`); it just isn't something you
compare with `=`/`!=`.

## Literals

| Form | Example |
|------|---------|
| String (double-quoted) | `"AGGREGATE"` |
| Number | `42`, `3.14` |
| Boolean / null | `true`, `false`, `null` |
| Array | `["a", "b", "c"]` |
| Object | `{ code: id, label: name }` |

## Variables

| Variable | Meaning |
|----------|---------|
| `$this` | The current row (in a stage) or item (inside a function applied per element). |
| `$index` | Zero-based position of the current row. |
| `$rows` | Inside `fold`, the whole stream of rows. |
| `$name` | A `define`d scalar, e.g. `define MinLevel: 3` → `$MinLevel`. |
| `$param` | A `define function`'s parameter, e.g. `define function f(de): $de.name`. |

## Navigation

| Syntax | Meaning | Example |
|--------|---------|---------|
| `a.b` | Member access (flattens over collections) | `categoryCombo.name` |
| `a[0]` | Index into a collection | `coding[0]` |
| `a["key"]` | Member access by key, for non-identifier field names | `extension["us-core-race"]` |
| `a.b.c` | Chained navigation | `name.given.first()` |

```text
# coding.where(system = "dhis2").code  over  {"coding":[{"system":"dhis2","code":"X"},{"system":"loinc","code":"Y"}]}
=> ["X"]
```

## Operators

**Comparison** (existential over collections): `=`, `!=`, `<`, `<=`, `>`, `>=`.

**Matching:** `like` (case-insensitive substring; written `name like "anc"`) and `~` (its symbolic
form). `matches(regex)` for full regular expressions.

**Membership:** `value in ["A", "B"]`; `collection contains item`.

**Logical:** `and`, `or`, `xor`, `implies`, and the `not()` function. `and`/`or` short-circuit.

**Arithmetic:** `+`, `-`, `*`, `/`, integer `div`, `mod`.

**Type test:** `value is Integer` (also `Decimal`, `String`, `Boolean`).

```text
where domainType = "AGGREGATE" and (name like "ANC" or name like "BCG")
where level in [2, 3]
transform { ratio: numerator / denominator, ok: value >= 100 }
```

---

# Function reference

Functions are called with method syntax on their input collection — `name.upper()`,
`items.where(qty > 0)` — except `iif`, which is a free function. Every example below is run with
`d2w query d2path '<expr>' --input data.json` and shows the real result.

## Filtering & projection

### `where(predicate)`
Keep items for which `predicate` is true. `$this` is the current item.
```text
coding.where(system = "dhis2").code   over {"coding":[{"system":"dhis2","code":"X"},{"system":"loinc","code":"Y"}]}
=> ["X"]
```

### `select(expr)`
Map each item to `expr` (project). Build a new object per item with `{ … }`.
```text
options.select({ code: code, display: name })   # one {code, display} per option
```

### `exists(predicate?)`
True if any item exists (optionally matching `predicate`).
```text
items.exists(qty > 2)   over {"items":[{"qty":1},{"qty":5}]}   => [true]
```

### `all(predicate)`
True if `predicate` holds for every item.
```text
items.all(qty > 0)   over {"items":[{"qty":1},{"qty":5}]}   => [true]
```

### `empty()`
True if the collection is empty.
```text
tags.empty()   over {"tags":[]}   => [true]
```

### `iif(condition, then, else)`
Conditional expression (free function).
```text
iif(active, "on", "off")   over {"active":true}   => ["on"]
```

### `not()`
Boolean negation of a single-item boolean collection.
```text
active.not()   over {"active":false}   => [true]
```

## Subsetting & set operations

### `first()` · `last()`
The first / last item.
```text
coding.first().code   over {"coding":[{"code":"X"},{"code":"Y"}]}   => ["X"]
```

### `tail()` · `skip(n)` · `take(n)`
All but the first (`tail`); drop the first `n` (`skip`); keep the first `n` (`take`).
```text
scores.skip(1)   over {"scores":[3,5,2]}   => [5, 2]
scores.take(2)   over {"scores":[3,5,2]}   => [3, 5]
```

### `count()`
Number of items.
```text
parts.split(",").count()   over {"parts":"a,b,c"}   => [3]
```

### `distinct()` · `isDistinct()`
Unique items; whether all items are already unique.
```text
tags.distinct()   over {"tags":["a","b","a"]}   => ["a", "b"]
```

### `union(other)` · `combine(other)`
Set union (de-duplicated) and plain concatenation (keeps duplicates).
```text
a.union(b)     # de-duped
a.combine(b)   # concatenated
```

## Strings

### `upper()` · `lower()` · `length()` · `trim()`
```text
name.upper()    over {"name":"anc"}    => ["ANC"]
name.lower()    over {"name":"ANC"}    => ["anc"]
name.length()   over {"name":"Penta"}  => [5]
```

### `toChars()`
Split a string into its characters.
```text
code.toChars()   over {"code":"AB"}   => ["A", "B"]
```

### `startsWith(s)` · `endsWith(s)` · `contains(s)`
```text
name.startsWith("AN")   over {"name":"ANC 1st visit"}   => [true]
```

### `substring(start, length?)`
Substring from `start`, optionally `length` chars.
```text
name.substring(0, 3)   over {"name":"Albendazole"}   => ["Alb"]
```

### `indexOf(s)` · `replace(find, replacement)`
```text
name.replace("visit", "v.")   over {"name":"ANC visit"}   => ["ANC v."]
```

### `matches(regex)`
True if the string matches the regular expression.
```text
code.matches("^[A-Z]{2}[0-9]+$")
```

### `split(sep)` · `join(sep)`
Split a string into a list; join a list into a string.
```text
parts.split(",")        over {"parts":"a,b,c"}                       => ["a", "b", "c"]
name.given.join(" ")    over {"name":{"given":["Ada","Lovelace"]}}   => ["Ada Lovelace"]
```

## Numbers & aggregates

### `sum()` · `min()` · `max()` · `avg()`
Reduce a numeric collection.
```text
scores.sum()   over {"scores":[3,5,2]}   => [10.0]
scores.avg()   over {"scores":[3,5,2]}   => [3.3333333333333335]
scores.max()   over {"scores":[3,5,2]}   => [5.0]
```
These are also the aggregations used in `group by { total: sum(value) }`.

### `abs()` · `round(places?)`
```text
value.round(1)   over {"value":3.14159}   => [3.1]
```

## Conversion & temporal

### `toInteger()` · `toDecimal()` · `toString()`
Parse/format scalars.
```text
value.toInteger()   over {"value":"42"}   => [42]
```

### `today()` · `now()`
Current date / timestamp (ISO 8601).
```text
today()   => ["2026-06-23"]
```

---

## See also

- [d2ql tutorial](d2ql-tutorial.md) and [d2ql reference](d2ql.md) — where these expressions are used.
- [`dhis2w_ql` API](../api/query.md) — evaluate d2path from Python.
