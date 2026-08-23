"""Tests for ELM models and loader."""

import json

import pytest

from dhis2w_fhir_engine.engine.elm.exceptions import ELMValidationError
from dhis2w_fhir_engine.engine.elm.loader import ELMLoader
from dhis2w_fhir_engine.engine.elm.models.expressions import (
    ELMAdd,
    ELMAnd,
    ELMEqual,
    ELMIf,
    ELMList,
    ELMLiteral,
    ELMNull,
    ELMOr,
    ELMQuery,
    ELMReturnClause,
    ELMSubtract,
    ELMTuple,
)
from dhis2w_fhir_engine.engine.elm.models.library import (
    ELMAnnotation,
    ELMCodeDef,
    ELMCodeSystem,
    ELMDefinition,
    ELMFunctionDef,
    ELMIdentifier,
    ELMInclude,
    ELMLibrary,
    ELMOperandDef,
    ELMParameter,
    ELMStatements,
    ELMUsing,
    ELMValueSet,
)
from dhis2w_fhir_engine.engine.elm.models.types import (
    ELMListTypeSpecifier,
    ELMNamedTypeSpecifier,
    ELMTupleTypeSpecifier,
)


class TestELMIdentifier:
    def test_basic_identifier(self) -> None:
        identifier = ELMIdentifier(id="TestLibrary", version="1.0.0")
        assert identifier.id == "TestLibrary"
        assert identifier.version == "1.0.0"

    def test_identifier_without_version(self) -> None:
        identifier = ELMIdentifier(id="TestLibrary")
        assert identifier.id == "TestLibrary"
        assert identifier.version is None

    def test_identifier_with_system(self) -> None:
        identifier = ELMIdentifier(id="urn:hl7-org:elm", version="r1", system="http://hl7.org")
        assert identifier.id == "urn:hl7-org:elm"
        assert identifier.version == "r1"
        assert identifier.system == "http://hl7.org"


class TestELMUsing:
    def test_fhir_using(self) -> None:
        using = ELMUsing(
            localIdentifier="FHIR",
            uri="http://hl7.org/fhir",
            version="4.0.1",
        )
        assert using.localIdentifier == "FHIR"
        assert using.uri == "http://hl7.org/fhir"
        assert using.version == "4.0.1"


class TestELMInclude:
    def test_library_include(self) -> None:
        include = ELMInclude(
            localIdentifier="FHIRHelpers",
            path="FHIRHelpers",
            version="4.0.1",
        )
        assert include.localIdentifier == "FHIRHelpers"
        assert include.path == "FHIRHelpers"
        assert include.version == "4.0.1"


class TestELMParameter:
    def test_basic_parameter(self) -> None:
        param = ELMParameter(
            name="MeasurementPeriod",
            accessLevel="Public",
        )
        assert param.name == "MeasurementPeriod"
        assert param.accessLevel == "Public"


class TestELMCodeSystem:
    def test_codesystem(self) -> None:
        cs = ELMCodeSystem(
            name="LOINC",
            id="http://loinc.org",
            version="2.72",
        )
        assert cs.name == "LOINC"
        assert cs.id == "http://loinc.org"
        assert cs.version == "2.72"


class TestELMValueSet:
    def test_valueset(self) -> None:
        vs = ELMValueSet(
            name="Diabetes",
            id="http://example.org/fhir/ValueSet/diabetes",
        )
        assert vs.name == "Diabetes"
        assert vs.id == "http://example.org/fhir/ValueSet/diabetes"


class TestELMCodeDef:
    def test_code_definition(self) -> None:
        from dhis2w_fhir_engine.engine.elm.models.library import ELMCodeSystemRef

        code = ELMCodeDef(
            name="Systolic BP",
            id="8480-6",
            display="Systolic blood pressure",
            codeSystem=ELMCodeSystemRef(name="LOINC"),
        )
        assert code.name == "Systolic BP"
        assert code.id == "8480-6"
        assert code.display == "Systolic blood pressure"
        assert code.codeSystem.name == "LOINC"


class TestELMDefinition:
    def test_simple_definition(self) -> None:
        definition = ELMDefinition(
            name="Sum",
            context="Patient",
            accessLevel="Public",
            expression={"type": "Literal", "value": "42", "valueType": "{urn:hl7-org:elm-types:r1}Integer"},
        )
        assert definition.name == "Sum"
        assert definition.context == "Patient"
        assert definition.accessLevel == "Public"
        assert definition.expression["type"] == "Literal"


class TestELMFunctionDef:
    def test_function_definition(self) -> None:
        func = ELMFunctionDef(
            name="Add",
            operand=[
                ELMOperandDef(name="a"),
                ELMOperandDef(name="b"),
            ],
            expression={"type": "Add", "operand": []},
        )
        assert func.name == "Add"
        assert len(func.operand) == 2
        assert func.operand[0].name == "a"
        assert func.operand[1].name == "b"


class TestELMTypeSpecifiers:
    def test_named_type_specifier(self) -> None:
        ts = ELMNamedTypeSpecifier(namespace="FHIR", name="Patient")
        assert ts.type == "NamedTypeSpecifier"
        assert ts.namespace == "FHIR"
        assert ts.name == "Patient"

    def test_list_type_specifier(self) -> None:
        element_type = ELMNamedTypeSpecifier(namespace="System", name="String")
        ts = ELMListTypeSpecifier(elementType=element_type)
        assert ts.type == "ListTypeSpecifier"
        assert isinstance(ts.elementType, ELMNamedTypeSpecifier)
        assert ts.elementType.name == "String"

    def test_tuple_type_specifier(self) -> None:
        from dhis2w_fhir_engine.engine.elm.models.types import ELMTupleElementDefinition

        ts = ELMTupleTypeSpecifier(
            element=[
                ELMTupleElementDefinition(name="value"),
                ELMTupleElementDefinition(name="unit"),
            ]
        )
        assert ts.type == "TupleTypeSpecifier"
        assert len(ts.element) == 2


class TestELMExpressions:
    def test_literal(self) -> None:
        lit = ELMLiteral(
            valueType="{urn:hl7-org:elm-types:r1}Integer",
            value="42",
        )
        assert lit.type == "Literal"
        assert lit.valueType == "{urn:hl7-org:elm-types:r1}Integer"
        assert lit.value == "42"

    def test_null(self) -> None:
        null = ELMNull()
        assert null.type == "Null"

    def test_add(self) -> None:
        add = ELMAdd(operand=[])
        assert add.type == "Add"

    def test_subtract(self) -> None:
        sub = ELMSubtract(operand=[])
        assert sub.type == "Subtract"

    def test_equal(self) -> None:
        eq = ELMEqual(operand=[])
        assert eq.type == "Equal"

    def test_and(self) -> None:
        and_expr = ELMAnd(operand=[])
        assert and_expr.type == "And"

    def test_or(self) -> None:
        or_expr = ELMOr(operand=[])
        assert or_expr.type == "Or"

    def test_list(self) -> None:
        lst = ELMList(element=[])
        assert lst.type == "List"

    def test_tuple(self) -> None:
        tup = ELMTuple(element=[])
        assert tup.type == "Tuple"

    def test_if(self) -> None:
        if_expr = ELMIf(
            condition=ELMLiteral(valueType="{urn:hl7-org:elm-types:r1}Boolean", value="true"),
            then=ELMLiteral(valueType="{urn:hl7-org:elm-types:r1}Integer", value="1"),
        )
        assert if_expr.type == "If"
        assert isinstance(if_expr.condition, ELMLiteral)
        assert if_expr.condition.value == "true"
        assert isinstance(if_expr.then, ELMLiteral)
        assert if_expr.then.value == "1"

    def test_query(self) -> None:
        query = ELMQuery(source=[])
        assert query.type == "Query"


class TestKeywordAliasedFields:
    """Fields whose ELM wire name is a Python keyword, or shadows one of the model's own names."""

    def test_an_else_branch_is_given_by_field_name(self) -> None:
        if_expr = ELMIf(
            condition=ELMLiteral(valueType="{urn:hl7-org:elm-types:r1}Boolean", value="true"),
            then=ELMLiteral(valueType="{urn:hl7-org:elm-types:r1}Integer", value="1"),
            else_=ELMLiteral(valueType="{urn:hl7-org:elm-types:r1}Integer", value="2"),
        )
        assert isinstance(if_expr.else_, ELMLiteral)
        assert if_expr.else_.value == "2"

    def test_an_else_branch_reads_and_writes_the_wire_name(self) -> None:
        if_expr = ELMIf.model_validate(
            {
                "condition": {"type": "Literal", "valueType": "x", "value": "true"},
                "then": {"type": "Literal", "valueType": "x", "value": "1"},
                "else": {"type": "Literal", "valueType": "x", "value": "2"},
            }
        )
        assert if_expr.else_ is not None
        assert "else" in if_expr.model_dump(by_alias=True, exclude_none=True)

    def test_statements_are_given_by_field_name(self) -> None:
        statements = ELMStatements(definitions=[ELMDefinition(name="Sum", expression={})])
        assert [definition.name for definition in statements.definitions] == ["Sum"]
        assert statements.model_dump(by_alias=True, exclude_none=True)["def"][0]["name"] == "Sum"

    def test_statements_read_the_wire_name(self) -> None:
        statements = ELMStatements.model_validate({"def": [{"name": "Sum", "expression": {}}]})
        assert [definition.name for definition in statements.definitions] == ["Sum"]

    def test_an_annotation_type_is_given_by_field_name(self) -> None:
        annotation = ELMAnnotation(type="CqlToElmInfo")
        assert annotation.type == "CqlToElmInfo"
        assert annotation.model_dump(by_alias=True, exclude_none=True) == {"t": "CqlToElmInfo"}
        assert ELMAnnotation.model_validate({"t": "CqlToElmInfo"}).type == "CqlToElmInfo"

    def test_a_query_return_clause_is_given_by_field_name(self) -> None:
        query = ELMQuery(source=[], return_=ELMReturnClause(expression=ELMLiteral(valueType="x", value="1")))
        assert query.return_ is not None
        assert "return" in query.model_dump(by_alias=True, exclude_none=True)


class TestELMLibrary:
    def test_minimal_library(self) -> None:
        library = ELMLibrary(
            identifier=ELMIdentifier(id="TestLibrary", version="1.0.0"),
        )
        assert library.identifier.id == "TestLibrary"
        assert library.identifier.version == "1.0.0"

    def test_full_library(self) -> None:
        library = ELMLibrary(
            identifier=ELMIdentifier(id="TestLibrary", version="1.0.0"),
            schemaIdentifier=ELMIdentifier(id="urn:hl7-org:elm", version="r1"),
            usings=[ELMUsing(localIdentifier="FHIR", uri="http://hl7.org/fhir", version="4.0.1")],
            includes=[ELMInclude(localIdentifier="FHIRHelpers", path="FHIRHelpers", version="4.0.1")],
            parameters=[ELMParameter(name="MeasurementPeriod")],
            codeSystems=[ELMCodeSystem(name="LOINC", id="http://loinc.org")],
            valueSets=[ELMValueSet(name="Diabetes", id="http://example.org/ValueSet/diabetes")],
            statements=ELMStatements(
                definitions=[
                    ELMDefinition(
                        name="Sum",
                        expression={"type": "Literal", "value": "42"},
                    ),
                ]
            ),
        )
        assert library.identifier.id == "TestLibrary"
        assert len(library.usings) == 1
        assert len(library.includes) == 1
        assert len(library.parameters) == 1
        assert len(library.codeSystems) == 1
        assert len(library.valueSets) == 1
        assert library.statements is not None
        assert len(library.statements.definitions) == 1

    def test_get_definition(self) -> None:
        library = ELMLibrary(
            identifier=ELMIdentifier(id="TestLibrary"),
            statements=ELMStatements(
                definitions=[
                    ELMDefinition(name="First", expression={}),
                    ELMDefinition(name="Second", expression={}),
                ]
            ),
        )
        assert library.get_definition("First") is not None
        assert library.get_definition("Second") is not None
        assert library.get_definition("Third") is None

    def test_get_function(self) -> None:
        library = ELMLibrary(
            identifier=ELMIdentifier(id="TestLibrary"),
            statements=ELMStatements(
                definitions=[
                    ELMFunctionDef(name="Add", operand=[], expression={}),
                ]
            ),
        )
        assert library.get_function("Add") is not None
        assert library.get_function("Missing") is None

    def test_get_parameter(self) -> None:
        library = ELMLibrary(
            identifier=ELMIdentifier(id="TestLibrary"),
            parameters=[ELMParameter(name="Param1")],
        )
        assert library.get_parameter("Param1") is not None
        assert library.get_parameter("Missing") is None

    def test_get_codesystem(self) -> None:
        library = ELMLibrary(
            identifier=ELMIdentifier(id="TestLibrary"),
            codeSystems=[ELMCodeSystem(name="LOINC", id="http://loinc.org")],
        )
        assert library.get_codesystem("LOINC") is not None
        assert library.get_codesystem("Missing") is None

    def test_get_valueset(self) -> None:
        library = ELMLibrary(
            identifier=ELMIdentifier(id="TestLibrary"),
            valueSets=[ELMValueSet(name="Diabetes", id="http://example.org/ValueSet/diabetes")],
        )
        assert library.get_valueset("Diabetes") is not None
        assert library.get_valueset("Missing") is None


class TestELMLoader:
    def test_parse_minimal_library(self) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary", "version": "1.0.0"},
            }
        }
        library = ELMLoader.parse(data)
        assert library.identifier.id == "TestLibrary"
        assert library.identifier.version == "1.0.0"

    def test_parse_unwrapped_library(self) -> None:
        data = {
            "identifier": {"id": "TestLibrary", "version": "1.0.0"},
        }
        library = ELMLoader.parse(data)
        assert library.identifier.id == "TestLibrary"

    def test_load_json_string(self) -> None:
        json_str = json.dumps(
            {
                "library": {
                    "identifier": {"id": "TestLibrary", "version": "1.0.0"},
                }
            }
        )
        library = ELMLoader.load_json(json_str)
        assert library.identifier.id == "TestLibrary"

    def test_validate_valid_library(self) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary", "version": "1.0.0"},
                "schemaIdentifier": {"id": "urn:hl7-org:elm", "version": "r1"},
            }
        }
        errors = ELMLoader.validate(data)
        assert len(errors) == 0

    def test_validate_missing_identifier(self) -> None:
        data = {
            "library": {
                "schemaIdentifier": {"id": "urn:hl7-org:elm"},
            }
        }
        errors = ELMLoader.validate(data)
        assert len(errors) > 0
        assert "identifier" in errors[0].lower()

    def test_validate_missing_identifier_id(self) -> None:
        data = {
            "library": {
                "identifier": {"version": "1.0.0"},
            }
        }
        errors = ELMLoader.validate(data)
        assert len(errors) > 0
        assert "identifier.id" in errors[0].lower()

    def test_validate_invalid_identifier_type(self) -> None:
        data = {
            "library": {
                "identifier": "not an object",
            }
        }
        errors = ELMLoader.validate(data)
        assert len(errors) > 0

    def test_parse_invalid_json_raises_error(self) -> None:
        with pytest.raises(ELMValidationError):
            ELMLoader.load_json("not valid json")

    def test_parse_missing_identifier_raises_error(self) -> None:
        with pytest.raises(ELMValidationError):
            ELMLoader.parse({"library": {}})

    def test_get_library_info(self) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary", "version": "1.0.0"},
                "schemaIdentifier": {"id": "urn:hl7-org:elm", "version": "r1"},
                "usings": [{"localIdentifier": "FHIR", "uri": "http://hl7.org/fhir"}],
                "statements": {
                    "def": [
                        {"name": "Sum", "expression": {}},
                        {"name": "Add", "operand": [], "expression": {}},
                    ]
                },
            }
        }
        info = ELMLoader.get_library_info(data)
        assert info["id"] == "TestLibrary"
        assert info["version"] == "1.0.0"
        assert info["schemaId"] == "urn:hl7-org:elm"
        assert info["usings"] == 1
        assert info["definitions"] == 2
        assert info["functions"] == 1
        assert info["expressions"] == 1

    def test_parse_library_with_statements(self) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {
                            "name": "Sum",
                            "expression": {
                                "type": "Add",
                                "operand": [
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                                ],
                            },
                        }
                    ]
                },
            }
        }
        library = ELMLoader.parse(data)
        assert library.statements is not None
        assert len(library.statements.definitions) == 1
        assert library.statements.definitions[0].name == "Sum"

    def test_parse_library_with_function(self) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {
                            "name": "Add",
                            "operand": [
                                {"name": "a", "operandType": "{urn:hl7-org:elm-types:r1}Integer"},
                                {"name": "b", "operandType": "{urn:hl7-org:elm-types:r1}Integer"},
                            ],
                            "expression": {
                                "type": "Add",
                                "operand": [
                                    {"type": "OperandRef", "name": "a"},
                                    {"type": "OperandRef", "name": "b"},
                                ],
                            },
                        }
                    ]
                },
            }
        }
        library = ELMLoader.parse(data)
        func = library.get_function("Add")
        assert func is not None
        assert len(func.operand) == 2
