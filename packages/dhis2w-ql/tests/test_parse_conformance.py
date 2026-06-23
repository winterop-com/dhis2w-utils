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
