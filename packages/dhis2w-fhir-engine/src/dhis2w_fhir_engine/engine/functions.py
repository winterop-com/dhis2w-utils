"""Function registry for FHIRPath and CQL functions."""

from collections.abc import Callable
from typing import Any

from .context import EvaluationContext
from .exceptions import FHIRPathError

# Type alias for function signatures
FHIRPathFunction = Callable[..., Any]


class FunctionRegistry:
    """Registry for FHIRPath/CQL functions.

    Functions are registered globally and can be overridden in context.
    CQL extends this by registering additional functions.
    """

    _functions: dict[str, FHIRPathFunction] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[FHIRPathFunction], FHIRPathFunction]:
        """Decorator to register a function.

        Usage:
            @FunctionRegistry.register("exists")
            def fn_exists(ctx, collection):
                return len(collection) > 0
        """

        def decorator(fn: FHIRPathFunction) -> FHIRPathFunction:
            cls._functions[name] = fn
            return fn

        return decorator

    @classmethod
    def get(cls, name: str) -> FHIRPathFunction | None:
        """Get a registered function by name."""
        return cls._functions.get(name)

    @classmethod
    def has(cls, name: str) -> bool:
        """Check if a function is registered."""
        return name in cls._functions

    @classmethod
    def call(
        cls,
        name: str,
        ctx: EvaluationContext,
        input_collection: list[Any],
        *args: Any,
    ) -> Any:
        """Call a registered function.

        Args:
            name: Function name
            ctx: Evaluation context
            input_collection: The collection the function is called on
            *args: Additional arguments to the function

        Returns:
            Function result
        """
        # Check for context-specific override first
        override = ctx.get_function_override(name)
        if override:
            return override(ctx, input_collection, *args)

        # Fall back to registered function
        fn = cls.get(name)
        if fn is None:
            raise FHIRPathError(f"Unknown function: {name}()")

        return fn(ctx, input_collection, *args)

    @classmethod
    def list_functions(cls) -> list[str]:
        """List all registered function names."""
        return sorted(cls._functions.keys())
