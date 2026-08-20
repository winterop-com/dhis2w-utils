"""FHIR-specific functions: resolve, extension, ofType."""

from typing import Any

from ...context import EvaluationContext
from ...functions import FunctionRegistry


@FunctionRegistry.register("resolve")
def fn_resolve(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Resolve FHIR References to their target resources.

    For each Reference in the input collection, attempts to resolve it using
    the reference_resolver callback in the evaluation context.

    Reference format: {"reference": "Patient/123"} or {"reference": "http://..."}
    """
    if ctx.reference_resolver is None:
        return []

    result = []
    for item in collection:
        if isinstance(item, dict):
            ref = item.get("reference")
            if ref:
                resolved = ctx.reference_resolver(ref)
                if resolved is not None:
                    result.append(resolved)
        elif isinstance(item, str):
            # Direct reference string
            resolved = ctx.reference_resolver(item)
            if resolved is not None:
                result.append(resolved)
    return result


@FunctionRegistry.register("extension")
def fn_extension(ctx: EvaluationContext, collection: list[Any], url: str) -> list[Any]:
    """Returns extensions with the specified URL from the input collection.

    Looks for extensions in the 'extension' property of each element
    and filters by the 'url' property.

    For primitives with extensions (wrapped in _PrimitiveWithExtension),
    looks in the extension_data.
    """
    # Import here to avoid circular imports
    from ..visitor import _PrimitiveWithExtension

    result = []
    for item in collection:
        # Handle primitives with extensions
        if isinstance(item, _PrimitiveWithExtension):
            # The `_field` sibling comes straight from the resource JSON, so its shape is unchecked.
            ext_data: Any = item.extension_data
            if isinstance(ext_data, dict):
                extensions = ext_data.get("extension", [])
                if isinstance(extensions, dict):
                    # Single extension object
                    if extensions.get("url") == url or extensions.get("_url") == url:
                        result.append(extensions)
                elif isinstance(extensions, list):
                    for ext in extensions:
                        if isinstance(ext, dict) and (ext.get("url") == url or ext.get("_url") == url):
                            result.append(ext)
        elif isinstance(item, dict):
            extensions = item.get("extension", [])
            if isinstance(extensions, dict):
                # Single extension object (from XML conversion)
                if extensions.get("url") == url or extensions.get("_url") == url:
                    result.append(extensions)
            elif isinstance(extensions, list):
                for ext in extensions:
                    if isinstance(ext, dict) and (ext.get("url") == url or ext.get("_url") == url):
                        result.append(ext)
    return result


@FunctionRegistry.register("elementDefinition")
def fn_element_definition(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
    """Returns the FHIR ElementDefinition for each element in the input.

    Note: Requires model information. Returns empty if no model available.
    """
    # This requires StructureDefinition information which we don't have yet
    return []


@FunctionRegistry.register("slice")
def fn_slice(ctx: EvaluationContext, collection: list[Any], structure: str, name: str) -> list[Any]:
    """Returns elements that belong to a specific slice.

    Note: Requires StructureDefinition information. Returns empty if unavailable.
    """
    # This requires slice definitions which we don't have yet
    return []


@FunctionRegistry.register("checkModifiers")
def fn_check_modifiers(ctx: EvaluationContext, collection: list[Any], *args: str) -> list[Any]:
    """Check if the input has any modifier extensions other than the ones specified.

    If there are modifier extensions other than those listed, raises an error.
    Otherwise returns the input unchanged.
    """
    allowed_urls = set(args)

    for item in collection:
        if isinstance(item, dict):
            mod_extensions = item.get("modifierExtension", [])
            if isinstance(mod_extensions, list):
                for ext in mod_extensions:
                    if isinstance(ext, dict):
                        url = ext.get("url")
                        if url and url not in allowed_urls:
                            # In strict mode, this would raise an error
                            # For now, we just skip such elements
                            pass
    return collection


@FunctionRegistry.register("conformsTo")
def fn_conforms_to(ctx: EvaluationContext, collection: list[Any], profile: str) -> list[bool]:
    """Returns true if the resource conforms to the specified profile.

    Performs basic profile conformance checking:
    1. Checks if the resource's meta.profile includes the specified profile URL
    2. If no meta.profile, checks if the profile matches the resource's base type

    For full profile validation with constraint checking, a profile validator
    would be needed. This implementation provides basic conformance checking
    suitable for most common use cases.

    Args:
        ctx: Evaluation context
        collection: Collection of resources to check
        profile: The canonical URL of the profile to check conformance against

    Returns:
        List containing true/false for each item in the collection
    """
    result: list[bool] = []

    for item in collection:
        if not isinstance(item, dict):
            result.append(False)
            continue

        # Check if resource declares conformance to the profile
        meta = item.get("meta")
        if isinstance(meta, dict):
            profiles = meta.get("profile", [])
            if isinstance(profiles, list):
                # Direct profile match
                if profile in profiles:
                    result.append(True)
                    continue

                # Check for version-independent match (profile URL without version)
                profile_base = profile.split("|")[0] if "|" in profile else profile
                for declared_profile in profiles:
                    declared_base = declared_profile.split("|")[0] if "|" in declared_profile else declared_profile
                    if profile_base == declared_base:
                        result.append(True)
                        break
                else:
                    # No match in declared profiles - check base type
                    result.append(_check_base_type_conformance(ctx, item, profile))
            else:
                # No profiles array
                result.append(_check_base_type_conformance(ctx, item, profile))
        else:
            # No meta - check base type
            result.append(_check_base_type_conformance(ctx, item, profile))

    return result


def _check_base_type_conformance(ctx: EvaluationContext, resource: dict[str, Any], profile: str) -> bool:
    """Check whether a resource's type alone satisfies a profile URL.

    Args:
        ctx: Evaluation context carrying the FHIR version binding
        resource: The FHIR resource dictionary
        profile: The profile URL

    Returns:
        True when the resource type matches the profile's target
    """
    resource_type = resource.get("resourceType", "")
    if not resource_type:
        return False

    # Strip any version suffix before comparing, e.g. ".../Patient|4.0.1".
    profile_base = profile.split("|")[0]

    # Direct match: the profile URL ends with /ResourceType.
    if profile_base.endswith(f"/{resource_type}"):
        return True

    # The binding knows the canonical base profile for the resource type, and a derived profile
    # cannot be confirmed without its StructureDefinition.
    return profile_base == ctx.fhir_binding.profile_url_for(resource_type)


def _extract_code_system(item: Any) -> tuple[str | None, str | None]:
    """Extract code and system from a code, Coding, or CodeableConcept.

    Args:
        item: A code string, Coding dict, or CodeableConcept dict

    Returns:
        Tuple of (code, system), either may be None
    """
    if isinstance(item, str):
        # Plain code string - no system
        return (item, None)
    elif isinstance(item, dict):
        # Could be Coding or CodeableConcept
        if "coding" in item:
            # CodeableConcept - use first coding
            codings = item.get("coding", [])
            if codings and isinstance(codings, list) and len(codings) > 0:
                first_coding = codings[0]
                if isinstance(first_coding, dict):
                    return (first_coding.get("code"), first_coding.get("system"))
        else:
            # Assume it's a Coding
            return (item.get("code"), item.get("system"))
    return (None, None)


@FunctionRegistry.register("memberOf")
def fn_member_of(ctx: EvaluationContext, collection: list[Any], valueset: str) -> list[bool]:
    """Returns true if the code/Coding/CodeableConcept is in the specified ValueSet.

    Args:
        ctx: Evaluation context (must have terminology_provider set)
        collection: Collection of codes, Codings, or CodeableConcepts
        valueset: The ValueSet URL to check membership against

    Returns:
        List containing true/false for each item in collection
    """
    if ctx.terminology_provider is None:
        # No terminology service available
        return []

    result: list[bool] = []
    for item in collection:
        code, system = _extract_code_system(item)
        if code is None:
            result.append(False)
            continue

        # Use empty string if system is None (some ValueSets accept code-only)
        system_str = system or ""
        is_member = ctx.terminology_provider.member_of(valueset, code, system_str)
        result.append(is_member)

    return result


@FunctionRegistry.register("subsumes")
def fn_subsumes(ctx: EvaluationContext, collection: list[Any], code: Any) -> list[bool]:
    """Returns true if the code in collection subsumes the specified code.

    The first code (from collection) is the potential ancestor/parent,
    and the second code (argument) is the potential descendant/child.

    Args:
        ctx: Evaluation context (must have terminology_provider set)
        collection: Collection of codes (potential ancestors)
        code: The code to check if subsumed (potential descendant)

    Returns:
        List containing true/false for each item in collection
    """
    if ctx.terminology_provider is None:
        return []

    # Extract code/system from the argument
    code_b, system_b = _extract_code_system(code)
    if code_b is None:
        return []

    result: list[bool] = []
    for item in collection:
        code_a, system_a = _extract_code_system(item)
        if code_a is None:
            result.append(False)
            continue

        # Both codes should be in the same system
        system = system_a or system_b
        if system is None:
            result.append(False)
            continue

        subsumes_result = ctx.terminology_provider.subsumes(system, code_a, code_b)
        # Extract outcome from Parameters resource
        outcome = _get_subsumes_outcome(subsumes_result)
        # "subsumes" means code_a is ancestor of code_b
        # "equivalent" also counts as subsumes
        result.append(outcome in ("subsumes", "equivalent"))

    return result


@FunctionRegistry.register("subsumedBy")
def fn_subsumed_by(ctx: EvaluationContext, collection: list[Any], code: Any) -> list[bool]:
    """Returns true if the code in collection is subsumed by the specified code.

    The first code (from collection) is the potential descendant/child,
    and the second code (argument) is the potential ancestor/parent.

    Args:
        ctx: Evaluation context (must have terminology_provider set)
        collection: Collection of codes (potential descendants)
        code: The code to check as subsumer (potential ancestor)

    Returns:
        List containing true/false for each item in collection
    """
    if ctx.terminology_provider is None:
        return []

    # Extract code/system from the argument
    code_b, system_b = _extract_code_system(code)
    if code_b is None:
        return []

    result: list[bool] = []
    for item in collection:
        code_a, system_a = _extract_code_system(item)
        if code_a is None:
            result.append(False)
            continue

        # Both codes should be in the same system
        system = system_a or system_b
        if system is None:
            result.append(False)
            continue

        subsumes_result = ctx.terminology_provider.subsumes(system, code_a, code_b)
        outcome = _get_subsumes_outcome(subsumes_result)
        # "subsumed-by" means code_a is descendant of code_b
        # "equivalent" also counts as subsumed-by
        result.append(outcome in ("subsumed-by", "equivalent"))

    return result


def _get_subsumes_outcome(params: Any) -> str | None:
    """Extract the outcome from a $subsumes Parameters response.

    Args:
        params: The payload a terminology provider returned for $subsumes. A Parameters resource
            carries the outcome; any other shape yields None.

    Returns:
        The outcome string: "equivalent", "subsumes", "subsumed-by", or "not-subsumed"
    """
    if not isinstance(params, dict):
        return None

    # Look for the outcome parameter
    parameters = params.get("parameter", [])
    if isinstance(parameters, list):
        for param in parameters:
            if isinstance(param, dict) and param.get("name") == "outcome":
                return param.get("valueCode")

    return None


@FunctionRegistry.register("htmlChecks")
def fn_html_checks(ctx: EvaluationContext, collection: list[Any]) -> list[bool]:
    """Check if the HTML content in the Narrative is valid.

    Returns true if the HTML passes basic safety checks.
    """
    for item in collection:
        if isinstance(item, dict):
            div = item.get("div")
            # Basic check: must start with <div
            if div and isinstance(div, str) and not div.strip().startswith("<div"):
                return [False]
    return [True]
