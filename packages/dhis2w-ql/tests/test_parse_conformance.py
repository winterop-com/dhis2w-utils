"""Parsing + d2path conformance: every sample parses, and a table of expressions evaluates."""

from __future__ import annotations

import pytest
from dhis2w_ql import (
    SAMPLES,
    Evaluator,
    LexError,
    ParseError,
    Sample,
    generate,
    parse,
    parse_expression,
)

_PATIENT = {
    "resourceType": "Patient",
    "active": True,
    "gender": "male",
    "name": [
        {"use": "official", "given": ["Ada", "Lovelace"], "family": "King"},
        {"use": "nick", "given": ["Countess"]},
    ],
    "telecom": [{"system": "phone", "value": "555-1"}, {"system": "email", "value": "a@b.c"}],
}


@pytest.mark.parametrize("sample", SAMPLES, ids=[s.id for s in SAMPLES])
def test_every_curated_sample_parses(sample: Sample) -> None:
    if sample.language == "d2path":
        parse_expression(sample.source)
    else:
        parse(sample.source)


def test_source_only_define_is_a_named_query() -> None:
    from dhis2w_ql.ast import Define, NameSource

    library = parse("define All: dataElements\nAll | limit 5")
    define = library.definitions[0]
    assert isinstance(define, Define)
    assert isinstance(define.body.source, NameSource)
    assert define.body.source.name == "dataElements"
    assert library.terminal is not None
    assert isinstance(library.terminal.source, NameSource)
    assert library.terminal.source.name == "All"


def test_committed_example_programs_parse() -> None:
    from pathlib import Path

    examples = Path(__file__).resolve().parents[3] / "examples" / "d2ql"
    if not examples.exists():  # not present when the package is built/used standalone
        pytest.skip("examples/d2ql is not available")
    files = sorted(examples.glob("*.d2ql"))
    assert files, "expected committed .d2ql example programs"
    for path in files:
        parse(path.read_text(encoding="utf-8"))


def test_generated_corpus_parses() -> None:
    corpus = generate()
    assert len(corpus) > 500
    for example in corpus:
        if example.language == "d2path":
            parse_expression(example.source)
        else:
            parse(example.source)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", [7.0]),
        ("(1 + 2) * 3", [9.0]),
        ('gender = "male"', [True]),
        ('gender = "female"', [False]),
        ('gender ~ "MAL"', [True]),
        ('active = true and gender = "male"', [True]),
        ('active = true and gender = "female"', [False]),
        ('name.where(use = "official").family', ["King"]),
        ("name.given.first()", ["Ada"]),
        ("name.given.last()", ["Countess"]),
        ("name.given.count()", [3]),
        ('name.where(use = "official").given', ["Ada", "Lovelace"]),
        ('telecom.where(system = "phone").value', ["555-1"]),
        ("name.family.first().upper()", ["KING"]),
        ('gender in ["male", "female"]', [True]),
        ('gender in ["x", "y"]', [False]),
        ('iif(gender = "male", "M", "F")', ["M"]),
        ("name.exists()", [True]),
        ('name.where(use = "missing").exists()', [False]),
        ('name.given.join(" ")', ["Ada Lovelace Countess"]),
        ('"a" + "b"', ["ab"]),
        ("name.count() > 1", [True]),
    ],
)
def test_d2path_conformance(expression: str, expected: list) -> None:
    result = Evaluator().evaluate(parse_expression(expression), [_PATIENT])
    assert result == expected


def test_navigating_a_missing_field_is_empty() -> None:
    assert Evaluator().evaluate(parse_expression("doesNotExist"), [_PATIENT]) == []


def test_collection_comparisons_are_existential() -> None:
    ev = Evaluator()
    person = {"given": ["Ada", "Lovelace"]}
    assert ev.evaluate(parse_expression('given = "Lovelace"'), [person]) == [True]
    assert ev.evaluate(parse_expression('given = "Nope"'), [person]) == [False]
    assert ev.evaluate(parse_expression('given != "Lovelace"'), [person]) == [False]
    assert ev.evaluate(parse_expression('given ~ "lov"'), [person]) == [True]
    # singletons keep scalar behaviour
    assert ev.evaluate(parse_expression('given = "Ada"'), [{"given": "Ada"}]) == [True]


def test_is_type_test_takes_a_type_name() -> None:
    ev = Evaluator()
    assert ev.evaluate(parse_expression("value is Integer"), [{"value": 5}]) == [True]
    assert ev.evaluate(parse_expression('value is "Integer"'), [{"value": 5}]) == [True]
    assert ev.evaluate(parse_expression("value is String"), [{"value": 5}]) == [False]


def test_logical_operators_short_circuit() -> None:
    ev = Evaluator()
    # `and` does not evaluate the right side when the left is false (no division-by-zero raise).
    assert ev.evaluate(parse_expression("1 = 2 and (1 div 0) > 0"), [{}]) == [False]
    # `or` does not evaluate the right side when the left is true.
    assert ev.evaluate(parse_expression("1 = 1 or (1 div 0) > 0"), [{}]) == [True]
    # a guarded predicate excludes the bad row instead of raising.
    rows = [{"value": 0}, {"value": 50}]
    kept = [r for r in rows if ev.evaluate(parse_expression("value != 0 and (100 div value) > 1"), [r]) == [True]]
    assert kept == [{"value": 50}]


def test_lex_error_has_position() -> None:
    with pytest.raises(LexError) as info:
        parse("dataElements | where name = 'unterminated")
    assert info.value.line == 1


def test_parse_error_on_missing_stage() -> None:
    with pytest.raises(ParseError):
        parse("dataElements | ")


def test_parse_call_source() -> None:
    library = parse('analytics(dx: "abc", pe: "LAST_12_MONTHS", ou: "xyz") | limit 5')
    assert library.terminal is not None
    source = library.terminal.source
    assert source.kind == "call"
    assert source.name == "analytics"
    assert [arg.name for arg in source.args] == ["dx", "pe", "ou"]


def test_parse_aggregate_stage() -> None:
    library = parse("dataElements | group by domainType { total: sum(value), n: count() }")
    assert library.terminal is not None
    stage = library.terminal.stages[0]
    assert stage.kind == "aggregate"
    assert [field.name for field in stage.aggregations.fields] == ["total", "n"]
