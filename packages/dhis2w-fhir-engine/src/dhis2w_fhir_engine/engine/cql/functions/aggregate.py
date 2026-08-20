"""CQL Aggregate Functions.

Implements: Count, Sum, Avg, Min, Max, AllTrue, AnyTrue, AllFalse, AnyFalse,
Product, GeometricMean, PopulationVariance, Variance, PopulationStdDev, StdDev, Median, Mode
"""

import math
from collections import Counter
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .registry import FunctionRegistry


def _count(args: list[Any]) -> int:
    """Count non-null elements in a list.

    Per CQL spec: Count returns the number of non-null elements in the list.
    """
    if args and isinstance(args[0], list):
        return sum(1 for v in args[0] if v is not None)
    return 0


def _sum(args: list[Any]) -> Any:
    """Sum numeric values in a list."""
    if not args or not isinstance(args[0], list):
        return None
    values = [v for v in args[0] if v is not None]
    if not values:
        return None
    return sum(values)


def _avg(args: list[Any]) -> Any:
    """Average of numeric values in a list."""
    if not args or not isinstance(args[0], list):
        return None
    values = [v for v in args[0] if v is not None]
    if not values:
        return None
    total = sum(values)
    if isinstance(total, Decimal):
        return total / Decimal(len(values))
    return total / len(values)


def _min(args: list[Any]) -> Any:
    """Minimum value in a list."""
    if not args or not isinstance(args[0], list):
        return None
    values = [v for v in args[0] if v is not None]
    if not values:
        return None
    return min(values)


def _max(args: list[Any]) -> Any:
    """Maximum value in a list."""
    if not args or not isinstance(args[0], list):
        return None
    values = [v for v in args[0] if v is not None]
    if not values:
        return None
    return max(values)


def _all_true(args: list[Any]) -> bool:
    """Check if all values in list are true."""
    if not args or not isinstance(args[0], list):
        return True
    values = args[0]
    if not values:
        return True
    return all(v is True for v in values if v is not None)


def _any_true(args: list[Any]) -> bool:
    """Check if any value in list is true."""
    if not args or not isinstance(args[0], list):
        return False
    values = args[0]
    return any(v is True for v in values if v is not None)


def _all_false(args: list[Any]) -> bool:
    """Check if all values in list are false."""
    if not args or not isinstance(args[0], list):
        return True
    values = args[0]
    if not values:
        return True
    return all(v is False for v in values if v is not None)


def _any_false(args: list[Any]) -> bool:
    """Check if any value in list is false."""
    if not args or not isinstance(args[0], list):
        return False
    values = args[0]
    return any(v is False for v in values if v is not None)


def _product(args: list[Any]) -> Any:
    """Product of numeric values in a list."""
    if not args or not isinstance(args[0], list):
        return None
    values = [v for v in args[0] if v is not None]
    if not values:
        return None
    result = values[0]
    for v in values[1:]:
        result = result * v
    return result


def _geometric_mean(args: list[Any]) -> float | None:
    """Geometric mean of numeric values."""
    if not args or not isinstance(args[0], list):
        return None
    values = [float(v) for v in args[0] if v is not None and v > 0]
    if not values:
        return None
    log_sum = sum(math.log(v) for v in values)
    return math.exp(log_sum / len(values))


def _population_variance(args: list[Any]) -> float | None:
    """Population variance of numeric values."""
    if not args or not isinstance(args[0], list):
        return None
    values = [float(v) for v in args[0] if v is not None]
    if len(values) < 1:
        return None
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _variance(args: list[Any]) -> float | None:
    """Sample variance of numeric values."""
    if not args or not isinstance(args[0], list):
        return None
    values = [float(v) for v in args[0] if v is not None]
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


def _population_stddev(args: list[Any]) -> float | None:
    """Population standard deviation."""
    var = _population_variance(args)
    return math.sqrt(var) if var is not None else None


def _stddev(args: list[Any]) -> float | None:
    """Sample standard deviation."""
    var = _variance(args)
    return math.sqrt(var) if var is not None else None


def _median(args: list[Any]) -> Any:
    """Median of numeric values."""
    if not args or not isinstance(args[0], list):
        return None
    values = sorted(v for v in args[0] if v is not None)
    if not values:
        return None
    n = len(values)
    mid = n // 2
    if n % 2 == 0:
        return (values[mid - 1] + values[mid]) / 2
    return values[mid]


def _mode(args: list[Any]) -> Any:
    """Mode (most frequent value) in a list."""
    if not args or not isinstance(args[0], list):
        return None
    values = [v for v in args[0] if v is not None]
    if not values:
        return None
    counter = Counter(values)
    max_count = counter.most_common(1)[0][1]
    modes = [v for v, count in counter.items() if count == max_count]
    return modes[0] if len(modes) == 1 else modes


def register(registry: "FunctionRegistry") -> None:
    """Register all aggregate functions."""
    registry.register("Count", _count, category="aggregate", min_args=1, max_args=1)
    registry.register("Sum", _sum, category="aggregate", min_args=1, max_args=1)
    registry.register("Avg", _avg, aliases=["Average"], category="aggregate", min_args=1, max_args=1)
    registry.register("Min", _min, category="aggregate", min_args=1, max_args=1)
    registry.register("Max", _max, category="aggregate", min_args=1, max_args=1)
    registry.register("AllTrue", _all_true, category="aggregate", min_args=1, max_args=1)
    registry.register("AnyTrue", _any_true, category="aggregate", min_args=1, max_args=1)
    registry.register("AllFalse", _all_false, category="aggregate", min_args=1, max_args=1)
    registry.register("AnyFalse", _any_false, category="aggregate", min_args=1, max_args=1)
    registry.register("Product", _product, category="aggregate", min_args=1, max_args=1)
    registry.register("GeometricMean", _geometric_mean, category="aggregate", min_args=1, max_args=1)
    registry.register("PopulationVariance", _population_variance, category="aggregate", min_args=1, max_args=1)
    registry.register("Variance", _variance, category="aggregate", min_args=1, max_args=1)
    registry.register("PopulationStdDev", _population_stddev, category="aggregate", min_args=1, max_args=1)
    registry.register("StdDev", _stddev, category="aggregate", min_args=1, max_args=1)
    registry.register("Median", _median, category="aggregate", min_args=1, max_args=1)
    registry.register("Mode", _mode, category="aggregate", min_args=1, max_args=1)
