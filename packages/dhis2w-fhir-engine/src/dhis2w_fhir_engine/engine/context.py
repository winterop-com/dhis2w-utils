"""Evaluation context for FHIRPath and CQL."""

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from ..binding import FhirVersionBinding, resolve_binding
from ..ingest import ResourceInput, as_resource_dict


class TerminologyProvider(Protocol):
    """Protocol for the terminology operations FHIRPath calls during evaluation."""

    def member_of(self, valueset_url: str, code: str, system: str) -> bool:
        """Report whether a code is a member of a value set."""
        ...

    def subsumes(self, system: str, code_a: str, code_b: str) -> dict[str, Any]:
        """Report the subsumption relationship between two codes as a FHIR Parameters resource.

        The outcome sits in the `outcome` parameter's `valueCode` and reads `equivalent`, `subsumes`,
        `subsumed-by`, or `not-subsumed`.
        """
        ...


class ModelProvider(Protocol):
    """Protocol for FHIR model information (needed by CQL)."""

    def get_type_info(self, type_name: str) -> dict[str, Any]:
        """Get type information for a FHIR type."""
        ...

    def get_property_type(self, type_name: str, property_name: str) -> str | None:
        """Get the type of a property on a FHIR type."""
        ...


class EvaluationContext:
    """Context for FHIRPath/CQL expression evaluation.

    This context is designed to be extended by CQL for additional
    functionality like library management, retrieve operations, etc.
    """

    def __init__(
        self,
        resource: ResourceInput | None = None,
        root_resource: ResourceInput | None = None,
        model: ModelProvider | None = None,
        now: datetime | None = None,
        reference_resolver: Callable[[str], dict[str, Any] | None] | None = None,
        terminology_provider: TerminologyProvider | None = None,
        fhir_binding: FhirVersionBinding | None = None,
    ):
        """Initialize evaluation context.

        Args:
            resource: Current resource (%resource), as a wire dict or a pydantic model
            root_resource: Root resource for nested evaluations (%rootResource), dict or model
            model: FHIR model provider for type information
            now: Fixed datetime for today()/now() functions (useful for testing)
            reference_resolver: Callback to resolve FHIR references
            terminology_provider: Provider for terminology operations (memberOf, subsumes)
            fhir_binding: FHIR version binding; the installed default is used when omitted
        """
        self.resource = as_resource_dict(resource)
        self.root_resource = as_resource_dict(root_resource) or self.resource
        self.model = model
        self.now = now
        self.reference_resolver = reference_resolver
        self.terminology_provider = terminology_provider
        self.fhir_binding = resolve_binding(fhir_binding)

        # Variable stack for $this, $index, $total
        self._this_stack: list[Any] = []
        self._index_stack: list[int] = []
        self._total_stack: list[Any] = []

        # External constants (%name)
        self._constants: dict[str, Any] = {}

        # Custom function overrides
        self._function_overrides: dict[str, Callable[..., Any]] = {}

    @property
    def this(self) -> Any:
        """Get current $this value."""
        return self._this_stack[-1] if self._this_stack else None

    @property
    def index(self) -> int | None:
        """Get current $index value."""
        return self._index_stack[-1] if self._index_stack else None

    @property
    def total(self) -> Any:
        """Get current $total value (for aggregate)."""
        return self._total_stack[-1] if self._total_stack else None

    def push_this(self, value: Any) -> None:
        """Push a new $this value onto the stack."""
        self._this_stack.append(value)

    def pop_this(self) -> Any:
        """Pop $this value from the stack."""
        return self._this_stack.pop() if self._this_stack else None

    def push_index(self, value: int) -> None:
        """Push a new $index value onto the stack."""
        self._index_stack.append(value)

    def pop_index(self) -> int | None:
        """Pop $index value from the stack."""
        return self._index_stack.pop() if self._index_stack else None

    def push_total(self, value: Any) -> None:
        """Push a new $total value onto the stack."""
        self._total_stack.append(value)

    def pop_total(self) -> Any:
        """Pop $total value from the stack."""
        return self._total_stack.pop() if self._total_stack else None

    def set_constant(self, name: str, value: Any) -> None:
        """Set an external constant (%name)."""
        self._constants[name] = value

    # Standard FHIRPath environment constants
    _DEFAULT_CONSTANTS: dict[str, str] = {
        "sct": "http://snomed.info/sct",
        "loinc": "http://loinc.org",
        "ucum": "http://unitsofmeasure.org",
        "vs-administrative-gender": "http://hl7.org/fhir/ValueSet/administrative-gender",
    }

    def get_constant(self, name: str) -> Any:
        """Get an external constant (%name)."""
        if name == "resource":
            return self.resource
        if name == "rootResource":
            return self.root_resource
        if name == "context":
            return self.resource  # Default context is resource
        # Check user-defined constants first, then default FHIRPath constants
        if name in self._constants:
            return self._constants[name]
        return self._DEFAULT_CONSTANTS.get(name)

    def register_function(self, name: str, fn: Callable[..., Any]) -> None:
        """Register a custom function override."""
        self._function_overrides[name] = fn

    def get_function_override(self, name: str) -> Callable[..., Any] | None:
        """Get a custom function override if registered."""
        return self._function_overrides.get(name)

    def child(self, resource: ResourceInput | None = None) -> "EvaluationContext":
        """Create a child context, optionally with a new resource given as a wire dict or a pydantic model.

        Useful for nested evaluations while preserving parent context.
        """
        child_ctx = EvaluationContext(
            resource=as_resource_dict(resource) or self.resource,
            root_resource=self.root_resource,
            model=self.model,
            now=self.now,
            reference_resolver=self.reference_resolver,
            terminology_provider=self.terminology_provider,
            fhir_binding=self.fhir_binding,
        )
        child_ctx._constants = self._constants.copy()
        child_ctx._function_overrides = self._function_overrides.copy()
        return child_ctx
