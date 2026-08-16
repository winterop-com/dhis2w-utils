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
| Date / datetime | `@2026-06-23`, `@2026-06-23T12:00:00` |
| Array | `["a", "b", "c"]` |
| Object | `{ code: id, label: name }` |

Strings use double quotes (single quotes lex identically). A number with a fractional part is a
`Decimal`, otherwise an `Integer` (the two are distinguished by `is`, below). Date and datetime
literals are covered in their own section next.

## Date and datetime literals

A literal date is written `@YYYY-MM-DD` and a datetime `@YYYY-MM-DDThh:mm:ss` (an optional zone
suffix like `Z` or `+02:00` is accepted). **At runtime a date/datetime literal is its ISO-8601
string** — there is no separate date value type — so `@2026-06-23` evaluates to `"2026-06-23"` and
`@2026-06-23 is String` is `true`. Because ISO-8601 sorts lexicographically, ordinary string
comparison gives the correct chronological order, which is the whole point of the literal:

```text
@2026-06-23 < @2026-07-01                         => [true]
@2026-06-23 = @2026-06-23                          => [true]
@2026-06-23 < @2026-06-23T12:00:00                 => [true]   # a bare date sorts before any time on that day
```

Use them to bound a date field. Against JSON where the field is itself an ISO string (a DHIS2
`lastUpdated`, a FHIR `effectiveDateTime`), the comparison is a plain lexicographic string compare
and reads naturally:

```d2path
lastUpdated >= @2026-01-01 and lastUpdated < @2026-07-01
```

```d2path
created >= @2026-06-23T00:00:00
```

A literal also equals its plain-string twin — `@2026-06-23 = "2026-06-23"` is `true` — so the `@`
form is purely a readability convenience over quoting the date yourself.

> **Note — typed date fields under-match locally.** The comparison is a string compare, so it only
> lines up when the field is *also* a string. When a leading `where` on a date field is
> [pushed down](d2ql.md#pushdown-what-runs-where) to DHIS2, DHIS2's date semantics apply and the
> result is correct. When the same predicate stays local over a wire model whose field parsed into a
> typed timestamp (not a string), the value is not a string and the comparison yields the empty
> collection — it under-matches rather than raising. Keep date predicates leading so they push down,
> or compare over JSON where the field is a string.

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

**Comparison** (existential over collections): `=`, `!=`, `<`, `<=`, `>`, `>=`. See
[Existential comparison](#existential-comparison) for what these mean when a side is a repeated field.

**Matching:** `like` (case-insensitive substring; written `name like "anc"`) and `~` (its symbolic
form) — the two are the same operator, normalised to `~` in the AST. `!~` is its negation
(`name !~ "draft"` keeps names that do *not* contain "draft"). `matches(regex)` handles full regular
expressions.

```d2path
name !~ "draft"
```

**Membership:** `value in ["A", "B"]` tests whether a scalar is one of a list's members;
`collection contains item` is the mirror image — whether a list contains a value. `contains` is
also a string method (`name.contains("ANC")`), disambiguated by its form: infix `contains` between
two expressions is membership, `.contains(...)` on a string tests substring:

```d2path
tags contains "priority"
```

**Logical:** `and`, `or`, `xor`, `implies`, and the `not()` function. `and`/`or`/`implies`
short-circuit on their left operand (so a guarded predicate like `value != 0 and 100 / value > 1`
excludes a row rather than raising); `xor` always evaluates both sides. `xor` is exclusive-or (true
when exactly one side is true); `a implies b` is `not a or b` — vacuously true whenever `a` is false,
and right-associative so `a implies b implies c` groups as `a implies (b implies c)`:

```d2path
active xor deleted
```

```d2path
domainType = "AGGREGATE" implies categoryCombo.name != "default"
```

**Arithmetic:** `+`, `-`, `*`, `/`, integer `div`, `mod`, and unary `-`/`+` — see
[Arithmetic](#arithmetic). `+` also concatenates two strings — see [Building strings](#building-strings).

**Type test:** `value is <Type>` returns a boolean. The five type labels are `Integer`, `Decimal`,
`String`, `Boolean`, and `Object` (any dict / model / nested node; a list is tested by its first
item). An integer literal is `Integer`, a fractional literal is `Decimal`, and a date/datetime
literal is `String` (it is its ISO text):

```d2path
value is Decimal
```

```text
where domainType = "AGGREGATE" and (name like "ANC" or name like "BCG")
where level in [2, 3]
transform { ratio: numerator / denominator, ok: value >= 100 }
```

## Existential comparison

Because every side of a comparison is a collection, `=` `!=` `<` `<=` `>` `>=` are **existential**:
`=` (and `<`, `>`, …) is true when **any** left-item/right-item pair satisfies it, and `!=` / `!~`
are its negation — true when **no** pair matches. That is the intuitive reading for a `where` over a
repeated field. Take a row with `scores: [3, 5, 2]`:

```text
scores = 5    over {"scores":[3,5,2]}   => [true]    # some score is 5
scores = 9    over {"scores":[3,5,2]}   => [false]   # no score is 9
scores != 5   over {"scores":[3,5,2]}   => [false]   # a 5 exists, so "no pair equal" is false
scores != 9   over {"scores":[3,5,2]}   => [true]    # nothing equals 9
scores > 4    over {"scores":[3,5,2]}   => [true]    # some score exceeds 4
```

The subtle case is `!=`: `scores != 5` is **not** "some score differs from 5" (which would always be
true here) — it is "no score equals 5". When both sides are single values this collapses to ordinary
scalar comparison; the existential rule only changes behaviour once a side has more than one item.
For explicit membership regardless of arity, reach for `in` / `contains` instead.

## Building strings

`+` between two strings concatenates them (with numbers it adds — see [Arithmetic](#arithmetic)).
Use it to compose keys, labels, and codes:

```text
"DE-" + id                          over {"id":"abc"}                => ["DE-abc"]
categoryCombo.name + " / " + valueType   over {"categoryCombo":{"name":"default"},"valueType":"NUMBER"}   => ["default / NUMBER"]
```

```d2path
"urn:dhis2:" + id
```

`+` joins exactly two strings at a time. To collapse a whole collection into one string with a
separator, use [`join(sep)`](#splitsep-joinsep) instead — `given.join(" ")` turns `["Ada","Grace"]`
into `"Ada Grace"`, which `+` cannot do because it never sees the list as a unit.

## Arithmetic

`+` `-` `*` operate on the first value of each side (arithmetic is scalar, not existential). Division
comes in two flavours: `/` is true division (`7 / 2` is `3.5`) and `div` is integer division
(`7 div 2` is `3.0` — the quotient, floored toward zero). `mod` is the remainder. Unary `-` negates.
**Dividing by zero raises a typed evaluation error** (`/`, `div`, and `mod` all do), which a
short-circuiting `and` can guard against:

```text
7 / 2       => [3.5]
7 div 2     => [3.0]
7 mod 2     => [1.0]
-balance    over {"balance":40}   => [-40.0]
```

```d2path
numerator / denominator * 100
```

```d2path
value != 0 and total div value > 1
```

Every arithmetic result is a `Decimal` (float); apply [`toInteger()`](#tointeger-todecimal-tostring)
if you need a whole number, and [`round(places)`](#abs-roundplaces) to fix the precision.

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
The first / last item. `last()` is how you reach the end without a negative index (which d2path does
not support — see [Gotchas](#gotchas-and-limits)).
```text
coding.first().code   over {"coding":[{"code":"X"},{"code":"Y"}]}   => ["X"]
scores.last()         over {"scores":[3,5,2]}                        => [2]
```

### `tail()` · `skip(n)` · `take(n)`
All but the first (`tail`); drop the first `n` (`skip`); keep the first `n` (`take`).
```text
scores.tail()    over {"scores":[3,5,2]}   => [5, 2]
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
tags.distinct()     over {"tags":["a","b","a"]}   => ["a", "b"]
tags.isDistinct()   over {"tags":["a","b","a"]}   => [false]
```

### `union(other)` · `combine(other)`
Set union (de-duplicated) and plain concatenation (keeps duplicates).
```text
a.union(b)     # de-duped
a.combine(b)   # concatenated
```

## Strings

### `upper()` · `lower()` · `length()` · `trim()`
Case folding, character length, and whitespace stripping (`trim` removes leading/trailing whitespace).
```text
name.upper()    over {"name":"anc"}      => ["ANC"]
name.lower()    over {"name":"ANC"}      => ["anc"]
name.length()   over {"name":"Penta"}    => [5]
label.trim()    over {"label":"  hi  "}  => ["hi"]
```

### `toChars()`
Split a string into its characters.
```text
code.toChars()   over {"code":"AB"}   => ["A", "B"]
```

### `startsWith(s)` · `endsWith(s)` · `contains(s)`
Prefix, suffix, and substring tests on a string (all case-sensitive; use `~` / `like` for a
case-insensitive substring). The `.contains(s)` *method* tests a substring within one string —
distinct from the infix `collection contains item` membership operator.
```text
name.startsWith("AN")     over {"name":"ANC 1st visit"}   => [true]
name.endsWith("visit")    over {"name":"ANC 1st visit"}   => [true]
name.contains("1st")      over {"name":"ANC 1st visit"}   => [true]
```

### `substring(start, length?)`
Substring from `start`, optionally `length` chars.
```text
name.substring(0, 3)   over {"name":"Albendazole"}   => ["Alb"]
```

### `indexOf(s)` · `replace(find, replacement)`
`indexOf` returns the zero-based position of the first match (or `-1` when absent); `replace`
substitutes every occurrence.
```text
name.indexOf("1st")           over {"name":"ANC 1st visit"}   => [4]
name.replace("visit", "v.")   over {"name":"ANC visit"}       => ["ANC v."]
```

### `matches(regex)`
True if the string matches the regular expression. Patterns run on Python's stdlib `re` engine, and
`matches()` raises a typed evaluation error for a pattern that is invalid, longer than 1000
characters, or that nests quantifiers (`(a+)+`, `(a*)*`, `(a+)*`, `(a*)+`, and kin) — the shape that
drives catastrophic backtracking. That guard is a safety rail for honest mistakes, **not** a defence
against adversarial input: `matches()` is not intended to run untrusted regex.
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
Reduce a numeric collection. A non-numeric member raises rather than being skipped.
```text
scores.sum()   over {"scores":[3,5,2]}   => [10.0]
scores.min()   over {"scores":[3,5,2]}   => [2.0]
scores.max()   over {"scores":[3,5,2]}   => [5.0]
scores.avg()   over {"scores":[3,5,2]}   => [3.3333333333333335]
```
These are also the aggregations used in `group by { total: sum(value) }`.

### `abs()` · `round(places?)`
Absolute value; rounding to `places` decimals (default `0`).
```text
delta.abs()      over {"delta":-4}       => [4.0]
value.round(1)   over {"value":3.14159}  => [3.1]
```

## Conversion & temporal

### `toInteger()` · `toDecimal()` · `toString()`
Parse/format scalars. `toInteger` truncates toward zero; `toDecimal` yields a float; `toString`
renders any scalar (booleans as `"true"`/`"false"`).
```text
value.toInteger()   over {"value":"42"}     => [42]
value.toDecimal()   over {"value":"3.5"}    => [3.5]
active.toString()   over {"active":true}    => ["true"]
```

### `today()` · `now()`
Current date / timestamp as an ISO-8601 string — the same shape as a `@`-date/datetime literal, so
`created >= today()` compares correctly.
```text
today()   => ["2026-06-23"]
now()     => ["2026-06-23T09:12:43.512000"]
```

---

## Gotchas and limits

A handful of edge rules are worth knowing before they surprise you:

- **Indexing takes a non-negative integer literal.** `coding[0]` works; an out-of-bounds index is
  the empty collection, not an error (`coding[99]` → `[]`). A **negative** index (`coding[-1]`) and
  any **computed** index (`coding[1 + 1]`) raise — a `-`/arithmetic result is a `Decimal`, which is
  not a valid subscript. Reach the end with [`last()`](#first-last) / [`tail()`](#tail-skipn-taken)
  instead of a negative index.
- **A boolean is not a valid index.** `items[true]` raises; use `iif(...)` to choose an index value.
- **A string subscript is member-access by key**, not indexing — `node["us-core-race"]` reaches a
  field whose name is not an identifier (hyphens, spaces, leading digit), mirroring `.name`.
- **Division by zero raises** for `/`, `div`, and `mod`; guard with a short-circuiting `and`.
- **Expression nesting is capped at 64 levels** (`MAX_EXPRESSION_DEPTH`) — parentheses/operators
  nested deeper are rejected at parse time. No real query approaches this.
- **A `matches()` pattern is capped at 1000 characters** (`MAX_REGEX_PATTERN_LENGTH`), and an invalid
  pattern or one that nests quantifiers (`(a+)+` and kin) raises a typed error before it ever
  compiles. Together the length cap and the nested-quantifier pre-scan block the common ReDoS shapes,
  but `matches()` is a convenience for well-formed patterns, not a shield for adversarial regex.
- **`define function` composition is capped at 32 levels** (`MAX_FUNCTION_CALL_DEPTH`) and a
  self-referential or cyclic definition is rejected as recursive rather than looping.

## See also

- [d2ql tutorial](d2ql-tutorial.md) and [d2ql reference](d2ql.md) — where these expressions are used.
- [Language semantics](semantics.md) — the precise operator/precedence/pushdown rules.
- [d2path examples](d2path-examples.md) — a validated per-function example gallery.
- [`dhis2w_ql` API](../api/query.md) — evaluate d2path from Python.
