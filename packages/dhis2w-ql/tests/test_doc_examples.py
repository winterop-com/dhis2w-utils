"""Conformance for the d2path documentation catalog: every entry parses, evaluates, and matches.

Also enforces catalog hygiene (unique entries, real registry references) and carries a coverage
gate over the built-in function registry that is skipped until content authors fill the catalog.
"""

from __future__ import annotations

import pytest
from dhis2w_ql import Evaluator, parse_expression
from dhis2w_ql.d2path.functions import _REGISTRY
from dhis2w_ql.doc_examples import DOC_EXAMPLES, FunctionExample

# The catalog covers every registry function, so the coverage test hard-fails on any future gap.
ENFORCE_FULL_COVERAGE = True


def _is_topic(function_or_topic: str) -> bool:
    """A topic slug (`operator-implies`) carries a hyphen; a registry function name never does."""
    return "-" in function_or_topic


def _covered_registry_names() -> set[str]:
    """Return the set of registry function names that have at least one catalog example."""
    return {example.function_or_topic for example in DOC_EXAMPLES if example.function_or_topic in _REGISTRY}


_UNCOVERED = sorted(set(_REGISTRY) - _covered_registry_names())


@pytest.mark.parametrize("example", DOC_EXAMPLES, ids=[f"{e.function_or_topic}:{e.expression}" for e in DOC_EXAMPLES])
def test_doc_example_evaluates_to_expected(example: FunctionExample) -> None:
    result = Evaluator().evaluate(parse_expression(example.expression), example.focus())
    if example.expected_kind == "exact":
        assert result == example.expected
    else:
        # Nondeterministic output (today()/now()): assert only parse+eval success and matching shape.
        assert isinstance(result, list)
        assert len(result) == len(example.expected)
        assert [type(item) for item in result] == [type(item) for item in example.expected]


def test_catalog_entries_are_unique() -> None:
    pairs = [(example.function_or_topic, example.expression) for example in DOC_EXAMPLES]
    duplicates = sorted({pair for pair in pairs if pairs.count(pair) > 1})
    assert not duplicates, f"duplicate (function_or_topic, expression) pairs: {duplicates}"


def test_referenced_registry_functions_exist() -> None:
    missing = sorted(
        example.function_or_topic
        for example in DOC_EXAMPLES
        if not _is_topic(example.function_or_topic) and example.function_or_topic not in _REGISTRY
    )
    assert not missing, f"catalog references unknown registry functions: {missing}"


@pytest.mark.skipif(
    not ENFORCE_FULL_COVERAGE,
    reason=f"{len(_UNCOVERED)} registry function(s) still lack a doc example: {_UNCOVERED}",
)
def test_every_registry_function_has_an_example() -> None:
    assert not _UNCOVERED, f"registry functions with zero doc examples: {_UNCOVERED}"
