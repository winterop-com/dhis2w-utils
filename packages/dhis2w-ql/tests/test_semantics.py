"""Executable conformance for docs/query/semantics.md — every documented rule is asserted here.

Each test name maps to a section of the Language semantics page, so the spec cannot drift from the
implementation without a test failing.
"""

from __future__ import annotations

import pytest
from dhis2w_ql import Evaluator, InMemoryBinder, QueryEngine, parse, parse_expression
from dhis2w_ql.errors import D2qlError, EvaluationError, ParseError, SemanticError

_ROWS = [
    {"id": "a1", "name": "ANC 1st visit", "domainType": "AGGREGATE", "categoryCombo": {"name": "default"}, "value": 12},
    {"id": "b2", "name": "BCG doses", "domainType": "AGGREGATE", "categoryCombo": {"name": "default"}, "value": 7},
    {"id": "c3", "name": "ANC 2nd visit", "domainType": "TRACKER", "categoryCombo": {"name": "EPI"}, "value": 30},
]


def _p(expression: str, data: object) -> list:
    """Evaluate a bare d2path expression over one JSON node."""
    return Evaluator().evaluate(parse_expression(expression), [data])


async def _rows(program: str) -> list:
    """Run a d2ql program over the in-memory `dataElements` resource."""
    return (await QueryEngine(parse(program), InMemoryBinder({"dataElements": _ROWS})).run_terminal()).rows


# ---------------------------------------------------------------- Focus modes & variables


async def test_row_mode_this_and_index() -> None:
    rows = await _rows("dataElements | transform { id: $this.id, pos: $index } | limit 2")
    assert rows == [{"id": "a1", "pos": 0}, {"id": "b2", "pos": 1}]


async def test_group_mode_aggregates_over_bucket() -> None:
    rows = await _rows("dataElements | group by domainType { n: count(), total: sum(value) }")
    assert rows == [
        {"domainType": "AGGREGATE", "n": 2, "total": 19.0},
        {"domainType": "TRACKER", "n": 1, "total": 30.0},
    ]


async def test_whole_stream_mode_rows_in_fold() -> None:
    assert await _rows("dataElements | fold { total: $rows.count() }") == [{"total": 3}]


async def test_index_is_inert_in_order() -> None:
    # `$index` is fixed to 0 inside an order comparator, so ordering by it is a no-op.
    assert [r["id"] for r in await _rows("dataElements | order $index desc | select id")] == ["a1", "b2", "c3"]


async def test_scalar_define_resolves_via_dollar_name() -> None:
    rows = await _rows("define Min: 10\ndataElements | where value > $Min | select id")
    assert [r["id"] for r in rows] == ["a1", "c3"]


# ---------------------------------------------------------------- Sources & name resolution


async def test_bound_resource_shadows_a_same_named_define() -> None:
    # The terminal `dataElements` binds the resource (3 rows), not the define (which would filter to 0).
    assert await _rows('define dataElements: dataElements | where domainType = "NONE"\ndataElements | count') == [3]


async def test_unknown_source_is_an_error() -> None:
    with pytest.raises(SemanticError, match="unknown source"):
        await _rows("bogusResource | limit 1")


async def test_query_define_used_as_source() -> None:
    rows = await _rows('define Agg: dataElements | where domainType = "AGGREGATE"\nAgg | select id')
    assert [r["id"] for r in rows] == ["a1", "b2"]


def test_positional_call_is_an_expression_named_call_is_a_source() -> None:
    from dhis2w_ql.ast import CallSource, ExprSource

    expr = parse('iif(true, "a", "b")')
    assert expr.terminal is not None and isinstance(expr.terminal.source, ExprSource)
    call = parse('analytics(dx: "x", pe: "y", ou: "z")')
    assert call.terminal is not None and isinstance(call.terminal.source, CallSource)


# ---------------------------------------------------------------- select vs transform


async def test_select_derives_names_and_transform_keeps_keys() -> None:
    assert await _rows("dataElements | select id, categoryCombo.name as combo | limit 1") == [
        {"id": "a1", "combo": "default"}
    ]
    assert await _rows("dataElements | transform { code: id, deep: { combo: categoryCombo.name } } | limit 1") == [
        {"code": "a1", "deep": {"combo": "default"}}
    ]


async def test_select_arbitrary_expression_is_columnN() -> None:
    assert await _rows("dataElements | select value > 10 | limit 1") == [{"column1": True}]


async def test_duplicate_projection_names_are_rejected() -> None:
    with pytest.raises(SemanticError, match="two columns named 'name'"):
        await _rows("dataElements | select name, categoryCombo.name")
    with pytest.raises(SemanticError, match="two columns named 'domainType'"):
        await _rows("dataElements | group by domainType { domainType: count() }")


# ---------------------------------------------------------------- Operators


def test_operator_precedence() -> None:
    assert _p("1 + 2 * 3", {}) == [7.0]  # multiplicative binds tighter than additive
    assert _p("true or false and false", {}) == [True]  # `and` binds tighter than `or`
    assert _p("7 div 2", {}) == [3.0]
    assert _p("7 mod 2", {}) == [1.0]


def test_comparisons_are_existential() -> None:
    assert _p("items.qty > 2", {"items": [{"qty": 1}, {"qty": 5}]}) == [True]


def test_not_is_a_function_and_contains_is_dual() -> None:
    assert _p("active.not()", {"active": False}) == [True]
    assert _p('tags contains "a"', {"tags": ["a", "b"]}) == [True]  # operator
    assert _p('name.contains("ov")', {"name": "Lovelace"}) == [True]  # method


def test_like_is_case_insensitive_substring_not_sql_or_regex() -> None:
    assert _p('name ~ "lov"', {"name": "Lovelace"}) == [True]  # case-insensitive substring
    assert _p('name ~ "%lov%"', {"name": "Lovelace"}) == [False]  # not SQL LIKE wildcards
    assert _p('name.matches("^Lov")', {"name": "Lovelace"}) == [True]  # regex is separate
    assert _p('name.startsWith("Lov")', {"name": "Lovelace"}) == [True]


# ---------------------------------------------------------------- matches() ReDoS guard


def test_matches_rejects_nested_quantifier_pattern_quickly() -> None:
    # `(a+)+` over `aaaa...!` is the classic catastrophic-backtracking input; the pre-scan rejects the
    # pattern before it is ever compiled, so this raises immediately instead of hanging.
    with pytest.raises(D2qlError, match="nests quantifiers"):
        _p(r'name.matches("(a+)+$")', {"name": "a" * 40 + "!"})


def test_matches_rejects_further_nested_quantifier_shapes() -> None:
    for pattern in ("(a*)*", "(a+)*", "(a*)+", "(.*)+", r"(\d+){2,}"):
        with pytest.raises(D2qlError, match="nests quantifiers"):
            _p(f'name.matches("{pattern}")', {"name": "x"})


def test_matches_allows_ordinary_patterns() -> None:
    assert _p(r'code.matches("^[A-Z]{2}[0-9]+$")', {"code": "DE42"}) == [True]
    assert _p('name.matches("(abc)+")', {"name": "abcabc"}) == [True]
    assert _p('url.matches("https?://")', {"url": "http://x"}) == [True]
    assert _p('name.matches("(ab?c)+")', {"name": "abcac"}) == [True]  # bounded/optional inner is fine


# ---------------------------------------------------------------- numeric coercion is typed


def test_div_of_overflowing_string_raises_typed_error() -> None:
    # "1e999" parses to float inf; `div` truncates to int, which would raise a raw OverflowError —
    # wrapped so it stays inside the D2qlError hierarchy.
    with pytest.raises(D2qlError):
        _p("x div 1", {"x": "1e999"})


def test_to_integer_of_non_finite_raises_typed_error() -> None:
    for value in ("1e999", "-1e999", "nan"):
        with pytest.raises(D2qlError):
            _p("x.toInteger()", {"x": value})


def test_to_number_and_arithmetic_stay_finite_for_ordinary_values() -> None:
    assert _p("x div 1", {"x": "7.5"}) == [7.0]
    assert _p("x.toInteger()", {"x": "42"}) == [42]


# ---------------------------------------------------------------- null / missing


def test_null_and_missing_are_empty_use_exists_empty() -> None:
    assert _p("value = null", {"value": None}) == []  # never matches
    assert _p("value.empty()", {"value": None}) == [True]
    assert _p("value.exists()", {"value": None}) == [False]
    assert _p("gone.empty()", {"value": 1}) == [True]  # missing field


# ---------------------------------------------------------------- `[]` overload & field names


async def test_bracket_at_source_is_an_inline_filter() -> None:
    rows = await _rows('dataElements[domainType = "AGGREGATE"] | select id')
    assert [r["id"] for r in rows] == ["a1", "b2"]


def test_bracket_integer_index() -> None:
    assert _p("coding[0]", {"coding": [{"x": 1}, {"x": 2}]}) == [{"x": 1}]


def test_bracket_string_subscript_reaches_non_identifier_fields() -> None:
    # A string subscript is member access by key, so hyphen/space keys are navigable.
    assert _p('extension["us-core-race"]', {"extension": {"us-core-race": "x"}}) == ["x"]
    assert _p('items["bad name"].v', {"items": {"bad name": {"v": 9}}}) == [9]


async def test_bracket_string_subscript_with_this_in_a_pipeline() -> None:
    binder = InMemoryBinder({"res": [{"id": "a", "code-x": "P"}]})
    rows = (await QueryEngine(parse('res | transform { id: id, cx: $this["code-x"] }'), binder).run_terminal()).rows
    assert rows == [{"id": "a", "cx": "P"}]


def test_bracket_non_integer_non_string_is_rejected() -> None:
    with pytest.raises(EvaluationError, match="integer or a string key"):
        _p("value[true]", {"value": [1, 2]})


# ---------------------------------------------------------------- Definition safety


async def test_recursive_definitions_are_rejected() -> None:
    for program in (
        "define A: $A\ndataElements | transform { x: $A }",  # scalar self-reference
        "define A: A\nA",  # query self-reference
        "define A: B\ndefine B: A\nA",  # mutual cycle
    ):
        with pytest.raises(SemanticError, match="recursive definition"):
            await _rows(program)


async def test_duplicate_definition_names_are_rejected() -> None:
    with pytest.raises(SemanticError, match="duplicate definition"):
        await _rows("define A: dataElements\ndefine A: dataElements\nA | count")


async def test_function_cannot_shadow_a_builtin() -> None:
    with pytest.raises(SemanticError, match="shadows a built-in"):
        await _rows("define function upper(x): 1\ndataElements | select id")


def test_implies_is_right_associative() -> None:
    # `a implies b implies c` parses as `a implies (b implies c)`.
    assert _p("false implies false implies false", {}) == [True]


def test_duplicate_object_keys_are_rejected() -> None:
    with pytest.raises(ParseError, match="duplicate object key"):
        parse_expression("{ a: 1, a: 2 }")


async def test_user_functions_see_caller_this_and_index() -> None:
    # An extracted helper still sees the caller's `$this`/`$index`.
    rows = await _rows(
        "define function here(): { rid: $this.id, pos: $index }\ndataElements | transform here() | limit 2"
    )
    assert rows == [{"rid": "a1", "pos": 0}, {"rid": "b2", "pos": 1}]


async def test_recursive_function_is_rejected() -> None:
    with pytest.raises(SemanticError, match="recursive function"):
        await _rows("define function f(x): f($x)\ndataElements | transform { y: f(id) }")


def test_duplicate_function_parameters_are_rejected() -> None:
    with pytest.raises(ParseError, match="duplicate parameter"):
        parse("define function f(x, x): $x\ndataElements")


# ---------------------------------------------------------------- Pushdown corners


def test_filter_metacharacter_values_are_kept_local() -> None:
    # DHIS2's `property:operator:value` filter syntax has no escaping for `:` `,` `[` `]`, so a
    # predicate whose value contains one of them is kept local instead of pushed down.
    from dhis2w_ql import SourceCapabilities, parse_pipeline, plan_pipeline

    capabilities = SourceCapabilities(filter=True, order=True, paging=True)
    pipeline = parse_pipeline('dataElements | where name = "a:b,c"')
    plan = plan_pipeline("dataElements", capabilities, pipeline.stages)
    assert plan.native.filters == []
    assert [stage.kind for stage in plan.residual] == ["where"]
