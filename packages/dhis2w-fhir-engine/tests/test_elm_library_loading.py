"""Tests for loading ELM libraries and resolving references, queries and retrieves against them."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir_engine.engine.cql.context import CQLContext
from dhis2w_fhir_engine.engine.cql.types import CQLCode, CQLInterval
from dhis2w_fhir_engine.engine.elm.evaluator import ELMEvaluator
from dhis2w_fhir_engine.engine.elm.exceptions import ELMExecutionError, ELMReferenceError, ELMValidationError
from dhis2w_fhir_engine.engine.elm.loader import ELMLoader
from dhis2w_fhir_engine.engine.elm.models.library import ELMLibrary
from dhis2w_fhir_engine.engine.elm.visitor import ELMExpressionVisitor

ELM_TYPE = "{urn:hl7-org:elm-types:r1}"

NULL: dict[str, Any] = {"type": "Null"}


def integer(value: int) -> dict[str, Any]:
    """Build an ELM Integer literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}Integer", "value": str(value)}


def string(value: str) -> dict[str, Any]:
    """Build an ELM String literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}String", "value": value}


def boolean(value: bool) -> dict[str, Any]:
    """Build an ELM Boolean literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}Boolean", "value": "true" if value else "false"}


def elm_list(*elements: dict[str, Any]) -> dict[str, Any]:
    """Build an ELM List node."""
    return {"type": "List", "element": list(elements)}


def alias(name: str) -> dict[str, Any]:
    """Build an ELM AliasRef node."""
    return {"type": "AliasRef", "name": name}


def query_over(source: dict[str, Any], **clauses: Any) -> dict[str, Any]:
    """Build a single-source ELM Query aliased as N."""
    node: dict[str, Any] = {"type": "Query", "source": [{"alias": "N", "expression": source}]}
    node.update(clauses)
    return node


class RetrieveCall(BaseModel):
    """One recorded call into the test data source."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    resource_type: str
    code_path: str | None = None
    codes: list[Any] | None = None
    date_path: str | None = None
    date_range: Any | None = None


class RecordingDataSource(BaseModel):
    """A data source that records its retrieve calls and answers value-set membership."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    calls: list[RetrieveCall] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)

    def retrieve(
        self,
        resource_type: str,
        context: CQLContext | None = None,
        code_path: str | None = None,
        codes: list[Any] | None = None,
        valueset: str | None = None,
        date_path: str | None = None,
        date_range: Any | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Record the call and return one synthetic resource."""
        self.calls.append(
            RetrieveCall(
                resource_type=resource_type,
                code_path=code_path,
                codes=codes,
                date_path=date_path,
                date_range=date_range,
            )
        )
        return [{"resourceType": resource_type, "id": "r1"}]

    def resolve_reference(self, reference: str) -> dict[str, Any] | None:
        """Resolve nothing; the tests never follow references."""
        return None

    def in_valueset(self, code: Any, valueset_url: str) -> bool:
        """Report membership for the value sets this source was seeded with."""
        return valueset_url in self.members


LIBRARY_SOURCE: dict[str, Any] = {
    "library": {
        "identifier": {"id": "Fixture", "version": "1.0"},
        "parameters": [{"name": "Threshold", "default": integer(10)}, {"name": "NoDefault"}],
        "statements": {
            "def": [
                {"name": "Base", "expression": integer(10)},
                {"name": "Secret", "accessLevel": "Private", "expression": integer(1)},
                {"name": "Broken", "expression": {"type": "NotARealType"}},
                {
                    "name": "Doubler",
                    "type": "FunctionDef",
                    "operand": [{"name": "x"}],
                    "expression": {"type": "Multiply", "operand": [{"type": "OperandRef", "name": "x"}, integer(2)]},
                },
                {"name": "Ext", "type": "FunctionDef", "external": True, "operand": [{"name": "x"}]},
                {"name": "NoBody", "type": "FunctionDef", "operand": []},
            ]
        },
    }
}


@pytest.fixture
def library() -> ELMLibrary:
    """The fixture library, parsed into models."""
    return ELMLoader.parse(LIBRARY_SOURCE)


@pytest.fixture
def visitor(library: ELMLibrary) -> ELMExpressionVisitor:
    """A visitor bound to the fixture library."""
    bound = ELMExpressionVisitor(CQLContext())
    bound.set_library(library)
    return bound


class TestExpressionReferences:
    """ExpressionRef resolution, caching and error paths."""

    def test_expression_ref_resolves_a_definition(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "ExpressionRef", "name": "Base"}) == 10

    def test_expression_ref_result_is_cached_for_reuse(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Add",
            "operand": [{"type": "ExpressionRef", "name": "Base"}, {"type": "ExpressionRef", "name": "Base"}],
        }
        assert visitor.evaluate(node) == 20
        found, cached = visitor.context.get_cached_definition("Base")
        assert (found, cached) == (True, 10)

    @pytest.mark.parametrize(
        ("node", "message"),
        [
            ({"type": "ExpressionRef"}, "Expression reference missing name"),
            ({"type": "ExpressionRef", "name": "Ghost"}, "Definition not found: Ghost"),
            ({"type": "ExpressionRef", "name": "Base", "libraryName": "Other"}, "Included library 'Other' not found"),
        ],
    )
    def test_expression_ref_errors(self, visitor: ELMExpressionVisitor, node: dict[str, Any], message: str) -> None:
        with pytest.raises(ELMExecutionError, match=message):
            visitor.evaluate(node)

    def test_expression_ref_without_a_library_is_an_error(self) -> None:
        unbound = ELMExpressionVisitor(CQLContext())
        with pytest.raises(ELMExecutionError, match="No library context for expression reference"):
            unbound.evaluate({"type": "ExpressionRef", "name": "Base"})


class TestFunctionReferences:
    """FunctionRef resolution, built-ins and error paths."""

    def test_function_ref_binds_operands(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "FunctionRef", "name": "Doubler", "operand": [integer(21)]}
        assert visitor.evaluate(node) == 42

    @pytest.mark.parametrize(
        ("name", "argument", "expected"),
        [("ToString", integer(7), "7"), ("ToInteger", string("7"), 7)],
    )
    def test_built_in_functions_bypass_the_library(
        self, visitor: ELMExpressionVisitor, name: str, argument: dict[str, Any], expected: Any
    ) -> None:
        assert visitor.evaluate({"type": "FunctionRef", "name": name, "operand": [argument]}) == expected

    def test_built_in_to_decimal(self, visitor: ELMExpressionVisitor) -> None:
        result = visitor.evaluate({"type": "FunctionRef", "name": "ToDecimal", "operand": [string("7.5")]})
        assert str(result) == "7.5"

    @pytest.mark.parametrize(
        ("node", "message"),
        [
            ({"type": "FunctionRef"}, "Function reference missing name"),
            ({"type": "FunctionRef", "name": "Ghost", "operand": []}, "Function not found: Ghost"),
            ({"type": "FunctionRef", "name": "Ext", "operand": [integer(1)]}, "External function not implemented"),
            (
                {"type": "FunctionRef", "name": "Doubler", "libraryName": "Other", "operand": [integer(1)]},
                "Included library 'Other' not found",
            ),
        ],
    )
    def test_function_ref_errors(self, visitor: ELMExpressionVisitor, node: dict[str, Any], message: str) -> None:
        with pytest.raises(ELMExecutionError, match=message):
            visitor.evaluate(node)

    def test_function_ref_without_a_library_is_an_error(self) -> None:
        unbound = ELMExpressionVisitor(CQLContext())
        node = {"type": "FunctionRef", "name": "Doubler", "operand": []}
        with pytest.raises(ELMExecutionError, match="No library context for function reference"):
            unbound.evaluate(node)


class TestOtherReferences:
    """Parameter, operand, alias and identifier references."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("Threshold", 10), ("NoDefault", None), ("Ghost", None)],
    )
    def test_parameter_ref(self, visitor: ELMExpressionVisitor, name: str, expected: int | None) -> None:
        assert visitor.evaluate({"type": "ParameterRef", "name": name}) == expected

    def test_parameter_ref_prefers_a_context_value(self, visitor: ELMExpressionVisitor) -> None:
        visitor.context.set_parameter("Threshold", 99)
        assert visitor.evaluate({"type": "ParameterRef", "name": "Threshold"}) == 99

    def test_operand_ref_reads_a_bound_alias(self, visitor: ELMExpressionVisitor) -> None:
        visitor.context.set_alias("x", 5)
        assert visitor.evaluate({"type": "OperandRef", "name": "x"}) == 5

    def test_operand_ref_unbound_is_null(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "OperandRef", "name": "x"}) is None

    def test_identifier_ref_prefers_an_alias(self, visitor: ELMExpressionVisitor) -> None:
        visitor.context.set_alias("Base", 1)
        assert visitor.evaluate({"type": "IdentifierRef", "name": "Base"}) == 1

    def test_identifier_ref_falls_back_to_a_parameter(self, visitor: ELMExpressionVisitor) -> None:
        visitor.context.set_parameter("Threshold", 3)
        assert visitor.evaluate({"type": "IdentifierRef", "name": "Threshold"}) == 3

    def test_identifier_ref_falls_back_to_a_definition(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "IdentifierRef", "name": "Base"}) == 10

    def test_identifier_ref_without_a_library_is_an_error(self) -> None:
        unbound = ELMExpressionVisitor(CQLContext())
        with pytest.raises(ELMExecutionError, match="Identifier not found: Base"):
            unbound.evaluate({"type": "IdentifierRef", "name": "Base"})

    @pytest.mark.parametrize(
        ("node", "message"),
        [
            ({"type": "ParameterRef"}, "Parameter reference missing name"),
            ({"type": "OperandRef"}, "Operand reference missing name"),
            ({"type": "AliasRef"}, "Alias reference missing name"),
            ({"type": "QueryLetRef"}, "Query let reference missing name"),
            ({"type": "IdentifierRef"}, "Identifier reference missing name"),
        ],
    )
    def test_reference_without_a_name_is_an_error(
        self, visitor: ELMExpressionVisitor, node: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(ELMExecutionError, match=message):
            visitor.evaluate(node)

    def test_query_let_ref_reads_an_alias(self, visitor: ELMExpressionVisitor) -> None:
        visitor.context.set_alias("d", 8)
        assert visitor.evaluate({"type": "QueryLetRef", "name": "d"}) == 8


class TestIncludedLibraries:
    """Qualified references into included libraries."""

    @pytest.fixture
    def helper(self) -> ELMLibrary:
        return ELMLoader.parse(
            {
                "library": {
                    "identifier": {"id": "Helpers", "version": "1.0"},
                    "statements": {
                        "def": [
                            {"name": "Ten", "expression": integer(10)},
                            {
                                "name": "Triple",
                                "type": "FunctionDef",
                                "operand": [{"name": "x"}],
                                "expression": {
                                    "type": "Multiply",
                                    "operand": [{"type": "OperandRef", "name": "x"}, integer(3)],
                                },
                            },
                        ]
                    },
                }
            }
        )

    def test_register_and_read_back_an_included_library(
        self, visitor: ELMExpressionVisitor, helper: ELMLibrary
    ) -> None:
        visitor.add_included_library("H", helper)
        assert visitor.get_included_library("H") is helper
        assert visitor.get_included_library("Missing") is None

    def test_qualified_expression_ref_reads_the_included_library(
        self, visitor: ELMExpressionVisitor, helper: ELMLibrary
    ) -> None:
        visitor.add_included_library("H", helper)
        assert visitor.evaluate({"type": "ExpressionRef", "name": "Ten", "libraryName": "H"}) == 10

    def test_qualified_function_ref_reads_the_included_library(
        self, visitor: ELMExpressionVisitor, helper: ELMLibrary
    ) -> None:
        visitor.add_included_library("H", helper)
        node = {"type": "FunctionRef", "name": "Triple", "libraryName": "H", "operand": [integer(4)]}
        assert visitor.evaluate(node) == 12

    def test_the_local_library_is_restored_after_a_qualified_reference(
        self, visitor: ELMExpressionVisitor, helper: ELMLibrary
    ) -> None:
        visitor.add_included_library("H", helper)
        visitor.evaluate({"type": "ExpressionRef", "name": "Ten", "libraryName": "H"})
        assert visitor.evaluate({"type": "ExpressionRef", "name": "Base"}) == 10

    def test_clearing_drops_every_included_library(self, visitor: ELMExpressionVisitor, helper: ELMLibrary) -> None:
        visitor.add_included_library("H", helper)
        visitor.clear_included_libraries()
        assert visitor.get_included_library("H") is None


class TestQueries:
    """Query sources, clauses and aggregation."""

    @pytest.fixture
    def visitor(self) -> ELMExpressionVisitor:
        return ELMExpressionVisitor(CQLContext())

    def test_query_returns_its_source_items(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(elm_list(integer(1), integer(2), integer(3)))
        assert visitor.evaluate(node) == [1, 2, 3]

    def test_query_without_sources_is_empty(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "Query", "source": []}) == []

    @pytest.mark.parametrize("source", [elm_list(), NULL])
    def test_query_over_an_empty_source_is_empty(self, visitor: ELMExpressionVisitor, source: dict[str, Any]) -> None:
        assert visitor.evaluate(query_over(source)) == []

    def test_query_promotes_a_scalar_source(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate(query_over(integer(5))) == [5]

    def test_query_where_filters_items(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(
            elm_list(integer(1), integer(2), integer(3)),
            where={"type": "Greater", "operand": [alias("N"), integer(1)]},
        )
        assert visitor.evaluate(node) == [2, 3]

    def test_query_return_shapes_each_item(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(
            elm_list(integer(1), integer(2)),
            **{"return": {"expression": {"type": "Multiply", "operand": [alias("N"), integer(10)]}}},
        )
        assert visitor.evaluate(node) == [10, 20]

    def test_query_return_is_distinct_by_default(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(elm_list(integer(1), integer(1)), **{"return": {"expression": alias("N")}})
        assert visitor.evaluate(node) == [1]

    def test_query_let_binds_a_named_expression(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(
            elm_list(integer(1), integer(2)),
            let=[{"identifier": "d", "expression": {"type": "Multiply", "operand": [alias("N"), integer(2)]}}],
            **{"return": {"expression": {"type": "QueryLetRef", "name": "d"}}},
        )
        assert visitor.evaluate(node) == [2, 4]

    def test_query_over_two_sources_walks_the_cross_product(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Query",
            "source": [
                {"alias": "A", "expression": elm_list(integer(1), integer(2))},
                {"alias": "B", "expression": elm_list(integer(10), integer(20))},
            ],
            "return": {"expression": {"type": "Add", "operand": [alias("A"), alias("B")]}},
        }
        assert visitor.evaluate(node) == [11, 21, 12, 22]

    @pytest.mark.parametrize(
        ("direction", "expected"),
        [("asc", [1, 2, 3]), ("ascending", [1, 2, 3]), ("desc", [3, 2, 1]), ("descending", [3, 2, 1])],
    )
    def test_query_sort_orders_the_results(
        self, visitor: ELMExpressionVisitor, direction: str, expected: list[int]
    ) -> None:
        node = query_over(elm_list(integer(3), integer(1), integer(2)), sort={"by": [{"direction": direction}]})
        assert visitor.evaluate(node) == expected

    def test_query_sort_without_keys_keeps_the_source_order(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(elm_list(integer(3), integer(1)), sort={"by": []})
        assert visitor.evaluate(node) == [3, 1]

    def test_query_sort_by_expression(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(
            elm_list(integer(3), integer(1)),
            sort={"by": [{"expression": alias("$this"), "direction": "asc"}]},
        )
        assert visitor.evaluate(node) == [1, 3]

    def test_query_sort_by_path(self, visitor: ELMExpressionVisitor) -> None:
        left = {"type": "Instance", "classType": "Row", "element": [{"name": "rank", "value": integer(2)}]}
        right = {"type": "Instance", "classType": "Row", "element": [{"name": "rank", "value": integer(1)}]}
        node = query_over(elm_list(left, right), sort={"by": [{"path": "rank", "direction": "asc"}]})
        assert visitor.evaluate(node) == [{"resourceType": "Row", "rank": 1}, {"resourceType": "Row", "rank": 2}]

    def test_query_aggregate_accumulates(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(
            elm_list(integer(1), integer(2), integer(3)),
            aggregate={
                "identifier": "T",
                "starting": integer(0),
                "expression": {"type": "Add", "operand": [alias("T"), alias("N")]},
            },
        )
        assert visitor.evaluate(node) == 6

    def test_query_aggregate_distinct_folds_duplicates_first(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(
            elm_list(integer(1), integer(1), integer(3)),
            aggregate={
                "identifier": "T",
                "distinct": True,
                "starting": integer(0),
                "expression": {"type": "Add", "operand": [alias("T"), alias("N")]},
            },
        )
        assert visitor.evaluate(node) == 4

    def test_query_aggregate_without_an_identifier_returns_the_rows(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(elm_list(integer(1)), aggregate={"starting": integer(0)})
        assert visitor.evaluate(node) == [1]

    def test_query_aggregate_without_an_expression_returns_the_starting_value(
        self, visitor: ELMExpressionVisitor
    ) -> None:
        node = query_over(elm_list(integer(1)), aggregate={"identifier": "T", "starting": integer(9)})
        assert visitor.evaluate(node) == 9

    def test_query_aggregate_over_an_empty_source_returns_the_starting_value(
        self, visitor: ELMExpressionVisitor
    ) -> None:
        node = query_over(
            elm_list(),
            aggregate={"identifier": "T", "starting": integer(7), "expression": alias("T")},
        )
        assert visitor.evaluate(node) == 7

    def test_query_aggregate_without_a_starting_value_begins_at_null(self, visitor: ELMExpressionVisitor) -> None:
        node = query_over(elm_list(integer(1)), aggregate={"identifier": "T", "expression": alias("T")})
        assert visitor.evaluate(node) is None

    def test_query_with_keeps_rows_that_have_a_match(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Query",
            "source": [{"alias": "A", "expression": elm_list(integer(1), integer(2))}],
            "relationship": [
                {
                    "type": "With",
                    "alias": "B",
                    "expression": elm_list(integer(2)),
                    "suchThat": {"type": "Equal", "operand": [alias("A"), alias("B")]},
                }
            ],
        }
        assert visitor.evaluate(node) == [2]

    def test_query_with_a_bare_relationship_keeps_rows_when_the_other_side_is_non_empty(
        self, visitor: ELMExpressionVisitor
    ) -> None:
        node = {
            "type": "Query",
            "source": [{"alias": "A", "expression": elm_list(integer(1))}],
            "relationship": [{"type": "With", "alias": "B", "expression": elm_list(integer(9))}],
        }
        assert visitor.evaluate(node) == [1]

    def test_query_with_an_empty_relationship_drops_every_row(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Query",
            "source": [{"alias": "A", "expression": elm_list(integer(1))}],
            "relationship": [
                {"type": "With", "alias": "B", "expression": NULL, "suchThat": boolean(True)},
            ],
        }
        assert visitor.evaluate(node) == []

    def test_query_without_a_bare_relationship_drops_matching_rows(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Query",
            "source": [{"alias": "A", "expression": elm_list(integer(1))}],
            "relationship": [{"type": "Without", "alias": "B", "expression": elm_list(integer(9))}],
        }
        assert visitor.evaluate(node) == []

    def test_query_without_a_bare_relationship_keeps_rows_when_the_other_side_is_empty(
        self, visitor: ELMExpressionVisitor
    ) -> None:
        node = {
            "type": "Query",
            "source": [{"alias": "A", "expression": elm_list(integer(1))}],
            "relationship": [{"type": "Without", "alias": "B", "expression": elm_list()}],
        }
        assert visitor.evaluate(node) == [1]


class TestRetrieve:
    """Retrieve delegates to the context data source."""

    def test_retrieve_without_a_data_source_is_empty(self) -> None:
        visitor = ELMExpressionVisitor(CQLContext())
        assert visitor.evaluate({"type": "Retrieve", "dataType": "{http://hl7.org/fhir}Patient"}) == []

    def test_retrieve_passes_the_local_resource_name_and_filters(self) -> None:
        data_source = RecordingDataSource()
        visitor = ELMExpressionVisitor(CQLContext(data_source=data_source))
        node = {
            "type": "Retrieve",
            "dataType": "{http://hl7.org/fhir}Observation",
            "codeProperty": "code",
            "codes": string("x"),
            "dateProperty": "effective",
            "dateRange": {"type": "Interval", "low": integer(1), "high": integer(2)},
        }
        assert visitor.evaluate(node) == [{"resourceType": "Observation", "id": "r1"}]
        assert data_source.calls == [
            RetrieveCall(
                resource_type="Observation",
                code_path="code",
                codes=["x"],
                date_path="effective",
                date_range=CQLInterval(low=1, high=2),
            )
        ]

    def test_retrieve_accepts_an_unqualified_data_type(self) -> None:
        data_source = RecordingDataSource()
        visitor = ELMExpressionVisitor(CQLContext(data_source=data_source))
        assert visitor.evaluate({"type": "Retrieve", "dataType": "Patient"}) == [
            {"resourceType": "Patient", "id": "r1"}
        ]
        assert data_source.calls[0].resource_type == "Patient"

    def test_retrieve_wraps_a_scalar_code_filter_in_a_list(self) -> None:
        data_source = RecordingDataSource()
        visitor = ELMExpressionVisitor(CQLContext(data_source=data_source))
        node = {"type": "Retrieve", "dataType": "Observation", "codes": elm_list(string("a"), string("b"))}
        visitor.evaluate(node)
        assert data_source.calls[0].codes == ["a", "b"]

    def test_in_value_set_asks_the_data_source(self) -> None:
        data_source = RecordingDataSource(members=["http://example.org/vs/diabetes"])
        visitor = ELMExpressionVisitor(CQLContext(data_source=data_source))
        visitor.set_library(
            ELMLoader.parse(
                {
                    "library": {
                        "identifier": {"id": "T"},
                        "valueSets": [{"name": "Diabetes", "id": "http://example.org/vs/diabetes"}],
                    }
                }
            )
        )
        node = {
            "type": "InValueSet",
            "code": {"type": "Code", "code": "c", "system": string("s")},
            "valuesetRef": {"name": "Diabetes"},
        }
        assert visitor.evaluate(node) is True

    def test_in_value_set_reports_a_non_member(self) -> None:
        data_source = RecordingDataSource(members=[])
        visitor = ELMExpressionVisitor(CQLContext(data_source=data_source))
        node = {
            "type": "InValueSet",
            "code": {"type": "Code", "code": "c", "system": string("s")},
            "valueset": string("http://example.org/vs/other"),
        }
        assert visitor.evaluate(node) is False


class TestEvaluatorLoading:
    """ELMEvaluator.load accepts dicts, JSON strings, paths and files."""

    def test_load_from_a_dict(self) -> None:
        evaluator = ELMEvaluator()
        loaded = evaluator.load(LIBRARY_SOURCE)
        assert loaded.identifier.id == "Fixture"
        assert evaluator.current_library is loaded

    def test_load_from_a_json_string(self) -> None:
        evaluator = ELMEvaluator()
        assert evaluator.load(json.dumps(LIBRARY_SOURCE)).identifier.id == "Fixture"

    def test_load_from_a_path(self, tmp_path: Path) -> None:
        elm_file = tmp_path / "library.json"
        elm_file.write_text(json.dumps(LIBRARY_SOURCE), encoding="utf-8")
        assert ELMEvaluator().load(elm_file).identifier.id == "Fixture"

    def test_load_file_from_a_string_path(self, tmp_path: Path) -> None:
        elm_file = tmp_path / "library.json"
        elm_file.write_text(json.dumps(LIBRARY_SOURCE), encoding="utf-8")
        assert ELMEvaluator().load_file(str(elm_file)).identifier.id == "Fixture"

    def test_load_from_a_path_shaped_string(self, tmp_path: Path) -> None:
        elm_file = tmp_path / "library.json"
        elm_file.write_text(json.dumps(LIBRARY_SOURCE), encoding="utf-8")
        assert ELMEvaluator().load(str(elm_file)).identifier.id == "Fixture"

    def test_load_of_a_non_existent_path_is_treated_as_json(self) -> None:
        with pytest.raises(ELMValidationError, match="Invalid JSON"):
            ELMEvaluator().load("no/such/library.json")

    def test_load_rejects_an_unsupported_source_type(self) -> None:
        with pytest.raises(ELMValidationError, match="Unsupported source type"):
            ELMEvaluator().load(123)  # type: ignore[arg-type]

    def test_load_registers_the_library_under_its_versioned_key(self) -> None:
        evaluator = ELMEvaluator()
        evaluator.load(LIBRARY_SOURCE)
        assert evaluator.get_elm_library("Fixture", "1.0") is evaluator.current_library
        assert evaluator.get_elm_library("Fixture") is evaluator.current_library
        assert evaluator.get_elm_library("Fixture", "9.9") is None
        assert evaluator.get_elm_library("Ghost") is None

    def test_load_registers_an_unversioned_library_under_its_bare_name(self) -> None:
        evaluator = ELMEvaluator()
        evaluator.load({"library": {"identifier": {"id": "Bare"}}})
        assert evaluator.get_elm_library("Bare") is not None

    def test_library_manager_is_exposed(self) -> None:
        evaluator = ELMEvaluator()
        assert evaluator.library_manager is not None


class TestEvaluatorDefinitions:
    """Evaluating definitions and functions through the evaluator."""

    @pytest.fixture
    def evaluator(self) -> ELMEvaluator:
        evaluator = ELMEvaluator()
        evaluator.load(LIBRARY_SOURCE)
        return evaluator

    def test_definition_uses_the_library_parameter_default(self) -> None:
        evaluator = ELMEvaluator()
        evaluator.load(
            {
                "library": {
                    "identifier": {"id": "Params"},
                    "parameters": [{"name": "Factor", "default": integer(3)}],
                    "statements": {
                        "def": [
                            {
                                "name": "Scaled",
                                "expression": {
                                    "type": "Multiply",
                                    "operand": [{"type": "ParameterRef", "name": "Factor"}, integer(2)],
                                },
                            }
                        ]
                    },
                }
            }
        )
        assert evaluator.evaluate_definition("Scaled") == 6
        assert evaluator.evaluate_definition("Scaled", parameters={"Factor": 5}) == 10

    def test_definition_reads_the_context_resource(self) -> None:
        evaluator = ELMEvaluator()
        evaluator.load(
            {
                "library": {
                    "identifier": {"id": "Res"},
                    "statements": {"def": [{"name": "Birth", "expression": {"type": "Property", "path": "birthDate"}}]},
                }
            }
        )
        resource = {"resourceType": "Patient", "birthDate": "2000-01-01"}
        assert evaluator.evaluate_definition("Birth", resource=resource) == "2000-01-01"

    def test_definition_without_an_expression_is_null(self) -> None:
        evaluator = ELMEvaluator()
        evaluator.load(
            {"library": {"identifier": {"id": "E"}, "statements": {"def": [{"name": "Empty", "expression": None}]}}}
        )
        assert evaluator.evaluate_definition("Empty") is None

    def test_evaluate_definition_falls_back_to_a_function(self, evaluator: ELMEvaluator) -> None:
        assert evaluator.evaluate_definition("Doubler") is None

    @pytest.mark.parametrize(
        ("name", "message"),
        [("Ext", "External function not implemented"), ("NoBody", "Function has no expression")],
    )
    def test_unusable_functions_raise(self, evaluator: ELMEvaluator, name: str, message: str) -> None:
        with pytest.raises(ELMExecutionError, match=message):
            evaluator.evaluate_definition(name)

    def test_evaluate_definition_accepts_an_explicit_library(self, evaluator: ELMEvaluator) -> None:
        other = ELMLoader.parse(
            {
                "library": {
                    "identifier": {"id": "Other"},
                    "statements": {"def": [{"name": "Nine", "expression": integer(9)}]},
                }
            }
        )
        assert evaluator.evaluate_definition("Nine", library=other) == 9

    def test_evaluate_all_definitions_collects_errors(self, evaluator: ELMEvaluator) -> None:
        results = evaluator.evaluate_all_definitions()
        assert results["Base"] == 10
        assert "Secret" not in results
        assert "Unsupported expression type: NotARealType" in results["_errors"]["Broken"]

    def test_evaluate_all_definitions_can_include_private_ones(self, evaluator: ELMEvaluator) -> None:
        assert evaluator.evaluate_all_definitions(include_private=True)["Secret"] == 1

    def test_definition_names_skip_private_definitions_by_default(self, evaluator: ELMEvaluator) -> None:
        assert evaluator.get_definition_names() == ["Base", "Broken"]
        assert evaluator.get_definition_names(include_private=True) == ["Base", "Secret", "Broken"]

    def test_function_names(self, evaluator: ELMEvaluator) -> None:
        assert evaluator.get_function_names() == ["Doubler", "Ext", "NoBody"]

    def test_function_names_skip_private_functions(self) -> None:
        evaluator = ELMEvaluator()
        evaluator.load(
            {
                "library": {
                    "identifier": {"id": "P"},
                    "statements": {
                        "def": [
                            {"name": "Hidden", "type": "FunctionDef", "accessLevel": "Private", "operand": []},
                            {"name": "Shown", "type": "FunctionDef", "operand": []},
                        ]
                    },
                }
            }
        )
        assert evaluator.get_function_names() == ["Shown"]
        assert evaluator.get_function_names(include_private=True) == ["Hidden", "Shown"]

    def test_definition_not_found(self, evaluator: ELMEvaluator) -> None:
        with pytest.raises(ELMReferenceError, match="Definition not found: Ghost"):
            evaluator.evaluate_definition("Ghost")

    def test_evaluate_all_definitions_without_a_library(self) -> None:
        with pytest.raises(ELMExecutionError, match="No ELM library loaded"):
            ELMEvaluator().evaluate_all_definitions()

    def test_names_without_a_library_are_empty(self) -> None:
        evaluator = ELMEvaluator()
        assert evaluator.get_definition_names() == []
        assert evaluator.get_function_names() == []
        assert evaluator.get_library_info() == {}


class TestEvaluatorLibraryInfo:
    """The library summary the evaluator reports."""

    def test_info_lists_every_section(self) -> None:
        evaluator = ELMEvaluator()
        evaluator.load(
            {
                "library": {
                    "identifier": {"id": "Full", "version": "2.0"},
                    "schemaIdentifier": {"id": "urn:hl7-org:elm", "version": "r1"},
                    "usings": [{"localIdentifier": "FHIR", "uri": "http://hl7.org/fhir", "version": "4.0.1"}],
                    "includes": [{"localIdentifier": "H", "path": "Helpers", "version": "1.0"}],
                    "parameters": [{"name": "P"}],
                    "codeSystems": [{"name": "LOINC", "id": "http://loinc.org"}],
                    "valueSets": [{"name": "VS", "id": "http://example.org/vs"}],
                    "codes": [{"name": "C", "id": "1", "codeSystem": {"name": "LOINC"}}],
                    "concepts": [{"name": "K", "code": [{"name": "C"}]}],
                    "statements": {
                        "def": [
                            {"name": "One", "expression": integer(1)},
                            {"name": "Fn", "type": "FunctionDef", "operand": []},
                        ]
                    },
                }
            }
        )
        info = evaluator.get_library_info()
        assert info["id"] == "Full"
        assert info["version"] == "2.0"
        assert info["schemaIdentifier"] == {"id": "urn:hl7-org:elm", "version": "r1"}
        assert info["usings"] == [{"localIdentifier": "FHIR", "uri": "http://hl7.org/fhir", "version": "4.0.1"}]
        assert info["includes"] == [{"localIdentifier": "H", "path": "Helpers", "version": "1.0"}]
        assert info["parameters"] == ["P"]
        assert info["codeSystems"] == ["LOINC"]
        assert info["valueSets"] == ["VS"]
        assert info["codes"] == ["C"]
        assert info["concepts"] == ["K"]
        assert info["definitions"] == ["One"]
        assert info["functions"] == ["Fn"]

    def test_info_without_a_schema_identifier(self) -> None:
        evaluator = ELMEvaluator()
        evaluator.load(LIBRARY_SOURCE)
        assert evaluator.get_library_info()["schemaIdentifier"] is None


class TestEvaluatorValidation:
    """The validate() front door onto ELMLoader.validate."""

    def test_valid_dict(self) -> None:
        is_valid, errors = ELMEvaluator().validate(LIBRARY_SOURCE)
        assert (is_valid, errors) == (True, [])

    def test_missing_identifier(self) -> None:
        is_valid, errors = ELMEvaluator().validate({"library": {}})
        assert is_valid is False
        assert errors == ["Missing required 'identifier' field"]

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"library": {"identifier": "Fixture"}}, ["'identifier' must be an object"]),
            ({"library": {"identifier": {}}}, ["Missing required 'identifier.id' field"]),
            (
                {"library": {"identifier": {"id": "X"}, "schemaIdentifier": {"id": "urn:other"}}},
                ["Unexpected schema identifier: urn:other"],
            ),
            (
                {"library": {"identifier": {"id": "X"}, "statements": {"def": "nope"}}},
                ["'statements.def' must be an array"],
            ),
            (
                {"library": {"identifier": {"id": "X"}, "statements": {"def": ["nope"]}}},
                ["Statement 0 must be an object"],
            ),
            (
                {"library": {"identifier": {"id": "X"}, "statements": {"def": [{"expression": {}}]}}},
                ["Statement 0 missing 'name' field"],
            ),
        ],
    )
    def test_structural_errors(self, payload: dict[str, Any], expected: list[str]) -> None:
        is_valid, errors = ELMEvaluator().validate(payload)
        assert is_valid is False
        assert errors == expected

    def test_validate_a_json_string(self) -> None:
        is_valid, errors = ELMEvaluator().validate(json.dumps({"library": {"identifier": {"id": "X"}}}))
        assert (is_valid, errors) == (True, [])

    def test_validate_a_file(self, tmp_path: Path) -> None:
        elm_file = tmp_path / "library.json"
        elm_file.write_text(json.dumps(LIBRARY_SOURCE), encoding="utf-8")
        assert ELMEvaluator().validate(elm_file) == (True, [])
        assert ELMEvaluator().validate(str(elm_file)) == (True, [])

    def test_validate_reports_unparseable_input(self) -> None:
        is_valid, errors = ELMEvaluator().validate("not json")
        assert is_valid is False
        assert len(errors) == 1


class TestLoader:
    """ELMLoader file and JSON entry points."""

    def test_load_file_reports_a_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ELMValidationError, match="ELM file not found"):
            ELMLoader.load_file(tmp_path / "absent.json")

    def test_load_file_reports_invalid_json(self, tmp_path: Path) -> None:
        elm_file = tmp_path / "broken.json"
        elm_file.write_text("{ not json", encoding="utf-8")
        with pytest.raises(ELMValidationError, match="Invalid JSON"):
            ELMLoader.load_file(elm_file)

    def test_load_file_reports_a_structural_problem(self, tmp_path: Path) -> None:
        elm_file = tmp_path / "empty.json"
        elm_file.write_text("{}", encoding="utf-8")
        with pytest.raises(ELMValidationError, match="missing required 'identifier'"):
            ELMLoader.load_file(elm_file)

    def test_parse_accepts_an_unwrapped_library(self) -> None:
        assert ELMLoader.parse({"identifier": {"id": "Unwrapped"}}).identifier.id == "Unwrapped"

    def test_parse_reports_a_model_error(self) -> None:
        with pytest.raises(ELMValidationError, match="Error parsing ELM library"):
            ELMLoader.parse({"library": {"identifier": {"id": "X"}, "usings": "nope"}})

    def test_validate_allows_a_statement_without_an_expression(self) -> None:
        payload = {"library": {"identifier": {"id": "X"}, "statements": {"def": [{"name": "Ext"}]}}}
        assert ELMLoader.validate(payload) == []

    def test_library_info_counts_each_section(self) -> None:
        info = ELMLoader.get_library_info(LIBRARY_SOURCE)
        assert info["id"] == "Fixture"
        assert info["version"] == "1.0"
        assert info["parameters"] == 2
        assert info["definitions"] == 6
        assert info["functions"] == 3
        assert info["expressions"] == 3

    def test_library_info_of_an_empty_library(self) -> None:
        info = ELMLoader.get_library_info({"library": {}})
        assert info["id"] == "Unknown"
        assert info["version"] is None
        assert info["definitions"] == 0


class TestLibraryLookups:
    """The lookup helpers on ELMLibrary."""

    def test_lookups_on_a_library_without_statements(self) -> None:
        library = ELMLoader.parse({"library": {"identifier": {"id": "Bare"}}})
        assert library.get_definition("X") is None
        assert library.get_function("X") is None
        assert library.get_definitions() == []
        assert library.get_functions() == []

    def test_terminology_lookups(self) -> None:
        library = ELMLoader.parse(
            {
                "library": {
                    "identifier": {"id": "Term"},
                    "codeSystems": [{"name": "LOINC", "id": "http://loinc.org"}],
                    "valueSets": [{"name": "VS", "id": "http://example.org/vs"}],
                    "codes": [{"name": "C", "id": "1", "codeSystem": {"name": "LOINC"}}],
                    "concepts": [{"name": "K", "code": [{"name": "C"}]}],
                }
            }
        )
        assert library.get_codesystem("LOINC") is not None
        assert library.get_codesystem("Ghost") is None
        assert library.get_valueset("VS") is not None
        assert library.get_valueset("Ghost") is None
        assert library.get_code("C") is not None
        assert library.get_code("Ghost") is None
        assert library.get_concept("K") is not None
        assert library.get_concept("Ghost") is None

    def test_parameter_lookup(self, library: ELMLibrary) -> None:
        assert library.get_parameter("Threshold") is not None
        assert library.get_parameter("Ghost") is None

    def test_code_ref_without_a_code_system_yields_an_empty_system(self) -> None:
        library = ELMLoader.parse(
            {
                "library": {
                    "identifier": {"id": "Orphan"},
                    "codes": [{"name": "C", "id": "1", "codeSystem": {"name": "Missing"}}],
                }
            }
        )
        visitor = ELMExpressionVisitor(CQLContext())
        visitor.set_library(library)
        assert visitor.evaluate({"type": "CodeRef", "name": "C"}) == CQLCode(code="1", system="")
