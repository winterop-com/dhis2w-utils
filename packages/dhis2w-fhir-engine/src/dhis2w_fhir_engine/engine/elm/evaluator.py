"""ELM evaluator - main entry point for executing ELM libraries.

This module provides the ELMEvaluator class for loading and executing
ELM (Expression Logical Model) JSON libraries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dhis2w_fhir_engine.engine.cql.context import CQLContext, DataSource
from dhis2w_fhir_engine.engine.cql.library import LibraryManager
from dhis2w_fhir_engine.engine.elm.exceptions import ELMExecutionError, ELMReferenceError, ELMValidationError
from dhis2w_fhir_engine.engine.elm.loader import ELMLoader
from dhis2w_fhir_engine.engine.elm.models.library import ELMDefinition, ELMFunctionDef, ELMLibrary
from dhis2w_fhir_engine.engine.elm.visitor import ELMExpressionVisitor
from dhis2w_fhir_engine.ingest import ResourceInput


class ELMEvaluator:
    """Main ELM evaluation engine.

    This class provides methods for:
    - Loading ELM JSON libraries from files, strings, or dictionaries
    - Evaluating named definitions within libraries
    - Evaluating all definitions in a library
    - Managing library dependencies

    Example:
        evaluator = ELMEvaluator()

        # Load from JSON string
        library = evaluator.load('''
            {
                "library": {
                    "identifier": {"id": "Example", "version": "1.0"},
                    "statements": {
                        "def": [{
                            "name": "Sum",
                            "expression": {
                                "type": "Add",
                                "operand": [
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"}
                                ]
                            }
                        }]
                    }
                }
            }
        ''')

        # Evaluate a definition
        result = evaluator.evaluate_definition("Sum")
        # Returns: 3
    """

    def __init__(
        self,
        data_source: DataSource | None = None,
        library_manager: LibraryManager | None = None,
    ):
        """Initialize the ELM evaluator.

        Args:
            data_source: Optional data source for retrieve operations.
            library_manager: Optional library manager for dependencies.
        """
        self._library_manager = library_manager or LibraryManager()
        self._data_source = data_source
        self._current_library: ELMLibrary | None = None
        self._elm_libraries: dict[str, ELMLibrary] = {}

    @property
    def library_manager(self) -> LibraryManager:
        """Get the library manager."""
        return self._library_manager

    @property
    def current_library(self) -> ELMLibrary | None:
        """Get the currently loaded ELM library."""
        return self._current_library

    def load(self, source: str | dict[str, Any] | Path) -> ELMLibrary:
        """Load an ELM library from various sources.

        Args:
            source: ELM source - can be:
                - str: JSON string or file path
                - dict: Parsed JSON dictionary
                - Path: Path to JSON file

        Returns:
            Parsed ELMLibrary object.

        Raises:
            ELMValidationError: If loading or parsing fails.
        """
        if isinstance(source, Path):
            library = ELMLoader.load_file(source)
        elif isinstance(source, dict):
            library = ELMLoader.parse(source)
        # The `str` arm and the `else` guard below both stay: `load` is reached from CLI arguments and
        # JSON payloads, so a caller can hand it a value the annotation does not admit.
        elif isinstance(source, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            # Check if it looks like JSON content first (starts with { or [)
            stripped = source.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                # It's JSON content
                library = ELMLoader.load_json(source)
            else:
                # Check if it's a file path
                try:
                    path = Path(source)
                    if path.exists() and path.is_file():
                        library = ELMLoader.load_file(path)
                    else:
                        # Try to parse as JSON anyway
                        library = ELMLoader.load_json(source)
                except (OSError, ValueError):
                    # If path check fails, try as JSON
                    library = ELMLoader.load_json(source)
        else:
            raise ELMValidationError(f"Unsupported source type: {type(source)}")

        # Register the library
        lib_id = library.identifier.id
        lib_version = library.identifier.version
        key = f"{lib_id}:{lib_version}" if lib_version else lib_id
        self._elm_libraries[key] = library
        self._current_library = library

        return library

    def load_file(self, path: str | Path) -> ELMLibrary:
        """Load an ELM library from a file.

        Args:
            path: Path to the ELM JSON file.

        Returns:
            Parsed ELMLibrary object.

        Raises:
            ELMValidationError: If loading fails.
        """
        return self.load(Path(path))

    def get_elm_library(self, name: str, version: str | None = None) -> ELMLibrary | None:
        """Get a loaded ELM library by name.

        Args:
            name: Library identifier.
            version: Optional library version.

        Returns:
            ELMLibrary or None if not found.
        """
        if version:
            key = f"{name}:{version}"
            if key in self._elm_libraries:
                return self._elm_libraries[key]

        # Try without version
        if name in self._elm_libraries:
            return self._elm_libraries[name]

        # Search for any version
        for candidate in self._elm_libraries.values():
            if candidate.identifier.id == name and (version is None or candidate.identifier.version == version):
                return candidate

        return None

    def evaluate_definition(
        self,
        definition_name: str,
        resource: ResourceInput | None = None,
        parameters: dict[str, Any] | None = None,
        library: ELMLibrary | None = None,
    ) -> Any:
        """Evaluate a named definition within an ELM library.

        Args:
            definition_name: Name of the definition to evaluate.
            resource: Optional context resource (e.g., Patient), as a wire dict or a pydantic model.
            parameters: Optional parameter values.
            library: Optional library (uses current library if not specified).

        Returns:
            Evaluation result.

        Raises:
            ELMExecutionError: If no library is loaded.
            ELMReferenceError: If definition is not found.
        """
        lib = library or self._current_library
        if not lib:
            raise ELMExecutionError("No ELM library loaded")

        definition = lib.get_definition(definition_name)
        if not definition:
            # Also check functions
            func = lib.get_function(definition_name)
            if not func:
                raise ELMReferenceError(f"Definition not found: {definition_name}")
            return self._evaluate_function(func, [], resource, parameters, lib)

        return self._evaluate_definition_impl(definition, resource, parameters, lib)

    def _evaluate_definition_impl(
        self,
        definition: ELMDefinition,
        resource: ResourceInput | None,
        parameters: dict[str, Any] | None,
        library: ELMLibrary,
    ) -> Any:
        """Internal implementation for evaluating a definition.

        Args:
            definition: The definition to evaluate.
            resource: Optional context resource, as a wire dict or a pydantic model.
            parameters: Optional parameter values.
            library: The containing library.

        Returns:
            Evaluation result.
        """
        # Create context
        context = CQLContext(
            resource=resource,
            library_manager=self._library_manager,
            data_source=self._data_source,
        )

        # Set parameters from library defaults
        for param in library.parameters:
            if param.default is not None:
                # Evaluate default value
                visitor = ELMExpressionVisitor(context)
                visitor.set_library(library)
                default_value = visitor.evaluate(param.default)
                context.set_parameter(param.name, default_value)

        # Override with provided parameters
        if parameters:
            for name, value in parameters.items():
                context.set_parameter(name, value)

        # Evaluate
        visitor = ELMExpressionVisitor(context)
        visitor.set_library(library)

        # The expression is stored as a dict in the model
        expression = definition.expression
        if expression is None:
            return None

        # Convert to dict if it's a model
        if hasattr(expression, "model_dump"):
            expression = expression.model_dump(by_alias=True, exclude_none=True)

        return visitor.evaluate(expression)

    def _evaluate_function(
        self,
        func: ELMFunctionDef,
        args: list[Any],
        resource: ResourceInput | None,
        parameters: dict[str, Any] | None,
        library: ELMLibrary,
    ) -> Any:
        """Evaluate a function definition.

        Args:
            func: The function definition.
            args: Function arguments.
            resource: Optional context resource, as a wire dict or a pydantic model.
            parameters: Optional parameter values.
            library: The containing library.

        Returns:
            Evaluation result.
        """
        if func.external:
            raise ELMExecutionError(f"External function not implemented: {func.name}")

        if func.expression is None:
            raise ELMExecutionError(f"Function has no expression: {func.name}")

        # Create context
        context = CQLContext(
            resource=resource,
            library_manager=self._library_manager,
            data_source=self._data_source,
        )

        # Set parameters
        if parameters:
            for name, value in parameters.items():
                context.set_parameter(name, value)

        # Bind function arguments as operands using alias scope
        context.push_alias_scope()
        for i, operand in enumerate(func.operand):
            if i < len(args):
                context.set_alias(operand.name, args[i])

        # Evaluate
        try:
            visitor = ELMExpressionVisitor(context)
            visitor.set_library(library)

            expression = func.expression
            if hasattr(expression, "model_dump"):
                expression = expression.model_dump(by_alias=True, exclude_none=True)

            return visitor.evaluate(expression)
        finally:
            context.pop_alias_scope()

    def evaluate_all_definitions(
        self,
        resource: ResourceInput | None = None,
        parameters: dict[str, Any] | None = None,
        library: ELMLibrary | None = None,
        include_private: bool = False,
    ) -> dict[str, Any]:
        """Evaluate all definitions in an ELM library.

        Args:
            resource: Optional context resource, as a wire dict or a pydantic model.
            parameters: Optional parameter values.
            library: Optional library (uses current library if not specified).
            include_private: Whether to include private definitions.

        Returns:
            Dictionary mapping definition names to their results.

        Raises:
            ELMExecutionError: If no library is loaded.
        """
        lib = library or self._current_library
        if not lib:
            raise ELMExecutionError("No ELM library loaded")

        results: dict[str, Any] = {}
        errors: dict[str, str] = {}

        for definition in lib.get_definitions():
            # Skip private definitions unless requested
            if not include_private and definition.accessLevel == "Private":
                continue

            try:
                results[definition.name] = self._evaluate_definition_impl(definition, resource, parameters, lib)
            except Exception as e:
                errors[definition.name] = str(e)

        # If any errors occurred, include them in results
        if errors:
            results["_errors"] = errors

        return results

    def get_definition_names(self, library: ELMLibrary | None = None, include_private: bool = False) -> list[str]:
        """Get names of all definitions in a library.

        Args:
            library: Optional library (uses current library if not specified).
            include_private: Whether to include private definitions.

        Returns:
            List of definition names.
        """
        lib = library or self._current_library
        if not lib:
            return []

        names = []
        for definition in lib.get_definitions():
            if not include_private and definition.accessLevel == "Private":
                continue
            names.append(definition.name)

        return names

    def get_function_names(self, library: ELMLibrary | None = None, include_private: bool = False) -> list[str]:
        """Get names of all functions in a library.

        Args:
            library: Optional library (uses current library if not specified).
            include_private: Whether to include private functions.

        Returns:
            List of function names.
        """
        lib = library or self._current_library
        if not lib:
            return []

        names = []
        for func in lib.get_functions():
            if not include_private and func.accessLevel == "Private":
                continue
            names.append(func.name)

        return names

    def get_library_info(self, library: ELMLibrary | None = None) -> dict[str, Any]:
        """Get summary information about a library.

        Args:
            library: Optional library (uses current library if not specified).

        Returns:
            Dictionary with library information.
        """
        lib = library or self._current_library
        if not lib:
            return {}

        return {
            "id": lib.identifier.id,
            "version": lib.identifier.version,
            "schemaIdentifier": (
                {
                    "id": lib.schemaIdentifier.id,
                    "version": lib.schemaIdentifier.version,
                }
                if lib.schemaIdentifier
                else None
            ),
            "usings": [{"localIdentifier": u.localIdentifier, "uri": u.uri, "version": u.version} for u in lib.usings],
            "includes": [
                {"localIdentifier": i.localIdentifier, "path": i.path, "version": i.version} for i in lib.includes
            ],
            "parameters": [p.name for p in lib.parameters],
            "codeSystems": [cs.name for cs in lib.codeSystems],
            "valueSets": [vs.name for vs in lib.valueSets],
            "codes": [c.name for c in lib.codes],
            "concepts": [c.name for c in lib.concepts],
            "definitions": self.get_definition_names(lib, include_private=True),
            "functions": self.get_function_names(lib, include_private=True),
        }

    def validate(self, source: str | dict[str, Any] | Path) -> tuple[bool, list[str]]:
        """Validate ELM without fully loading.

        Args:
            source: ELM source (JSON string, dict, or file path).

        Returns:
            Tuple of (is_valid, list of error messages).
        """
        try:
            if isinstance(source, Path):
                import json

                data = json.loads(source.read_text(encoding="utf-8"))
            elif isinstance(source, str):
                path = Path(source)
                if path.exists() and path.is_file():
                    import json

                    data = json.loads(path.read_text(encoding="utf-8"))
                else:
                    import json

                    data = json.loads(source)
            else:
                data = source

            errors = ELMLoader.validate(data)
            return len(errors) == 0, errors

        except Exception as e:
            return False, [str(e)]
