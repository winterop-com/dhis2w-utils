"""CQL libraries shipped with the FHIR R4 binding, chiefly FHIRHelpers 4.0.1."""

from ...binding import FhirVersionBinding
from ...engine.cql.library_resolver import InMemoryLibraryResolver


def builtin_resolver(binding: FhirVersionBinding) -> InMemoryLibraryResolver:
    """Build a library resolver holding every built-in CQL library a binding carries."""
    resolver = InMemoryLibraryResolver()
    for library in binding.builtin_libraries:
        resolver.add_library(library.name, library.source, library.version)
    return resolver


def get_builtin_resolver() -> InMemoryLibraryResolver:
    """Build a library resolver holding the R4 built-in CQL libraries."""
    from ..binding import R4_BINDING

    return builtin_resolver(R4_BINDING)


__all__ = ["builtin_resolver", "get_builtin_resolver"]
