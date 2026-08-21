"""Tests for CQL query clauses, library declarations, and retrieve expressions.

These drive `CQLEvaluatorVisitor` through whole libraries so the declaration visitors
(parameter, codesystem, valueset, code, concept, context, function) and the query-clause
helpers (source, let, where, return, sort, aggregate, with, without) all execute.
"""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_engine.engine.cql import (
    CQLCode,
    CQLConcept,
    CQLContext,
    CQLEvaluator,
    CQLInterval,
    CQLTuple,
    InMemoryLibraryResolver,
)
from dhis2w_fhir_engine.engine.exceptions import CQLError
from dhis2w_fhir_engine.engine.types import Quantity


class RetrieveCall(BaseModel):
    """One recorded call into the data source."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    resource_type: str
    code_path: str | None
    codes: list[Any] | None
    valueset: str | None


class RecordingDataSource:
    """Data source that records every retrieve and serves resources from a fixed map."""

    def __init__(self, resources: dict[str, list[dict[str, Any]]] | None = None) -> None:
        """Store the canned resources and start an empty call log."""
        self.resources = resources or {}
        self.calls: list[RetrieveCall] = []

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
        """Record the retrieve arguments and return the canned resources for the type."""
        self.calls.append(
            RetrieveCall(resource_type=resource_type, code_path=code_path, codes=codes, valueset=valueset)
        )
        return self.resources.get(resource_type, [])

    def resolve_reference(self, reference: str) -> dict[str, Any] | None:
        """Resolve nothing; these tests never follow references."""
        return None


@pytest.fixture
def evaluator() -> CQLEvaluator:
    """Create a CQL evaluator."""
    return CQLEvaluator()


class TestParameterDeclarations:
    """`parameter` declarations carry a name, an optional type, and an optional default."""

    def test_declarations_land_in_the_library(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile("""
            library Params version '1.0'
            parameter MeasurementPeriod Interval<Integer> default Interval[1, 10]
            parameter Threshold default 5
            parameter Untyped Integer
            define UsesParameter: Threshold + 1
        """)

        assert set(library.parameters) == {"MeasurementPeriod", "Threshold", "Untyped"}
        assert library.parameters["MeasurementPeriod"].default_value == CQLInterval(low=1, high=10)
        assert library.parameters["MeasurementPeriod"].type_specifier == "Interval<Integer>"
        assert library.parameters["Threshold"].default_value == 5
        assert library.parameters["Threshold"].type_specifier is None
        assert library.parameters["Untyped"].default_value is None
        assert library.parameters["Untyped"].type_specifier == "Integer"

    def test_a_default_is_visible_to_definitions(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Params version '1.0'
            parameter Threshold default 5
            define UsesParameter: Threshold + 1
        """)
        assert evaluator.evaluate_definition("UsesParameter") == 6


TERMINOLOGY_LIBRARY = """
library Terms version '1.0'
codesystem SNOMED: 'http://snomed.info/sct' version 'v1'
codesystem LOINC: 'http://loinc.org'
valueset Diabetes: 'http://example.org/vs/diabetes' version 'v2'
valueset Combined: 'http://example.org/vs/combined' codesystems { SNOMED, LOINC }
code Headache: '25064002' from SNOMED display 'Headache'
code Fever: '386661006' from SNOMED
concept Symptoms: { Headache, Fever } display 'Symptoms'
define TheCode: Headache
define TheConcept: Symptoms
define InlineCode: Code '1234' from SNOMED display 'Inline'
define InlineConcept: Concept { Code '1' from SNOMED, Code '2' from LOINC } display 'Both'
"""


class TestTerminologyDeclarations:
    """`codesystem`, `valueset`, `code`, and `concept` declarations."""

    def test_codesystem_declarations(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile(TERMINOLOGY_LIBRARY)
        assert library.codesystems["SNOMED"].id == "http://snomed.info/sct"
        assert library.codesystems["SNOMED"].version == "v1"
        assert library.codesystems["LOINC"].id == "http://loinc.org"
        assert library.codesystems["LOINC"].version is None

    def test_valueset_declarations(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile(TERMINOLOGY_LIBRARY)
        assert library.valuesets["Diabetes"].id == "http://example.org/vs/diabetes"
        assert library.valuesets["Diabetes"].version == "v2"
        assert library.valuesets["Diabetes"].codesystems == []
        assert library.valuesets["Combined"].codesystems == ["SNOMED", "LOINC"]

    def test_code_declarations(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile(TERMINOLOGY_LIBRARY)
        assert library.codes["Headache"].code == "25064002"
        assert library.codes["Headache"].codesystem == "SNOMED"
        assert library.codes["Headache"].display == "Headache"
        assert library.codes["Fever"].display is None

    def test_concept_declaration(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile(TERMINOLOGY_LIBRARY)
        assert library.concepts["Symptoms"].codes == ["Headache", "Fever"]
        assert library.concepts["Symptoms"].display == "Symptoms"

    def test_declared_code_resolves_to_a_code_value(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile(TERMINOLOGY_LIBRARY)
        assert evaluator.evaluate_definition("TheCode") == CQLCode(
            code="25064002", system="http://snomed.info/sct", display="Headache"
        )

    def test_declared_concept_resolves_to_its_codes(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile(TERMINOLOGY_LIBRARY)
        assert evaluator.evaluate_definition("TheConcept") == CQLConcept(
            codes=(
                CQLCode(code="25064002", system="http://snomed.info/sct", display="Headache"),
                CQLCode(code="386661006", system="http://snomed.info/sct"),
            ),
            display="Symptoms",
        )

    def test_inline_code_selector(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile(TERMINOLOGY_LIBRARY)
        assert evaluator.evaluate_definition("InlineCode") == CQLCode(
            code="1234", system="http://snomed.info/sct", display="Inline"
        )

    def test_inline_concept_selector(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile(TERMINOLOGY_LIBRARY)
        assert evaluator.evaluate_definition("InlineConcept") == CQLConcept(
            codes=(
                CQLCode(code="1", system="http://snomed.info/sct"),
                CQLCode(code="2", system="http://loinc.org"),
            ),
            display="Both",
        )


class TestFunctionAndAccessDeclarations:
    """`define function`, access modifiers, and function invocation."""

    def test_function_declarations_land_in_the_library(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile("""
            library Funcs version '1.0'
            define function Doubled(value Integer): value * 2
            define function Add(a Integer, b Integer) returns Integer: a + b
        """)
        assert set(library.functions) == {"Doubled", "Add"}
        doubled = library.get_function("Doubled", 1)
        assert doubled is not None
        assert doubled.parameters == [("value", "Integer")]
        assert doubled.return_type is None
        added = library.get_function("Add", 2)
        assert added is not None
        assert added.parameters == [("a", "Integer"), ("b", "Integer")]
        assert added.return_type == "Integer"

    def test_single_parameter_function_call(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Funcs version '1.0'
            define function Doubled(value Integer): value * 2
            define UsesFunction: Doubled(21)
        """)
        assert evaluator.evaluate_definition("UsesFunction") == 42

    def test_two_parameter_function_call(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Funcs version '1.0'
            define function Add(a Integer, b Integer) returns Integer: a + b
            define UsesFunction: Add(2, 3)
        """)
        assert evaluator.evaluate_definition("UsesFunction") == 5

    def test_access_modifiers_are_recorded(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile("""
            library Access version '1.0'
            define private Hidden: 7
            define public Shown: 8
            define Plain: 9
        """)
        assert library.definitions["Hidden"].access_modifier == "private"
        assert library.definitions["Shown"].access_modifier == "public"
        assert library.definitions["Plain"].access_modifier is None

    def test_private_definitions_still_evaluate_inside_their_library(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Access version '1.0'
            define private Hidden: 7
            define Uses: Hidden + 1
        """)
        assert evaluator.evaluate_definition("Uses") == 8


class TestContextDeclarations:
    """`context Patient` and `context Unfiltered`."""

    def test_patient_context(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile("""
            library Ctx version '1.0'
            using FHIR version '4.0.1'
            context Patient
            define Anything: 1
        """)
        assert library.contexts == ["Patient"]
        assert library.current_context == "Patient"
        assert library.definitions["Anything"].context == "Patient"

    def test_unfiltered_context(self, evaluator: CQLEvaluator) -> None:
        library = evaluator.compile("""
            library Ctx version '1.0'
            using FHIR version '4.0.1'
            context Unfiltered
            define Anything: 2
        """)
        assert library.contexts == ["Unfiltered"]
        assert library.current_context == "Unfiltered"

    def test_the_context_name_resolves_to_the_context_resource(self, evaluator: CQLEvaluator) -> None:
        patient: dict[str, Any] = {"resourceType": "Patient", "id": "p1"}
        evaluator.compile("""
            library Ctx version '1.0'
            using FHIR version '4.0.1'
            context Patient
            define Subject: Patient
        """)
        assert evaluator.evaluate_definition("Subject", resource=patient) == patient


class TestIncludedLibraries:
    """`include ... called ...` exposes another library's definitions and functions."""

    def test_qualified_definition_and_function(self) -> None:
        resolver = InMemoryLibraryResolver(
            {
                "Helper": """
                library Helper version '1.0'
                define Answer: 42
                define function Doubled(value Integer): value * 2
                """
            }
        )
        evaluator = CQLEvaluator(library_resolver=resolver)
        library = evaluator.compile("""
            library Main version '1.0'
            include Helper version '1.0' called H
            define UsesDefinition: H.Answer
            define UsesFunction: H.Doubled(21)
            define MissingDefinition: H.Nope
        """)

        assert len(library.includes) == 1
        assert library.includes[0].library == "Helper"
        assert library.includes[0].version == "1.0"
        assert library.includes[0].alias == "H"
        assert evaluator.evaluate_definition("UsesDefinition") == 42
        assert evaluator.evaluate_definition("UsesFunction") == 42
        assert evaluator.evaluate_definition("MissingDefinition") is None


class TestQuerySources:
    """Single-source and multi-source `from` clauses."""

    def test_multi_source_cross_join(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("from ({1, 2}) A, ({10, 20}) B return A + B")
        assert result == [11, 21, 12, 22]

    def test_multi_source_with_where(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("from ({1, 2}) A, ({10, 20}) B where A = 1 return B")
        assert result == [10, 20]

    def test_single_source_without_return_unwraps_the_alias(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 3}) N where N > 1") == [2, 3]

    def test_query_over_a_named_definition(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Sources version '1.0'
            define Numbers: {1, 2, 3}
            define Large: Numbers N where N > 1 return N
        """)
        assert evaluator.evaluate_definition("Large") == [2, 3]

    def test_nested_query_in_the_return_clause(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({1, 2}) N return (({10, 20}) M return M + N)")
        assert result == [[11, 21], [12, 22]]


class TestLetClause:
    """`let` binds an extra name per row."""

    def test_single_let_binding(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 3}) N let doubled: N * 2 return doubled") == [2, 4, 6]

    def test_let_binding_used_by_where(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({1, 2, 3, 4, 5}) N let square: N * N where square > 10 return square")
        assert result == [16, 25]

    def test_two_let_bindings_chain(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({1, 2}) N let doubled: N * 2, tripled: doubled + N return tripled")
        assert result == [3, 6]


class TestSortClause:
    """`sort asc` / `sort desc` on the returned values."""

    def test_sort_ascending(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({5, 2, 8, 1}) N return N sort asc") == [1, 2, 5, 8]

    def test_sort_descending(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({5, 2, 8, 1}) N return N sort desc") == [8, 5, 2, 1]

    def test_sort_ascending_puts_nulls_last(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({3, 1, null, 2}) N return N sort asc") == [1, 2, 3, None]

    def test_sort_descending_puts_nulls_last(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({3, 1, null, 2}) N return N sort desc") == [3, 2, 1, None]

    def test_sort_leaves_unorderable_values_alone(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({Tuple { a: 2 }, Tuple { a: 1 }}) T return T sort asc")
        assert result == [CQLTuple(elements={"a": 2}), CQLTuple(elements={"a": 1})]

    def test_sort_by_a_constant_key_keeps_the_source_order(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({3, 1, 2}) N return N sort by 5") == [3, 1, 2]

    def test_sort_by_a_constant_key_descending_keeps_the_source_order(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({3, 1, 2}) N return N sort by 5 desc") == [3, 1, 2]


class TestSortByExpression:
    """`sort by <expression>` evaluates the expression against each element and orders by the answer."""

    def test_sort_by_this_orders_the_elements_themselves(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({3, 1, 2}) N return N sort by $this") == [1, 2, 3]

    def test_sort_by_this_descending(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({3, 1, 2}) N return N sort by $this desc") == [3, 2, 1]

    def test_sort_by_a_tuple_element(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression(
            "({Tuple { n: 3 }, Tuple { n: 1 }, Tuple { n: 2 }}) T return T sort by n"
        )
        assert [tuple_value.elements["n"] for tuple_value in result] == [1, 2, 3]

    def test_sort_by_a_tuple_element_descending(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression(
            "({Tuple { n: 3 }, Tuple { n: 1 }, Tuple { n: 2 }}) T return T sort by n desc"
        )
        assert [tuple_value.elements["n"] for tuple_value in result] == [3, 2, 1]

    def test_sort_by_a_resource_element(self) -> None:
        source = RecordingDataSource(
            {
                "Observation": [
                    {"resourceType": "Observation", "id": "o2", "issued": "2024-02-01"},
                    {"resourceType": "Observation", "id": "o1", "issued": "2024-01-01"},
                    {"resourceType": "Observation", "id": "o3", "issued": "2024-03-01"},
                ]
            }
        )
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile("""
            library Sorted version '1.0'
            using FHIR version '4.0.1'
            define Ordered: [Observation] O return O sort by issued
        """)
        assert [row["id"] for row in evaluator.evaluate_definition("Ordered")] == ["o1", "o2", "o3"]

    def test_two_sort_keys_break_ties_left_to_right(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression(
            "({Tuple { a: 2, b: 1 }, Tuple { a: 1, b: 2 }, Tuple { a: 1, b: 1 }}) T return T sort by a, b"
        )
        assert [(row.elements["a"], row.elements["b"]) for row in result] == [(1, 1), (1, 2), (2, 1)]

    def test_sort_by_an_expression_puts_nulls_last(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression(
            "({Tuple { n: 3 }, Tuple { m: 9 }, Tuple { n: 1 }}) T return T sort by n"
        )
        assert [row.elements.get("n") for row in result] == [1, 3, None]


class TestReturnClause:
    """`return`, `return all`, and `return distinct`."""

    def test_return_shapes_each_row(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 3}) N return N * 2") == [2, 4, 6]

    def test_return_all_keeps_every_row(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 2, 3}) N return all N") == [1, 2, 2, 3]

    def test_return_a_tuple_per_row(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({1, 2}) N return Tuple { value: N, doubled: N * 2 }")
        assert result == [
            CQLTuple(elements={"value": 1, "doubled": 2}),
            CQLTuple(elements={"value": 2, "doubled": 4}),
        ]


class TestReturnDistinct:
    """`distinct` is CQL's default return qualifier, and `all` is what keeps duplicates."""

    def test_return_distinct_drops_repeated_values(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 2, 3, 3, 3}) N return distinct N") == [1, 2, 3]

    def test_a_bare_return_is_distinct(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 2, 3, 3, 3}) N return N") == [1, 2, 3]

    def test_return_all_is_the_only_form_that_keeps_duplicates(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 2, 3, 3, 3}) N return all N") == [1, 2, 2, 3, 3, 3]

    def test_distinct_keeps_the_first_occurrence_order(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({'b', 'a', 'b', 'c', 'a'}) S return distinct S") == ["b", "a", "c"]

    def test_distinct_folds_a_shaped_expression(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 3, 4}) N return distinct N mod 2") == [1, 0]

    def test_distinct_folds_repeated_tuples(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({Tuple { a: 1 }, Tuple { a: 1 }, Tuple { a: 2 }}) T return distinct T")
        assert result == [CQLTuple(elements={"a": 1}), CQLTuple(elements={"a": 2})]

    def test_distinct_folds_repeated_codes(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Codes version '1.0'
            codesystem SNOMED: 'http://snomed.info/sct'
            code Headache: '25064002' from SNOMED
            define Repeated: {Headache, Headache}
            define Folded: Repeated C return distinct C
        """)
        assert evaluator.evaluate_definition("Folded") == [CQLCode(code="25064002", system="http://snomed.info/sct")]

    def test_distinct_collapses_repeated_nulls_to_one(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({null, null, null}) N return distinct N") == [None]

    def test_distinct_keeps_a_boolean_apart_from_an_integer(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({1, 2}) N return distinct (if N = 1 then true else 1)")
        assert result == [True, 1]

    def test_distinct_runs_before_sort(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({3, 1, 3, 2}) N return distinct N sort asc") == [1, 2, 3]


class TestAggregateClause:
    """`aggregate` accumulates one value across the rows."""

    def test_aggregate_with_an_integer_start(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 3}) N aggregate Total starting 0: Total + N") == 6

    def test_aggregate_without_a_start_begins_at_null(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({1, 2, 3}) N aggregate Total: Coalesce(Total, 0) + N")
        assert result == 6

    def test_aggregate_all_matches_the_plain_form(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 3}) N aggregate all Total starting 0: Total + N") == 6

    def test_aggregate_distinct_folds_repeated_rows(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 2, 3}) N aggregate distinct Total starting 0: Total + N") == 6

    def test_aggregate_with_a_parenthesised_start(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("({1, 2, 3}) N aggregate Total starting (2 * 5): Total + N") == 16

    def test_aggregate_with_a_quantity_start(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({1, 2}) N aggregate Total starting 1 'mg': Total")
        assert result == Quantity(value=Decimal("1"), unit="mg")

    def test_aggregate_with_a_string_start(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({'a', 'b'}) S aggregate Joined starting '': Joined & S")
        assert result == "ab"

    def test_aggregate_runs_after_where(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("({1, 2, 3, 4}) N where N > 2 aggregate Total starting 0: Total + N")
        assert result == 7


class TestWithAndWithoutClauses:
    """`with ... such that` and `without ... such that`."""

    def test_with_clause_keeps_matching_rows(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Inclusion version '1.0'
            define Orders: {1, 2, 3}
            define Known: {1, 3}
            define Matched: Orders O with Known K such that O = K return O
        """)
        assert evaluator.evaluate_definition("Matched") == [1, 3]

    def test_without_clause_keeps_unmatched_rows(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Inclusion version '1.0'
            define Orders: {1, 2, 3}
            define Known: {1, 3}
            define Unmatched: Orders O without Known K such that O = K return O
        """)
        assert evaluator.evaluate_definition("Unmatched") == [2]

    def test_with_and_without_combine(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Inclusion version '1.0'
            define Numbers: {1, 2, 3, 4}
            define Small: {1, 2, 3}
            define Excluded: {1}
            define Kept: Numbers N with Small S such that N = S without Excluded E such that N = E return N
        """)
        assert evaluator.evaluate_definition("Kept") == [2, 3]

    def test_with_clause_over_a_scalar_source(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Inclusion version '1.0'
            define Numbers: {1, 2, 3}
            define Target: 2
            define Matched: Numbers N with Target T such that N = T return N
        """)
        assert evaluator.evaluate_definition("Matched") == [2]


RETRIEVE_LIBRARY = """
library Retrieves version '1.0'
using FHIR version '4.0.1'
codesystem SNOMED: 'http://snomed.info/sct'
valueset Diabetes: 'http://example.org/vs/diabetes'
code Headache: '25064002' from SNOMED
define AllConditions: [Condition]
define ByValueSet: [Condition: Diabetes]
define ByCode: [Condition: Headache]
define ByExplicitPath: [Observation: code in Diabetes]
define Immunizations: [Immunization]
define MedicationRequests: [MedicationRequest]
define UnmappedType: [Basic]
"""


class TestRetrieve:
    """Retrieve expressions pass resource type, code path, and terminology to the data source."""

    def test_retrieve_without_a_data_source_is_empty(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("[Condition]") == []

    def test_plain_retrieve_uses_the_default_code_path(self) -> None:
        source = RecordingDataSource({"Condition": [{"resourceType": "Condition", "id": "c1"}]})
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile(RETRIEVE_LIBRARY)

        assert evaluator.evaluate_definition("AllConditions") == [{"resourceType": "Condition", "id": "c1"}]
        assert source.calls == [RetrieveCall(resource_type="Condition", code_path="code", codes=None, valueset=None)]

    def test_retrieve_filtered_by_a_declared_valueset(self) -> None:
        source = RecordingDataSource()
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile(RETRIEVE_LIBRARY)

        evaluator.evaluate_definition("ByValueSet")
        assert source.calls == [
            RetrieveCall(
                resource_type="Condition",
                code_path="code",
                codes=None,
                valueset="http://example.org/vs/diabetes",
            )
        ]

    def test_retrieve_filtered_by_a_declared_code(self) -> None:
        source = RecordingDataSource()
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile(RETRIEVE_LIBRARY)

        evaluator.evaluate_definition("ByCode")
        assert source.calls == [
            RetrieveCall(
                resource_type="Condition",
                code_path="code",
                codes=[CQLCode(code="25064002", system="http://snomed.info/sct")],
                valueset=None,
            )
        ]

    def test_retrieve_with_an_explicit_code_path(self) -> None:
        source = RecordingDataSource()
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile(RETRIEVE_LIBRARY)

        evaluator.evaluate_definition("ByExplicitPath")
        assert source.calls == [
            RetrieveCall(
                resource_type="Observation",
                code_path="code",
                codes=None,
                valueset="http://example.org/vs/diabetes",
            )
        ]

    @pytest.mark.parametrize(
        ("definition_name", "resource_type", "code_path"),
        [
            ("Immunizations", "Immunization", "vaccineCode"),
            ("MedicationRequests", "MedicationRequest", "medication.concept"),
            ("UnmappedType", "Basic", None),
        ],
    )
    def test_default_code_path_per_resource_type(
        self, definition_name: str, resource_type: str, code_path: str | None
    ) -> None:
        source = RecordingDataSource()
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile(RETRIEVE_LIBRARY)

        evaluator.evaluate_definition(definition_name)
        assert source.calls == [
            RetrieveCall(resource_type=resource_type, code_path=code_path, codes=None, valueset=None)
        ]

    def test_retrieve_feeds_a_query(self) -> None:
        source = RecordingDataSource(
            {
                "Condition": [
                    {"resourceType": "Condition", "id": "c1", "clinicalStatus": "active"},
                    {"resourceType": "Condition", "id": "c2", "clinicalStatus": "resolved"},
                ]
            }
        )
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile("""
            library Queried version '1.0'
            using FHIR version '4.0.1'
            define Active: [Condition] C where C.clinicalStatus = 'active' return C.id
        """)
        assert evaluator.evaluate_definition("Active") == ["c1"]


class TestRetrieveTerminologyIsResolved:
    """A retrieve whose terminology resolves to nothing is refused, never widened to the whole type."""

    def test_an_undeclared_valueset_is_refused(self) -> None:
        source = RecordingDataSource({"Condition": [{"resourceType": "Condition", "id": "c1"}]})
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile("""
            library Retrieves version '1.0'
            using FHIR version '4.0.1'
            valueset Diabetes: 'http://example.org/vs/diabetes'
            define Widened: [Condition: Hypertension]
        """)

        with pytest.raises(CQLError, match="Hypertension"):
            evaluator.evaluate_definition("Widened")
        assert source.calls == []

    def test_a_retrieve_with_no_library_at_all_is_refused(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="Diabetes"):
            evaluator.evaluate_expression("[Condition: Diabetes]")

    def test_a_declared_valueset_still_resolves(self) -> None:
        source = RecordingDataSource()
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile("""
            library Retrieves version '1.0'
            using FHIR version '4.0.1'
            valueset Diabetes: 'http://example.org/vs/diabetes'
            define Narrowed: [Condition: Diabetes]
        """)

        evaluator.evaluate_definition("Narrowed")
        assert source.calls == [
            RetrieveCall(
                resource_type="Condition",
                code_path="code",
                codes=None,
                valueset="http://example.org/vs/diabetes",
            )
        ]

    def test_a_definition_holding_codes_resolves(self) -> None:
        source = RecordingDataSource()
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile("""
            library Retrieves version '1.0'
            using FHIR version '4.0.1'
            codesystem SNOMED: 'http://snomed.info/sct'
            code Headache: '25064002' from SNOMED
            define Wanted: {Headache}
            define Narrowed: [Condition: Wanted]
        """)

        evaluator.evaluate_definition("Narrowed")
        assert source.calls == [
            RetrieveCall(
                resource_type="Condition",
                code_path="code",
                codes=[CQLCode(code="25064002", system="http://snomed.info/sct")],
                valueset=None,
            )
        ]

    def test_a_string_where_a_terminology_reference_belongs_is_refused(self) -> None:
        source = RecordingDataSource({"Observation": [{"resourceType": "Observation", "id": "o1"}]})
        evaluator = CQLEvaluator(data_source=source)
        evaluator.compile("""
            library Retrieves version '1.0'
            using FHIR version '4.0.1'
            define Bare: [Observation: 'x']
        """)

        with pytest.raises(CQLError, match="terminology reference"):
            evaluator.evaluate_definition("Bare")
        assert source.calls == []


class TestExternalConstants:
    """`%name` reads a constant out of the evaluation context."""

    def test_unknown_external_constant_is_null(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("%unknown") is None
