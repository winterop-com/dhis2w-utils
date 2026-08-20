"""CQL function implementations.

This package contains implementations of CQL built-in functions
organized by category:
- aggregate: Count, Sum, Avg, Min, Max, etc.
- conversion: ToString, ToInteger, ToDecimal, etc. + math functions
- datetime: Date/time manipulation
- list: First, Last, Tail, Take, Skip, etc.
- string: String manipulation

Functions are registered with the CQL function registry
and can be invoked from CQL expressions.
"""

from .registry import FunctionRegistry, get_registry

__all__ = ["FunctionRegistry", "get_registry"]
