"""Tests for CQL library definitions, the library manager and the evaluator.

Covers the definition models in the library module, terminology resolution,
library caching and include resolution, and the evaluator surface: compilation,
definition and expression evaluation, parameter binding, ELM conversion and the
error paths behind each of them.
"""

from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator
from dhis2w_fhir_engine.engine.cql.evaluator import compile_library, evaluate
from dhis2w_fhir_engine.engine.cql.library import (
    CodeDefinition,
    CodeSystemDefinition,
    ConceptDefinition,
    CQLLibrary,
    ExpressionDefinition,
    FunctionDefinition,
    IncludeDefinition,
    LibraryManager,
    ParameterDefinition,
    UsingDefinition,
    ValueSetDefinition,
)
from dhis2w_fhir_engine.engine.cql.library_resolver import InMemoryLibraryResolver
from dhis2w_fhir_engine.engine.cql.plugins import CQLPluginRegistry
from dhis2w_fhir_engine.engine.cql.types import CQLCode, CQLConcept
from dhis2w_fhir_engine.engine.exceptions import CQLError

DEPENDENCY_SOURCE = "library Dep version '1' define Answer: 42"


@pytest.fixture
def terminology_library() -> CQLLibrary:
    """A library carrying one codesystem, two codes and one concept."""
    library = CQLLibrary(name="Terminology", version="1.0")
    library.codesystems["CS"] = CodeSystemDefinition(name="CS", id="http://cs", version="2")
    library.codes["Known"] = CodeDefinition(name="Known", code="c1", codesystem="CS", display="One")
    library.codes["Orphan"] = CodeDefinition(name="Orphan", code="o1", codesystem="Absent")
    library.concepts["Mixed"] = ConceptDefinition(name="Mixed", codes=["Known", "Absent"], display="Kay")
    return library


@pytest.fixture
def dependency_manager() -> LibraryManager:
    """A library manager wired to resolve and compile one in-memory dependency."""
    resolver = InMemoryLibraryResolver()
    resolver.add_library("Dep", DEPENDENCY_SOURCE, "1")
    manager = LibraryManager()
    manager.set_resolver(resolver)
    manager.set_compile_function(CQLEvaluator()._compile_source)
    return manager


class TestDefinitionModels:
    """The definition models that make up a compiled library."""

    def test_using_definition_carries_a_model_and_version(self) -> None:
        using = UsingDefinition(model="FHIR", version="4.0.1")
        assert using.model == "FHIR"
        assert using.version == "4.0.1"

    def test_include_definition_defaults_to_no_alias(self) -> None:
        include = IncludeDefinition(library="Common")
        assert include.alias is None
        assert include.version is None

    def test_parameter_definition_defaults_to_no_value(self) -> None:
        parameter = ParameterDefinition(name="MeasurementPeriod")
        assert parameter.default_value is None
        assert parameter.type_specifier is None

    def test_valueset_definition_starts_with_no_codesystems(self) -> None:
        valueset = ValueSetDefinition(name="Diabetes", id="http://vs/diabetes")
        assert valueset.codesystems == []

    def test_code_definition_resolves_against_a_supplied_url(self) -> None:
        code = CodeDefinition(name="Known", code="c1", codesystem="CS", display="One")
        assert code.to_cql_code("http://elsewhere") == CQLCode(code="c1", system="http://elsewhere", display="One")

    def test_function_definition_defaults(self) -> None:
        function = FunctionDefinition(name="Helper")
        assert function.parameters == []
        assert function.fluent is False
        assert function.external is False


class TestLibraryContents:
    """Adding and reading definitions on a library."""

    def test_string_form_includes_the_version_when_present(self) -> None:
        assert str(CQLLibrary(name="L", version="1.0")) == "library L version '1.0'"

    def test_string_form_omits_a_missing_version(self) -> None:
        assert str(CQLLibrary(name="L")) == "library L"

    def test_add_and_get_a_definition(self) -> None:
        library = CQLLibrary(name="L")
        definition = ExpressionDefinition(name="D")
        library.add_definition(definition)
        assert library.get_definition("D") is definition

    def test_get_a_missing_definition_yields_null(self) -> None:
        assert CQLLibrary(name="L").get_definition("Absent") is None

    def test_functions_overload_by_argument_count(self) -> None:
        library = CQLLibrary(name="L")
        one_argument = FunctionDefinition(name="F", parameters=[("a", "Integer")])
        two_arguments = FunctionDefinition(name="F", parameters=[("a", "Integer"), ("b", "Integer")])
        library.add_function(one_argument)
        library.add_function(two_arguments)
        assert library.get_function("F", 1) is one_argument
        assert library.get_function("F", 2) is two_arguments

    def test_function_lookup_without_a_count_returns_the_first_overload(self) -> None:
        library = CQLLibrary(name="L")
        first = FunctionDefinition(name="F", parameters=[("a", "Integer")])
        library.add_function(first)
        library.add_function(FunctionDefinition(name="F", parameters=[]))
        assert library.get_function("F") is first

    def test_function_lookup_falls_back_to_the_first_overload(self) -> None:
        library = CQLLibrary(name="L")
        first = FunctionDefinition(name="F", parameters=[("a", "Integer")])
        library.add_function(first)
        assert library.get_function("F", 5) is first

    def test_get_a_missing_function_yields_null(self) -> None:
        assert CQLLibrary(name="L").get_function("Absent") is None


class TestTerminologyResolution:
    """Resolving code and concept references against a library."""

    def test_resolve_code(self, terminology_library: CQLLibrary) -> None:
        assert terminology_library.resolve_code("Known") == CQLCode(code="c1", system="http://cs", display="One")

    def test_resolve_an_unknown_code_yields_null(self, terminology_library: CQLLibrary) -> None:
        assert terminology_library.resolve_code("Absent") is None

    def test_resolve_a_code_with_an_unknown_codesystem_yields_null(self, terminology_library: CQLLibrary) -> None:
        assert terminology_library.resolve_code("Orphan") is None

    def test_resolve_concept_keeps_only_the_resolvable_codes(self, terminology_library: CQLLibrary) -> None:
        resolved = terminology_library.resolve_concept("Mixed")
        assert resolved == CQLConcept(codes=(CQLCode(code="c1", system="http://cs"),))
        assert resolved is not None
        assert resolved.display == "Kay"

    def test_resolve_an_unknown_concept_yields_null(self, terminology_library: CQLLibrary) -> None:
        assert terminology_library.resolve_concept("Absent") is None


class TestLibraryManager:
    """Caching, resolution and include handling."""

    def test_an_empty_manager_resolves_nothing(self) -> None:
        assert LibraryManager().get_library("Absent") is None

    def test_registered_sources_are_kept_by_name(self) -> None:
        manager = LibraryManager()
        manager.register_source("Src", DEPENDENCY_SOURCE)
        assert manager._sources == {"Src": DEPENDENCY_SOURCE}

    def test_added_libraries_are_listed_and_retrievable(self) -> None:
        manager = LibraryManager()
        library = CQLLibrary(name="L", version="1.0")
        manager.add_library(library)
        assert manager.list_libraries() == ["L"]
        assert manager.get_library("L", "1.0") is library

    def test_clearing_the_cache_forgets_every_library(self) -> None:
        manager = LibraryManager()
        manager.add_library(CQLLibrary(name="L", version="1.0"))
        manager.clear_cache()
        assert manager.list_libraries() == []
        assert manager.get_library("L", "1.0") is None

    def test_a_resolver_without_a_compile_function_resolves_nothing(self) -> None:
        resolver = InMemoryLibraryResolver()
        resolver.add_library("Dep", DEPENDENCY_SOURCE, "1")
        manager = LibraryManager()
        manager.set_resolver(resolver)
        assert manager.get_library("Dep", "1") is None

    def test_a_resolved_library_is_compiled_and_cached(self, dependency_manager: LibraryManager) -> None:
        resolved = dependency_manager.get_library("Dep", "1")
        assert resolved is not None
        assert resolved.name == "Dep"
        assert "Answer" in resolved.definitions
        assert dependency_manager.get_library("Dep", "1") is resolved

    def test_an_unresolvable_library_yields_null(self, dependency_manager: LibraryManager) -> None:
        assert dependency_manager.get_library("Absent") is None

    def test_includes_resolve_under_their_alias(self, dependency_manager: LibraryManager) -> None:
        library = CQLLibrary(
            name="Main",
            includes=[
                IncludeDefinition(library="Dep", version="1", alias="D"),
                IncludeDefinition(library="Absent"),
            ],
        )
        resolved = dependency_manager.resolve_includes(library)
        assert list(resolved) == ["D"]
        assert resolved["D"].name == "Dep"

    def test_includes_without_an_alias_use_the_library_name(self, dependency_manager: LibraryManager) -> None:
        library = CQLLibrary(name="Main", includes=[IncludeDefinition(library="Dep", version="1")])
        assert list(dependency_manager.resolve_includes(library)) == ["Dep"]


class TestEvaluatorCompilation:
    """Compiling CQL source into a library."""

    def test_compile_records_the_source_and_becomes_the_current_library(self) -> None:
        evaluator = CQLEvaluator()
        source = "library L version '1.0'\ndefine A: 1 + 1"
        library = evaluator.compile(source)
        assert library.name == "L"
        assert library.version == "1.0"
        assert library.source == source
        assert evaluator.current_library is library
        assert evaluator.library_manager.get_library("L", "1.0") is library

    def test_a_syntax_error_raises(self) -> None:
        with pytest.raises(CQLError, match="Syntax error"):
            CQLEvaluator().compile("define X: (")

    def test_internal_compilation_of_broken_source_yields_null(self) -> None:
        assert CQLEvaluator()._compile_source("define X: (") is None

    def test_internal_compilation_leaves_the_current_library_alone(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("library Outer\ndefine A: 1")
        compiled = evaluator._compile_source(DEPENDENCY_SOURCE)
        assert compiled is not None
        assert compiled.name == "Dep"
        assert evaluator.current_library is not None
        assert evaluator.current_library.name == "Outer"

    def test_the_module_level_helper_compiles_a_library(self) -> None:
        library = compile_library("library Helper\ndefine A: 1")
        assert library.name == "Helper"


class TestEvaluatorConfiguration:
    """Evaluator construction options and accessors."""

    def test_the_fhir_binding_is_exposed(self) -> None:
        binding = CQLEvaluator().fhir_binding
        assert binding.fhir_version == "4.0.1"

    def test_the_plugin_registry_is_readable_and_writable(self) -> None:
        evaluator = CQLEvaluator()
        assert evaluator.plugin_registry is None
        registry = CQLPluginRegistry()
        evaluator.plugin_registry = registry
        assert evaluator.plugin_registry is registry

    def test_dropping_the_builtins_leaves_no_resolver(self) -> None:
        evaluator = CQLEvaluator(include_builtins=False)
        assert evaluator.library_manager._resolver is None

    def test_load_library_resolves_through_the_configured_resolver(self) -> None:
        resolver = InMemoryLibraryResolver()
        resolver.add_library("Lib", "library Lib version '2' define V: 5", "2")
        evaluator = CQLEvaluator(library_resolver=resolver)
        loaded = evaluator.load_library("Lib", "2")
        assert loaded is not None
        assert loaded.name == "Lib"
        assert evaluator.current_library is loaded

    def test_load_library_keeps_the_current_library_when_nothing_resolves(self) -> None:
        resolver = InMemoryLibraryResolver()
        resolver.add_library("Lib", "library Lib version '2' define V: 5", "2")
        evaluator = CQLEvaluator(library_resolver=resolver)
        evaluator.load_library("Lib", "2")
        assert evaluator.load_library("Absent") is None
        assert evaluator.current_library is not None
        assert evaluator.current_library.name == "Lib"


class TestEvaluatorDefinitions:
    """Evaluating named definitions and reading library metadata."""

    @pytest.fixture
    def evaluator(self) -> CQLEvaluator:
        """An evaluator holding a library with a parameter and three definitions."""
        evaluator = CQLEvaluator()
        evaluator.compile(
            "library L version '1.0'\nparameter P default 7\ndefine A: 1 + 1\ndefine B: A * 3\ndefine C: P"
        )
        return evaluator

    def test_definition_names(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.get_definitions() == ["A", "B", "C"]

    def test_parameter_defaults(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.get_parameters() == {"P": 7}

    def test_definition_names_without_a_library(self) -> None:
        assert CQLEvaluator().get_definitions() == []

    def test_parameter_defaults_without_a_library(self) -> None:
        assert CQLEvaluator().get_parameters() == {}

    def test_evaluate_a_definition(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_definition("B") == 6

    def test_a_parameter_default_is_used_when_nothing_is_bound(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_definition("C") == 7

    def test_a_bound_parameter_overrides_the_default(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_definition("C", parameters={"P": 99}) == 99

    def test_evaluating_without_a_library_raises(self) -> None:
        with pytest.raises(CQLError, match="No library loaded"):
            CQLEvaluator().evaluate_definition("A")

    def test_evaluating_an_unknown_definition_raises(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="Definition not found: Absent"):
            evaluator.evaluate_definition("Absent")

    def test_evaluating_a_definition_without_an_expression_raises(self, evaluator: CQLEvaluator) -> None:
        library = CQLLibrary(name="Manual")
        library.add_definition(ExpressionDefinition(name="Empty"))
        with pytest.raises(CQLError, match="Definition has no expression: Empty"):
            evaluator.evaluate_definition("Empty", library=library)

    def test_evaluate_all_definitions(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_all_definitions() == {"A": 2, "B": 6, "C": 7}

    def test_evaluate_all_definitions_binds_parameters(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_all_definitions(parameters={"P": 3})["C"] == 3

    def test_evaluate_all_definitions_without_a_library_raises(self) -> None:
        with pytest.raises(CQLError, match="No library loaded"):
            CQLEvaluator().evaluate_all_definitions()

    def test_a_failing_definition_is_reported_in_place(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("library E\ndefine Good: 1\ndefine Bad: Ln(0)")
        results = evaluator.evaluate_all_definitions()
        assert results["Good"] == 1
        failure = results["Bad"]
        assert isinstance(failure, CQLError)
        assert "Error evaluating Bad" in str(failure)


class TestEvaluatorExpressions:
    """Evaluating inline expressions and caching parsed trees."""

    def test_evaluate_an_expression(self) -> None:
        assert CQLEvaluator().evaluate_expression("1 + 2 * 3") == 7

    def test_an_expression_can_read_a_bound_parameter(self) -> None:
        evaluator = CQLEvaluator()
        library = evaluator.compile("library L\nparameter P default 1\ndefine A: P")
        assert evaluator.evaluate_expression("P + 1", parameters={"P": 5}, library=library) == 6

    def test_an_expression_can_reference_a_library_definition(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("library L\ndefine A: 4")
        assert evaluator.evaluate_expression("A + 1") == 5

    def test_a_syntax_error_raises(self) -> None:
        with pytest.raises(CQLError, match="Syntax error"):
            CQLEvaluator().evaluate_expression("((")

    def test_parsed_expressions_are_cached_and_reused(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.evaluate_expression("1 + 1")
        cached = evaluator._expression_cache["1 + 1"]
        assert evaluator.evaluate_expression("1 + 1") == 2
        assert evaluator._expression_cache["1 + 1"] is cached

    def test_clearing_the_cache_drops_every_parsed_tree(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.evaluate_expression("1 + 1")
        evaluator.clear_cache()
        assert evaluator._expression_cache == {}

    def test_the_module_level_helper_evaluates_an_expression(self) -> None:
        assert evaluate("2 + 3") == 5


class TestEvaluatorElmOutput:
    """Converting CQL source to ELM."""

    def test_to_elm_uses_the_current_library_source(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("library T version '1' define S: 1 + 2")
        elm = evaluator.to_elm()
        assert elm.identifier is not None
        assert elm.identifier.id == "T"

    def test_to_elm_accepts_explicit_source(self) -> None:
        elm = CQLEvaluator().to_elm("library Given define S: 1")
        assert elm.identifier is not None
        assert elm.identifier.id == "Given"

    def test_to_elm_json_is_indented_json(self) -> None:
        text = CQLEvaluator().to_elm_json("library T define S: 1")
        assert text.startswith("{\n")
        assert '"library"' in text

    def test_to_elm_dict_is_wrapped_in_a_library_key(self) -> None:
        result: dict[str, Any] = CQLEvaluator().to_elm_dict("library T define S: 1")
        assert list(result) == ["library"]

    @pytest.mark.parametrize("method_name", ["to_elm", "to_elm_json", "to_elm_dict"])
    def test_conversion_without_any_source_raises(self, method_name: str) -> None:
        evaluator = CQLEvaluator()
        with pytest.raises(CQLError, match="No CQL source available"):
            getattr(evaluator, method_name)()
