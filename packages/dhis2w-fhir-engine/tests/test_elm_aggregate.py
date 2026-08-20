"""Tests for ELM Query Aggregate Clause."""

from dhis2w_fhir_engine.engine.cql.context import CQLContext
from dhis2w_fhir_engine.engine.elm.visitor import ELMExpressionVisitor


class TestAggregateClause:
    """Test aggregate clause in ELM queries."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.context = CQLContext()
        self.visitor = ELMExpressionVisitor(self.context)

    def test_aggregate_sum(self) -> None:
        """Test aggregate clause for summing values."""
        # Query: from {1, 2, 3, 4, 5} X aggregate Total starting 0: Total + X
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [
                            {"type": "Literal", "valueType": "Integer", "value": "1"},
                            {"type": "Literal", "valueType": "Integer", "value": "2"},
                            {"type": "Literal", "valueType": "Integer", "value": "3"},
                            {"type": "Literal", "valueType": "Integer", "value": "4"},
                            {"type": "Literal", "valueType": "Integer", "value": "5"},
                        ],
                    },
                }
            ],
            "aggregate": {
                "identifier": "Total",
                "starting": {"type": "Literal", "valueType": "Integer", "value": "0"},
                "expression": {
                    "type": "Add",
                    "operand": [
                        {"type": "IdentifierRef", "name": "Total"},
                        {"type": "IdentifierRef", "name": "X"},
                    ],
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == 15  # 1+2+3+4+5

    def test_aggregate_product(self) -> None:
        """Test aggregate clause for computing product."""
        # Query: from {1, 2, 3, 4} X aggregate Product starting 1: Product * X
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [
                            {"type": "Literal", "valueType": "Integer", "value": "1"},
                            {"type": "Literal", "valueType": "Integer", "value": "2"},
                            {"type": "Literal", "valueType": "Integer", "value": "3"},
                            {"type": "Literal", "valueType": "Integer", "value": "4"},
                        ],
                    },
                }
            ],
            "aggregate": {
                "identifier": "Product",
                "starting": {"type": "Literal", "valueType": "Integer", "value": "1"},
                "expression": {
                    "type": "Multiply",
                    "operand": [
                        {"type": "IdentifierRef", "name": "Product"},
                        {"type": "IdentifierRef", "name": "X"},
                    ],
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == 24  # 1*2*3*4

    def test_aggregate_count(self) -> None:
        """Test aggregate clause for counting."""
        # Query: from {10, 20, 30} X aggregate Count starting 0: Count + 1
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [
                            {"type": "Literal", "valueType": "Integer", "value": "10"},
                            {"type": "Literal", "valueType": "Integer", "value": "20"},
                            {"type": "Literal", "valueType": "Integer", "value": "30"},
                        ],
                    },
                }
            ],
            "aggregate": {
                "identifier": "Count",
                "starting": {"type": "Literal", "valueType": "Integer", "value": "0"},
                "expression": {
                    "type": "Add",
                    "operand": [
                        {"type": "IdentifierRef", "name": "Count"},
                        {"type": "Literal", "valueType": "Integer", "value": "1"},
                    ],
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == 3

    def test_aggregate_with_filter(self) -> None:
        """Test aggregate with where clause filtering."""
        # Query: from {1, 2, 3, 4, 5, 6} X where X > 3 aggregate Total starting 0: Total + X
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [
                            {"type": "Literal", "valueType": "Integer", "value": "1"},
                            {"type": "Literal", "valueType": "Integer", "value": "2"},
                            {"type": "Literal", "valueType": "Integer", "value": "3"},
                            {"type": "Literal", "valueType": "Integer", "value": "4"},
                            {"type": "Literal", "valueType": "Integer", "value": "5"},
                            {"type": "Literal", "valueType": "Integer", "value": "6"},
                        ],
                    },
                }
            ],
            "where": {
                "type": "Greater",
                "operand": [
                    {"type": "IdentifierRef", "name": "X"},
                    {"type": "Literal", "valueType": "Integer", "value": "3"},
                ],
            },
            "aggregate": {
                "identifier": "Total",
                "starting": {"type": "Literal", "valueType": "Integer", "value": "0"},
                "expression": {
                    "type": "Add",
                    "operand": [
                        {"type": "IdentifierRef", "name": "Total"},
                        {"type": "IdentifierRef", "name": "X"},
                    ],
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == 15  # 4+5+6

    def test_aggregate_string_concat(self) -> None:
        """Test aggregate clause for string concatenation."""
        # Query: from {'a', 'b', 'c'} X aggregate Str starting '': Str + X
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [
                            {"type": "Literal", "valueType": "String", "value": "a"},
                            {"type": "Literal", "valueType": "String", "value": "b"},
                            {"type": "Literal", "valueType": "String", "value": "c"},
                        ],
                    },
                }
            ],
            "aggregate": {
                "identifier": "Str",
                "starting": {"type": "Literal", "valueType": "String", "value": ""},
                "expression": {
                    "type": "Concatenate",
                    "operand": [
                        {"type": "IdentifierRef", "name": "Str"},
                        {"type": "IdentifierRef", "name": "X"},
                    ],
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == "abc"

    def test_aggregate_max(self) -> None:
        """Test aggregate clause for finding maximum."""
        # Query: from {3, 1, 4, 1, 5, 9, 2, 6} X aggregate Max starting null: if Max is null or X > Max then X else Max
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [
                            {"type": "Literal", "valueType": "Integer", "value": "3"},
                            {"type": "Literal", "valueType": "Integer", "value": "1"},
                            {"type": "Literal", "valueType": "Integer", "value": "4"},
                            {"type": "Literal", "valueType": "Integer", "value": "1"},
                            {"type": "Literal", "valueType": "Integer", "value": "5"},
                            {"type": "Literal", "valueType": "Integer", "value": "9"},
                            {"type": "Literal", "valueType": "Integer", "value": "2"},
                            {"type": "Literal", "valueType": "Integer", "value": "6"},
                        ],
                    },
                }
            ],
            "aggregate": {
                "identifier": "Max",
                "starting": {"type": "Null"},
                "expression": {
                    "type": "If",
                    "condition": {
                        "type": "Or",
                        "operand": [
                            {"type": "IsNull", "operand": {"type": "IdentifierRef", "name": "Max"}},
                            {
                                "type": "Greater",
                                "operand": [
                                    {"type": "IdentifierRef", "name": "X"},
                                    {"type": "IdentifierRef", "name": "Max"},
                                ],
                            },
                        ],
                    },
                    "then": {"type": "IdentifierRef", "name": "X"},
                    "else": {"type": "IdentifierRef", "name": "Max"},
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == 9

    def test_aggregate_empty_source(self) -> None:
        """Test aggregate with empty source returns starting value."""
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [],
                    },
                }
            ],
            "aggregate": {
                "identifier": "Total",
                "starting": {"type": "Literal", "valueType": "Integer", "value": "42"},
                "expression": {
                    "type": "Add",
                    "operand": [
                        {"type": "IdentifierRef", "name": "Total"},
                        {"type": "IdentifierRef", "name": "X"},
                    ],
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == 42  # Starting value returned unchanged

    def test_aggregate_no_starting_value(self) -> None:
        """Test aggregate without starting value starts with null."""
        # Query: from {1, 2, 3} X aggregate Result: Coalesce(Result, 0) + X
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [
                            {"type": "Literal", "valueType": "Integer", "value": "1"},
                            {"type": "Literal", "valueType": "Integer", "value": "2"},
                            {"type": "Literal", "valueType": "Integer", "value": "3"},
                        ],
                    },
                }
            ],
            "aggregate": {
                "identifier": "Result",
                # No starting value - defaults to null
                "expression": {
                    "type": "Add",
                    "operand": [
                        {
                            "type": "Coalesce",
                            "operand": [
                                {"type": "IdentifierRef", "name": "Result"},
                                {"type": "Literal", "valueType": "Integer", "value": "0"},
                            ],
                        },
                        {"type": "IdentifierRef", "name": "X"},
                    ],
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == 6  # 0+1+2+3

    def test_aggregate_distinct(self) -> None:
        """Test aggregate with distinct modifier."""
        # Query: from {1, 1, 2, 2, 3, 3} X aggregate distinct Total starting 0: Total + X
        node = {
            "type": "Query",
            "source": [
                {
                    "alias": "X",
                    "expression": {
                        "type": "List",
                        "element": [
                            {"type": "Literal", "valueType": "Integer", "value": "1"},
                            {"type": "Literal", "valueType": "Integer", "value": "1"},
                            {"type": "Literal", "valueType": "Integer", "value": "2"},
                            {"type": "Literal", "valueType": "Integer", "value": "2"},
                            {"type": "Literal", "valueType": "Integer", "value": "3"},
                            {"type": "Literal", "valueType": "Integer", "value": "3"},
                        ],
                    },
                }
            ],
            "aggregate": {
                "identifier": "Total",
                "distinct": True,
                "starting": {"type": "Literal", "valueType": "Integer", "value": "0"},
                "expression": {
                    "type": "Add",
                    "operand": [
                        {"type": "IdentifierRef", "name": "Total"},
                        {"type": "IdentifierRef", "name": "X"},
                    ],
                },
            },
        }
        result = self.visitor.evaluate(node)
        assert result == 6  # 1+2+3 (distinct values only)
