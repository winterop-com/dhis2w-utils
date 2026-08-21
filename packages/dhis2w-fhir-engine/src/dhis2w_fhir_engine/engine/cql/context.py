"""CQL execution context.

Extends the base EvaluationContext with CQL-specific features:
- Library management
- Query alias resolution
- Parameter values
- Definition evaluation caching
"""

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from ...ingest import ResourceInput, as_resource_dict
from ..context import EvaluationContext, ModelProvider

if TYPE_CHECKING:
    from .library import CQLLibrary, LibraryManager
    from .plugins import CQLPluginRegistry


class DataSource(Protocol):
    """Protocol for CQL data retrieval."""

    def retrieve(
        self,
        resource_type: str,
        context: "CQLContext | None" = None,
        code_path: str | None = None,
        codes: list[Any] | None = None,
        valueset: str | None = None,
        date_path: str | None = None,
        date_range: Any | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Retrieve resources of a given type with optional filters."""
        ...

    def resolve_reference(self, reference: str) -> dict[str, Any] | None:
        """Resolve a FHIR reference to a resource."""
        ...


class CQLContext(EvaluationContext):
    """CQL-specific evaluation context.

    Extends EvaluationContext with:
    - Library management and resolution
    - Query alias scopes
    - Parameter binding
    - Definition result caching
    - Data source integration
    """

    def __init__(
        self,
        resource: ResourceInput | None = None,
        root_resource: ResourceInput | None = None,
        model: ModelProvider | None = None,
        now: datetime | None = None,
        reference_resolver: Callable[[str], dict[str, Any] | None] | None = None,
        library: "CQLLibrary | None" = None,
        library_manager: "LibraryManager | None" = None,
        data_source: DataSource | None = None,
        plugin_registry: "CQLPluginRegistry | None" = None,
    ):
        """Initialize CQL evaluation context.

        Args:
            resource: Current context resource (e.g., Patient), as a wire dict or a pydantic model
            root_resource: Root resource for nested evaluations, dict or model
            model: FHIR model provider for type information
            now: Fixed datetime for Today()/Now() functions
            reference_resolver: Callback to resolve FHIR references
            library: Current CQL library being evaluated
            library_manager: Manager for loading/caching libraries
            data_source: Source for retrieve operations
            plugin_registry: Optional registry for custom plugin functions
        """
        super().__init__(
            resource=resource,
            root_resource=root_resource,
            model=model,
            now=now,
            reference_resolver=reference_resolver,
        )

        self._library = library
        self._library_manager = library_manager
        self._data_source = data_source
        self._plugin_registry = plugin_registry

        # Query alias stack for nested queries
        self._alias_scopes: list[dict[str, Any]] = [{}]

        # Parameter values
        self._parameters: dict[str, Any] = {}

        # Definition evaluation cache (for memoization)
        self._definition_cache: dict[str, Any] = {}

        # Evaluation stack to detect recursion
        self._eval_stack: set[str] = set()

    @property
    def library(self) -> "CQLLibrary | None":
        """Get the current library."""
        return self._library

    @library.setter
    def library(self, value: "CQLLibrary | None") -> None:
        """Set the current library."""
        self._library = value

    @property
    def library_manager(self) -> "LibraryManager | None":
        """Get the library manager."""
        return self._library_manager

    @property
    def data_source(self) -> DataSource | None:
        """Get the data source."""
        return self._data_source

    @data_source.setter
    def data_source(self, value: DataSource | None) -> None:
        """Set the data source."""
        self._data_source = value

    @property
    def plugin_registry(self) -> "CQLPluginRegistry | None":
        """Get the plugin registry."""
        return self._plugin_registry

    @plugin_registry.setter
    def plugin_registry(self, value: "CQLPluginRegistry | None") -> None:
        """Set the plugin registry."""
        self._plugin_registry = value

    # Alias scope management for queries

    def push_alias_scope(self) -> None:
        """Push a new alias scope for nested queries."""
        self._alias_scopes.append({})

    def pop_alias_scope(self) -> dict[str, Any]:
        """Pop the current alias scope."""
        if len(self._alias_scopes) > 1:
            return self._alias_scopes.pop()
        return {}

    def push_scope(self) -> None:
        """Alias for push_alias_scope for query execution."""
        self.push_alias_scope()

    def pop_scope(self) -> dict[str, Any]:
        """Alias for pop_alias_scope for query execution."""
        return self.pop_alias_scope()

    def set_alias(self, name: str, value: Any) -> None:
        """Set an alias in the current scope."""
        self._alias_scopes[-1][name] = value

    def get_alias(self, name: str) -> Any | None:
        """Get an alias value, searching from innermost to outermost scope."""
        for scope in reversed(self._alias_scopes):
            if name in scope:
                return scope[name]
        return None

    def has_alias(self, name: str) -> bool:
        """Check if an alias exists in any scope."""
        return any(name in scope for scope in reversed(self._alias_scopes))

    # Parameter management

    def set_parameter(self, name: str, value: Any) -> None:
        """Set a parameter value."""
        self._parameters[name] = value

    def get_parameter(self, name: str) -> Any | None:
        """Get a parameter value."""
        if name in self._parameters:
            return self._parameters[name]
        # Check library default
        if self._library and name in self._library.parameters:
            return self._library.parameters[name].default_value
        return None

    def has_parameter(self, name: str) -> bool:
        """Check if a parameter is defined."""
        return name in self._parameters or (self._library is not None and name in self._library.parameters)

    # Definition caching

    def get_cached_definition(self, name: str) -> tuple[bool, Any]:
        """Get a cached definition result. Returns (found, value)."""
        if name in self._definition_cache:
            return (True, self._definition_cache[name])
        return (False, None)

    def cache_definition(self, name: str, value: Any) -> None:
        """Cache a definition result."""
        self._definition_cache[name] = value

    def clear_definition_cache(self) -> None:
        """Clear the definition cache."""
        self._definition_cache.clear()

    # Recursion detection

    def start_evaluation(self, name: str) -> bool:
        """Start evaluating a definition. Returns False if recursive."""
        if name in self._eval_stack:
            return False
        self._eval_stack.add(name)
        return True

    def end_evaluation(self, name: str) -> None:
        """End evaluating a definition."""
        self._eval_stack.discard(name)

    # Library resolution

    def resolve_library(self, alias: str) -> "CQLLibrary | None":
        """Resolve a library by its alias.

        When no alias is specified in the include statement, the library name
        is used as the alias.
        """
        if not self._library or not self._library_manager:
            return None

        for include in self._library.includes:
            # Match by explicit alias, or by library name if no alias was specified
            effective_alias = include.alias or include.library
            if effective_alias == alias:
                return self._library_manager.get_library(include.library, include.version)

        return None

    # Override child context creation

    def child(self, resource: ResourceInput | None = None) -> "CQLContext":
        """Create a child context for nested evaluations, from a wire dict or a pydantic model."""
        child_ctx = CQLContext(
            resource=as_resource_dict(resource) or self.resource,
            root_resource=self.root_resource,
            model=self.model,
            now=self.now,
            reference_resolver=self.reference_resolver,
            library=self._library,
            library_manager=self._library_manager,
            data_source=self._data_source,
            plugin_registry=self._plugin_registry,
        )
        child_ctx._constants = self._constants.copy()
        child_ctx._function_overrides = self._function_overrides.copy()
        child_ctx._parameters = self._parameters.copy()
        # Alias scopes are NOT copied - child starts fresh
        # Definition cache is shared
        child_ctx._definition_cache = self._definition_cache
        child_ctx._eval_stack = self._eval_stack
        return child_ctx

    def for_query_source(self, alias: str, value: Any) -> "CQLContext":
        """Create a context for evaluating within a query source."""
        child = self.child()
        child.push_alias_scope()
        child.set_alias(alias, value)
        return child


class PatientContext(CQLContext):
    """Patient-centric evaluation context.

    Used when evaluating CQL with 'context Patient'.
    The resource is expected to be a Patient resource.
    """

    @property
    def patient(self) -> dict[str, Any] | None:
        """Get the current patient resource."""
        return self.resource


class UnfilteredContext(CQLContext):
    """Unfiltered (population-level) evaluation context.

    Used when evaluating CQL with 'context Unfiltered'.
    No automatic filtering by patient is applied.
    """

    pass


class EncounterContext(CQLContext):
    """Encounter-scoped evaluation context.

    Used when evaluating CQL with 'context Encounter'.
    Contains both patient and encounter resources.
    """

    def __init__(
        self,
        patient: ResourceInput | None = None,
        encounter: ResourceInput | None = None,
        **kwargs: Any,
    ):
        """Initialize an encounter-scoped context from wire dicts or pydantic models."""
        super().__init__(resource=encounter, **kwargs)
        self._patient = as_resource_dict(patient)

    @property
    def patient(self) -> dict[str, Any] | None:
        """Get the patient resource."""
        return self._patient

    @property
    def encounter(self) -> dict[str, Any] | None:
        """Get the encounter resource."""
        return self.resource
