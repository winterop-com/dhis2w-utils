# d2path examples

A validated gallery of d2path expressions grouped by category. Every expression, its input, and its result are checked by the test suite (`packages/dhis2w-ql/tests/test_doc_examples.py`) and rendered from `dhis2w_ql.doc_examples.DOC_EXAMPLES` — do not edit by hand. Rebuild via `make docs-d2path` (chained into `make docs-build`).

**Total examples**: 140.

## Filtering & projection

### `where()`

Keep the matching sub-object, then navigate into it.

```d2path
name.where(use = "official").family
```

Input:
```json
{
  "name": [
    {
      "use": "official",
      "given": [
        "Ada",
        "Lovelace"
      ],
      "family": "King"
    },
    {
      "use": "nick",
      "given": [
        "Countess"
      ]
    }
  ]
}
```

Result:
```json
[
  "King"
]
```

Filter a collection of objects by a numeric predicate on `$this`.

```d2path
items.where(qty > 2)
```

Input:
```json
{
  "items": [
    {
      "qty": 1
    },
    {
      "qty": 5
    },
    {
      "qty": 3
    }
  ]
}
```

Result:
```json
[
  {
    "qty": 5
  },
  {
    "qty": 3
  }
]
```

Select one telecom channel by its system, then read its value.

```d2path
telecom.where(system = "phone").value
```

Input:
```json
{
  "telecom": [
    {
      "system": "phone",
      "value": "555-1"
    },
    {
      "system": "email",
      "value": "a@b.c"
    }
  ]
}
```

Result:
```json
[
  "555-1"
]
```

Filter data elements by valueType, then read the surviving names.

```d2path
elements.where(valueType = "NUMBER").name
```

Input:
```json
{
  "elements": [
    {
      "name": "Malaria cases",
      "valueType": "NUMBER"
    },
    {
      "name": "Clinical notes",
      "valueType": "TEXT"
    }
  ]
}
```

Result:
```json
[
  "Malaria cases"
]
```

### `select()`

Reshape each item into a new object with an object constructor.

```d2path
options.select({ code: code, display: name })
```

Input:
```json
{
  "options": [
    {
      "code": "M",
      "name": "Male"
    },
    {
      "code": "F",
      "name": "Female"
    }
  ]
}
```

Result:
```json
[
  {
    "code": "M",
    "display": "Male"
  },
  {
    "code": "F",
    "display": "Female"
  }
]
```

Map every item through an arithmetic expression on `$this`.

```d2path
scores.select($this * 2)
```

Input:
```json
{
  "scores": [
    1,
    2,
    3
  ]
}
```

Result:
```json
[
  2.0,
  4.0,
  6.0
]
```

Project and transform a field from each item.

```d2path
people.select(name.upper())
```

Input:
```json
{
  "people": [
    {
      "name": "ada"
    },
    {
      "name": "bob"
    }
  ]
}
```

Result:
```json
[
  "ADA",
  "BOB"
]
```

Rename organisation-unit fields into a compact projection.

```d2path
orgUnits.select({ id: id, depth: level })
```

Input:
```json
{
  "orgUnits": [
    {
      "id": "SL",
      "level": 1
    },
    {
      "id": "Bo",
      "level": 2
    }
  ]
}
```

Result:
```json
[
  {
    "id": "SL",
    "depth": 1
  },
  {
    "id": "Bo",
    "depth": 2
  }
]
```

### `iif()`

Return one of two values based on a predicate.

```d2path
iif(gender = "male", "M", "F")
```

Input:
```json
{
  "gender": "male"
}
```

Result:
```json
[
  "M"
]
```

Branch on a boolean field.

```d2path
iif(active, "on", "off")
```

Input:
```json
{
  "active": false
}
```

Result:
```json
[
  "off"
]
```

Threshold a numeric field into a label.

```d2path
iif(qty > 10, "high", "low")
```

Input:
```json
{
  "qty": 5
}
```

Result:
```json
[
  "low"
]
```

Label a coverage value that clears a target.

```d2path
iif(value > 50, "high", "low")
```

Input:
```json
{
  "value": 87
}
```

Result:
```json
[
  "high"
]
```

## Existence & logic

### `exists()`

With no argument, report whether the collection is non-empty.

```d2path
codes.exists()
```

Input:
```json
{
  "codes": [
    "ANC1"
  ]
}
```

Result:
```json
[
  true
]
```

An empty (or missing) collection does not exist.

```d2path
orgUnits.exists()
```

Input:
```json
{
  "orgUnits": []
}
```

Result:
```json
[
  false
]
```

With a predicate, report whether any item satisfies it.

```d2path
rows.exists(value > 20)
```

Input:
```json
{
  "rows": [
    {
      "value": 12
    },
    {
      "value": 30
    }
  ]
}
```

Result:
```json
[
  true
]
```

### `all()`

True when every item satisfies the predicate.

```d2path
rows.all(active)
```

Input:
```json
{
  "rows": [
    {
      "active": true
    },
    {
      "active": true
    }
  ]
}
```

Result:
```json
[
  true
]
```

A single failing item makes `all` false.

```d2path
stages.all(completed)
```

Input:
```json
{
  "stages": [
    {
      "completed": true
    },
    {
      "completed": false
    }
  ]
}
```

Result:
```json
[
  false
]
```

### `empty()`

An empty collection is empty.

```d2path
tags.empty()
```

Input:
```json
{
  "tags": []
}
```

Result:
```json
[
  true
]
```

A non-empty collection is not empty.

```d2path
roles.empty()
```

Input:
```json
{
  "roles": [
    "ADMIN"
  ]
}
```

Result:
```json
[
  false
]
```

A missing field navigates to the empty collection, which is empty.

```d2path
closedDate.empty()
```

Input:
```json
{
  "openingDate": "2020-01-01"
}
```

Result:
```json
[
  true
]
```

### `not()`

Negate a boolean field.

```d2path
verified.not()
```

Input:
```json
{
  "verified": false
}
```

Result:
```json
[
  true
]
```

Negate a true flag.

```d2path
flag.not()
```

Input:
```json
{
  "flag": true
}
```

Result:
```json
[
  false
]
```

An empty focus is falsy, so `not()` returns true.

```d2path
middleName.not()
```

Input:
```json
{
  "firstName": "Ada"
}
```

Result:
```json
[
  true
]
```

## Subsetting & set operations

### `first()`

Keep the first item of a collection.

```d2path
first()
```

Input:
```json
[
  10,
  20,
  30
]
```

Result:
```json
[
  10
]
```

Take the first name after navigating a repeated field.

```d2path
names.first()
```

Input:
```json
{
  "names": [
    "ANC 1st visit",
    "BCG doses"
  ]
}
```

Result:
```json
[
  "ANC 1st visit"
]
```

### `last()`

Keep the last item of a collection.

```d2path
last()
```

Input:
```json
[
  10,
  20,
  30
]
```

Result:
```json
[
  30
]
```

Read the most recent period from an ordered list.

```d2path
periods.last()
```

Input:
```json
{
  "periods": [
    "202601",
    "202602",
    "202603"
  ]
}
```

Result:
```json
[
  "202603"
]
```

### `tail()`

Drop the first item, keeping the rest.

```d2path
tail()
```

Input:
```json
[
  10,
  20,
  30
]
```

Result:
```json
[
  20,
  30
]
```

The tail of a single-element collection is empty.

```d2path
names.tail()
```

Input:
```json
{
  "names": [
    "ANC 1st visit"
  ]
}
```

Result:
```json
[]
```

### `skip()`

Drop the first N items.

```d2path
skip(2)
```

Input:
```json
[
  10,
  20,
  30,
  40
]
```

Result:
```json
[
  30,
  40
]
```

Skipping past the end yields the empty collection.

```d2path
skip(9)
```

Input:
```json
[
  10,
  20
]
```

Result:
```json
[]
```

### `take()`

Keep the first N items.

```d2path
take(2)
```

Input:
```json
[
  10,
  20,
  30,
  40
]
```

Result:
```json
[
  10,
  20
]
```

Taking zero items yields the empty collection.

```d2path
take(0)
```

Input:
```json
[
  10,
  20
]
```

Result:
```json
[]
```

### `count()`

Count the items in a collection.

```d2path
count()
```

Input:
```json
[
  1,
  2,
  3,
  4
]
```

Result:
```json
[
  4
]
```

Count a repeated field after navigation.

```d2path
tags.count()
```

Input:
```json
{
  "tags": [
    "malaria",
    "epi",
    "anc"
  ]
}
```

Result:
```json
[
  3
]
```

### `distinct()`

Drop duplicate strings, preserving first-seen order.

```d2path
tags.distinct()
```

Input:
```json
{
  "tags": [
    "a",
    "b",
    "a",
    "c",
    "b"
  ]
}
```

Result:
```json
[
  "a",
  "b",
  "c"
]
```

De-duplicate a numeric collection.

```d2path
values.distinct()
```

Input:
```json
{
  "values": [
    1,
    1,
    2,
    3,
    3,
    3
  ]
}
```

Result:
```json
[
  1,
  2,
  3
]
```

Chain into `count()` to count the unique values.

```d2path
codes.distinct().count()
```

Input:
```json
{
  "codes": [
    "A",
    "B",
    "A"
  ]
}
```

Result:
```json
[
  2
]
```

### `isDistinct()`

True when a collection has no duplicates.

```d2path
codes.isDistinct()
```

Input:
```json
{
  "codes": [
    "A",
    "B",
    "C"
  ]
}
```

Result:
```json
[
  true
]
```

Repeated organisation-unit levels are not distinct.

```d2path
orgUnits.level.isDistinct()
```

Input:
```json
{
  "orgUnits": [
    {
      "level": 2
    },
    {
      "level": 3
    },
    {
      "level": 2
    }
  ]
}
```

Result:
```json
[
  false
]
```

### `union()`

Union with itself collapses to the distinct set.

```d2path
codes.union(codes)
```

Input:
```json
{
  "codes": [
    "ANC",
    "BCG",
    "ANC"
  ]
}
```

Result:
```json
[
  "ANC",
  "BCG"
]
```

Merge in a projected collection, de-duplicating the result.

```d2path
union(select($this + 100))
```

Input:
```json
[
  1,
  2,
  3
]
```

Result:
```json
[
  1,
  2,
  3,
  101.0,
  102.0,
  103.0
]
```

### `combine()`

Append another collection, keeping duplicates (unlike `union`).

```d2path
combine(tail())
```

Input:
```json
[
  10,
  20,
  30
]
```

Result:
```json
[
  10,
  20,
  30,
  20,
  30
]
```

Concatenating a collection with a copy of itself doubles it.

```d2path
combine(take(2))
```

Input:
```json
[
  1,
  2
]
```

Result:
```json
[
  1,
  2,
  1,
  2
]
```

## Strings

### `substring()`

Take a fixed-length slice from a start offset.

```d2path
name.substring(0, 3)
```

Input:
```json
{
  "name": "Albendazole"
}
```

Result:
```json
[
  "Alb"
]
```

Omit the length to slice to the end of the string.

```d2path
code.substring(2)
```

Input:
```json
{
  "code": "DE1234"
}
```

Result:
```json
[
  "1234"
]
```

Slice a prefix for grouping or matching.

```d2path
name.substring(0, 4)
```

Input:
```json
{
  "name": "Pentavalent"
}
```

Result:
```json
[
  "Pent"
]
```

A length past the end of the string clips to what remains.

```d2path
code.substring(3, 10)
```

Input:
```json
{
  "code": "DE01"
}
```

Result:
```json
[
  "1"
]
```

### `upper()`

Upper-case a string.

```d2path
name.upper()
```

Input:
```json
{
  "name": "malaria"
}
```

Result:
```json
[
  "MALARIA"
]
```

A non-string (or missing) focus yields the empty collection.

```d2path
label.upper()
```

Input:
```json
{
  "label": null
}
```

Result:
```json
[]
```

### `lower()`

Lower-case a string.

```d2path
name.lower()
```

Input:
```json
{
  "name": "BCG"
}
```

Result:
```json
[
  "bcg"
]
```

Normalise a code to lower case.

```d2path
code.lower()
```

Input:
```json
{
  "code": "DE_ANC"
}
```

Result:
```json
[
  "de_anc"
]
```

### `length()`

Report a string's character count.

```d2path
name.length()
```

Input:
```json
{
  "name": "Pentavalent"
}
```

Result:
```json
[
  11
]
```

A missing field yields the empty collection, not zero.

```d2path
nickname.length()
```

Input:
```json
{
  "name": "Ada"
}
```

Result:
```json
[]
```

### `trim()`

Strip leading and trailing whitespace.

```d2path
label.trim()
```

Input:
```json
{
  "label": "  ANC 1st visit  "
}
```

Result:
```json
[
  "ANC 1st visit"
]
```

Trim removes tabs and newlines too.

```d2path
code.trim()
```

Input:
```json
{
  "code": "\tDE01\n"
}
```

Result:
```json
[
  "DE01"
]
```

### `toChars()`

Explode a string into its characters.

```d2path
code.toChars()
```

Input:
```json
{
  "code": "DE01"
}
```

Result:
```json
[
  [
    "D",
    "E",
    "0",
    "1"
  ]
]
```

A single-character string becomes a one-element list.

```d2path
flag.toChars()
```

Input:
```json
{
  "flag": "Y"
}
```

Result:
```json
[
  [
    "Y"
  ]
]
```

### `startsWith()`

Test a string prefix.

```d2path
name.startsWith("ANC")
```

Input:
```json
{
  "name": "ANC 1st visit"
}
```

Result:
```json
[
  true
]
```

A non-matching prefix is false.

```d2path
name.startsWith("BCG")
```

Input:
```json
{
  "name": "ANC 1st visit"
}
```

Result:
```json
[
  false
]
```

### `endsWith()`

Test a string suffix.

```d2path
name.endsWith("visit")
```

Input:
```json
{
  "name": "ANC 1st visit"
}
```

Result:
```json
[
  true
]
```

A non-matching suffix is false.

```d2path
filename.endsWith(".csv")
```

Input:
```json
{
  "filename": "export.json"
}
```

Result:
```json
[
  false
]
```

### `contains()`

Test whether a string contains a substring (method form).

```d2path
name.contains("1st")
```

Input:
```json
{
  "name": "ANC 1st visit"
}
```

Result:
```json
[
  true
]
```

A missing substring is not contained.

```d2path
name.contains("xyz")
```

Input:
```json
{
  "name": "ANC 1st visit"
}
```

Result:
```json
[
  false
]
```

### `indexOf()`

Find the zero-based offset of a substring.

```d2path
name.indexOf("visit")
```

Input:
```json
{
  "name": "ANC 1st visit"
}
```

Result:
```json
[
  8
]
```

A substring that is absent returns -1.

```d2path
name.indexOf("xyz")
```

Input:
```json
{
  "name": "ANC 1st visit"
}
```

Result:
```json
[
  -1
]
```

### `replace()`

Replace every occurrence of a literal substring.

```d2path
path.replace("/", " > ")
```

Input:
```json
{
  "path": "Sierra Leone/Bo/Ngelehun"
}
```

Result:
```json
[
  "Sierra Leone > Bo > Ngelehun"
]
```

Swap a separator character in a code.

```d2path
code.replace("_", "-")
```

Input:
```json
{
  "code": "DE_01"
}
```

Result:
```json
[
  "DE-01"
]
```

### `matches()`

Test a string against a regular expression.

```d2path
code.matches("^[A-Z]{2}[0-9]+$")
```

Input:
```json
{
  "code": "DE01"
}
```

Result:
```json
[
  true
]
```

A pattern that does not match returns false.

```d2path
code.matches("^[0-9]+$")
```

Input:
```json
{
  "code": "DE01"
}
```

Result:
```json
[
  false
]
```

### `split()`

Split a string on a separator into a collection.

```d2path
period.split("-")
```

Input:
```json
{
  "period": "2026-Q1-BCG"
}
```

Result:
```json
[
  "2026",
  "Q1",
  "BCG"
]
```

A separator that is absent yields the whole string as one element.

```d2path
code.split("/")
```

Input:
```json
{
  "code": "ABC"
}
```

Result:
```json
[
  "ABC"
]
```

### `join()`

Join a collection with a separator.

```d2path
parts.join("-")
```

Input:
```json
{
  "parts": [
    "2026",
    "Q1",
    "BCG"
  ]
}
```

Result:
```json
[
  "2026-Q1-BCG"
]
```

Build a comma-separated label from tags.

```d2path
tags.join(", ")
```

Input:
```json
{
  "tags": [
    "malaria",
    "epi"
  ]
}
```

Result:
```json
[
  "malaria, epi"
]
```

## Math & aggregates

### `sum()`

Sum a numeric collection (aggregates return decimals).

```d2path
values.sum()
```

Input:
```json
{
  "values": [
    1,
    2,
    3
  ]
}
```

Result:
```json
[
  6.0
]
```

Analytics values arrive as strings; `sum` coerces them to numbers.

```d2path
rows.value.sum()
```

Input:
```json
{
  "rows": [
    {
      "value": "12"
    },
    {
      "value": "7"
    },
    {
      "value": "30"
    }
  ]
}
```

Result:
```json
[
  49.0
]
```

### `min()`

Smallest value in a numeric collection.

```d2path
deltas.min()
```

Input:
```json
{
  "deltas": [
    -3,
    5,
    -1
  ]
}
```

Result:
```json
[
  -3.0
]
```

Minimum over string-typed analytics values.

```d2path
rows.value.min()
```

Input:
```json
{
  "rows": [
    {
      "value": "12"
    },
    {
      "value": "7"
    }
  ]
}
```

Result:
```json
[
  7.0
]
```

### `max()`

Largest value in a numeric collection.

```d2path
deltas.max()
```

Input:
```json
{
  "deltas": [
    -3,
    5,
    -1
  ]
}
```

Result:
```json
[
  5.0
]
```

Maximum over string-typed analytics values.

```d2path
rows.value.max()
```

Input:
```json
{
  "rows": [
    {
      "value": "12"
    },
    {
      "value": "7"
    }
  ]
}
```

Result:
```json
[
  12.0
]
```

### `avg()`

Arithmetic mean of a numeric collection.

```d2path
scores.avg()
```

Input:
```json
{
  "scores": [
    10,
    20,
    30
  ]
}
```

Result:
```json
[
  20.0
]
```

Average of string-typed analytics values.

```d2path
rows.value.avg()
```

Input:
```json
{
  "rows": [
    {
      "value": "12"
    },
    {
      "value": "8"
    }
  ]
}
```

Result:
```json
[
  10.0
]
```

### `abs()`

Absolute value of a number.

```d2path
balance.abs()
```

Input:
```json
{
  "balance": -12.5
}
```

Result:
```json
[
  12.5
]
```

Absolute value of a scalar focus.

```d2path
abs()
```

Input:
```json
-3
```

Result:
```json
[
  3.0
]
```

### `round()`

Round to a given number of decimal places.

```d2path
value.round(2)
```

Input:
```json
{
  "value": 3.14159
}
```

Result:
```json
[
  3.14
]
```

Round a coverage figure to one decimal place.

```d2path
coverage.round(1)
```

Input:
```json
{
  "coverage": 87.456
}
```

Result:
```json
[
  87.5
]
```

Omitting the precision rounds to the nearest whole number.

```d2path
rate.round()
```

Input:
```json
{
  "rate": 3.6
}
```

Result:
```json
[
  4.0
]
```

## Conversion & temporal

### `toInteger()`

Parse a numeric string into an integer.

```d2path
value.toInteger()
```

Input:
```json
{
  "value": "42"
}
```

Result:
```json
[
  42
]
```

A decimal is truncated toward zero.

```d2path
score.toInteger()
```

Input:
```json
{
  "score": 3.9
}
```

Result:
```json
[
  3
]
```

### `toDecimal()`

Parse a numeric string into a decimal.

```d2path
value.toDecimal()
```

Input:
```json
{
  "value": "3.14"
}
```

Result:
```json
[
  3.14
]
```

Widen an integer into a decimal.

```d2path
total.toDecimal()
```

Input:
```json
{
  "total": 7
}
```

Result:
```json
[
  7.0
]
```

### `toString()`

Render a number as a string.

```d2path
level.toString()
```

Input:
```json
{
  "level": 3
}
```

Result:
```json
[
  "3"
]
```

A boolean renders as the canonical `true`/`false` text.

```d2path
active.toString()
```

Input:
```json
{
  "active": true
}
```

Result:
```json
[
  "true"
]
```

A null (or missing) focus yields the empty collection.

```d2path
value.toString()
```

Input:
```json
{
  "value": null
}
```

Result:
```json
[]
```

### `today()`

Current date as an ISO-8601 string; the exact value varies at runtime.

```d2path
today()
```

Result (varies at runtime; shape shown):
```json
[
  "2026-07-11"
]
```

An ISO date is always ten characters long.

```d2path
today().length()
```

Result:
```json
[
  10
]
```

Slice the year out of today's date; the value varies at runtime.

```d2path
today().substring(0, 4)
```

Result (varies at runtime; shape shown):
```json
[
  "2026"
]
```

### `now()`

Current timestamp as an ISO-8601 string; the exact value varies at runtime.

```d2path
now()
```

Result (varies at runtime; shape shown):
```json
[
  "2026-07-11T09:00:00.000000"
]
```

Slice the date portion out of the current timestamp; the value varies at runtime.

```d2path
now().substring(0, 10)
```

Result (varies at runtime; shape shown):
```json
[
  "2026-07-11"
]
```

## Operators

### operator-implies

`a implies b` is false only when `a` holds but `b` does not.

```d2path
active implies verified
```

Input:
```json
{
  "active": true,
  "verified": false
}
```

Result:
```json
[
  false
]
```

A false antecedent makes `implies` vacuously true.

```d2path
isDraft implies reviewed
```

Input:
```json
{
  "isDraft": false,
  "reviewed": false
}
```

Result:
```json
[
  true
]
```

A true antecedent with a true consequent holds.

```d2path
verified implies active
```

Input:
```json
{
  "verified": true,
  "active": true
}
```

Result:
```json
[
  true
]
```

### operator-in

Test membership of a scalar in an array literal.

```d2path
valueType in ["NUMBER", "INTEGER"]
```

Input:
```json
{
  "valueType": "NUMBER"
}
```

Result:
```json
[
  true
]
```

A value outside the set is not a member.

```d2path
status in ["ACTIVE", "COMPLETED"]
```

Input:
```json
{
  "status": "CANCELLED"
}
```

Result:
```json
[
  false
]
```

### operator-concat

`+` concatenates two strings.

```d2path
firstName + " " + lastName
```

Input:
```json
{
  "firstName": "Ada",
  "lastName": "Lovelace"
}
```

Result:
```json
[
  "Ada Lovelace"
]
```

Prefix a field with a string literal to build a label.

```d2path
"OU-" + code
```

Input:
```json
{
  "code": "SL01"
}
```

Result:
```json
[
  "OU-SL01"
]
```

Build an analytics dimension key from fields.

```d2path
dx + "." + pe
```

Input:
```json
{
  "dx": "fbfJHSPpUQD",
  "pe": "202601"
}
```

Result:
```json
[
  "fbfJHSPpUQD.202601"
]
```

### operator-arithmetic

`/` is true division and keeps the fraction.

```d2path
7 / 2
```

Result:
```json
[
  3.5
]
```

`div` is integer division, truncating toward zero.

```d2path
7 div 2
```

Result:
```json
[
  3.0
]
```

`mod` is the remainder.

```d2path
7 mod 2
```

Result:
```json
[
  1.0
]
```

Unary minus negates a number (arithmetic is decimal-valued).

```d2path
-delta
```

Input:
```json
{
  "delta": 5
}
```

Result:
```json
[
  -5.0
]
```

### operator-xor

`xor` is true when exactly one side holds.

```d2path
smsEnabled xor emailEnabled
```

Input:
```json
{
  "smsEnabled": true,
  "emailEnabled": false
}
```

Result:
```json
[
  true
]
```

Both sides true is not exclusive, so `xor` is false.

```d2path
draft xor published
```

Input:
```json
{
  "draft": true,
  "published": true
}
```

Result:
```json
[
  false
]
```

### operator-not-match

`!~` is true when the case-insensitive substring is absent.

```d2path
name !~ "malaria"
```

Input:
```json
{
  "name": "BCG doses"
}
```

Result:
```json
[
  true
]
```

`~` matches case-insensitively, so `!~` is false when it would match.

```d2path
name !~ "bcg"
```

Input:
```json
{
  "name": "BCG doses"
}
```

Result:
```json
[
  false
]
```

### operator-contains

Infix `contains` tests membership in a collection.

```d2path
orgUnitGroups contains "CHW"
```

Input:
```json
{
  "orgUnitGroups": [
    "CHW",
    "PHU"
  ]
}
```

Result:
```json
[
  true
]
```

A value not in the collection is not contained.

```d2path
orgUnitGroups contains "MOH"
```

Input:
```json
{
  "orgUnitGroups": [
    "CHW",
    "PHU"
  ]
}
```

Result:
```json
[
  false
]
```

With a string on both sides, infix `contains` is a substring test.

```d2path
name contains "ov"
```

Input:
```json
{
  "name": "Lovelace"
}
```

Result:
```json
[
  true
]
```

### operator-is

`is Integer` tests for an integer value.

```d2path
value is Integer
```

Input:
```json
{
  "value": 42
}
```

Result:
```json
[
  true
]
```

`is Decimal` tests for a floating-point value.

```d2path
value is Decimal
```

Input:
```json
{
  "value": 3.14
}
```

Result:
```json
[
  true
]
```

`is String` tests for a string value.

```d2path
value is String
```

Input:
```json
{
  "value": "NUMBER"
}
```

Result:
```json
[
  true
]
```

`is Boolean` tests for a boolean value.

```d2path
value is Boolean
```

Input:
```json
{
  "value": true
}
```

Result:
```json
[
  true
]
```

`is Object` tests for a structured node.

```d2path
value is Object
```

Input:
```json
{
  "value": {
    "k": 1
  }
}
```

Result:
```json
[
  true
]
```

A numeric string is a String, not an Integer.

```d2path
code is Integer
```

Input:
```json
{
  "code": "42"
}
```

Result:
```json
[
  false
]
```

### existential-comparison

`>` over a repeated field is true when any item exceeds the scalar.

```d2path
items.qty > 2
```

Input:
```json
{
  "items": [
    {
      "qty": 1
    },
    {
      "qty": 5
    }
  ]
}
```

Result:
```json
[
  true
]
```

`=` holds when any value in the collection matches.

```d2path
given = "Ada"
```

Input:
```json
{
  "given": [
    "Ada",
    "Grace"
  ]
}
```

Result:
```json
[
  true
]
```

`!=` means no pair is equal, so a present match makes it false.

```d2path
given != "Ada"
```

Input:
```json
{
  "given": [
    "Ada",
    "Grace"
  ]
}
```

Result:
```json
[
  false
]
```

`<` holds when some value falls below the scalar.

```d2path
levels < 3
```

Input:
```json
{
  "levels": [
    4,
    2
  ]
}
```

Result:
```json
[
  true
]
```

`~` holds when any value matches case-insensitively.

```d2path
codes ~ "anc"
```

Input:
```json
{
  "codes": [
    "ANC1",
    "BCG"
  ]
}
```

Result:
```json
[
  true
]
```

`!~` means no value matches, so a present match makes it false.

```d2path
codes !~ "anc"
```

Input:
```json
{
  "codes": [
    "ANC1",
    "BCG"
  ]
}
```

Result:
```json
[
  false
]
```

## Literals & navigation

### literal-date

A `@`-prefixed date literal evaluates to its ISO-8601 string.

```d2path
@2026-06-23
```

Result:
```json
[
  "2026-06-23"
]
```

Compare an event date against a date literal (ISO strings order lexically).

```d2path
eventDate > @2026-01-01
```

Input:
```json
{
  "eventDate": "2026-06-23"
}
```

Result:
```json
[
  true
]
```

A date literal equals a matching ISO date string.

```d2path
eventDate = @2026-06-23
```

Input:
```json
{
  "eventDate": "2026-06-23"
}
```

Result:
```json
[
  true
]
```

### literal-datetime

A `@`-prefixed datetime literal evaluates to its ISO-8601 string.

```d2path
@2026-06-23T12:00:00
```

Result:
```json
[
  "2026-06-23T12:00:00"
]
```

Compare a timestamp field against a datetime literal.

```d2path
lastUpdated >= @2026-06-23T00:00:00
```

Input:
```json
{
  "lastUpdated": "2026-06-23T12:30:00"
}
```

Result:
```json
[
  true
]
```

### path-navigation

A positive integer subscript indexes a collection.

```d2path
coding[0]
```

Input:
```json
{
  "coding": [
    {
      "x": 1
    },
    {
      "x": 2
    }
  ]
}
```

Result:
```json
[
  {
    "x": 1
  }
]
```

An out-of-bounds index yields the empty collection, not an error.

```d2path
coding[9]
```

Input:
```json
{
  "coding": [
    {
      "x": 1
    },
    {
      "x": 2
    }
  ]
}
```

Result:
```json
[]
```

An integer-valued index may be negative, counting from the end.

```d2path
coding[pos]
```

Input:
```json
{
  "coding": [
    {
      "x": 1
    },
    {
      "x": 2
    },
    {
      "x": 3
    }
  ],
  "pos": -1
}
```

Result:
```json
[
  {
    "x": 3
  }
]
```

A string subscript reaches keys that are not identifiers.

```d2path
attributes["Birth date"]
```

Input:
```json
{
  "attributes": {
    "Birth date": "2000-01-01"
  }
}
```

Result:
```json
[
  "2000-01-01"
]
```

Each navigation hop flattens one level of nested collections.

```d2path
orgUnits.ancestors.name
```

Input:
```json
{
  "orgUnits": [
    {
      "ancestors": [
        {
          "name": "Sierra Leone"
        },
        {
          "name": "Bo"
        }
      ]
    }
  ]
}
```

Result:
```json
[
  "Sierra Leone",
  "Bo"
]
```
