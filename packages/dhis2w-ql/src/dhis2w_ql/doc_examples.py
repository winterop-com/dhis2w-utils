"""A machine-validated catalog of d2path expression examples for the documentation.

Every entry is parsed, evaluated with the real `Evaluator` against its `input`, and (for
deterministic entries) asserted equal to `expected` by `tests/test_doc_examples.py`. The generator
`infra/scripts/gen_d2path_examples.py` renders this catalog into `docs/query/d2path-examples.md`, so
the shipped examples and their results never drift from the implementation. Content authors extend
the documentation by appending entries here, not by hand-writing result blocks.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

ExpectedKind = Literal["exact", "nondeterministic"]


class FunctionExample(BaseModel):
    """One documented d2path expression with its input focus and evaluated result."""

    model_config = ConfigDict(frozen=True)

    function_or_topic: str
    category: str
    description: str
    expression: str
    input: JsonValue = None
    expected_kind: ExpectedKind = "exact"
    expected: list[JsonValue]

    def focus(self) -> list[JsonValue]:
        """Return the evaluator focus collection for this example's `input`."""
        if self.input is None:
            return []
        if isinstance(self.input, list):
            return self.input
        return [self.input]


DOC_EXAMPLES: list[FunctionExample] = [
    # ================================================================ Filtering & projection
    # ---------------------------------------------------------------- where
    FunctionExample(
        function_or_topic="where",
        category="Filtering & projection",
        description="Keep the matching sub-object, then navigate into it.",
        expression='name.where(use = "official").family',
        input={
            "name": [
                {"use": "official", "given": ["Ada", "Lovelace"], "family": "King"},
                {"use": "nick", "given": ["Countess"]},
            ]
        },
        expected=["King"],
    ),
    FunctionExample(
        function_or_topic="where",
        category="Filtering & projection",
        description="Filter a collection of objects by a numeric predicate on `$this`.",
        expression="items.where(qty > 2)",
        input={"items": [{"qty": 1}, {"qty": 5}, {"qty": 3}]},
        expected=[{"qty": 5}, {"qty": 3}],
    ),
    FunctionExample(
        function_or_topic="where",
        category="Filtering & projection",
        description="Select one telecom channel by its system, then read its value.",
        expression='telecom.where(system = "phone").value',
        input={
            "telecom": [
                {"system": "phone", "value": "555-1"},
                {"system": "email", "value": "a@b.c"},
            ]
        },
        expected=["555-1"],
    ),
    FunctionExample(
        function_or_topic="where",
        category="Filtering & projection",
        description="Filter data elements by valueType, then read the surviving names.",
        expression='elements.where(valueType = "NUMBER").name',
        input={
            "elements": [
                {"name": "Malaria cases", "valueType": "NUMBER"},
                {"name": "Clinical notes", "valueType": "TEXT"},
            ]
        },
        expected=["Malaria cases"],
    ),
    # ---------------------------------------------------------------- select
    FunctionExample(
        function_or_topic="select",
        category="Filtering & projection",
        description="Reshape each item into a new object with an object constructor.",
        expression="options.select({ code: code, display: name })",
        input={"options": [{"code": "M", "name": "Male"}, {"code": "F", "name": "Female"}]},
        expected=[{"code": "M", "display": "Male"}, {"code": "F", "display": "Female"}],
    ),
    FunctionExample(
        function_or_topic="select",
        category="Filtering & projection",
        description="Map every item through an arithmetic expression on `$this`.",
        expression="scores.select($this * 2)",
        input={"scores": [1, 2, 3]},
        expected=[2.0, 4.0, 6.0],
    ),
    FunctionExample(
        function_or_topic="select",
        category="Filtering & projection",
        description="Project and transform a field from each item.",
        expression="people.select(name.upper())",
        input={"people": [{"name": "ada"}, {"name": "bob"}]},
        expected=["ADA", "BOB"],
    ),
    FunctionExample(
        function_or_topic="select",
        category="Filtering & projection",
        description="Rename organisation-unit fields into a compact projection.",
        expression="orgUnits.select({ id: id, depth: level })",
        input={"orgUnits": [{"id": "SL", "level": 1}, {"id": "Bo", "level": 2}]},
        expected=[{"id": "SL", "depth": 1}, {"id": "Bo", "depth": 2}],
    ),
    # ---------------------------------------------------------------- iif
    FunctionExample(
        function_or_topic="iif",
        category="Filtering & projection",
        description="Return one of two values based on a predicate.",
        expression='iif(gender = "male", "M", "F")',
        input={"gender": "male"},
        expected=["M"],
    ),
    FunctionExample(
        function_or_topic="iif",
        category="Filtering & projection",
        description="Branch on a boolean field.",
        expression='iif(active, "on", "off")',
        input={"active": False},
        expected=["off"],
    ),
    FunctionExample(
        function_or_topic="iif",
        category="Filtering & projection",
        description="Threshold a numeric field into a label.",
        expression='iif(qty > 10, "high", "low")',
        input={"qty": 5},
        expected=["low"],
    ),
    FunctionExample(
        function_or_topic="iif",
        category="Filtering & projection",
        description="Label a coverage value that clears a target.",
        expression='iif(value > 50, "high", "low")',
        input={"value": 87},
        expected=["high"],
    ),
    # ================================================================ Existence & logic
    # ---------------------------------------------------------------- exists
    FunctionExample(
        function_or_topic="exists",
        category="Existence & logic",
        description="With no argument, report whether the collection is non-empty.",
        expression="codes.exists()",
        input={"codes": ["ANC1"]},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="exists",
        category="Existence & logic",
        description="An empty (or missing) collection does not exist.",
        expression="orgUnits.exists()",
        input={"orgUnits": []},
        expected=[False],
    ),
    FunctionExample(
        function_or_topic="exists",
        category="Existence & logic",
        description="With a predicate, report whether any item satisfies it.",
        expression="rows.exists(value > 20)",
        input={"rows": [{"value": 12}, {"value": 30}]},
        expected=[True],
    ),
    # ---------------------------------------------------------------- all
    FunctionExample(
        function_or_topic="all",
        category="Existence & logic",
        description="True when every item satisfies the predicate.",
        expression="rows.all(active)",
        input={"rows": [{"active": True}, {"active": True}]},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="all",
        category="Existence & logic",
        description="A single failing item makes `all` false.",
        expression="stages.all(completed)",
        input={"stages": [{"completed": True}, {"completed": False}]},
        expected=[False],
    ),
    # ---------------------------------------------------------------- empty
    FunctionExample(
        function_or_topic="empty",
        category="Existence & logic",
        description="An empty collection is empty.",
        expression="tags.empty()",
        input={"tags": []},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="empty",
        category="Existence & logic",
        description="A non-empty collection is not empty.",
        expression="roles.empty()",
        input={"roles": ["ADMIN"]},
        expected=[False],
    ),
    FunctionExample(
        function_or_topic="empty",
        category="Existence & logic",
        description="A missing field navigates to the empty collection, which is empty.",
        expression="closedDate.empty()",
        input={"openingDate": "2020-01-01"},
        expected=[True],
    ),
    # ---------------------------------------------------------------- not
    FunctionExample(
        function_or_topic="not",
        category="Existence & logic",
        description="Negate a boolean field.",
        expression="verified.not()",
        input={"verified": False},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="not",
        category="Existence & logic",
        description="Negate a true flag.",
        expression="flag.not()",
        input={"flag": True},
        expected=[False],
    ),
    FunctionExample(
        function_or_topic="not",
        category="Existence & logic",
        description="An empty focus is falsy, so `not()` returns true.",
        expression="middleName.not()",
        input={"firstName": "Ada"},
        expected=[True],
    ),
    # ================================================================ Subsetting & set operations
    # ---------------------------------------------------------------- first
    FunctionExample(
        function_or_topic="first",
        category="Subsetting & set operations",
        description="Keep the first item of a collection.",
        expression="first()",
        input=[10, 20, 30],
        expected=[10],
    ),
    FunctionExample(
        function_or_topic="first",
        category="Subsetting & set operations",
        description="Take the first name after navigating a repeated field.",
        expression="names.first()",
        input={"names": ["ANC 1st visit", "BCG doses"]},
        expected=["ANC 1st visit"],
    ),
    # ---------------------------------------------------------------- last
    FunctionExample(
        function_or_topic="last",
        category="Subsetting & set operations",
        description="Keep the last item of a collection.",
        expression="last()",
        input=[10, 20, 30],
        expected=[30],
    ),
    FunctionExample(
        function_or_topic="last",
        category="Subsetting & set operations",
        description="Read the most recent period from an ordered list.",
        expression="periods.last()",
        input={"periods": ["202601", "202602", "202603"]},
        expected=["202603"],
    ),
    # ---------------------------------------------------------------- tail
    FunctionExample(
        function_or_topic="tail",
        category="Subsetting & set operations",
        description="Drop the first item, keeping the rest.",
        expression="tail()",
        input=[10, 20, 30],
        expected=[20, 30],
    ),
    FunctionExample(
        function_or_topic="tail",
        category="Subsetting & set operations",
        description="The tail of a single-element collection is empty.",
        expression="names.tail()",
        input={"names": ["ANC 1st visit"]},
        expected=[],
    ),
    # ---------------------------------------------------------------- skip
    FunctionExample(
        function_or_topic="skip",
        category="Subsetting & set operations",
        description="Drop the first N items.",
        expression="skip(2)",
        input=[10, 20, 30, 40],
        expected=[30, 40],
    ),
    FunctionExample(
        function_or_topic="skip",
        category="Subsetting & set operations",
        description="Skipping past the end yields the empty collection.",
        expression="skip(9)",
        input=[10, 20],
        expected=[],
    ),
    # ---------------------------------------------------------------- take
    FunctionExample(
        function_or_topic="take",
        category="Subsetting & set operations",
        description="Keep the first N items.",
        expression="take(2)",
        input=[10, 20, 30, 40],
        expected=[10, 20],
    ),
    FunctionExample(
        function_or_topic="take",
        category="Subsetting & set operations",
        description="Taking zero items yields the empty collection.",
        expression="take(0)",
        input=[10, 20],
        expected=[],
    ),
    # ---------------------------------------------------------------- count
    FunctionExample(
        function_or_topic="count",
        category="Subsetting & set operations",
        description="Count the items in a collection.",
        expression="count()",
        input=[1, 2, 3, 4],
        expected=[4],
    ),
    FunctionExample(
        function_or_topic="count",
        category="Subsetting & set operations",
        description="Count a repeated field after navigation.",
        expression="tags.count()",
        input={"tags": ["malaria", "epi", "anc"]},
        expected=[3],
    ),
    # ---------------------------------------------------------------- distinct
    FunctionExample(
        function_or_topic="distinct",
        category="Subsetting & set operations",
        description="Drop duplicate strings, preserving first-seen order.",
        expression="tags.distinct()",
        input={"tags": ["a", "b", "a", "c", "b"]},
        expected=["a", "b", "c"],
    ),
    FunctionExample(
        function_or_topic="distinct",
        category="Subsetting & set operations",
        description="De-duplicate a numeric collection.",
        expression="values.distinct()",
        input={"values": [1, 1, 2, 3, 3, 3]},
        expected=[1, 2, 3],
    ),
    FunctionExample(
        function_or_topic="distinct",
        category="Subsetting & set operations",
        description="Chain into `count()` to count the unique values.",
        expression="codes.distinct().count()",
        input={"codes": ["A", "B", "A"]},
        expected=[2],
    ),
    # ---------------------------------------------------------------- isDistinct
    FunctionExample(
        function_or_topic="isDistinct",
        category="Subsetting & set operations",
        description="True when a collection has no duplicates.",
        expression="codes.isDistinct()",
        input={"codes": ["A", "B", "C"]},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="isDistinct",
        category="Subsetting & set operations",
        description="Repeated organisation-unit levels are not distinct.",
        expression="orgUnits.level.isDistinct()",
        input={"orgUnits": [{"level": 2}, {"level": 3}, {"level": 2}]},
        expected=[False],
    ),
    # ---------------------------------------------------------------- union
    FunctionExample(
        function_or_topic="union",
        category="Subsetting & set operations",
        description="Union with itself collapses to the distinct set.",
        expression="codes.union(codes)",
        input={"codes": ["ANC", "BCG", "ANC"]},
        expected=["ANC", "BCG"],
    ),
    FunctionExample(
        function_or_topic="union",
        category="Subsetting & set operations",
        description="Merge in a projected collection, de-duplicating the result.",
        expression="union(select($this + 100))",
        input=[1, 2, 3],
        expected=[1, 2, 3, 101.0, 102.0, 103.0],
    ),
    # ---------------------------------------------------------------- combine
    FunctionExample(
        function_or_topic="combine",
        category="Subsetting & set operations",
        description="Append another collection, keeping duplicates (unlike `union`).",
        expression="combine(tail())",
        input=[10, 20, 30],
        expected=[10, 20, 30, 20, 30],
    ),
    FunctionExample(
        function_or_topic="combine",
        category="Subsetting & set operations",
        description="Concatenating a collection with a copy of itself doubles it.",
        expression="combine(take(2))",
        input=[1, 2],
        expected=[1, 2, 1, 2],
    ),
    # ================================================================ Strings
    # ---------------------------------------------------------------- substring
    FunctionExample(
        function_or_topic="substring",
        category="Strings",
        description="Take a fixed-length slice from a start offset.",
        expression="name.substring(0, 3)",
        input={"name": "Albendazole"},
        expected=["Alb"],
    ),
    FunctionExample(
        function_or_topic="substring",
        category="Strings",
        description="Omit the length to slice to the end of the string.",
        expression="code.substring(2)",
        input={"code": "DE1234"},
        expected=["1234"],
    ),
    FunctionExample(
        function_or_topic="substring",
        category="Strings",
        description="Slice a prefix for grouping or matching.",
        expression="name.substring(0, 4)",
        input={"name": "Pentavalent"},
        expected=["Pent"],
    ),
    FunctionExample(
        function_or_topic="substring",
        category="Strings",
        description="A length past the end of the string clips to what remains.",
        expression="code.substring(3, 10)",
        input={"code": "DE01"},
        expected=["1"],
    ),
    # ---------------------------------------------------------------- upper
    FunctionExample(
        function_or_topic="upper",
        category="Strings",
        description="Upper-case a string.",
        expression="name.upper()",
        input={"name": "malaria"},
        expected=["MALARIA"],
    ),
    FunctionExample(
        function_or_topic="upper",
        category="Strings",
        description="A non-string (or missing) focus yields the empty collection.",
        expression="label.upper()",
        input={"label": None},
        expected=[],
    ),
    # ---------------------------------------------------------------- lower
    FunctionExample(
        function_or_topic="lower",
        category="Strings",
        description="Lower-case a string.",
        expression="name.lower()",
        input={"name": "BCG"},
        expected=["bcg"],
    ),
    FunctionExample(
        function_or_topic="lower",
        category="Strings",
        description="Normalise a code to lower case.",
        expression="code.lower()",
        input={"code": "DE_ANC"},
        expected=["de_anc"],
    ),
    # ---------------------------------------------------------------- length
    FunctionExample(
        function_or_topic="length",
        category="Strings",
        description="Report a string's character count.",
        expression="name.length()",
        input={"name": "Pentavalent"},
        expected=[11],
    ),
    FunctionExample(
        function_or_topic="length",
        category="Strings",
        description="A missing field yields the empty collection, not zero.",
        expression="nickname.length()",
        input={"name": "Ada"},
        expected=[],
    ),
    # ---------------------------------------------------------------- trim
    FunctionExample(
        function_or_topic="trim",
        category="Strings",
        description="Strip leading and trailing whitespace.",
        expression="label.trim()",
        input={"label": "  ANC 1st visit  "},
        expected=["ANC 1st visit"],
    ),
    FunctionExample(
        function_or_topic="trim",
        category="Strings",
        description="Trim removes tabs and newlines too.",
        expression="code.trim()",
        input={"code": "\tDE01\n"},
        expected=["DE01"],
    ),
    # ---------------------------------------------------------------- toChars
    FunctionExample(
        function_or_topic="toChars",
        category="Strings",
        description="Explode a string into its characters.",
        expression="code.toChars()",
        input={"code": "DE01"},
        expected=[["D", "E", "0", "1"]],
    ),
    FunctionExample(
        function_or_topic="toChars",
        category="Strings",
        description="A single-character string becomes a one-element list.",
        expression="flag.toChars()",
        input={"flag": "Y"},
        expected=[["Y"]],
    ),
    # ---------------------------------------------------------------- startsWith
    FunctionExample(
        function_or_topic="startsWith",
        category="Strings",
        description="Test a string prefix.",
        expression='name.startsWith("ANC")',
        input={"name": "ANC 1st visit"},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="startsWith",
        category="Strings",
        description="A non-matching prefix is false.",
        expression='name.startsWith("BCG")',
        input={"name": "ANC 1st visit"},
        expected=[False],
    ),
    # ---------------------------------------------------------------- endsWith
    FunctionExample(
        function_or_topic="endsWith",
        category="Strings",
        description="Test a string suffix.",
        expression='name.endsWith("visit")',
        input={"name": "ANC 1st visit"},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="endsWith",
        category="Strings",
        description="A non-matching suffix is false.",
        expression='filename.endsWith(".csv")',
        input={"filename": "export.json"},
        expected=[False],
    ),
    # ---------------------------------------------------------------- contains
    FunctionExample(
        function_or_topic="contains",
        category="Strings",
        description="Test whether a string contains a substring (method form).",
        expression='name.contains("1st")',
        input={"name": "ANC 1st visit"},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="contains",
        category="Strings",
        description="A missing substring is not contained.",
        expression='name.contains("xyz")',
        input={"name": "ANC 1st visit"},
        expected=[False],
    ),
    # ---------------------------------------------------------------- indexOf
    FunctionExample(
        function_or_topic="indexOf",
        category="Strings",
        description="Find the zero-based offset of a substring.",
        expression='name.indexOf("visit")',
        input={"name": "ANC 1st visit"},
        expected=[8],
    ),
    FunctionExample(
        function_or_topic="indexOf",
        category="Strings",
        description="A substring that is absent returns -1.",
        expression='name.indexOf("xyz")',
        input={"name": "ANC 1st visit"},
        expected=[-1],
    ),
    # ---------------------------------------------------------------- replace
    FunctionExample(
        function_or_topic="replace",
        category="Strings",
        description="Replace every occurrence of a literal substring.",
        expression='path.replace("/", " > ")',
        input={"path": "Sierra Leone/Bo/Ngelehun"},
        expected=["Sierra Leone > Bo > Ngelehun"],
    ),
    FunctionExample(
        function_or_topic="replace",
        category="Strings",
        description="Swap a separator character in a code.",
        expression='code.replace("_", "-")',
        input={"code": "DE_01"},
        expected=["DE-01"],
    ),
    # ---------------------------------------------------------------- matches
    FunctionExample(
        function_or_topic="matches",
        category="Strings",
        description="Test a string against a regular expression.",
        expression='code.matches("^[A-Z]{2}[0-9]+$")',
        input={"code": "DE01"},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="matches",
        category="Strings",
        description="A pattern that does not match returns false.",
        expression='code.matches("^[0-9]+$")',
        input={"code": "DE01"},
        expected=[False],
    ),
    # ---------------------------------------------------------------- split
    FunctionExample(
        function_or_topic="split",
        category="Strings",
        description="Split a string on a separator into a collection.",
        expression='period.split("-")',
        input={"period": "2026-Q1-BCG"},
        expected=["2026", "Q1", "BCG"],
    ),
    FunctionExample(
        function_or_topic="split",
        category="Strings",
        description="A separator that is absent yields the whole string as one element.",
        expression='code.split("/")',
        input={"code": "ABC"},
        expected=["ABC"],
    ),
    # ---------------------------------------------------------------- join
    FunctionExample(
        function_or_topic="join",
        category="Strings",
        description="Join a collection with a separator.",
        expression='parts.join("-")',
        input={"parts": ["2026", "Q1", "BCG"]},
        expected=["2026-Q1-BCG"],
    ),
    FunctionExample(
        function_or_topic="join",
        category="Strings",
        description="Build a comma-separated label from tags.",
        expression='tags.join(", ")',
        input={"tags": ["malaria", "epi"]},
        expected=["malaria, epi"],
    ),
    # ================================================================ Math & aggregates
    # ---------------------------------------------------------------- sum
    FunctionExample(
        function_or_topic="sum",
        category="Math & aggregates",
        description="Sum a numeric collection (aggregates return decimals).",
        expression="values.sum()",
        input={"values": [1, 2, 3]},
        expected=[6.0],
    ),
    FunctionExample(
        function_or_topic="sum",
        category="Math & aggregates",
        description="Analytics values arrive as strings; `sum` coerces them to numbers.",
        expression="rows.value.sum()",
        input={"rows": [{"value": "12"}, {"value": "7"}, {"value": "30"}]},
        expected=[49.0],
    ),
    # ---------------------------------------------------------------- min
    FunctionExample(
        function_or_topic="min",
        category="Math & aggregates",
        description="Smallest value in a numeric collection.",
        expression="deltas.min()",
        input={"deltas": [-3, 5, -1]},
        expected=[-3.0],
    ),
    FunctionExample(
        function_or_topic="min",
        category="Math & aggregates",
        description="Minimum over string-typed analytics values.",
        expression="rows.value.min()",
        input={"rows": [{"value": "12"}, {"value": "7"}]},
        expected=[7.0],
    ),
    # ---------------------------------------------------------------- max
    FunctionExample(
        function_or_topic="max",
        category="Math & aggregates",
        description="Largest value in a numeric collection.",
        expression="deltas.max()",
        input={"deltas": [-3, 5, -1]},
        expected=[5.0],
    ),
    FunctionExample(
        function_or_topic="max",
        category="Math & aggregates",
        description="Maximum over string-typed analytics values.",
        expression="rows.value.max()",
        input={"rows": [{"value": "12"}, {"value": "7"}]},
        expected=[12.0],
    ),
    # ---------------------------------------------------------------- avg
    FunctionExample(
        function_or_topic="avg",
        category="Math & aggregates",
        description="Arithmetic mean of a numeric collection.",
        expression="scores.avg()",
        input={"scores": [10, 20, 30]},
        expected=[20.0],
    ),
    FunctionExample(
        function_or_topic="avg",
        category="Math & aggregates",
        description="Average of string-typed analytics values.",
        expression="rows.value.avg()",
        input={"rows": [{"value": "12"}, {"value": "8"}]},
        expected=[10.0],
    ),
    # ---------------------------------------------------------------- abs
    FunctionExample(
        function_or_topic="abs",
        category="Math & aggregates",
        description="Absolute value of a number.",
        expression="balance.abs()",
        input={"balance": -12.5},
        expected=[12.5],
    ),
    FunctionExample(
        function_or_topic="abs",
        category="Math & aggregates",
        description="Absolute value of a scalar focus.",
        expression="abs()",
        input=-3,
        expected=[3.0],
    ),
    # ---------------------------------------------------------------- round
    FunctionExample(
        function_or_topic="round",
        category="Math & aggregates",
        description="Round to a given number of decimal places.",
        expression="value.round(2)",
        input={"value": 3.14159},
        expected=[3.14],
    ),
    FunctionExample(
        function_or_topic="round",
        category="Math & aggregates",
        description="Round a coverage figure to one decimal place.",
        expression="coverage.round(1)",
        input={"coverage": 87.456},
        expected=[87.5],
    ),
    FunctionExample(
        function_or_topic="round",
        category="Math & aggregates",
        description="Omitting the precision rounds to the nearest whole number.",
        expression="rate.round()",
        input={"rate": 3.6},
        expected=[4.0],
    ),
    # ================================================================ Conversion & temporal
    # ---------------------------------------------------------------- toInteger
    FunctionExample(
        function_or_topic="toInteger",
        category="Conversion & temporal",
        description="Parse a numeric string into an integer.",
        expression="value.toInteger()",
        input={"value": "42"},
        expected=[42],
    ),
    FunctionExample(
        function_or_topic="toInteger",
        category="Conversion & temporal",
        description="A decimal is truncated toward zero.",
        expression="score.toInteger()",
        input={"score": 3.9},
        expected=[3],
    ),
    # ---------------------------------------------------------------- toDecimal
    FunctionExample(
        function_or_topic="toDecimal",
        category="Conversion & temporal",
        description="Parse a numeric string into a decimal.",
        expression="value.toDecimal()",
        input={"value": "3.14"},
        expected=[3.14],
    ),
    FunctionExample(
        function_or_topic="toDecimal",
        category="Conversion & temporal",
        description="Widen an integer into a decimal.",
        expression="total.toDecimal()",
        input={"total": 7},
        expected=[7.0],
    ),
    # ---------------------------------------------------------------- toString
    FunctionExample(
        function_or_topic="toString",
        category="Conversion & temporal",
        description="Render a number as a string.",
        expression="level.toString()",
        input={"level": 3},
        expected=["3"],
    ),
    FunctionExample(
        function_or_topic="toString",
        category="Conversion & temporal",
        description="A boolean renders as the canonical `true`/`false` text.",
        expression="active.toString()",
        input={"active": True},
        expected=["true"],
    ),
    FunctionExample(
        function_or_topic="toString",
        category="Conversion & temporal",
        description="A null (or missing) focus yields the empty collection.",
        expression="value.toString()",
        input={"value": None},
        expected=[],
    ),
    # ---------------------------------------------------------------- today
    FunctionExample(
        function_or_topic="today",
        category="Conversion & temporal",
        description="Current date as an ISO-8601 string; the exact value varies at runtime.",
        expression="today()",
        input=None,
        expected_kind="nondeterministic",
        expected=["2026-07-11"],
    ),
    FunctionExample(
        function_or_topic="today",
        category="Conversion & temporal",
        description="An ISO date is always ten characters long.",
        expression="today().length()",
        input=None,
        expected=[10],
    ),
    FunctionExample(
        function_or_topic="today",
        category="Conversion & temporal",
        description="Slice the year out of today's date; the value varies at runtime.",
        expression="today().substring(0, 4)",
        input=None,
        expected_kind="nondeterministic",
        expected=["2026"],
    ),
    # ---------------------------------------------------------------- now
    FunctionExample(
        function_or_topic="now",
        category="Conversion & temporal",
        description="Current timestamp as an ISO-8601 string; the exact value varies at runtime.",
        expression="now()",
        input=None,
        expected_kind="nondeterministic",
        expected=["2026-07-11T09:00:00.000000"],
    ),
    FunctionExample(
        function_or_topic="now",
        category="Conversion & temporal",
        description="Slice the date portion out of the current timestamp; the value varies at runtime.",
        expression="now().substring(0, 10)",
        input=None,
        expected_kind="nondeterministic",
        expected=["2026-07-11"],
    ),
    # ================================================================ Operators
    # ---------------------------------------------------------------- topic: operator-implies
    FunctionExample(
        function_or_topic="operator-implies",
        category="Operators",
        description="`a implies b` is false only when `a` holds but `b` does not.",
        expression="active implies verified",
        input={"active": True, "verified": False},
        expected=[False],
    ),
    FunctionExample(
        function_or_topic="operator-implies",
        category="Operators",
        description="A false antecedent makes `implies` vacuously true.",
        expression="isDraft implies reviewed",
        input={"isDraft": False, "reviewed": False},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-implies",
        category="Operators",
        description="A true antecedent with a true consequent holds.",
        expression="verified implies active",
        input={"verified": True, "active": True},
        expected=[True],
    ),
    # ---------------------------------------------------------------- topic: operator-in
    FunctionExample(
        function_or_topic="operator-in",
        category="Operators",
        description="Test membership of a scalar in an array literal.",
        expression='valueType in ["NUMBER", "INTEGER"]',
        input={"valueType": "NUMBER"},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-in",
        category="Operators",
        description="A value outside the set is not a member.",
        expression='status in ["ACTIVE", "COMPLETED"]',
        input={"status": "CANCELLED"},
        expected=[False],
    ),
    # ---------------------------------------------------------------- topic: operator-concat
    FunctionExample(
        function_or_topic="operator-concat",
        category="Operators",
        description="`+` concatenates two strings.",
        expression='firstName + " " + lastName',
        input={"firstName": "Ada", "lastName": "Lovelace"},
        expected=["Ada Lovelace"],
    ),
    FunctionExample(
        function_or_topic="operator-concat",
        category="Operators",
        description="Prefix a field with a string literal to build a label.",
        expression='"OU-" + code',
        input={"code": "SL01"},
        expected=["OU-SL01"],
    ),
    FunctionExample(
        function_or_topic="operator-concat",
        category="Operators",
        description="Build an analytics dimension key from fields.",
        expression='dx + "." + pe',
        input={"dx": "fbfJHSPpUQD", "pe": "202601"},
        expected=["fbfJHSPpUQD.202601"],
    ),
    # ---------------------------------------------------------------- topic: operator-arithmetic
    FunctionExample(
        function_or_topic="operator-arithmetic",
        category="Operators",
        description="`/` is true division and keeps the fraction.",
        expression="7 / 2",
        input=None,
        expected=[3.5],
    ),
    FunctionExample(
        function_or_topic="operator-arithmetic",
        category="Operators",
        description="`div` is integer division, truncating toward zero.",
        expression="7 div 2",
        input=None,
        expected=[3.0],
    ),
    FunctionExample(
        function_or_topic="operator-arithmetic",
        category="Operators",
        description="`mod` is the remainder.",
        expression="7 mod 2",
        input=None,
        expected=[1.0],
    ),
    FunctionExample(
        function_or_topic="operator-arithmetic",
        category="Operators",
        description="Unary minus negates a number (arithmetic is decimal-valued).",
        expression="-delta",
        input={"delta": 5},
        expected=[-5.0],
    ),
    # ---------------------------------------------------------------- topic: operator-xor
    FunctionExample(
        function_or_topic="operator-xor",
        category="Operators",
        description="`xor` is true when exactly one side holds.",
        expression="smsEnabled xor emailEnabled",
        input={"smsEnabled": True, "emailEnabled": False},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-xor",
        category="Operators",
        description="Both sides true is not exclusive, so `xor` is false.",
        expression="draft xor published",
        input={"draft": True, "published": True},
        expected=[False],
    ),
    # ---------------------------------------------------------------- topic: operator-not-match
    FunctionExample(
        function_or_topic="operator-not-match",
        category="Operators",
        description="`!~` is true when the case-insensitive substring is absent.",
        expression='name !~ "malaria"',
        input={"name": "BCG doses"},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-not-match",
        category="Operators",
        description="`~` matches case-insensitively, so `!~` is false when it would match.",
        expression='name !~ "bcg"',
        input={"name": "BCG doses"},
        expected=[False],
    ),
    # ---------------------------------------------------------------- topic: operator-contains
    FunctionExample(
        function_or_topic="operator-contains",
        category="Operators",
        description="Infix `contains` tests membership in a collection.",
        expression='orgUnitGroups contains "CHW"',
        input={"orgUnitGroups": ["CHW", "PHU"]},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-contains",
        category="Operators",
        description="A value not in the collection is not contained.",
        expression='orgUnitGroups contains "MOH"',
        input={"orgUnitGroups": ["CHW", "PHU"]},
        expected=[False],
    ),
    FunctionExample(
        function_or_topic="operator-contains",
        category="Operators",
        description="With a string on both sides, infix `contains` is a substring test.",
        expression='name contains "ov"',
        input={"name": "Lovelace"},
        expected=[True],
    ),
    # ---------------------------------------------------------------- topic: operator-is
    FunctionExample(
        function_or_topic="operator-is",
        category="Operators",
        description="`is Integer` tests for an integer value.",
        expression="value is Integer",
        input={"value": 42},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-is",
        category="Operators",
        description="`is Decimal` tests for a floating-point value.",
        expression="value is Decimal",
        input={"value": 3.14},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-is",
        category="Operators",
        description="`is String` tests for a string value.",
        expression="value is String",
        input={"value": "NUMBER"},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-is",
        category="Operators",
        description="`is Boolean` tests for a boolean value.",
        expression="value is Boolean",
        input={"value": True},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-is",
        category="Operators",
        description="`is Object` tests for a structured node.",
        expression="value is Object",
        input={"value": {"k": 1}},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="operator-is",
        category="Operators",
        description="A numeric string is a String, not an Integer.",
        expression="code is Integer",
        input={"code": "42"},
        expected=[False],
    ),
    # ---------------------------------------------------------------- topic: existential-comparison
    FunctionExample(
        function_or_topic="existential-comparison",
        category="Operators",
        description="`>` over a repeated field is true when any item exceeds the scalar.",
        expression="items.qty > 2",
        input={"items": [{"qty": 1}, {"qty": 5}]},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="existential-comparison",
        category="Operators",
        description="`=` holds when any value in the collection matches.",
        expression='given = "Ada"',
        input={"given": ["Ada", "Grace"]},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="existential-comparison",
        category="Operators",
        description="`!=` means no pair is equal, so a present match makes it false.",
        expression='given != "Ada"',
        input={"given": ["Ada", "Grace"]},
        expected=[False],
    ),
    FunctionExample(
        function_or_topic="existential-comparison",
        category="Operators",
        description="`<` holds when some value falls below the scalar.",
        expression="levels < 3",
        input={"levels": [4, 2]},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="existential-comparison",
        category="Operators",
        description="`~` holds when any value matches case-insensitively.",
        expression='codes ~ "anc"',
        input={"codes": ["ANC1", "BCG"]},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="existential-comparison",
        category="Operators",
        description="`!~` means no value matches, so a present match makes it false.",
        expression='codes !~ "anc"',
        input={"codes": ["ANC1", "BCG"]},
        expected=[False],
    ),
    # ================================================================ Literals & navigation
    # ---------------------------------------------------------------- topic: literal-date
    FunctionExample(
        function_or_topic="literal-date",
        category="Literals & navigation",
        description="A `@`-prefixed date literal evaluates to its ISO-8601 string.",
        expression="@2026-06-23",
        input=None,
        expected=["2026-06-23"],
    ),
    FunctionExample(
        function_or_topic="literal-date",
        category="Literals & navigation",
        description="Compare an event date against a date literal (ISO strings order lexically).",
        expression="eventDate > @2026-01-01",
        input={"eventDate": "2026-06-23"},
        expected=[True],
    ),
    FunctionExample(
        function_or_topic="literal-date",
        category="Literals & navigation",
        description="A date literal equals a matching ISO date string.",
        expression="eventDate = @2026-06-23",
        input={"eventDate": "2026-06-23"},
        expected=[True],
    ),
    # ---------------------------------------------------------------- topic: literal-datetime
    FunctionExample(
        function_or_topic="literal-datetime",
        category="Literals & navigation",
        description="A `@`-prefixed datetime literal evaluates to its ISO-8601 string.",
        expression="@2026-06-23T12:00:00",
        input=None,
        expected=["2026-06-23T12:00:00"],
    ),
    FunctionExample(
        function_or_topic="literal-datetime",
        category="Literals & navigation",
        description="Compare a timestamp field against a datetime literal.",
        expression="lastUpdated >= @2026-06-23T00:00:00",
        input={"lastUpdated": "2026-06-23T12:30:00"},
        expected=[True],
    ),
    # ---------------------------------------------------------------- topic: path-navigation
    FunctionExample(
        function_or_topic="path-navigation",
        category="Literals & navigation",
        description="A positive integer subscript indexes a collection.",
        expression="coding[0]",
        input={"coding": [{"x": 1}, {"x": 2}]},
        expected=[{"x": 1}],
    ),
    FunctionExample(
        function_or_topic="path-navigation",
        category="Literals & navigation",
        description="An out-of-bounds index yields the empty collection, not an error.",
        expression="coding[9]",
        input={"coding": [{"x": 1}, {"x": 2}]},
        expected=[],
    ),
    FunctionExample(
        function_or_topic="path-navigation",
        category="Literals & navigation",
        description="An integer-valued index may be negative, counting from the end.",
        expression="coding[pos]",
        input={"coding": [{"x": 1}, {"x": 2}, {"x": 3}], "pos": -1},
        expected=[{"x": 3}],
    ),
    FunctionExample(
        function_or_topic="path-navigation",
        category="Literals & navigation",
        description="A string subscript reaches keys that are not identifiers.",
        expression='attributes["Birth date"]',
        input={"attributes": {"Birth date": "2000-01-01"}},
        expected=["2000-01-01"],
    ),
    FunctionExample(
        function_or_topic="path-navigation",
        category="Literals & navigation",
        description="Each navigation hop flattens one level of nested collections.",
        expression="orgUnits.ancestors.name",
        input={"orgUnits": [{"ancestors": [{"name": "Sierra Leone"}, {"name": "Bo"}]}]},
        expected=["Sierra Leone", "Bo"],
    ),
]


def doc_examples_by_category() -> dict[str, list[FunctionExample]]:
    """Group the catalog by category, preserving definition order within each group."""
    grouped: dict[str, list[FunctionExample]] = {}
    for example in DOC_EXAMPLES:
        grouped.setdefault(example.category, []).append(example)
    return grouped
