"""CQL Function Registry.

Provides a registry for built-in CQL functions that can be called
from the visitor. Functions are organized by category and registered
with their names (case-insensitive).
"""

from collections.abc import Callable
from typing import Any

# Function signature: (args: list[Any]) -> Any
FunctionImpl = Callable[[list[Any]], Any]


class FunctionRegistry:
    """Registry for CQL built-in functions.

    Functions are registered by lowercase name and can optionally have
    aliases. The registry supports function lookup and execution.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._functions: dict[str, FunctionImpl] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        func: FunctionImpl,
        *,
        aliases: list[str] | None = None,
        category: str = "general",
        min_args: int = 0,
        max_args: int | None = None,
        description: str | None = None,
    ) -> None:
        """Register a function.

        Args:
            name: Primary function name (will be lowercased)
            func: Function implementation
            aliases: Optional list of alternative names
            category: Function category for organization
            min_args: Minimum number of arguments
            max_args: Maximum number of arguments (None for unlimited)
            description: Optional description
        """
        key = name.lower()
        self._functions[key] = func
        self._metadata[key] = {
            "name": name,
            "category": category,
            "min_args": min_args,
            "max_args": max_args,
            "description": description,
        }

        # Register aliases
        if aliases:
            for alias in aliases:
                alias_key = alias.lower()
                self._functions[alias_key] = func
                self._metadata[alias_key] = self._metadata[key]

    def has(self, name: str) -> bool:
        """Check if a function is registered."""
        return name.lower() in self._functions

    def get(self, name: str) -> FunctionImpl | None:
        """Get a function by name."""
        return self._functions.get(name.lower())

    def call(self, name: str, args: list[Any]) -> Any:
        """Call a registered function.

        Args:
            name: Function name
            args: List of arguments

        Returns:
            Function result

        Raises:
            KeyError: If function not found
        """
        func = self._functions.get(name.lower())
        if func is None:
            raise KeyError(f"Function not found: {name}")
        return func(args)

    def list_functions(self, category: str | None = None) -> list[str]:
        """List registered functions, optionally filtered by category."""
        if category is None:
            return list(set(m["name"] for m in self._metadata.values()))
        return list(set(m["name"] for m in self._metadata.values() if m["category"] == category))


# Global registry instance
_registry: FunctionRegistry | None = None


def get_registry() -> FunctionRegistry:
    """Get the global function registry, creating if needed."""
    global _registry
    if _registry is None:
        _registry = FunctionRegistry()
        _register_all_functions(_registry)
    return _registry


def _register_all_functions(registry: FunctionRegistry) -> None:
    """Register all built-in functions."""
    # Imported inside function to avoid circular imports
    from . import aggregate, conversion, datetime_funcs, list_funcs, string_funcs

    aggregate.register(registry)
    list_funcs.register(registry)
    string_funcs.register(registry)
    datetime_funcs.register(registry)
    conversion.register(registry)

    # Register messaging functions
    _register_messaging_functions(registry)


def _message(args: list[Any]) -> Any:
    """CQL Message function.

    Message(source, condition, code, severity, message)

    Per CQL spec: Returns the source value and emits a message if condition is true.
    Severity can be: 'Message', 'Warning', 'Error', 'Trace'

    For 'Error' severity with condition=true, raises an exception.
    """
    if not args:
        return None
    source = args[0]
    condition = args[1] if len(args) > 1 else True
    code = args[2] if len(args) > 2 else None
    severity = args[3] if len(args) > 3 else "Message"
    message = args[4] if len(args) > 4 else None

    # If condition is true and severity is 'Error', raise an exception
    if condition is True and severity == "Error":
        error_msg = f"CQL Error [{code}]: {message}" if code and message else str(message or "CQL Error")
        raise RuntimeError(error_msg)

    # For other severities (Message, Warning, Trace), just return the source
    # In a full implementation, we would emit the message to a message handler
    return source


def _register_messaging_functions(registry: FunctionRegistry) -> None:
    """Register messaging functions."""
    registry.register(
        "Message",
        _message,
        category="messaging",
        min_args=5,
        max_args=5,
        description="Emits a message and returns source value",
    )
