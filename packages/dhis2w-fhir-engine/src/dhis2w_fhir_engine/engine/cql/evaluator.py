"""CQL expression evaluator.

This module provides the main CQLEvaluator class for evaluating
CQL expressions and libraries against FHIR data.
"""

from pathlib import Path
from typing import Any

from antlr4 import CommonTokenStream, InputStream, Token  # type: ignore[import-untyped]
from antlr4.error.ErrorListener import ErrorListener  # type: ignore[import-untyped]

from ...binding import FhirVersionBinding, resolve_binding
from ...generated.cql.cqlLexer import cqlLexer
from ...generated.cql.cqlParser import cqlParser
from ...ingest import ResourceInput
from ..exceptions import CQLError
from .context import CQLContext, DataSource
from .library import CQLLibrary, LibraryManager
from .library_resolver import (
    CompositeLibraryResolver,
    FileLibraryResolver,
    InMemoryLibraryResolver,
    LibraryResolver,
)
from .plugins import CQLPluginRegistry
from .visitor import CQLEvaluatorVisitor

# Import ELM serializer (lazy import to avoid circular dependency)
ELMSerializer = None
ELMLibrary = None


def require_end_of_input(parser: cqlParser) -> None:
    """Refuse an expression the parser stopped short of the end of.

    The `expression` rule is not anchored at EOF, so ANTLR happily parses `1 +` as `1` and leaves the
    `+` unread. Reading the token the parser stopped on turns that silence into a syntax error with a
    position, spelled the way the listener spells one so a caller reads both the same way.
    """
    token: Any = parser.getCurrentToken()
    if token is None or token.type == Token.EOF:
        return
    raise CQLError(
        f"Syntax error at line {token.line}:{token.column}: extraneous input '{token.text}' expecting end of expression"
    )


class CQLErrorListener(ErrorListener):
    """ANTLR error listener that raises CQLError."""

    def syntaxError(
        self,
        recognizer: Any,
        offendingSymbol: Any,
        line: int,
        column: int,
        msg: str,
        e: Any,
    ) -> None:
        raise CQLError(f"Syntax error at line {line}:{column}: {msg}")

    def reportAmbiguity(
        self,
        recognizer: Any,
        dfa: Any,
        startIndex: int,
        stopIndex: int,
        exact: bool,
        ambigAlts: Any,
        configs: Any,
    ) -> None:
        pass

    def reportAttemptingFullContext(
        self,
        recognizer: Any,
        dfa: Any,
        startIndex: int,
        stopIndex: int,
        conflictingAlts: Any,
        configs: Any,
    ) -> None:
        pass

    def reportContextSensitivity(
        self,
        recognizer: Any,
        dfa: Any,
        startIndex: int,
        stopIndex: int,
        prediction: int,
        configs: Any,
    ) -> None:
        pass


class CQLEvaluator:
    """Main CQL evaluation engine.

    This class provides methods for:
    - Parsing and compiling CQL libraries
    - Evaluating CQL expressions
    - Evaluating named definitions within libraries
    - Managing library dependencies

    Example:
        evaluator = CQLEvaluator()

        # Load a library
        library = evaluator.compile('''
            library Example version '1.0'
            using FHIR version '4.0.1'
            define Sum: 1 + 2 + 3
        ''')

        # Evaluate a definition
        result = evaluator.evaluate_definition("Sum")
        # Returns: 6

        # Evaluate an inline expression
        result = evaluator.evaluate_expression("1 + 2 * 3")
        # Returns: 7
    """

    def __init__(
        self,
        data_source: DataSource | None = None,
        library_manager: LibraryManager | None = None,
        library_resolver: LibraryResolver | None = None,
        library_paths: list[Path | str] | None = None,
        plugin_registry: CQLPluginRegistry | None = None,
        include_builtins: bool = True,
        fhir_binding: FhirVersionBinding | None = None,
    ):
        """Initialize the CQL evaluator.

        Args:
            data_source: Optional data source for retrieve operations
            library_manager: Optional library manager for dependencies
            library_resolver: Optional library resolver for loading includes
            library_paths: Optional list of directories to search for libraries
            plugin_registry: Optional plugin registry for custom functions
            include_builtins: Whether to include built-in libraries like FHIRHelpers (default True)
            fhir_binding: FHIR version binding; the installed default is used when omitted
        """
        self._fhir_binding = resolve_binding(fhir_binding)
        self._library_manager = library_manager or LibraryManager()
        self._data_source = data_source
        self._plugin_registry = plugin_registry
        self._current_library: CQLLibrary | None = None
        self._expression_cache: dict[str, cqlParser.ExpressionContext] = {}

        # Build resolver chain: user resolver -> builtins -> file paths
        resolvers: list[LibraryResolver] = []

        if library_resolver:
            resolvers.append(library_resolver)

        if include_builtins and self._fhir_binding.builtin_libraries:
            builtin_resolver = InMemoryLibraryResolver()
            for builtin in self._fhir_binding.builtin_libraries:
                builtin_resolver.add_library(builtin.name, builtin.source, builtin.version)
            resolvers.append(builtin_resolver)

        if library_paths:
            resolvers.append(FileLibraryResolver(library_paths))

        # Set up combined resolver
        if len(resolvers) == 1:
            self._library_manager.set_resolver(resolvers[0])
        elif len(resolvers) > 1:
            self._library_manager.set_resolver(CompositeLibraryResolver(resolvers))

        # Set compile function for library manager to resolve includes
        self._library_manager.set_compile_function(self._compile_source)

    @property
    def fhir_binding(self) -> FhirVersionBinding:
        """Get the FHIR version binding this evaluator was built with."""
        return self._fhir_binding

    @property
    def library_manager(self) -> LibraryManager:
        """Get the library manager."""
        return self._library_manager

    @property
    def current_library(self) -> CQLLibrary | None:
        """Get the currently loaded library."""
        return self._current_library

    @property
    def plugin_registry(self) -> CQLPluginRegistry | None:
        """Get the plugin registry."""
        return self._plugin_registry

    @plugin_registry.setter
    def plugin_registry(self, value: CQLPluginRegistry | None) -> None:
        """Set the plugin registry."""
        self._plugin_registry = value

    def compile(self, source: str) -> CQLLibrary:
        """Compile CQL source code into a library.

        Args:
            source: CQL source code

        Returns:
            Compiled CQLLibrary

        Raises:
            CQLError: If compilation fails
        """
        tree = self._parse_library(source)
        context = CQLContext(
            library_manager=self._library_manager,
            data_source=self._data_source,
            plugin_registry=self._plugin_registry,
        )
        visitor = CQLEvaluatorVisitor(context)

        library = visitor.visit(tree)
        if not isinstance(library, CQLLibrary):
            raise CQLError("Failed to compile library")

        library.source = source
        self._library_manager.add_library(library)
        self._current_library = library

        return library

    def _compile_source(self, source: str) -> CQLLibrary | None:
        """Internal compile method used by library manager for resolving includes.

        This method doesn't update current_library, which is important when
        resolving includes during compilation.

        Args:
            source: CQL source code

        Returns:
            Compiled CQLLibrary or None if compilation fails
        """
        try:
            tree = self._parse_library(source)
            context = CQLContext(
                library_manager=self._library_manager,
                data_source=self._data_source,
                plugin_registry=self._plugin_registry,
            )
            visitor = CQLEvaluatorVisitor(context)

            library = visitor.visit(tree)
            if not isinstance(library, CQLLibrary):
                return None

            library.source = source
            return library
        except Exception:
            return None

    def load_library(self, name: str, version: str | None = None) -> CQLLibrary | None:
        """Load a library by name.

        Args:
            name: Library name
            version: Optional library version

        Returns:
            CQLLibrary or None if not found
        """
        library = self._library_manager.get_library(name, version)
        if library:
            self._current_library = library
        return library

    def evaluate_definition(
        self,
        definition_name: str,
        resource: ResourceInput | None = None,
        parameters: dict[str, Any] | None = None,
        library: CQLLibrary | None = None,
    ) -> Any:
        """Evaluate a named definition within a library.

        Args:
            definition_name: Name of the definition to evaluate
            resource: Optional context resource (e.g., Patient), as a wire dict or a pydantic model
            parameters: Optional parameter values
            library: Optional library (uses current library if not specified)

        Returns:
            Evaluation result

        Raises:
            CQLError: If definition not found or evaluation fails
        """
        lib = library or self._current_library
        if not lib:
            raise CQLError("No library loaded")

        definition = lib.get_definition(definition_name)
        if not definition:
            raise CQLError(f"Definition not found: {definition_name}")

        if not definition.expression_tree:
            raise CQLError(f"Definition has no expression: {definition_name}")

        # Create context
        context = CQLContext(
            resource=resource,
            library=lib,
            library_manager=self._library_manager,
            data_source=self._data_source,
            plugin_registry=self._plugin_registry,
        )

        # Set parameters
        if parameters:
            for name, value in parameters.items():
                context.set_parameter(name, value)

        # Evaluate
        visitor = CQLEvaluatorVisitor(context)
        visitor._library = lib

        return visitor.visit(definition.expression_tree)

    def evaluate_expression(
        self,
        expression: str,
        resource: ResourceInput | None = None,
        parameters: dict[str, Any] | None = None,
        library: CQLLibrary | None = None,
    ) -> Any:
        """Evaluate a CQL expression.

        Args:
            expression: CQL expression to evaluate
            resource: Optional context resource, as a wire dict or a pydantic model
            parameters: Optional parameter values
            library: Optional library context for definition resolution

        Returns:
            Evaluation result

        Raises:
            CQLError: If evaluation fails
        """
        tree = self._parse_expression(expression)

        lib = library or self._current_library
        context = CQLContext(
            resource=resource,
            library=lib,
            library_manager=self._library_manager,
            data_source=self._data_source,
            plugin_registry=self._plugin_registry,
        )

        # Set parameters
        if parameters:
            for name, value in parameters.items():
                context.set_parameter(name, value)

        visitor = CQLEvaluatorVisitor(context)
        if lib:
            visitor._library = lib

        return visitor.visit(tree)

    def evaluate_all_definitions(
        self,
        resource: ResourceInput | None = None,
        parameters: dict[str, Any] | None = None,
        library: CQLLibrary | None = None,
    ) -> dict[str, Any]:
        """Evaluate all definitions in a library.

        Args:
            resource: Optional context resource, as a wire dict or a pydantic model
            parameters: Optional parameter values
            library: Optional library (uses current library if not specified)

        Returns:
            Dictionary mapping definition names to their values

        Raises:
            CQLError: If no library loaded
        """
        lib = library or self._current_library
        if not lib:
            raise CQLError("No library loaded")

        results: dict[str, Any] = {}

        # Create context
        context = CQLContext(
            resource=resource,
            library=lib,
            library_manager=self._library_manager,
            data_source=self._data_source,
            plugin_registry=self._plugin_registry,
        )

        # Set parameters
        if parameters:
            for name, value in parameters.items():
                context.set_parameter(name, value)

        visitor = CQLEvaluatorVisitor(context)
        visitor._library = lib

        for name, definition in lib.definitions.items():
            if definition.expression_tree:
                try:
                    results[name] = visitor.visit(definition.expression_tree)
                except Exception as e:
                    results[name] = CQLError(f"Error evaluating {name}: {e}")

        return results

    def get_definitions(self, library: CQLLibrary | None = None) -> list[str]:
        """Get list of definition names in a library.

        Args:
            library: Optional library (uses current library if not specified)

        Returns:
            List of definition names
        """
        lib = library or self._current_library
        if not lib:
            return []
        return list(lib.definitions.keys())

    def get_parameters(self, library: CQLLibrary | None = None) -> dict[str, Any]:
        """Get parameter definitions from a library.

        Args:
            library: Optional library (uses current library if not specified)

        Returns:
            Dictionary mapping parameter names to their default values
        """
        lib = library or self._current_library
        if not lib:
            return {}
        return {name: param.default_value for name, param in lib.parameters.items()}

    def to_elm(self, source: str | None = None) -> Any:
        """Convert CQL source to ELM (Expression Logical Model).

        Args:
            source: CQL source code. If not provided, uses the source
                from the current library.

        Returns:
            ELMLibrary model instance.

        Raises:
            CQLError: If no source is available or conversion fails.

        Example:
            evaluator = CQLEvaluator()
            evaluator.compile("library Test define Sum: 1 + 2")
            elm = evaluator.to_elm()
        """
        global ELMSerializer, ELMLibrary
        if ELMSerializer is None:
            from ..elm.models.library import ELMLibrary as _ELMLibrary
            from ..elm.serializer import ELMSerializer as _ELMSerializer

            ELMSerializer = _ELMSerializer
            ELMLibrary = _ELMLibrary

        # Get source
        if source is None:
            if self._current_library and self._current_library.source:
                source = self._current_library.source
            else:
                raise CQLError("No CQL source available. Provide source or compile a library first.")

        try:
            serializer = ELMSerializer()
            return serializer.serialize_to_model(source)
        except Exception as e:
            raise CQLError(f"Failed to convert to ELM: {e}") from e

    def to_elm_json(self, source: str | None = None, indent: int = 2) -> str:
        """Convert CQL source to ELM JSON string.

        Args:
            source: CQL source code. If not provided, uses the source
                from the current library.
            indent: JSON indentation level (default 2).

        Returns:
            ELM library as JSON string.

        Raises:
            CQLError: If no source is available or conversion fails.

        Example:
            evaluator = CQLEvaluator()
            evaluator.compile("library Test define Sum: 1 + 2")
            elm_json = evaluator.to_elm_json()
            print(elm_json)
        """
        global ELMSerializer
        if ELMSerializer is None:
            from ..elm.serializer import ELMSerializer as _ELMSerializer

            ELMSerializer = _ELMSerializer

        # Get source
        if source is None:
            if self._current_library and self._current_library.source:
                source = self._current_library.source
            else:
                raise CQLError("No CQL source available. Provide source or compile a library first.")

        try:
            serializer = ELMSerializer()
            return serializer.serialize_library_json(source, indent)
        except Exception as e:
            raise CQLError(f"Failed to convert to ELM JSON: {e}") from e

    def to_elm_dict(self, source: str | None = None) -> dict[str, Any]:
        """Convert CQL source to ELM dictionary.

        Args:
            source: CQL source code. If not provided, uses the source
                from the current library.

        Returns:
            ELM library as dictionary.

        Raises:
            CQLError: If no source is available or conversion fails.
        """
        global ELMSerializer
        if ELMSerializer is None:
            from ..elm.serializer import ELMSerializer as _ELMSerializer

            ELMSerializer = _ELMSerializer

        # Get source
        if source is None:
            if self._current_library and self._current_library.source:
                source = self._current_library.source
            else:
                raise CQLError("No CQL source available. Provide source or compile a library first.")

        try:
            serializer = ELMSerializer()
            return serializer.serialize_library(source)
        except Exception as e:
            raise CQLError(f"Failed to convert to ELM dict: {e}") from e

    def _parse_library(self, source: str) -> cqlParser.LibraryContext:
        """Parse CQL library source code."""
        try:
            input_stream = InputStream(source)
            lexer = cqlLexer(input_stream)
            token_stream = CommonTokenStream(lexer)
            parser = cqlParser(token_stream)

            parser.removeErrorListeners()
            parser.addErrorListener(CQLErrorListener())

            library: cqlParser.LibraryContext = parser.library()
            return library

        except CQLError:
            raise
        except Exception as e:
            raise CQLError(f"Failed to parse library: {e}") from e

    def _parse_expression(self, expression: str) -> cqlParser.ExpressionContext:
        """Parse a single CQL expression, which must be the whole of the text it was given."""
        if expression in self._expression_cache:
            return self._expression_cache[expression]

        try:
            input_stream = InputStream(expression)
            lexer = cqlLexer(input_stream)
            token_stream = CommonTokenStream(lexer)
            parser = cqlParser(token_stream)

            parser.removeErrorListeners()
            parser.addErrorListener(CQLErrorListener())

            tree: cqlParser.ExpressionContext = parser.expression()
            require_end_of_input(parser)
            self._expression_cache[expression] = tree
            return tree

        except CQLError:
            raise
        except Exception as e:
            raise CQLError(f"Failed to parse expression: {expression}") from e

    def clear_cache(self) -> None:
        """Clear expression parse cache."""
        self._expression_cache.clear()


def compile_library(source: str) -> CQLLibrary:
    """Convenience function to compile a CQL library.

    Args:
        source: CQL source code

    Returns:
        Compiled CQLLibrary
    """
    evaluator = CQLEvaluator()
    return evaluator.compile(source)


def evaluate(expression: str, resource: ResourceInput | None = None) -> Any:
    """Convenience function to evaluate a CQL expression.

    Args:
        expression: CQL expression
        resource: Optional context resource, as a wire dict or a pydantic model

    Returns:
        Evaluation result
    """
    evaluator = CQLEvaluator()
    return evaluator.evaluate_expression(expression, resource)
