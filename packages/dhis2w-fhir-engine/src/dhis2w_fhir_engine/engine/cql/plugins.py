"""CQL Plugin and Extension System.

This module provides a way to register custom functions that can be called
from CQL expressions. Plugins allow extending CQL functionality with
organization-specific or domain-specific operations.

Usage:
    from dhis2w_fhir_engine.engine.cql.plugins import CQLPluginRegistry, register_function

    # Using decorator
    @register_function("MyOrg.CustomCalc")
    def custom_calc(value: int) -> int:
        return value * 2

    # Or using registry directly
    registry = CQLPluginRegistry()
    registry.register("MyOrg.Double", lambda x: x * 2)

    # Use with evaluator
    evaluator = CQLEvaluator(plugin_registry=registry)
    result = evaluator.evaluate_expression("MyOrg.CustomCalc(21)")  # 42
"""

from collections.abc import Callable
from typing import Any, TypeVar

# Function signature type
FunctionType = Callable[..., Any]
T = TypeVar("T", bound=FunctionType)

# Global registry for decorator-based registration
_global_registry: "CQLPluginRegistry | None" = None


class CQLPluginRegistry:
    """Registry for custom CQL functions.

    Stores and manages custom functions that can be called from CQL expressions.
    Functions are registered with a name (optionally namespaced like "Org.FunctionName")
    and can accept any number of arguments.
    """

    def __init__(self) -> None:
        """Initialize an empty plugin registry."""
        self._functions: dict[str, FunctionType] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        func: FunctionType,
        *,
        description: str | None = None,
        param_types: list[str] | None = None,
        return_type: str | None = None,
    ) -> None:
        """Register a custom function.

        Args:
            name: The function name (can be namespaced like "MyOrg.Calculate").
            func: The Python callable to execute.
            description: Optional description of what the function does.
            param_types: Optional list of CQL type names for parameters.
            return_type: Optional CQL type name for the return value.
        """
        self._functions[name] = func
        self._metadata[name] = {
            "description": description,
            "param_types": param_types or [],
            "return_type": return_type,
        }

    def unregister(self, name: str) -> bool:
        """Unregister a custom function.

        Args:
            name: The function name to unregister.

        Returns:
            True if the function was found and removed, False otherwise.
        """
        if name in self._functions:
            del self._functions[name]
            del self._metadata[name]
            return True
        return False

    def get(self, name: str) -> FunctionType | None:
        """Get a registered function by name.

        Args:
            name: The function name.

        Returns:
            The registered function, or None if not found.
        """
        return self._functions.get(name)

    def has(self, name: str) -> bool:
        """Check if a function is registered.

        Args:
            name: The function name.

        Returns:
            True if the function is registered.
        """
        return name in self._functions

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Call a registered function.

        Args:
            name: The function name.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.

        Returns:
            The function's return value.

        Raises:
            KeyError: If the function is not registered.
        """
        func = self._functions.get(name)
        if func is None:
            raise KeyError(f"Plugin function not found: {name}")
        return func(*args, **kwargs)

    def list_functions(self) -> list[str]:
        """List all registered function names.

        Returns:
            List of registered function names.
        """
        return list(self._functions.keys())

    def get_metadata(self, name: str) -> dict[str, Any] | None:
        """Get metadata for a registered function.

        Args:
            name: The function name.

        Returns:
            Dictionary with description, param_types, and return_type,
            or None if the function is not registered.
        """
        return self._metadata.get(name)

    def merge(self, other: "CQLPluginRegistry") -> None:
        """Merge another registry into this one.

        Functions from the other registry are added to this one.
        If a function name already exists, it will be overwritten.

        Args:
            other: Another CQLPluginRegistry to merge from.
        """
        self._functions.update(other._functions)
        self._metadata.update(other._metadata)

    def clear(self) -> None:
        """Remove all registered functions."""
        self._functions.clear()
        self._metadata.clear()

    def __len__(self) -> int:
        """Return the number of registered functions."""
        return len(self._functions)

    def __contains__(self, name: str) -> bool:
        """Check if a function is registered."""
        return name in self._functions


def get_global_registry() -> CQLPluginRegistry:
    """Get the global plugin registry.

    Creates it if it doesn't exist.

    Returns:
        The global CQLPluginRegistry instance.
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = CQLPluginRegistry()
    return _global_registry


def register_function(
    name: str,
    *,
    description: str | None = None,
    param_types: list[str] | None = None,
    return_type: str | None = None,
) -> Callable[[T], T]:
    """Decorator to register a function in the global plugin registry.

    Args:
        name: The function name (can be namespaced like "MyOrg.Calculate").
        description: Optional description of what the function does.
        param_types: Optional list of CQL type names for parameters.
        return_type: Optional CQL type name for the return value.

    Returns:
        A decorator that registers the function and returns it unchanged.

    Example:
        @register_function("MyOrg.Double", description="Doubles a number")
        def double(x: int) -> int:
            return x * 2
    """

    def decorator(func: T) -> T:
        registry = get_global_registry()
        registry.register(
            name,
            func,
            description=description,
            param_types=param_types,
            return_type=return_type,
        )
        return func

    return decorator


def create_math_plugins() -> CQLPluginRegistry:
    """Create a registry with common math utility functions.

    Returns:
        A CQLPluginRegistry with math functions.
    """
    registry = CQLPluginRegistry()

    import math

    registry.register(
        "Math.Sin",
        lambda x: math.sin(x) if x is not None else None,
        description="Sine of angle in radians",
        param_types=["Decimal"],
        return_type="Decimal",
    )
    registry.register(
        "Math.Cos",
        lambda x: math.cos(x) if x is not None else None,
        description="Cosine of angle in radians",
        param_types=["Decimal"],
        return_type="Decimal",
    )
    registry.register(
        "Math.Tan",
        lambda x: math.tan(x) if x is not None else None,
        description="Tangent of angle in radians",
        param_types=["Decimal"],
        return_type="Decimal",
    )
    registry.register(
        "Math.Sqrt",
        lambda x: math.sqrt(x) if x is not None and x >= 0 else None,
        description="Square root",
        param_types=["Decimal"],
        return_type="Decimal",
    )
    registry.register(
        "Math.Log",
        lambda x: math.log(x) if x is not None and x > 0 else None,
        description="Natural logarithm",
        param_types=["Decimal"],
        return_type="Decimal",
    )
    registry.register(
        "Math.Log10",
        lambda x: math.log10(x) if x is not None and x > 0 else None,
        description="Base-10 logarithm",
        param_types=["Decimal"],
        return_type="Decimal",
    )

    return registry


def create_string_plugins() -> CQLPluginRegistry:
    """Create a registry with additional string utility functions.

    Returns:
        A CQLPluginRegistry with string functions.
    """
    registry = CQLPluginRegistry()

    registry.register(
        "String.Reverse",
        lambda s: s[::-1] if s is not None else None,
        description="Reverse a string",
        param_types=["String"],
        return_type="String",
    )
    registry.register(
        "String.Trim",
        lambda s: s.strip() if s is not None else None,
        description="Trim whitespace from both ends",
        param_types=["String"],
        return_type="String",
    )
    registry.register(
        "String.IsBlank",
        lambda s: s is None or s.strip() == "",
        description="Check if string is null or whitespace only",
        param_types=["String"],
        return_type="Boolean",
    )
    registry.register(
        "String.PadLeft",
        lambda s, n, c=" ": s.rjust(n, c) if s is not None else None,
        description="Pad string on the left",
        param_types=["String", "Integer", "String"],
        return_type="String",
    )
    registry.register(
        "String.PadRight",
        lambda s, n, c=" ": s.ljust(n, c) if s is not None else None,
        description="Pad string on the right",
        param_types=["String", "Integer", "String"],
        return_type="String",
    )

    return registry
