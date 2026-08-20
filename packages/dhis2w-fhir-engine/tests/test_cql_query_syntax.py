"""Tests for CQL query syntax to ensure grammar coverage.

These tests verify that query syntax works correctly, especially edge cases
that caused issues in the past.
"""

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator


@pytest.fixture
def evaluator() -> CQLEvaluator:
    """Create a CQL evaluator."""
    return CQLEvaluator()


class TestQueryWithListLiterals:
    """Test queries on inline list literals (require parentheses)."""

    def test_list_literal_query_basic(self, evaluator: CQLEvaluator) -> None:
        """List literals in queries require parentheses."""
        result = evaluator.evaluate_expression("({1, 2, 3, 4, 5}) N where N > 2 return N")
        assert result == [3, 4, 5]

    def test_list_literal_query_transform(self, evaluator: CQLEvaluator) -> None:
        """Transform list literal elements."""
        result = evaluator.evaluate_expression("({1, 2, 3}) N return N * 2")
        assert result == [2, 4, 6]

    def test_list_literal_query_strings(self, evaluator: CQLEvaluator) -> None:
        """Query on string list literal."""
        result = evaluator.evaluate_expression("({'a', 'b', 'c'}) S return Upper(S)")
        assert result == ["A", "B", "C"]

    def test_list_literal_query_with_let(self, evaluator: CQLEvaluator) -> None:
        """Query with let clause on list literal."""
        result = evaluator.evaluate_expression("({1, 2, 3, 4, 5}) N let sq: N * N where sq > 10 return sq")
        assert result == [16, 25]

    def test_list_literal_nested_parens(self, evaluator: CQLEvaluator) -> None:
        """Nested parentheses for complex expressions."""
        result = evaluator.evaluate_expression("(({1, 2, 3})) N return N")
        assert result == [1, 2, 3]


class TestQueryWithDefinitions:
    """Test queries referencing defined lists (no parentheses needed)."""

    def test_definition_query(self, evaluator: CQLEvaluator) -> None:
        """Query on a defined list works without parentheses."""
        evaluator.compile("""
            library Test
            define Numbers: {1, 2, 3, 4, 5}
            define Filtered: (Numbers) N where N > 2 return N
        """)
        result = evaluator.evaluate_definition("Filtered")
        assert result == [3, 4, 5]

    def test_definition_query_chained(self, evaluator: CQLEvaluator) -> None:
        """Query result used in another query."""
        evaluator.compile("""
            library Test
            define Numbers: {1, 2, 3, 4, 5}
            define Large: (Numbers) N where N > 2 return N
            define Doubled: (Large) N return N * 2
        """)
        result = evaluator.evaluate_definition("Doubled")
        assert result == [6, 8, 10]


class TestQuerySortSyntax:
    """Test query sort clause syntax."""

    def test_sort_asc(self, evaluator: CQLEvaluator) -> None:
        """Sort ascending."""
        result = evaluator.evaluate_expression("({5, 2, 8, 1}) N return N sort asc")
        assert result == [1, 2, 5, 8]

    def test_sort_desc(self, evaluator: CQLEvaluator) -> None:
        """Sort descending."""
        result = evaluator.evaluate_expression("({5, 2, 8, 1}) N return N sort desc")
        assert result == [8, 5, 2, 1]

    def test_sort_default(self, evaluator: CQLEvaluator) -> None:
        """Sort without direction (default ascending)."""
        result = evaluator.evaluate_expression("Sort({5, 2, 8, 1})")
        assert result == [1, 2, 5, 8]


class TestQueryAggregates:
    """Test aggregates with queries."""

    def test_sum_of_query(self, evaluator: CQLEvaluator) -> None:
        """Sum of query results."""
        result = evaluator.evaluate_expression("Sum(({1, 2, 3, 4, 5}) N return N * 2)")
        assert result == 30  # 2+4+6+8+10

    def test_count_of_filtered_query(self, evaluator: CQLEvaluator) -> None:
        """Count of filtered query."""
        result = evaluator.evaluate_expression("Count(({1, 2, 3, 4, 5}) N where N > 2 return N)")
        assert result == 3

    def test_avg_of_query(self, evaluator: CQLEvaluator) -> None:
        """Average of query results."""
        result = evaluator.evaluate_expression("Avg(({2, 4, 6}) N return N)")
        assert result == 4


class TestQueryEdgeCases:
    """Test edge cases in query syntax."""

    def test_empty_result(self, evaluator: CQLEvaluator) -> None:
        """Query that filters all elements."""
        result = evaluator.evaluate_expression("({1, 2, 3}) N where N > 100 return N")
        assert result == []

    def test_single_element(self, evaluator: CQLEvaluator) -> None:
        """Query on single element list."""
        result = evaluator.evaluate_expression("({42}) N return N * 2")
        assert result == [84]

    def test_empty_source(self, evaluator: CQLEvaluator) -> None:
        """Query on empty list."""
        result = evaluator.evaluate_expression("({}) N return N")
        assert result == []

    def test_null_handling(self, evaluator: CQLEvaluator) -> None:
        """Query with null values."""
        result = evaluator.evaluate_expression("({1, null, 3}) N where N is not null return N")
        assert result == [1, 3]

    def test_query_in_exists(self, evaluator: CQLEvaluator) -> None:
        """Query used in exists expression."""
        result = evaluator.evaluate_expression("exists(({1, 2, 3}) N where N > 2)")
        assert result is True

        result = evaluator.evaluate_expression("exists(({1, 2, 3}) N where N > 100)")
        assert result is False


class TestMultiSourceQueries:
    """Test queries with multiple sources."""

    def test_two_sources(self, evaluator: CQLEvaluator) -> None:
        """Query with two sources (cross product)."""
        evaluator.compile("""
            library Test
            define A: {1, 2}
            define B: {'x', 'y'}
            define CrossProduct:
                (A) a, (B) b
                return Tuple { num: a, char: b }
        """)
        result = evaluator.evaluate_definition("CrossProduct")
        assert len(result) == 4  # 2 x 2


class TestQueryReturnAll:
    """Test return all clause."""

    def test_return_all_preserves_duplicates(self, evaluator: CQLEvaluator) -> None:
        """Return all keeps duplicates."""
        evaluator.compile("""
            library Test
            define Numbers: {1, 1, 2, 2, 3}
            define AllNumbers: (Numbers) N return all N
        """)
        result = evaluator.evaluate_definition("AllNumbers")
        assert len(result) == 5
        assert result.count(1) == 2
        assert result.count(2) == 2


class TestQueryWithoutReturnClause:
    """Test queries without explicit return clause."""

    def test_implicit_return(self, evaluator: CQLEvaluator) -> None:
        """Query without return clause returns the alias."""
        result = evaluator.evaluate_expression("({1, 2, 3}) N where N > 1")
        assert result == [2, 3]
