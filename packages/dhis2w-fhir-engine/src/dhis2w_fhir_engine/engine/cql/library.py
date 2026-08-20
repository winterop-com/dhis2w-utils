"""CQL Library management.

This module handles:
- Parsing CQL libraries from source
- Storing library definitions (expressions, functions, parameters, etc.)
- Loading and caching compiled libraries
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from .types import CQLCode, CQLConcept

if TYPE_CHECKING:
    from .library_resolver import LibraryResolver


class UsingDefinition(BaseModel):
    """Represents a 'using' statement (e.g., using FHIR version '4.0.1')."""

    model_config = ConfigDict(frozen=True)

    model: str
    version: str | None = None


class IncludeDefinition(BaseModel):
    """Represents an 'include' statement for library dependencies."""

    model_config = ConfigDict(frozen=True)

    library: str
    version: str | None = None
    alias: str | None = None


class ParameterDefinition(BaseModel):
    """Represents a parameter definition."""

    name: str
    type_specifier: str | None = None
    default_value: Any = None


class CodeSystemDefinition(BaseModel):
    """Represents a codesystem definition."""

    model_config = ConfigDict(frozen=True)

    name: str
    id: str
    version: str | None = None


class ValueSetDefinition(BaseModel):
    """Represents a valueset definition."""

    name: str
    id: str
    version: str | None = None
    codesystems: list[str] = Field(default_factory=list)


class CodeDefinition(BaseModel):
    """Represents a code definition."""

    name: str
    code: str
    codesystem: str
    display: str | None = None

    def to_cql_code(self, codesystem_url: str) -> CQLCode:
        """Convert to CQLCode with resolved codesystem URL."""
        return CQLCode(code=self.code, system=codesystem_url, display=self.display)


class ConceptDefinition(BaseModel):
    """Represents a concept definition."""

    name: str
    codes: list[str]  # References to code definitions
    display: str | None = None


class ExpressionDefinition(BaseModel):
    """Represents an expression definition (define statement)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    context: str | None = None  # Patient, Unfiltered, etc.
    access_modifier: str | None = None  # public, private
    expression_tree: Any = None  # The parsed expression AST


class FunctionDefinition(BaseModel):
    """Represents a function definition."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    parameters: list[tuple[str, str]] = Field(default_factory=list)  # (name, type) pairs
    return_type: str | None = None
    body_tree: Any = None  # The parsed function body AST
    fluent: bool = False
    external: bool = False


class CQLLibrary(BaseModel):
    """Represents a parsed CQL library.

    Contains all definitions from a CQL library file:
    - Library name and version
    - Model declarations (using)
    - Library dependencies (include)
    - Codesystem/valueset/code/concept definitions
    - Parameters
    - Expression and function definitions
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    version: str | None = None

    # Model and dependencies
    using: list[UsingDefinition] = Field(default_factory=list)
    includes: list[IncludeDefinition] = Field(default_factory=list)

    # Terminology definitions
    codesystems: dict[str, CodeSystemDefinition] = Field(default_factory=dict)
    valuesets: dict[str, ValueSetDefinition] = Field(default_factory=dict)
    codes: dict[str, CodeDefinition] = Field(default_factory=dict)
    concepts: dict[str, ConceptDefinition] = Field(default_factory=dict)

    # Parameters
    parameters: dict[str, ParameterDefinition] = Field(default_factory=dict)

    # Context definitions
    contexts: list[str] = Field(default_factory=list)
    current_context: str = "Patient"

    # Expression and function definitions
    definitions: dict[str, ExpressionDefinition] = Field(default_factory=dict)
    functions: dict[str, list[FunctionDefinition]] = Field(default_factory=dict)  # Overloaded functions

    # Source tracking
    source: str | None = None

    def add_definition(self, definition: ExpressionDefinition) -> None:
        """Add an expression definition."""
        self.definitions[definition.name] = definition

    def add_function(self, function: FunctionDefinition) -> None:
        """Add a function definition (supports overloading)."""
        if function.name not in self.functions:
            self.functions[function.name] = []
        self.functions[function.name].append(function)

    def get_definition(self, name: str) -> ExpressionDefinition | None:
        """Get an expression definition by name."""
        return self.definitions.get(name)

    def get_function(self, name: str, arg_count: int | None = None) -> FunctionDefinition | None:
        """Get a function definition by name and optional argument count."""
        funcs = self.functions.get(name)
        if not funcs:
            return None
        if arg_count is None:
            return funcs[0]
        for func in funcs:
            if len(func.parameters) == arg_count:
                return func
        return funcs[0]  # Default to first if no exact match

    def resolve_code(self, name: str) -> CQLCode | None:
        """Resolve a code reference to a CQLCode value."""
        code_def = self.codes.get(name)
        if not code_def:
            return None

        # Resolve codesystem URL
        codesystem = self.codesystems.get(code_def.codesystem)
        if not codesystem:
            return None

        return code_def.to_cql_code(codesystem.id)

    def resolve_concept(self, name: str) -> CQLConcept | None:
        """Resolve a concept reference to a CQLConcept value."""
        concept_def = self.concepts.get(name)
        if not concept_def:
            return None

        codes = []
        for code_ref in concept_def.codes:
            code = self.resolve_code(code_ref)
            if code:
                codes.append(code)

        return CQLConcept(codes=tuple(codes), display=concept_def.display)

    def __str__(self) -> str:
        version_str = f" version '{self.version}'" if self.version else ""
        return f"library {self.name}{version_str}"


class LibraryManager:
    """Manages loading and caching of CQL libraries.

    Supports library resolution through configurable resolvers that can
    load libraries from the filesystem, memory, or other sources.
    """

    def __init__(self) -> None:
        from .library_resolver import LibraryResolver

        self._cache: dict[str, CQLLibrary] = {}
        self._sources: dict[str, str] = {}  # library name -> source path/content
        self._resolver: LibraryResolver | None = None
        # Set by the evaluator so resolved sources can be compiled on demand
        self._compile_function: Callable[[str], CQLLibrary | None] | None = None

    def set_resolver(self, resolver: "LibraryResolver") -> None:
        """Set the library resolver for loading dependencies.

        Args:
            resolver: Resolver to use for finding library sources
        """
        self._resolver = resolver

    def set_compile_function(self, compile_function: Callable[[str], "CQLLibrary | None"]) -> None:
        """Set the compilation function for compiling resolved sources.

        Args:
            compile_function: Function that takes source code and returns a CQLLibrary
        """
        self._compile_function = compile_function

    def register_source(self, name: str, source: str) -> None:
        """Register a library source by name."""
        self._sources[name] = source

    def get_library(self, name: str, version: str | None = None) -> CQLLibrary | None:
        """Get a library by name, loading if necessary.

        If the library is not in cache, attempts to resolve it using the
        configured resolver.

        Args:
            name: Library name
            version: Optional version string

        Returns:
            The loaded library, or None if not found
        """
        cache_key = f"{name}|{version or ''}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try to resolve and compile the library
        if self._resolver and self._compile_function:
            source = self._resolver.resolve(name, version)
            if source:
                library = self._compile_function(source)
                if library:
                    self.add_library(library)
                    return library

        return None

    def resolve_includes(self, library: CQLLibrary) -> dict[str, CQLLibrary]:
        """Resolve all include dependencies for a library.

        Args:
            library: The library with includes to resolve

        Returns:
            Dictionary mapping alias (or name) to resolved library
        """
        resolved: dict[str, CQLLibrary] = {}

        for include in library.includes:
            alias = include.alias or include.library
            included = self.get_library(include.library, include.version)
            if included:
                resolved[alias] = included

        return resolved

    def add_library(self, library: CQLLibrary) -> None:
        """Add a compiled library to the cache."""
        cache_key = f"{library.name}|{library.version or ''}"
        self._cache[cache_key] = library

    def clear_cache(self) -> None:
        """Clear the library cache."""
        self._cache.clear()

    def list_libraries(self) -> list[str]:
        """List all loaded library names."""
        return [lib.name for lib in self._cache.values()]
