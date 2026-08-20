"""ELM expression visitor for evaluation.

This module implements a type-based dispatch pattern for evaluating ELM expressions.
Each expression type is handled by a registered handler method.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from dhis2w_fhir_engine.engine.cql.context import CQLContext
from dhis2w_fhir_engine.engine.cql.types import CQLCode, CQLConcept, CQLInterval, CQLTuple
from dhis2w_fhir_engine.engine.elm.exceptions import ELMExecutionError, ELMReferenceError
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity

if TYPE_CHECKING:
    from dhis2w_fhir_engine.engine.elm.models.library import ELMLibrary

# Logger for CQL Message expressions
cql_logger = logging.getLogger("dhis2w_fhir_engine.cql.message")


class ELMExpressionVisitor:
    """Evaluates ELM expression nodes using type-based dispatch."""

    def __init__(self, context: CQLContext):
        """Initialize the visitor.

        Args:
            context: CQL context for execution state.
        """
        self.context = context
        self._library: ELMLibrary | None = None

        # Storage for included libraries (alias -> ELMLibrary)
        self._included_libraries: dict[str, ELMLibrary] = {}

        # Register type handlers
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            # Literals
            "Literal": self._eval_literal,
            "Null": self._eval_null,
            "Interval": self._eval_interval,
            "List": self._eval_list,
            "Tuple": self._eval_tuple,
            "Instance": self._eval_instance,
            "Quantity": self._eval_quantity,
            "Ratio": self._eval_ratio,
            "Code": self._eval_code,
            "Concept": self._eval_concept,
            # Arithmetic
            "Add": self._eval_add,
            "Subtract": self._eval_subtract,
            "Multiply": self._eval_multiply,
            "Divide": self._eval_divide,
            "TruncatedDivide": self._eval_truncated_divide,
            "Modulo": self._eval_modulo,
            "Power": self._eval_power,
            "Negate": self._eval_negate,
            "Abs": self._eval_abs,
            "Ceiling": self._eval_ceiling,
            "Floor": self._eval_floor,
            "Truncate": self._eval_truncate,
            "Round": self._eval_round,
            "Ln": self._eval_ln,
            "Log": self._eval_log,
            "Exp": self._eval_exp,
            "Successor": self._eval_successor,
            "Predecessor": self._eval_predecessor,
            "MinValue": self._eval_min_value,
            "MaxValue": self._eval_max_value,
            # Comparison
            "Equal": self._eval_equal,
            "NotEqual": self._eval_not_equal,
            "Equivalent": self._eval_equivalent,
            "Less": self._eval_less,
            "LessOrEqual": self._eval_less_or_equal,
            "Greater": self._eval_greater,
            "GreaterOrEqual": self._eval_greater_or_equal,
            # Boolean
            "And": self._eval_and,
            "Or": self._eval_or,
            "Xor": self._eval_xor,
            "Not": self._eval_not,
            "Implies": self._eval_implies,
            "IsTrue": self._eval_is_true,
            "IsFalse": self._eval_is_false,
            "IsNull": self._eval_is_null,
            # Conditional
            "If": self._eval_if,
            "Case": self._eval_case,
            "Coalesce": self._eval_coalesce,
            # String
            "Concatenate": self._eval_concatenate,
            "Combine": self._eval_combine,
            "Split": self._eval_split,
            "Length": self._eval_length,
            "Upper": self._eval_upper,
            "Lower": self._eval_lower,
            "Substring": self._eval_substring,
            "StartsWith": self._eval_starts_with,
            "EndsWith": self._eval_ends_with,
            "Matches": self._eval_matches,
            "ReplaceMatches": self._eval_replace_matches,
            "Indexer": self._eval_indexer,
            "PositionOf": self._eval_position_of,
            "LastPositionOf": self._eval_last_position_of,
            # Collections
            "First": self._eval_first,
            "Last": self._eval_last,
            "IndexOf": self._eval_index_of,
            "Contains": self._eval_contains,
            "In": self._eval_in,
            "Includes": self._eval_includes,
            "IncludedIn": self._eval_included_in,
            "ProperIncludes": self._eval_proper_includes,
            "ProperIncludedIn": self._eval_proper_included_in,
            "Distinct": self._eval_distinct,
            "Flatten": self._eval_flatten,
            "Exists": self._eval_exists,
            "SingletonFrom": self._eval_singleton_from,
            "ToList": self._eval_to_list,
            # Aggregates
            "Count": self._eval_count,
            "Sum": self._eval_sum,
            "Avg": self._eval_avg,
            "Min": self._eval_min,
            "Max": self._eval_max,
            "Median": self._eval_median,
            "Mode": self._eval_mode,
            "Variance": self._eval_variance,
            "PopulationVariance": self._eval_population_variance,
            "StdDev": self._eval_std_dev,
            "PopulationStdDev": self._eval_population_std_dev,
            "AllTrue": self._eval_all_true,
            "AnyTrue": self._eval_any_true,
            "Product": self._eval_product,
            "GeometricMean": self._eval_geometric_mean,
            # Set operations
            "Union": self._eval_union,
            "Intersect": self._eval_intersect,
            "Except": self._eval_except,
            # References
            "ExpressionRef": self._eval_expression_ref,
            "FunctionRef": self._eval_function_ref,
            "ParameterRef": self._eval_parameter_ref,
            "OperandRef": self._eval_operand_ref,
            "Property": self._eval_property,
            "AliasRef": self._eval_alias_ref,
            "QueryLetRef": self._eval_query_let_ref,
            "IdentifierRef": self._eval_identifier_ref,
            # Query
            "Query": self._eval_query,
            "Retrieve": self._eval_retrieve,
            "ForEach": self._eval_for_each,
            "Repeat": self._eval_repeat,
            "Filter": self._eval_filter,
            "Times": self._eval_times,
            # Type operations
            "As": self._eval_as,
            "Is": self._eval_is,
            "ToBoolean": self._eval_to_boolean,
            "ToInteger": self._eval_to_integer,
            "ToLong": self._eval_to_long,
            "ToDecimal": self._eval_to_decimal,
            "ToString": self._eval_to_string,
            "ToDateTime": self._eval_to_datetime,
            "ToDate": self._eval_to_date,
            "ToTime": self._eval_to_time,
            "ToQuantity": self._eval_to_quantity,
            "ToConcept": self._eval_to_concept,
            "ConvertsToBoolean": self._eval_converts_to_boolean,
            "ConvertsToInteger": self._eval_converts_to_integer,
            "ConvertsToDecimal": self._eval_converts_to_decimal,
            "ConvertsToString": self._eval_converts_to_string,
            "ConvertsToDateTime": self._eval_converts_to_datetime,
            "ConvertsToDate": self._eval_converts_to_date,
            "ConvertsToTime": self._eval_converts_to_time,
            "ConvertsToQuantity": self._eval_converts_to_quantity,
            # Date/Time
            "Today": self._eval_today,
            "Now": self._eval_now,
            "TimeOfDay": self._eval_time_of_day,
            "Date": self._eval_date_constructor,
            "DateTime": self._eval_datetime_constructor,
            "Time": self._eval_time_constructor,
            "DurationBetween": self._eval_duration_between,
            "DifferenceBetween": self._eval_difference_between,
            "DateFrom": self._eval_date_from,
            "TimeFrom": self._eval_time_from,
            "TimezoneOffsetFrom": self._eval_timezone_offset_from,
            "DateTimeComponentFrom": self._eval_datetime_component_from,
            "SameAs": self._eval_same_as,
            "SameOrBefore": self._eval_same_or_before,
            "SameOrAfter": self._eval_same_or_after,
            # Interval operations
            "Start": self._eval_start,
            "End": self._eval_end,
            "Width": self._eval_width,
            "Size": self._eval_size,
            "PointFrom": self._eval_point_from,
            "Overlaps": self._eval_overlaps,
            "OverlapsBefore": self._eval_overlaps_before,
            "OverlapsAfter": self._eval_overlaps_after,
            "Meets": self._eval_meets,
            "MeetsBefore": self._eval_meets_before,
            "MeetsAfter": self._eval_meets_after,
            "Before": self._eval_before,
            "After": self._eval_after,
            "Starts": self._eval_starts,
            "Ends": self._eval_ends,
            "Collapse": self._eval_collapse,
            "Expand": self._eval_expand,
            # Clinical
            "CodeRef": self._eval_code_ref,
            "CodeSystemRef": self._eval_codesystem_ref,
            "ValueSetRef": self._eval_valueset_ref,
            "ConceptRef": self._eval_concept_ref,
            "InValueSet": self._eval_in_valueset,
            "InCodeSystem": self._eval_in_codesystem,
            "CalculateAge": self._eval_calculate_age,
            "CalculateAgeAt": self._eval_calculate_age_at,
            # Message
            "Message": self._eval_message,
        }

    def evaluate(self, node: Any) -> Any:
        """Evaluate an ELM expression node.

        Args:
            node: ELM expression node (dict or Pydantic model).

        Returns:
            Evaluation result.

        Raises:
            ELMExecutionError: If evaluation fails.
        """
        if node is None:
            return None

        # Convert Pydantic model to dict if needed
        if hasattr(node, "model_dump"):
            node = node.model_dump(by_alias=True, exclude_none=True)

        if not isinstance(node, dict):
            return node  # Return primitive values as-is

        node_type = node.get("type")
        if not node_type:
            raise ELMExecutionError(f"Missing 'type' field in expression: {node}")

        handler = self._handlers.get(node_type)
        if not handler:
            raise ELMExecutionError(f"Unsupported expression type: {node_type}")

        try:
            return handler(node)
        except ELMExecutionError:
            raise
        except Exception as e:
            locator = node.get("locator")
            raise ELMExecutionError(f"Error evaluating {node_type}: {e}", locator) from e

    def set_library(self, library: ELMLibrary) -> None:
        """Set the ELM library for expression reference resolution.

        Args:
            library: The ELM library containing definitions.
        """
        self._library = library

    def add_included_library(self, alias: str, library: ELMLibrary) -> None:
        """Register an included library by its alias.

        Args:
            alias: The local identifier (alias) used in the include statement.
            library: The ELM library that was included.
        """
        self._included_libraries[alias] = library

    def get_included_library(self, alias: str) -> ELMLibrary | None:
        """Get an included library by alias.

        Args:
            alias: The local identifier (alias) from the include statement.

        Returns:
            The included ELM library, or None if not found.
        """
        return self._included_libraries.get(alias)

    def clear_included_libraries(self) -> None:
        """Clear all registered included libraries."""
        self._included_libraries.clear()

    # =========================================================================
    # Literal Handlers
    # =========================================================================

    def _eval_literal(self, node: dict[str, Any]) -> Any:
        """Evaluate a literal expression."""
        value_type = node.get("valueType", "")
        value = node.get("value")

        if value is None:
            return None

        # Parse value based on type
        if "Boolean" in value_type:
            return value.lower() == "true" if isinstance(value, str) else bool(value)
        elif "Integer" in value_type or "Long" in value_type:
            return int(value)
        elif "Decimal" in value_type:
            return Decimal(str(value))
        elif "String" in value_type:
            return str(value)
        elif "Date" in value_type and "DateTime" not in value_type:
            return FHIRDate.parse(value)
        elif "DateTime" in value_type:
            return FHIRDateTime.parse(value)
        elif "Time" in value_type:
            return value  # Keep as string for now
        elif "Quantity" in value_type:
            return self._parse_quantity(value)

        return value

    def _eval_null(self, node: dict[str, Any]) -> None:
        """Evaluate null literal."""
        return None

    def _eval_interval(self, node: dict[str, Any]) -> CQLInterval:
        """Evaluate interval expression."""
        low = self.evaluate(node.get("low"))
        high = self.evaluate(node.get("high"))

        # Handle dynamic closed flags
        low_closed = node.get("lowClosed", True)
        high_closed = node.get("highClosed", True)

        if "lowClosedExpression" in node:
            low_closed = self.evaluate(node["lowClosedExpression"])
        if "highClosedExpression" in node:
            high_closed = self.evaluate(node["highClosedExpression"])

        return CQLInterval(
            low=low,
            high=high,
            low_closed=bool(low_closed),
            high_closed=bool(high_closed),
        )

    def _eval_list(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate list expression."""
        elements = node.get("element", [])
        return [self.evaluate(e) for e in elements]

    def _eval_tuple(self, node: dict[str, Any]) -> CQLTuple:
        """Evaluate tuple expression."""
        elements = {}
        for elem in node.get("element", []):
            name = elem.get("name")
            value = self.evaluate(elem.get("value"))
            elements[name] = value
        return CQLTuple(elements=elements)

    def _eval_instance(self, node: dict[str, Any]) -> dict[str, Any]:
        """Evaluate instance expression (FHIR resource)."""
        result: dict[str, Any] = {}
        class_type = node.get("classType", "")

        # Extract resource type from class type, e.g. "{http://hl7.org/fhir}Patient"
        resource_type = class_type.split("}")[-1] if "{" in class_type else class_type

        result["resourceType"] = resource_type

        for elem in node.get("element", []):
            name = elem.get("name")
            value = self.evaluate(elem.get("value"))
            result[name] = value

        return result

    def _eval_quantity(self, node: dict[str, Any]) -> Quantity | None:
        """Evaluate quantity expression."""
        value = node.get("value")
        unit = node.get("unit", "1")

        if value is None:
            return None

        return Quantity(value=Decimal(str(value)), unit=unit)

    def _eval_ratio(self, node: dict[str, Any]) -> dict[str, Any]:
        """Evaluate ratio expression."""
        numerator = self.evaluate(node.get("numerator"))
        denominator = self.evaluate(node.get("denominator"))
        return {"numerator": numerator, "denominator": denominator}

    def _eval_code(self, node: dict[str, Any]) -> CQLCode:
        """Evaluate inline code."""
        code = node.get("code", "")
        system = node.get("system")
        if isinstance(system, dict):
            system = self.evaluate(system)
        display = node.get("display")
        version = node.get("version")

        return CQLCode(code=code, system=system or "", display=display, version=version)

    def _eval_concept(self, node: dict[str, Any]) -> CQLConcept:
        """Evaluate inline concept."""
        codes = tuple(self.evaluate(c) for c in node.get("code", []))
        display = node.get("display")
        return CQLConcept(codes=codes, display=display)

    # =========================================================================
    # Arithmetic Handlers
    # =========================================================================

    def _get_binary_operands(self, node: dict[str, Any]) -> tuple[Any, Any]:
        """Get two operands from a binary expression."""
        operands = node.get("operand", [])
        if len(operands) != 2:
            raise ELMExecutionError(f"Binary operator requires 2 operands, got {len(operands)}")
        return self.evaluate(operands[0]), self.evaluate(operands[1])

    def _get_unary_operand(self, node: dict[str, Any]) -> Any:
        """Get operand from a unary expression."""
        operand = node.get("operand")
        return self.evaluate(operand)

    def _eval_add(self, node: dict[str, Any]) -> Any:
        """Evaluate addition."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        return left + right

    def _eval_subtract(self, node: dict[str, Any]) -> Any:
        """Evaluate subtraction."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        return left - right

    def _eval_multiply(self, node: dict[str, Any]) -> Any:
        """Evaluate multiplication."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        return left * right

    def _eval_divide(self, node: dict[str, Any]) -> Any:
        """Evaluate division."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if right == 0:
            return None
        return Decimal(str(left)) / Decimal(str(right))

    def _eval_truncated_divide(self, node: dict[str, Any]) -> Any:
        """Evaluate truncated (integer) division."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if right == 0:
            return None
        return int(left) // int(right)

    def _eval_modulo(self, node: dict[str, Any]) -> Any:
        """Evaluate modulo."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if right == 0:
            return None
        return left % right

    def _eval_power(self, node: dict[str, Any]) -> Any:
        """Evaluate power."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        return left**right

    def _eval_negate(self, node: dict[str, Any]) -> Any:
        """Evaluate negation."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return -operand

    def _eval_abs(self, node: dict[str, Any]) -> Any:
        """Evaluate absolute value."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return abs(operand)

    def _eval_ceiling(self, node: dict[str, Any]) -> Any:
        """Evaluate ceiling."""
        import math

        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return math.ceil(operand)

    def _eval_floor(self, node: dict[str, Any]) -> Any:
        """Evaluate floor."""
        import math

        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return math.floor(operand)

    def _eval_truncate(self, node: dict[str, Any]) -> Any:
        """Evaluate truncate."""
        import math

        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return math.trunc(operand)

    def _eval_round(self, node: dict[str, Any]) -> Any:
        """Evaluate round."""
        operand = self.evaluate(node.get("operand"))
        precision = self.evaluate(node.get("precision"))
        if operand is None:
            return None
        if precision is None:
            return round(operand)
        return round(operand, int(precision))

    def _eval_ln(self, node: dict[str, Any]) -> Any:
        """Evaluate natural logarithm."""
        import math

        operand = self._get_unary_operand(node)
        if operand is None or operand <= 0:
            return None
        return Decimal(str(math.log(float(operand))))

    def _eval_log(self, node: dict[str, Any]) -> Any:
        """Evaluate logarithm with base."""
        import math

        left, right = self._get_binary_operands(node)
        if left is None or right is None or left <= 0 or right <= 0:
            return None
        return Decimal(str(math.log(float(left), float(right))))

    def _eval_exp(self, node: dict[str, Any]) -> Any:
        """Evaluate exponential."""
        import math

        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return Decimal(str(math.exp(float(operand))))

    def _eval_successor(self, node: dict[str, Any]) -> Any:
        """Evaluate successor - returns the next value after the operand.

        CQL semantics:
        - Integer: operand + 1
        - Decimal: operand + minimum decimal increment
        - Date: next day
        - DateTime: next millisecond
        - Time: next millisecond
        - Quantity: value + minimum increment for that unit
        """
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, int):
            return operand + 1
        if isinstance(operand, Decimal):
            # Minimum decimal increment (8 decimal places)
            return operand + Decimal("0.00000001")
        if isinstance(operand, FHIRDate):
            py_date = operand.to_date()
            if py_date:
                next_day = py_date + timedelta(days=1)
                return FHIRDate(year=next_day.year, month=next_day.month, day=next_day.day)
            # Partial date - increment at highest precision available
            if operand.month is not None:
                # Has month, increment month
                if operand.month == 12:
                    return FHIRDate(year=operand.year + 1, month=1)
                return FHIRDate(year=operand.year, month=operand.month + 1)
            # Year only
            return FHIRDate(year=operand.year + 1)
        if isinstance(operand, FHIRDateTime):
            py_dt = operand.to_datetime()
            if py_dt:
                next_ms = py_dt + timedelta(milliseconds=1)
                return FHIRDateTime(
                    year=next_ms.year,
                    month=next_ms.month,
                    day=next_ms.day,
                    hour=next_ms.hour,
                    minute=next_ms.minute,
                    second=next_ms.second,
                    millisecond=next_ms.microsecond // 1000,
                    tz_offset=operand.tz_offset,
                )
            # Partial datetime - increment at highest precision
            return self._increment_partial_datetime(operand, 1)
        if isinstance(operand, FHIRTime):
            py_time = operand.to_time()
            if py_time:
                # Convert to total milliseconds, add 1, convert back
                total_ms = (
                    py_time.hour * 3600000
                    + py_time.minute * 60000
                    + py_time.second * 1000
                    + py_time.microsecond // 1000
                )
                total_ms += 1
                if total_ms >= 86400000:  # Overflow past midnight
                    total_ms = 86400000 - 1  # Max time
                hour = total_ms // 3600000
                minute = (total_ms % 3600000) // 60000
                second = (total_ms % 60000) // 1000
                ms = total_ms % 1000
                return FHIRTime(hour=hour, minute=minute, second=second, millisecond=ms)
        if isinstance(operand, Quantity):
            # Increment by minimum unit (1 in the unit's smallest denomination)
            return Quantity(value=operand.value + Decimal("0.00000001"), unit=operand.unit)
        return operand

    def _eval_predecessor(self, node: dict[str, Any]) -> Any:
        """Evaluate predecessor - returns the value before the operand.

        CQL semantics:
        - Integer: operand - 1
        - Decimal: operand - minimum decimal decrement
        - Date: previous day
        - DateTime: previous millisecond
        - Time: previous millisecond
        - Quantity: value - minimum decrement for that unit
        """
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, int):
            return operand - 1
        if isinstance(operand, Decimal):
            return operand - Decimal("0.00000001")
        if isinstance(operand, FHIRDate):
            py_date = operand.to_date()
            if py_date:
                prev_day = py_date - timedelta(days=1)
                return FHIRDate(year=prev_day.year, month=prev_day.month, day=prev_day.day)
            # Partial date - decrement at highest precision available
            if operand.month is not None:
                if operand.month == 1:
                    return FHIRDate(year=operand.year - 1, month=12)
                return FHIRDate(year=operand.year, month=operand.month - 1)
            # Year only
            return FHIRDate(year=operand.year - 1)
        if isinstance(operand, FHIRDateTime):
            py_dt = operand.to_datetime()
            if py_dt:
                prev_ms = py_dt - timedelta(milliseconds=1)
                return FHIRDateTime(
                    year=prev_ms.year,
                    month=prev_ms.month,
                    day=prev_ms.day,
                    hour=prev_ms.hour,
                    minute=prev_ms.minute,
                    second=prev_ms.second,
                    millisecond=prev_ms.microsecond // 1000,
                    tz_offset=operand.tz_offset,
                )
            # Partial datetime - decrement at highest precision
            return self._increment_partial_datetime(operand, -1)
        if isinstance(operand, FHIRTime):
            py_time = operand.to_time()
            if py_time:
                total_ms = (
                    py_time.hour * 3600000
                    + py_time.minute * 60000
                    + py_time.second * 1000
                    + py_time.microsecond // 1000
                )
                total_ms -= 1
                if total_ms < 0:
                    total_ms = 0  # Min time
                hour = total_ms // 3600000
                minute = (total_ms % 3600000) // 60000
                second = (total_ms % 60000) // 1000
                ms = total_ms % 1000
                return FHIRTime(hour=hour, minute=minute, second=second, millisecond=ms)
        if isinstance(operand, Quantity):
            return Quantity(value=operand.value - Decimal("0.00000001"), unit=operand.unit)
        return operand

    def _increment_partial_datetime(self, dt: FHIRDateTime, delta: int) -> FHIRDateTime:
        """Increment/decrement a partial datetime at its highest precision."""
        if dt.second is not None:
            # Has seconds - increment milliseconds
            ms = (dt.millisecond or 0) + delta
            new_ms = max(0, min(999, ms))
            return FHIRDateTime(
                year=dt.year,
                month=dt.month,
                day=dt.day,
                hour=dt.hour,
                minute=dt.minute,
                second=dt.second,
                millisecond=new_ms,
                tz_offset=dt.tz_offset,
            )
        if dt.minute is not None:
            return FHIRDateTime(
                year=dt.year,
                month=dt.month,
                day=dt.day,
                hour=dt.hour,
                minute=dt.minute,
                second=max(0, min(59, 0 + delta)) if delta > 0 else 59,
                tz_offset=dt.tz_offset,
            )
        if dt.hour is not None:
            return FHIRDateTime(
                year=dt.year,
                month=dt.month,
                day=dt.day,
                hour=dt.hour,
                minute=max(0, min(59, 0 + delta)) if delta > 0 else 59,
                tz_offset=dt.tz_offset,
            )
        if dt.day is not None:
            return FHIRDateTime(
                year=dt.year,
                month=dt.month,
                day=dt.day,
                hour=max(0, min(23, 0 + delta)) if delta > 0 else 23,
                tz_offset=dt.tz_offset,
            )
        if dt.month is not None:
            new_day = 1 + delta if delta > 0 else 28  # Approximate last day
            return FHIRDateTime(
                year=dt.year,
                month=dt.month,
                day=max(1, min(28, new_day)),
                tz_offset=dt.tz_offset,
            )
        # Year only
        return FHIRDateTime(
            year=dt.year,
            month=1 + delta if delta > 0 else 12,
            tz_offset=dt.tz_offset,
        )

    def _eval_min_value(self, node: dict[str, Any]) -> Any:
        """Evaluate minimum value for type."""
        value_type = node.get("valueType", "")
        if "Integer" in value_type:
            return -(2**31)
        elif "Decimal" in value_type:
            return Decimal("-99999999999999999999.99999999")
        return None

    def _eval_max_value(self, node: dict[str, Any]) -> Any:
        """Evaluate maximum value for type."""
        value_type = node.get("valueType", "")
        if "Integer" in value_type:
            return 2**31 - 1
        elif "Decimal" in value_type:
            return Decimal("99999999999999999999.99999999")
        return None

    # =========================================================================
    # Comparison Handlers
    # =========================================================================

    def _eval_equal(self, node: dict[str, Any]) -> bool | None:
        """Evaluate equality."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        is_equal: bool = left == right
        return is_equal

    def _eval_not_equal(self, node: dict[str, Any]) -> bool | None:
        """Evaluate inequality."""
        result = self._eval_equal(node)
        if result is None:
            return None
        return not result

    def _eval_equivalent(self, node: dict[str, Any]) -> bool:
        """Evaluate equivalence (null-safe)."""
        left, right = self._get_binary_operands(node)
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False
        is_equivalent: bool = left == right
        return is_equivalent

    def _eval_less(self, node: dict[str, Any]) -> bool | None:
        """Evaluate less than."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        is_less: bool = left < right
        return is_less

    def _eval_less_or_equal(self, node: dict[str, Any]) -> bool | None:
        """Evaluate less than or equal."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        is_less_or_equal: bool = left <= right
        return is_less_or_equal

    def _eval_greater(self, node: dict[str, Any]) -> bool | None:
        """Evaluate greater than."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        is_greater: bool = left > right
        return is_greater

    def _eval_greater_or_equal(self, node: dict[str, Any]) -> bool | None:
        """Evaluate greater than or equal."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        is_greater_or_equal: bool = left >= right
        return is_greater_or_equal

    # =========================================================================
    # Boolean Handlers
    # =========================================================================

    def _eval_and(self, node: dict[str, Any]) -> bool | None:
        """Evaluate logical AND with three-valued logic."""
        left, right = self._get_binary_operands(node)

        # Three-valued logic
        if left is False or right is False:
            return False
        if left is None or right is None:
            return None
        conjunction: bool = left and right
        return conjunction

    def _eval_or(self, node: dict[str, Any]) -> bool | None:
        """Evaluate logical OR with three-valued logic."""
        left, right = self._get_binary_operands(node)

        # Three-valued logic
        if left is True or right is True:
            return True
        if left is None or right is None:
            return None
        disjunction: bool = left or right
        return disjunction

    def _eval_xor(self, node: dict[str, Any]) -> bool | None:
        """Evaluate logical XOR."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        return bool(left) != bool(right)

    def _eval_not(self, node: dict[str, Any]) -> bool | None:
        """Evaluate logical NOT."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return not operand

    def _eval_implies(self, node: dict[str, Any]) -> bool | None:
        """Evaluate logical implication."""
        left, right = self._get_binary_operands(node)

        # A implies B = not A or B
        if left is False:
            return True
        if left is True:
            consequent: bool | None = right
            return consequent
        # left is None
        if right is True:
            return True
        return None

    def _eval_is_true(self, node: dict[str, Any]) -> bool:
        """Check if value is true."""
        operand = self._get_unary_operand(node)
        return operand is True

    def _eval_is_false(self, node: dict[str, Any]) -> bool:
        """Check if value is false."""
        operand = self._get_unary_operand(node)
        return operand is False

    def _eval_is_null(self, node: dict[str, Any]) -> bool:
        """Check if value is null."""
        operand = self._get_unary_operand(node)
        return operand is None

    # =========================================================================
    # Conditional Handlers
    # =========================================================================

    def _eval_if(self, node: dict[str, Any]) -> Any:
        """Evaluate if-then-else."""
        condition = self.evaluate(node.get("condition"))
        if condition is True:
            return self.evaluate(node.get("then"))
        else:
            else_expr = node.get("else")
            if else_expr:
                return self.evaluate(else_expr)
            return None

    def _eval_case(self, node: dict[str, Any]) -> Any:
        """Evaluate case expression."""
        comparand = node.get("comparand")
        comparand_value = self.evaluate(comparand) if comparand else None

        for item in node.get("caseItem", []):
            when_expr = item.get("when")
            when_value = self.evaluate(when_expr)

            if comparand_value is not None:
                # With comparand: compare values
                if when_value == comparand_value:
                    return self.evaluate(item.get("then"))
            else:
                # Without comparand: evaluate as boolean
                if when_value is True:
                    return self.evaluate(item.get("then"))

        # Return else value if no match
        else_expr = node.get("else")
        if else_expr:
            return self.evaluate(else_expr)
        return None

    def _eval_coalesce(self, node: dict[str, Any]) -> Any:
        """Evaluate coalesce (first non-null)."""
        for operand in node.get("operand", []):
            result = self.evaluate(operand)
            if result is not None:
                # For collections, check if non-empty
                if isinstance(result, list):
                    if len(result) > 0:
                        return result
                else:
                    return result
        return None

    # =========================================================================
    # String Handlers
    # =========================================================================

    def _eval_concatenate(self, node: dict[str, Any]) -> str | None:
        """Evaluate string concatenation."""
        parts = []
        for operand in node.get("operand", []):
            value = self.evaluate(operand)
            if value is None:
                return None
            parts.append(str(value))
        return "".join(parts)

    def _eval_combine(self, node: dict[str, Any]) -> str | None:
        """Evaluate combine (join list with separator)."""
        source = self.evaluate(node.get("source"))
        separator = self.evaluate(node.get("separator")) or ""

        if source is None:
            return None
        if not isinstance(source, list):
            source = [source]

        # Filter out nulls and convert to strings
        parts = [str(s) for s in source if s is not None]
        return separator.join(parts)

    def _eval_split(self, node: dict[str, Any]) -> list[str] | None:
        """Evaluate split."""
        string = self.evaluate(node.get("stringToSplit"))
        separator = self.evaluate(node.get("separator"))

        if string is None:
            return None
        if separator is None:
            return [string]

        parts: list[str] = string.split(separator)
        return parts

    def _eval_length(self, node: dict[str, Any]) -> int | None:
        """Evaluate length (string or list)."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return len(operand)

    def _eval_upper(self, node: dict[str, Any]) -> str | None:
        """Evaluate uppercase."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return str(operand).upper()

    def _eval_lower(self, node: dict[str, Any]) -> str | None:
        """Evaluate lowercase."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return str(operand).lower()

    def _eval_substring(self, node: dict[str, Any]) -> str | None:
        """Evaluate substring."""
        # Support both named properties and operand array format
        operand = node.get("operand")
        if operand and isinstance(operand, list) and len(operand) >= 2:
            string = self.evaluate(operand[0])
            start = self.evaluate(operand[1])
            length = self.evaluate(operand[2]) if len(operand) > 2 else None
        else:
            string = self.evaluate(node.get("stringToSub"))
            start = self.evaluate(node.get("startIndex"))
            length = self.evaluate(node.get("length"))

        if string is None or start is None:
            return None

        start = int(start)
        if length is not None:
            bounded: str = string[start : start + int(length)]
            return bounded
        remainder: str = string[start:]
        return remainder

    def _eval_starts_with(self, node: dict[str, Any]) -> bool | None:
        """Evaluate starts with."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        return str(left).startswith(str(right))

    def _eval_ends_with(self, node: dict[str, Any]) -> bool | None:
        """Evaluate ends with."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        return str(left).endswith(str(right))

    def _eval_matches(self, node: dict[str, Any]) -> bool | None:
        """Evaluate regex match."""
        import re

        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        return bool(re.search(right, left))

    def _eval_replace_matches(self, node: dict[str, Any]) -> str | None:
        """Evaluate regex replace."""
        import re

        operands = node.get("operand", [])
        if len(operands) != 3:
            return None

        string = self.evaluate(operands[0])
        pattern = self.evaluate(operands[1])
        replacement = self.evaluate(operands[2])

        if string is None or pattern is None or replacement is None:
            return None

        replaced: str = re.sub(pattern, replacement, string)
        return replaced

    def _eval_indexer(self, node: dict[str, Any]) -> Any:
        """Evaluate indexer (string/list access)."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        try:
            return left[int(right)]
        except (IndexError, KeyError):
            return None

    def _eval_position_of(self, node: dict[str, Any]) -> int | None:
        """Evaluate position of substring."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        pos = str(right).find(str(left))
        return pos if pos >= 0 else None

    def _eval_last_position_of(self, node: dict[str, Any]) -> int | None:
        """Evaluate last position of substring."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        pos = str(right).rfind(str(left))
        return pos if pos >= 0 else None

    # =========================================================================
    # Collection Handlers
    # =========================================================================

    def _eval_first(self, node: dict[str, Any]) -> Any:
        """Evaluate first element."""
        source = self.evaluate(node.get("source"))
        if source is None or not isinstance(source, list) or len(source) == 0:
            return None
        return source[0]

    def _eval_last(self, node: dict[str, Any]) -> Any:
        """Evaluate last element."""
        source = self.evaluate(node.get("source"))
        if source is None or not isinstance(source, list) or len(source) == 0:
            return None
        return source[-1]

    def _eval_index_of(self, node: dict[str, Any]) -> int | None:
        """Evaluate index of element."""
        source = self.evaluate(node.get("source"))
        element = self.evaluate(node.get("element"))
        if source is None or element is None:
            return None
        try:
            index: int = source.index(element)
            return index
        except ValueError:
            return -1

    def _eval_contains(self, node: dict[str, Any]) -> bool | None:
        """Evaluate collection contains."""
        left, right = self._get_binary_operands(node)
        if left is None:
            return None
        if isinstance(left, list):
            return right in left
        if isinstance(left, CQLInterval):
            return left.contains(right)
        return None

    def _eval_in(self, node: dict[str, Any]) -> bool | None:
        """Evaluate element in collection."""
        left, right = self._get_binary_operands(node)
        if right is None:
            return None
        if isinstance(right, list):
            return left in right
        if isinstance(right, CQLInterval):
            return right.contains(left)
        return None

    def _eval_includes(self, node: dict[str, Any]) -> bool | None:
        """Evaluate collection includes."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, list) and isinstance(right, list):
            return all(r in left for r in right)
        return None

    def _eval_included_in(self, node: dict[str, Any]) -> bool | None:
        """Evaluate included in."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, list) and isinstance(right, list):
            return all(item in right for item in left)
        return None

    def _eval_proper_includes(self, node: dict[str, Any]) -> bool | None:
        """Evaluate proper includes."""
        includes = self._eval_includes(node)
        if includes is None:
            return None
        if not includes:
            return False
        left, right = self._get_binary_operands(node)
        return len(left) > len(right)

    def _eval_proper_included_in(self, node: dict[str, Any]) -> bool | None:
        """Evaluate proper included in."""
        included = self._eval_included_in(node)
        if included is None:
            return None
        if not included:
            return False
        left, right = self._get_binary_operands(node)
        return len(left) < len(right)

    def _eval_distinct(self, node: dict[str, Any]) -> list[Any] | None:
        """Evaluate distinct."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if not isinstance(operand, list):
            return [operand]

        # Preserve order while removing duplicates
        seen: set[Any] = set()
        result = []
        for item in operand:
            # Use tuple for unhashable types
            key = item if isinstance(item, (str, int, float, bool, type(None))) else id(item)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def _eval_flatten(self, node: dict[str, Any]) -> list[Any] | None:
        """Evaluate flatten."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if not isinstance(operand, list):
            return [operand]

        result = []
        for item in operand:
            if isinstance(item, list):
                result.extend(item)
            else:
                result.append(item)
        return result

    def _eval_exists(self, node: dict[str, Any]) -> bool:
        """Evaluate exists (non-empty check)."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return False
        if isinstance(operand, list):
            return len(operand) > 0
        return True

    def _eval_singleton_from(self, node: dict[str, Any]) -> Any:
        """Evaluate singleton from."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, list):
            if len(operand) == 0:
                return None
            if len(operand) == 1:
                return operand[0]
            raise ELMExecutionError("Expected single element, got multiple")
        return operand

    def _eval_to_list(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate to list."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return []
        if isinstance(operand, list):
            return operand
        return [operand]

    # =========================================================================
    # Aggregate Handlers
    # =========================================================================

    def _get_aggregate_source(self, node: dict[str, Any]) -> list[Any]:
        """Get source list for aggregate function."""
        source = self.evaluate(node.get("source"))
        if source is None:
            return []
        if not isinstance(source, list):
            return [source]
        return source

    def _eval_count(self, node: dict[str, Any]) -> int:
        """Evaluate count."""
        source = self._get_aggregate_source(node)
        return len([x for x in source if x is not None])

    def _eval_sum(self, node: dict[str, Any]) -> Any:
        """Evaluate sum."""
        source = self._get_aggregate_source(node)
        values = [x for x in source if x is not None]
        if not values:
            return None
        return sum(values)

    def _eval_avg(self, node: dict[str, Any]) -> Any:
        """Evaluate average."""
        source = self._get_aggregate_source(node)
        values = [x for x in source if x is not None]
        if not values:
            return None
        return Decimal(str(sum(values))) / len(values)

    def _eval_min(self, node: dict[str, Any]) -> Any:
        """Evaluate minimum."""
        source = self._get_aggregate_source(node)
        values = [x for x in source if x is not None]
        if not values:
            return None
        return min(values)

    def _eval_max(self, node: dict[str, Any]) -> Any:
        """Evaluate maximum."""
        source = self._get_aggregate_source(node)
        values = [x for x in source if x is not None]
        if not values:
            return None
        return max(values)

    def _eval_median(self, node: dict[str, Any]) -> Any:
        """Evaluate median."""
        import statistics

        source = self._get_aggregate_source(node)
        values = [x for x in source if x is not None]
        if not values:
            return None
        return statistics.median(values)

    def _eval_mode(self, node: dict[str, Any]) -> Any:
        """Evaluate mode."""
        import statistics

        source = self._get_aggregate_source(node)
        values = [x for x in source if x is not None]
        if not values:
            return None
        try:
            return statistics.mode(values)
        except statistics.StatisticsError:
            return values[0]  # Return first if no unique mode

    def _eval_variance(self, node: dict[str, Any]) -> Any:
        """Evaluate sample variance."""
        import statistics

        source = self._get_aggregate_source(node)
        values = [float(x) for x in source if x is not None]
        if len(values) < 2:
            return None
        return Decimal(str(statistics.variance(values)))

    def _eval_population_variance(self, node: dict[str, Any]) -> Any:
        """Evaluate population variance."""
        import statistics

        source = self._get_aggregate_source(node)
        values = [float(x) for x in source if x is not None]
        if not values:
            return None
        return Decimal(str(statistics.pvariance(values)))

    def _eval_std_dev(self, node: dict[str, Any]) -> Any:
        """Evaluate sample standard deviation."""
        import statistics

        source = self._get_aggregate_source(node)
        values = [float(x) for x in source if x is not None]
        if len(values) < 2:
            return None
        return Decimal(str(statistics.stdev(values)))

    def _eval_population_std_dev(self, node: dict[str, Any]) -> Any:
        """Evaluate population standard deviation."""
        import statistics

        source = self._get_aggregate_source(node)
        values = [float(x) for x in source if x is not None]
        if not values:
            return None
        return Decimal(str(statistics.pstdev(values)))

    def _eval_all_true(self, node: dict[str, Any]) -> bool:
        """Evaluate all true."""
        source = self._get_aggregate_source(node)
        return all(x is True for x in source)

    def _eval_any_true(self, node: dict[str, Any]) -> bool:
        """Evaluate any true."""
        source = self._get_aggregate_source(node)
        return any(x is True for x in source)

    def _eval_product(self, node: dict[str, Any]) -> Any:
        """Evaluate product."""
        import math

        source = self._get_aggregate_source(node)
        values = [x for x in source if x is not None]
        if not values:
            return None
        return math.prod(values)

    def _eval_geometric_mean(self, node: dict[str, Any]) -> Any:
        """Evaluate geometric mean."""
        import statistics

        source = self._get_aggregate_source(node)
        values = [float(x) for x in source if x is not None and x > 0]
        if not values:
            return None
        return Decimal(str(statistics.geometric_mean(values)))

    # =========================================================================
    # Set Operation Handlers
    # =========================================================================

    def _eval_union(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate set union."""
        result = []
        for operand in node.get("operand", []):
            items = self.evaluate(operand)
            if items is not None:
                if isinstance(items, list):
                    result.extend(items)
                else:
                    result.append(items)
        return result

    def _eval_intersect(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate set intersection."""
        operands = node.get("operand", [])
        if len(operands) < 2:
            return []

        first = self.evaluate(operands[0])
        if first is None:
            return []
        if not isinstance(first, list):
            first = [first]

        result = set(id(x) if not isinstance(x, (str, int, float, bool)) else x for x in first)
        first_by_id = {id(x) if not isinstance(x, (str, int, float, bool)) else x: x for x in first}

        for operand in operands[1:]:
            items = self.evaluate(operand)
            if items is None:
                return []
            if not isinstance(items, list):
                items = [items]
            item_set = set(id(x) if not isinstance(x, (str, int, float, bool)) else x for x in items)
            result &= item_set

        return [first_by_id[k] for k in result if k in first_by_id]

    def _eval_except(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate set difference."""
        operands = node.get("operand", [])
        if len(operands) < 2:
            return []

        first = self.evaluate(operands[0])
        if first is None:
            return []
        if not isinstance(first, list):
            first = [first]

        for operand in operands[1:]:
            items = self.evaluate(operand)
            if items is not None:
                if not isinstance(items, list):
                    items = [items]
                first = [x for x in first if x not in items]

        return first

    # =========================================================================
    # Reference Handlers
    # =========================================================================

    def _eval_expression_ref(self, node: dict[str, Any]) -> Any:
        """Evaluate expression reference.

        Supports both local and external (included) library references.
        When libraryName is specified, looks up the definition in that
        included library.
        """
        name = node.get("name")
        library_name = node.get("libraryName")

        if not name:
            raise ELMReferenceError("Expression reference missing name")

        # Create cache key (qualified for external refs)
        cache_key = f"{library_name}.{name}" if library_name else name

        # Check for cached definition
        found, cached = self.context.get_cached_definition(cache_key)
        if found:
            return cached

        # Find definition in library
        library = self._library
        if library_name:
            # Resolve included library
            library = self.get_included_library(library_name)
            if not library:
                raise ELMReferenceError(
                    f"Included library '{library_name}' not found. Make sure the library is loaded and registered."
                )

        if not library:
            raise ELMReferenceError(f"No library context for expression reference: {name}")

        definition = library.get_definition(name)
        if not definition:
            raise ELMReferenceError(f"Definition not found: {name}")

        # Get expression and convert to dict if needed
        expression = definition.expression
        if hasattr(expression, "model_dump"):
            expression = expression.model_dump(by_alias=True, exclude_none=True)

        # For external library references, temporarily switch library context
        original_library = self._library
        if library_name:
            self._library = library

        try:
            # Evaluate and cache
            result = self.evaluate(expression)
            self.context.cache_definition(cache_key, result)
            return result
        finally:
            # Restore original library context
            if library_name:
                self._library = original_library

    def _eval_function_ref(self, node: dict[str, Any]) -> Any:
        """Evaluate function reference.

        Supports both local and external (included) library references.
        When libraryName is specified, looks up the function in that
        included library.
        """
        name = node.get("name")
        library_name = node.get("libraryName")
        operands = node.get("operand", [])

        if not name:
            raise ELMReferenceError("Function reference missing name")

        # Evaluate operands
        args = [self.evaluate(op) for op in operands]

        # Check for built-in functions (only for non-qualified refs)
        if not library_name:
            builtin = self._get_builtin_function(name)
            if builtin:
                return builtin(*args)

        # Find function in library
        library = self._library
        if library_name:
            # Resolve included library
            library = self.get_included_library(library_name)
            if not library:
                raise ELMReferenceError(
                    f"Included library '{library_name}' not found. Make sure the library is loaded and registered."
                )

        if not library:
            raise ELMReferenceError(f"No library context for function reference: {name}")

        func_def = library.get_function(name)
        if not func_def:
            raise ELMReferenceError(f"Function not found: {name}")

        if func_def.external:
            raise ELMReferenceError(f"External function not implemented: {name}")

        # For external library references, temporarily switch library context
        original_library = self._library
        if library_name:
            self._library = library

        # Create new scope for function execution
        self.context.push_alias_scope()
        try:
            # Bind parameters
            for i, param in enumerate(func_def.operand):
                if i < len(args):
                    self.context.set_alias(param.name, args[i])

            # Evaluate function body
            return self.evaluate(func_def.expression)
        finally:
            self.context.pop_alias_scope()
            # Restore original library context
            if library_name:
                self._library = original_library

    def _eval_parameter_ref(self, node: dict[str, Any]) -> Any:
        """Evaluate parameter reference."""
        name = node.get("name")
        if not name:
            raise ELMReferenceError("Parameter reference missing name")

        # Check context parameters
        value = self.context.get_parameter(name)
        if value is not None:
            return value

        # Check library default
        if self._library:
            param = self._library.get_parameter(name)
            if param and param.default is not None:
                return self.evaluate(param.default)

        return None

    def _eval_operand_ref(self, node: dict[str, Any]) -> Any:
        """Evaluate operand reference (function parameter).

        OperandRef is used within function bodies to reference function parameters.
        The parameter values are bound as aliases when the function is called.
        """
        name = node.get("name")
        if not name:
            raise ELMReferenceError("Operand reference missing name")

        # Parameters are bound as aliases in the context
        return self.context.get_alias(name)

    def _eval_property(self, node: dict[str, Any]) -> Any:
        """Evaluate property access."""
        path = node.get("path")
        scope = node.get("scope")
        source = node.get("source")

        if source:
            obj = self.evaluate(source)
        elif scope:
            obj = self.context.get_alias(scope)
        else:
            obj = self.context.resource

        if obj is None or path is None:
            return None

        # Navigate the path
        return self._navigate_property(obj, path)

    def _navigate_property(self, obj: Any, path: str) -> Any:
        """Navigate a property path on an object."""
        if obj is None:
            return None

        parts = path.split(".")
        current = obj

        for part in parts:
            if current is None:
                return None

            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # Map property access over list
                current = [self._navigate_property(item, part) for item in current]
                current = [x for x in current if x is not None]
                if not current:
                    return None
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

        return current

    def _eval_alias_ref(self, node: dict[str, Any]) -> Any:
        """Evaluate alias reference."""
        name = node.get("name")
        if not name:
            raise ELMReferenceError("Alias reference missing name")
        return self.context.get_alias(name)

    def _eval_query_let_ref(self, node: dict[str, Any]) -> Any:
        """Evaluate query let reference."""
        name = node.get("name")
        if not name:
            raise ELMReferenceError("Query let reference missing name")
        return self.context.get_alias(name)

    def _eval_identifier_ref(self, node: dict[str, Any]) -> Any:
        """Evaluate generic identifier reference."""
        name = node.get("name")
        if not name:
            raise ELMReferenceError("Identifier reference missing name")

        # Try alias first (checking has_alias to handle None values)
        if self.context.has_alias(name):
            return self.context.get_alias(name)

        # Try parameter
        if self.context.has_parameter(name):
            return self.context.get_parameter(name)

        # Try definition
        if self._library:
            definition = self._library.get_definition(name)
            if definition:
                return self.evaluate(definition.expression)

        raise ELMReferenceError(f"Identifier not found: {name}")

    # =========================================================================
    # Query Handlers
    # =========================================================================

    def _eval_query(self, node: dict[str, Any]) -> Any:
        """Evaluate a query, yielding its result list or the accumulator when it aggregates."""
        sources = node.get("source", [])
        let_clauses = node.get("let", [])
        relationships = node.get("relationship", [])
        where = node.get("where")
        return_clause = node.get("return")
        aggregate = node.get("aggregate")
        sort = node.get("sort")

        # Process sources
        if not sources:
            return []

        # Evaluate all sources and get their data
        source_data_list: list[tuple[str, list[Any]]] = []
        for source in sources:
            alias = source.get("alias")
            source_expr = source.get("expression")
            source_data = self.evaluate(source_expr)

            if source_data is None:
                source_data = []
            if not isinstance(source_data, list):
                source_data = [source_data]

            source_data_list.append((alias, source_data))

        # If any source is empty, result is empty (but still process aggregate)
        if any(len(data) == 0 for _, data in source_data_list):
            # Still need to process aggregate with empty results
            if aggregate:
                first_alias = source_data_list[0][0] if source_data_list else None
                return self._apply_aggregate([], aggregate, first_alias)
            return []

        # Generate cross product of all sources
        source_combinations = self._generate_cross_product(source_data_list)

        results = []
        first_alias = source_data_list[0][0] if source_data_list else None

        for combination in source_combinations:
            self.context.push_alias_scope()
            try:
                # Set aliases for all sources in this combination
                for alias, item in combination:
                    self.context.set_alias(alias, item)

                # Process let clauses
                for let_clause in let_clauses or []:
                    let_id = let_clause.get("identifier")
                    let_expr = let_clause.get("expression")
                    let_value = self.evaluate(let_expr)
                    self.context.set_alias(let_id, let_value)

                # Process relationships (with/without)
                include = True
                for rel in relationships or []:
                    rel_type = "With" if "suchThat" in rel or rel.get("type") == "With" else "Without"
                    rel_alias = rel.get("alias")
                    rel_expr = rel.get("expression")
                    such_that = rel.get("suchThat")

                    rel_data = self.evaluate(rel_expr)
                    if rel_data is None:
                        rel_data = []
                    if not isinstance(rel_data, list):
                        rel_data = [rel_data]

                    found = False
                    for rel_item in rel_data:
                        self.context.set_alias(rel_alias, rel_item)
                        if such_that:
                            if self.evaluate(such_that) is True:
                                found = True
                                break
                        else:
                            found = True
                            break

                    if rel_type == "With" and not found:
                        include = False
                        break
                    if rel_type == "Without" and found:
                        include = False
                        break

                if not include:
                    continue

                # Process where clause
                if where:
                    where_result = self.evaluate(where)
                    if where_result is not True:
                        continue

                # Process return clause
                if return_clause:
                    return_expr = return_clause.get("expression")
                    result = self.evaluate(return_expr)
                else:
                    # Default: return first source item
                    result = combination[0][1] if combination else None

                results.append(result)

            finally:
                self.context.pop_alias_scope()

        # Handle distinct
        if return_clause and return_clause.get("distinct", True):
            results = self._make_distinct(results)

        # Process aggregate
        if aggregate:
            return self._apply_aggregate(results, aggregate, first_alias)

        # Process sort
        if sort:
            results = self._apply_sort(results, sort)

        return results

    def _generate_cross_product(self, source_data_list: list[tuple[str, list[Any]]]) -> list[list[tuple[str, Any]]]:
        """Generate cross product of multiple source lists.

        Args:
            source_data_list: List of (alias, data_list) tuples

        Returns:
            List of combinations, where each combination is a list of (alias, item) tuples
        """
        if not source_data_list:
            return []

        if len(source_data_list) == 1:
            alias, data = source_data_list[0]
            return [[(alias, item)] for item in data]

        # Recursive: combine first source with cross product of rest
        first_alias, first_data = source_data_list[0]
        rest_product = self._generate_cross_product(source_data_list[1:])

        result = []
        for item in first_data:
            for rest_combo in rest_product:
                result.append([(first_alias, item)] + rest_combo)

        return result

    def _make_distinct(self, items: list[Any]) -> list[Any]:
        """Make list distinct while preserving order."""
        seen: set[Any] = set()
        result = []
        for item in items:
            key = item if isinstance(item, (str, int, float, bool, type(None))) else id(item)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def _apply_aggregate(self, results: list[Any], aggregate: dict[str, Any], source_alias: str | None) -> Any:
        """Apply aggregate clause to accumulate a value across results.

        Aggregate clause syntax: aggregate [distinct] identifier starting value : expression

        Args:
            results: The query results to aggregate over
            aggregate: The aggregate clause definition
            source_alias: The source alias name for the query

        Returns:
            The accumulated result value
        """
        # Get the accumulator identifier
        identifier = aggregate.get("identifier")
        if not identifier:
            return results

        # Get starting value
        starting = aggregate.get("starting")
        accumulator = self.evaluate(starting) if starting else None

        # Check for distinct modifier
        is_distinct = aggregate.get("distinct", False)

        # Apply distinct if specified
        if is_distinct:
            results = self._make_distinct(results)

        # Get the aggregation expression
        agg_expression = aggregate.get("expression")
        if not agg_expression:
            return accumulator

        # Iterate through results, accumulating value
        for item in results:
            self.context.push_alias_scope()
            try:
                # Set the source item alias
                if source_alias:
                    self.context.set_alias(source_alias, item)
                self.context.set_alias("$this", item)

                # Set the accumulator variable
                self.context.set_alias(identifier, accumulator)

                # Evaluate the aggregation expression
                accumulator = self.evaluate(agg_expression)
            finally:
                self.context.pop_alias_scope()

        return accumulator

    def _apply_sort(self, items: list[Any], sort: dict[str, Any]) -> list[Any]:
        """Apply sort clause to results."""
        sort_by = sort.get("by", [])
        if not sort_by:
            return items

        def sort_key(item: Any) -> Any:
            keys = []
            for by_item in sort_by:
                path = by_item.get("path")
                if path:
                    value = self._navigate_property(item, path)
                else:
                    expr = by_item.get("expression")
                    if expr:
                        self.context.push_alias_scope()
                        try:
                            self.context.set_alias("$this", item)
                            value = self.evaluate(expr)
                        finally:
                            self.context.pop_alias_scope()
                    else:
                        value = item

                keys.append(value if value is not None else "")
            return tuple(keys)

        # Determine direction
        reverse = False
        if sort_by:
            direction = sort_by[0].get("direction", "asc")
            reverse = direction.lower() in ("desc", "descending")

        return sorted(items, key=sort_key, reverse=reverse)

    def _eval_retrieve(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate retrieve expression."""
        data_type = node.get("dataType", "")

        # Extract resource type from qualified name
        resource_type = data_type.split("}")[-1] if "{" in data_type else data_type

        # Get data source from context
        data_source = self.context._data_source
        if not data_source:
            return []

        # Get codes for filtering
        codes = None
        codes_expr = node.get("codes")
        if codes_expr:
            codes = self.evaluate(codes_expr)
            if codes is not None and not isinstance(codes, list):
                codes = [codes]

        # Get date range
        date_range = None
        date_range_expr = node.get("dateRange")
        if date_range_expr:
            date_range = self.evaluate(date_range_expr)

        # Retrieve from data source
        code_path = node.get("codeProperty")

        return data_source.retrieve(
            resource_type=resource_type,
            context=self.context,
            code_path=code_path,
            codes=codes,
            valueset=None,
            date_path=node.get("dateProperty"),
            date_range=date_range,
        )

    def _eval_for_each(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate for each expression."""
        source = self.evaluate(node.get("source"))
        element = node.get("element")
        scope = node.get("scope", "$this")

        if source is None:
            return []
        if not isinstance(source, list):
            source = [source]

        results = []
        for item in source:
            self.context.push_alias_scope()
            try:
                self.context.set_alias(scope, item)
                result = self.evaluate(element) if element else item
                results.append(result)
            finally:
                self.context.pop_alias_scope()

        return results

    def _eval_repeat(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate repeat expression."""
        # Similar to for each but recursive
        return self._eval_for_each(node)

    def _eval_filter(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate filter expression."""
        source = self.evaluate(node.get("source"))
        condition = node.get("condition")
        scope = node.get("scope", "$this")

        if source is None:
            return []
        if not isinstance(source, list):
            source = [source]

        results = []
        for item in source:
            self.context.push_alias_scope()
            try:
                self.context.set_alias(scope, item)
                if self.evaluate(condition) is True:
                    results.append(item)
            finally:
                self.context.pop_alias_scope()

        return results

    def _eval_times(self, node: dict[str, Any]) -> list[Any]:
        """Evaluate cartesian product."""
        import itertools

        operands = node.get("operand", [])
        if not operands:
            return []

        lists = []
        for op in operands:
            value = self.evaluate(op)
            if value is None:
                return []
            if not isinstance(value, list):
                value = [value]
            lists.append(value)

        return [list(combo) for combo in itertools.product(*lists)]

    # =========================================================================
    # Type Operation Handlers
    # =========================================================================

    def _eval_as(self, node: dict[str, Any]) -> Any:
        """Evaluate type cast (As expression).

        CQL semantics:
        - If the value is of the target type, return it unchanged
        - If the value can be implicitly converted, convert it
        - If strict=true and cast fails, raise error
        - If strict=false and cast fails, return null
        """
        operand = self.evaluate(node.get("operand"))
        strict = node.get("strict", False)

        # Get target type
        as_type = node.get("asType", "")
        as_type_specifier = node.get("asTypeSpecifier", {})

        target_type = as_type_specifier.get("name", "") if as_type_specifier else as_type

        # Handle null operand
        if operand is None:
            return None

        # Extract type name (remove namespace prefixes like System., FHIR., etc.)
        if "}" in target_type:
            target_type = target_type.split("}")[-1]
        if "." in target_type:
            target_type = target_type.split(".")[-1]
        target_type_lower = target_type.lower()

        # Perform type cast
        try:
            result = self._cast_to_type(operand, target_type_lower)
            if result is not None:
                return result

            # If cast failed and strict mode, raise error
            if strict:
                raise ELMExecutionError(f"Cannot cast {type(operand).__name__} to {target_type}")

            return None
        except (ValueError, TypeError) as e:
            if strict:
                raise ELMExecutionError(f"Cast error: {e}") from e
            return None

    def _cast_to_type(self, value: Any, target_type: str) -> Any:
        """Cast a value to the specified type.

        Returns the cast value, or None if cast is not possible.
        """
        # If value is already the correct type, return it
        if target_type in ("integer", "int"):
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, (float, Decimal)):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    return None
            return None

        if target_type == "decimal":
            if isinstance(value, Decimal):
                return value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return Decimal(str(value))
            if isinstance(value, str):
                try:
                    return Decimal(value)
                except Exception:
                    return None
            return None

        if target_type == "string":
            if isinstance(value, str):
                return value
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float, Decimal)):
                return str(value)
            if isinstance(value, FHIRDate):
                return str(value)
            if isinstance(value, FHIRDateTime):
                return str(value)
            if isinstance(value, FHIRTime):
                return str(value)
            return str(value)

        if target_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lower = value.lower()
                if lower in ("true", "t", "yes", "y", "1"):
                    return True
                if lower in ("false", "f", "no", "n", "0"):
                    return False
            if isinstance(value, (int, float, Decimal)):
                return value != 0
            return None

        if target_type == "date":
            if isinstance(value, FHIRDate):
                return value
            if isinstance(value, FHIRDateTime):
                return FHIRDate(year=value.year, month=value.month, day=value.day)
            if isinstance(value, str):
                return FHIRDate.parse(value)
            return None

        if target_type == "datetime":
            if isinstance(value, FHIRDateTime):
                return value
            if isinstance(value, FHIRDate):
                return FHIRDateTime(year=value.year, month=value.month, day=value.day)
            if isinstance(value, str):
                return FHIRDateTime.parse(value)
            return None

        if target_type == "time":
            if isinstance(value, FHIRTime):
                return value
            if isinstance(value, str):
                return FHIRTime.parse(value)
            return None

        if target_type == "quantity":
            if isinstance(value, Quantity):
                return value
            # Can't cast other types to Quantity without unit info
            return None

        if target_type == "code":
            if isinstance(value, CQLCode):
                return value
            # Handle dict-like objects
            if isinstance(value, dict) and "code" in value:
                return CQLCode(
                    code=value.get("code", ""),
                    system=value.get("system") or "",
                    display=value.get("display"),
                )
            return None

        if target_type == "concept":
            if isinstance(value, CQLConcept):
                return value
            if isinstance(value, CQLCode):
                return CQLConcept(codes=(value,), display=value.display)
            return None

        # List/collection types
        if target_type.startswith("list"):
            if isinstance(value, list):
                return value
            return [value]  # Singleton promotion

        # For FHIR resource types, check if it's a dict with resourceType
        if isinstance(value, dict):
            resource_type = value.get("resourceType", "")
            if resource_type.lower() == target_type:
                return value
            # Allow cast if target is Any or generic Resource
            if target_type in ("any", "resource", "domainresource"):
                return value

        # Default: return value if we can't determine incompatibility
        # This allows for FHIR subtype casting
        return value

    def _eval_is(self, node: dict[str, Any]) -> bool:
        """Evaluate type check."""
        operand = self.evaluate(node.get("operand"))
        is_type = node.get("isType", "")

        if operand is None:
            return False

        # Simple type checks
        if "Integer" in is_type:
            return isinstance(operand, int) and not isinstance(operand, bool)
        elif "Decimal" in is_type:
            return isinstance(operand, (Decimal, float))
        elif "String" in is_type:
            return isinstance(operand, str)
        elif "Boolean" in is_type:
            return isinstance(operand, bool)
        elif "Date" in is_type and "DateTime" not in is_type:
            return isinstance(operand, FHIRDate)
        elif "DateTime" in is_type:
            return isinstance(operand, FHIRDateTime)

        return True  # Default to true if type not recognized

    def _eval_to_boolean(self, node: dict[str, Any]) -> bool | None:
        """Convert to boolean."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, bool):
            return operand
        if isinstance(operand, str):
            lower = operand.lower()
            if lower in ("true", "t", "yes", "y", "1"):
                return True
            if lower in ("false", "f", "no", "n", "0"):
                return False
            return None
        if isinstance(operand, (int, float, Decimal)):
            return operand != 0
        return None

    def _eval_to_integer(self, node: dict[str, Any]) -> int | None:
        """Convert to integer."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        try:
            return int(operand)
        except (ValueError, TypeError):
            return None

    def _eval_to_long(self, node: dict[str, Any]) -> int | None:
        """Convert to long."""
        return self._eval_to_integer(node)

    def _eval_to_decimal(self, node: dict[str, Any]) -> Decimal | None:
        """Convert to decimal."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        try:
            return Decimal(str(operand))
        except (ValueError, TypeError):
            return None

    def _eval_to_string(self, node: dict[str, Any]) -> str | None:
        """Convert to string."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return str(operand)

    def _eval_to_datetime(self, node: dict[str, Any]) -> FHIRDateTime | None:
        """Convert to datetime."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, FHIRDateTime):
            return operand
        if isinstance(operand, str):
            return FHIRDateTime.parse(operand)
        return None

    def _eval_to_date(self, node: dict[str, Any]) -> FHIRDate | None:
        """Convert to date."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, FHIRDate):
            return operand
        if isinstance(operand, FHIRDateTime):
            return FHIRDate(year=operand.year, month=operand.month, day=operand.day)
        if isinstance(operand, str):
            return FHIRDate.parse(operand)
        return None

    def _eval_to_time(self, node: dict[str, Any]) -> str | None:
        """Convert to time."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        return str(operand)

    def _eval_to_quantity(self, node: dict[str, Any]) -> Quantity | None:
        """Convert to quantity."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, Quantity):
            return operand
        if isinstance(operand, (int, float, Decimal)):
            return Quantity(value=Decimal(str(operand)), unit="1")
        return None

    def _eval_to_concept(self, node: dict[str, Any]) -> CQLConcept | None:
        """Convert to concept."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, CQLConcept):
            return operand
        if isinstance(operand, CQLCode):
            return CQLConcept(codes=(operand,))
        return None

    def _eval_converts_to_boolean(self, node: dict[str, Any]) -> bool:
        """Check if converts to boolean."""
        return self._eval_to_boolean(node) is not None

    def _eval_converts_to_integer(self, node: dict[str, Any]) -> bool:
        """Check if converts to integer."""
        return self._eval_to_integer(node) is not None

    def _eval_converts_to_decimal(self, node: dict[str, Any]) -> bool:
        """Check if converts to decimal."""
        return self._eval_to_decimal(node) is not None

    def _eval_converts_to_string(self, node: dict[str, Any]) -> bool:
        """Check if converts to string."""
        return self._eval_to_string(node) is not None

    def _eval_converts_to_datetime(self, node: dict[str, Any]) -> bool:
        """Check if converts to datetime."""
        return self._eval_to_datetime(node) is not None

    def _eval_converts_to_date(self, node: dict[str, Any]) -> bool:
        """Check if converts to date."""
        return self._eval_to_date(node) is not None

    def _eval_converts_to_time(self, node: dict[str, Any]) -> bool:
        """Check if converts to time."""
        return self._eval_to_time(node) is not None

    def _eval_converts_to_quantity(self, node: dict[str, Any]) -> bool:
        """Check if converts to quantity."""
        return self._eval_to_quantity(node) is not None

    # =========================================================================
    # Date/Time Handlers
    # =========================================================================

    def _eval_today(self, node: dict[str, Any]) -> FHIRDate:
        """Evaluate Today()."""
        from datetime import date

        today = date.today()
        return FHIRDate(year=today.year, month=today.month, day=today.day)

    def _eval_now(self, node: dict[str, Any]) -> FHIRDateTime:
        """Evaluate Now()."""
        from datetime import datetime

        now = datetime.now()
        return FHIRDateTime(
            year=now.year,
            month=now.month,
            day=now.day,
            hour=now.hour,
            minute=now.minute,
            second=now.second,
        )

    def _eval_time_of_day(self, node: dict[str, Any]) -> str:
        """Evaluate TimeOfDay()."""
        from datetime import datetime

        now = datetime.now()
        return f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"

    def _eval_date_constructor(self, node: dict[str, Any]) -> FHIRDate | None:
        """Evaluate Date constructor."""
        year = self.evaluate(node.get("year"))
        month = self.evaluate(node.get("month"))
        day = self.evaluate(node.get("day"))

        if year is None:
            return None

        return FHIRDate(year=int(year), month=int(month) if month else None, day=int(day) if day else None)

    def _eval_datetime_constructor(self, node: dict[str, Any]) -> FHIRDateTime | None:
        """Evaluate DateTime constructor."""
        year = self.evaluate(node.get("year"))
        month = self.evaluate(node.get("month"))
        day = self.evaluate(node.get("day"))
        hour = self.evaluate(node.get("hour"))
        minute = self.evaluate(node.get("minute"))
        second = self.evaluate(node.get("second"))

        if year is None:
            return None

        return FHIRDateTime(
            year=int(year),
            month=int(month) if month else None,
            day=int(day) if day else None,
            hour=int(hour) if hour else None,
            minute=int(minute) if minute else None,
            second=int(second) if second else None,
        )

    def _eval_time_constructor(self, node: dict[str, Any]) -> str | None:
        """Evaluate Time constructor."""
        hour = self.evaluate(node.get("hour"))
        minute = self.evaluate(node.get("minute"))
        second = self.evaluate(node.get("second"))

        if hour is None:
            return None

        parts = [f"{int(hour):02d}"]
        if minute is not None:
            parts.append(f"{int(minute):02d}")
            if second is not None:
                parts.append(f"{int(second):02d}")

        return ":".join(parts)

    def _eval_duration_between(self, node: dict[str, Any]) -> int | None:
        """Evaluate duration between two dates/datetimes.

        CQL semantics: Returns the number of whole calendar periods between two dates.
        For example, years between 2000-01-01 and 2000-12-31 is 0 (not 1 complete year).
        """
        left, right = self._get_binary_operands(node)
        precision = node.get("precision", "Day").lower()

        if left is None or right is None:
            return None

        # Convert to Python datetime/date for calculation
        dt_left = self._to_python_datetime(left)
        dt_right = self._to_python_datetime(right)

        if dt_left is None or dt_right is None:
            return None

        # Calculate duration based on precision
        if precision == "year":
            return self._years_between(dt_left, dt_right)
        elif precision == "month":
            return self._months_between(dt_left, dt_right)
        elif precision == "week":
            delta = dt_right - dt_left
            return int(delta.days // 7)
        elif precision == "day":
            delta = dt_right - dt_left
            return int(delta.days)
        elif precision == "hour":
            delta = dt_right - dt_left
            return int(delta.total_seconds() // 3600)
        elif precision == "minute":
            delta = dt_right - dt_left
            return int(delta.total_seconds() // 60)
        elif precision == "second":
            delta = dt_right - dt_left
            return int(delta.total_seconds())
        elif precision == "millisecond":
            delta = dt_right - dt_left
            return int(delta.total_seconds() * 1000)

        return None

    def _to_python_datetime(self, value: Any) -> datetime | None:
        """Convert a FHIR date/datetime to Python datetime."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day)
        if isinstance(value, FHIRDateTime):
            return value.to_datetime()
        if isinstance(value, FHIRDate):
            py_date = value.to_date()
            if py_date:
                return datetime(py_date.year, py_date.month, py_date.day)
            # Partial date - use what we have
            return datetime(value.year, value.month or 1, value.day or 1)
        return None

    def _years_between(self, dt1: datetime, dt2: datetime) -> int:
        """Calculate whole years between two datetimes.

        CQL semantics: Returns completed years, not just year difference.
        """
        years = dt2.year - dt1.year
        # Adjust if we haven't reached the anniversary
        if (dt2.month, dt2.day, dt2.hour, dt2.minute, dt2.second) < (
            dt1.month,
            dt1.day,
            dt1.hour,
            dt1.minute,
            dt1.second,
        ):
            years -= 1
        return years

    def _months_between(self, dt1: datetime, dt2: datetime) -> int:
        """Calculate whole months between two datetimes.

        CQL semantics: Returns completed months.
        """
        months = (dt2.year - dt1.year) * 12 + (dt2.month - dt1.month)
        # Adjust if we haven't reached the day of month
        if (dt2.day, dt2.hour, dt2.minute, dt2.second) < (
            dt1.day,
            dt1.hour,
            dt1.minute,
            dt1.second,
        ):
            months -= 1
        return months

    def _eval_difference_between(self, node: dict[str, Any]) -> int | None:
        """Evaluate difference between dates."""
        return self._eval_duration_between(node)

    def _eval_date_from(self, node: dict[str, Any]) -> FHIRDate | None:
        """Extract date from datetime."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, FHIRDateTime):
            return FHIRDate(year=operand.year, month=operand.month, day=operand.day)
        if isinstance(operand, FHIRDate):
            return operand
        return None

    def _eval_time_from(self, node: dict[str, Any]) -> str | None:
        """Extract time from datetime."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, FHIRDateTime):
            parts = []
            if operand.hour is not None:
                parts.append(f"{operand.hour:02d}")
                if operand.minute is not None:
                    parts.append(f"{operand.minute:02d}")
                    if operand.second is not None:
                        parts.append(f"{operand.second:02d}")
            return ":".join(parts) if parts else None
        return None

    def _eval_timezone_offset_from(self, node: dict[str, Any]) -> float | None:
        """Extract timezone offset."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if hasattr(operand, "timezone_offset"):
            timezone_offset: float | None = operand.timezone_offset
            return timezone_offset
        return None

    def _eval_datetime_component_from(self, node: dict[str, Any]) -> int | None:
        """Extract datetime component."""
        operand = self._get_unary_operand(node)
        precision = node.get("precision", "")

        if operand is None:
            return None

        precision_lower = precision.lower()
        if precision_lower == "year":
            return getattr(operand, "year", None)
        elif precision_lower == "month":
            return getattr(operand, "month", None)
        elif precision_lower == "day":
            return getattr(operand, "day", None)
        elif precision_lower == "hour":
            return getattr(operand, "hour", None)
        elif precision_lower == "minute":
            return getattr(operand, "minute", None)
        elif precision_lower == "second":
            return getattr(operand, "second", None)

        return None

    def _eval_same_as(self, node: dict[str, Any]) -> bool | None:
        """Evaluate same as (datetime comparison)."""
        return self._eval_equal(node)

    def _eval_same_or_before(self, node: dict[str, Any]) -> bool | None:
        """Evaluate same or before."""
        return self._eval_less_or_equal(node)

    def _eval_same_or_after(self, node: dict[str, Any]) -> bool | None:
        """Evaluate same or after."""
        return self._eval_greater_or_equal(node)

    # =========================================================================
    # Interval Operation Handlers
    # =========================================================================

    def _eval_start(self, node: dict[str, Any]) -> Any:
        """Get start of interval."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, CQLInterval):
            return operand.low
        return None

    def _eval_end(self, node: dict[str, Any]) -> Any:
        """Get end of interval."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, CQLInterval):
            return operand.high
        return None

    def _eval_width(self, node: dict[str, Any]) -> Any:
        """Get width of interval."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, CQLInterval):
            if operand.low is None or operand.high is None:
                return None
            return operand.high - operand.low
        return None

    def _eval_size(self, node: dict[str, Any]) -> Any:
        """Get size of interval."""
        return self._eval_width(node)

    def _eval_point_from(self, node: dict[str, Any]) -> Any:
        """Get point from unit interval."""
        operand = self._get_unary_operand(node)
        if operand is None:
            return None
        if isinstance(operand, CQLInterval) and operand.low == operand.high:
            return operand.low
        return None

    def _eval_overlaps(self, node: dict[str, Any]) -> bool | None:
        """Check if intervals overlap."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left.overlaps(right)
        return None

    def _eval_overlaps_before(self, node: dict[str, Any]) -> bool | None:
        """Check if interval overlaps before another."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left.overlaps_before(right)
        return None

    def _eval_overlaps_after(self, node: dict[str, Any]) -> bool | None:
        """Check if interval overlaps after another."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left.overlaps_after(right)
        return None

    def _eval_meets(self, node: dict[str, Any]) -> bool | None:
        """Check if intervals meet."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left.meets(right)
        return None

    def _eval_meets_before(self, node: dict[str, Any]) -> bool | None:
        """Check if interval meets before another."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left.meets_before(right)
        return None

    def _eval_meets_after(self, node: dict[str, Any]) -> bool | None:
        """Check if interval meets after another."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left.meets_after(right)
        return None

    def _eval_before(self, node: dict[str, Any]) -> bool | None:
        """Check if before.

        CQL 'before' semantics:
        - Point before Point: A < B
        - Point before Interval: A < start of B
        - Interval before Point: end of A < B
        - Interval before Interval: end of A < start of B
        """
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None

        left_is_interval = isinstance(left, CQLInterval)
        right_is_interval = isinstance(right, CQLInterval)

        if left_is_interval and right_is_interval:
            # Interval before Interval: end of A < start of B
            if left.high is None or right.low is None:
                return None
            is_before: bool = left.high < right.low
            return is_before
        elif left_is_interval:
            # Interval before Point: end of A < B
            if left.high is None:
                return None
            is_before = left.high < right
            return is_before
        elif right_is_interval:
            # Point before Interval: A < start of B
            if right.low is None:
                return None
            is_before = left < right.low
            return is_before
        else:
            # Point before Point
            is_before = left < right
            return is_before

    def _eval_after(self, node: dict[str, Any]) -> bool | None:
        """Check if after.

        CQL 'after' semantics:
        - Point after Point: A > B
        - Point after Interval: A > end of B
        - Interval after Point: start of A > B
        - Interval after Interval: start of A > end of B
        """
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None

        left_is_interval = isinstance(left, CQLInterval)
        right_is_interval = isinstance(right, CQLInterval)

        if left_is_interval and right_is_interval:
            # Interval after Interval: start of A > end of B
            if left.low is None or right.high is None:
                return None
            is_after: bool = left.low > right.high
            return is_after
        elif left_is_interval:
            # Interval after Point: start of A > B
            if left.low is None:
                return None
            is_after = left.low > right
            return is_after
        elif right_is_interval:
            # Point after Interval: A > end of B
            if right.high is None:
                return None
            is_after = left > right.high
            return is_after
        else:
            # Point after Point
            is_after = left > right
            return is_after

    def _eval_starts(self, node: dict[str, Any]) -> bool | None:
        """Check if interval starts another."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left.starts(right)
        return None

    def _eval_ends(self, node: dict[str, Any]) -> bool | None:
        """Check if interval ends another."""
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left.ends(right)
        return None

    def _eval_collapse(self, node: dict[str, Any]) -> list[Any]:
        """Collapse overlapping/adjacent intervals into non-overlapping intervals.

        Takes a list of intervals and returns a list of non-overlapping intervals
        that cover the same range. Adjacent intervals (that meet) are merged.
        """
        operand = self.evaluate(node.get("operand"))
        if operand is None:
            return []

        # Ensure we have a list of intervals
        intervals: list[CQLInterval] = []
        if isinstance(operand, list):
            for item in operand:
                if isinstance(item, CQLInterval):
                    intervals.append(item)
        elif isinstance(operand, CQLInterval):
            intervals = [operand]
        else:
            return []

        if not intervals:
            return []

        # Sort intervals by low bound (None/unbounded first)
        def sort_key(iv: CQLInterval) -> tuple[bool, Any]:
            if iv.low is None:
                return (False, None)  # Unbounded comes first
            return (True, iv.low)

        sorted_intervals = sorted(intervals, key=sort_key)

        # Merge overlapping/adjacent intervals
        result: list[CQLInterval] = []
        current = sorted_intervals[0]

        for next_iv in sorted_intervals[1:]:
            # Try to merge current with next
            merged = current.union(next_iv)
            if merged is not None:
                current = merged
            else:
                result.append(current)
                current = next_iv

        result.append(current)
        return result

    def _eval_expand(self, node: dict[str, Any]) -> list[Any]:
        """Expand interval into a list of points based on per unit.

        Takes an interval and a per quantity, returning a list of intervals
        of the specified width covering the original interval.
        """
        operand = self.evaluate(node.get("operand"))
        per = self.evaluate(node.get("per"))

        if operand is None:
            return []

        # Handle list of intervals
        if isinstance(operand, list):
            result: list[Any] = []
            for item in operand:
                if isinstance(item, CQLInterval):
                    expanded = self._expand_single_interval(item, per)
                    result.extend(expanded)
            return result
        elif isinstance(operand, CQLInterval):
            return self._expand_single_interval(operand, per)

        return []

    def _expand_single_interval(self, interval: CQLInterval, per: Any) -> list[CQLInterval]:
        """Expand a single interval into unit intervals."""
        if interval.low is None or interval.high is None:
            # Cannot expand unbounded intervals
            return [interval]

        result: list[CQLInterval] = []

        # Determine step size
        step = 1  # Default step
        if per is not None:
            if isinstance(per, Quantity):
                step = int(per.value)
            elif isinstance(per, int | Decimal):
                step = int(per)

        # Handle integer intervals
        if isinstance(interval.low, int) and isinstance(interval.high, int):
            int_low = interval.low
            int_high = interval.high
            if not interval.low_closed:
                int_low += 1
            if not interval.high_closed:
                int_high -= 1

            int_current = int_low
            while int_current <= int_high:
                int_end = min(int_current + step - 1, int_high)
                result.append(CQLInterval(low=int_current, high=int_end, low_closed=True, high_closed=True))
                int_current = int_end + 1

        # Handle date intervals
        elif isinstance(interval.low, (date, FHIRDate)) and isinstance(interval.high, (date, FHIRDate)):
            low_date = interval.low.to_date() if isinstance(interval.low, FHIRDate) else interval.low
            high_date = interval.high.to_date() if isinstance(interval.high, FHIRDate) else interval.high

            if low_date is None or high_date is None:
                return [interval]

            if not interval.low_closed:
                low_date = low_date + timedelta(days=1)
            if not interval.high_closed:
                high_date = high_date - timedelta(days=1)

            current_date = low_date
            while current_date <= high_date:
                end_date = min(current_date + timedelta(days=step - 1), high_date)
                result.append(
                    CQLInterval(
                        low=FHIRDate(year=current_date.year, month=current_date.month, day=current_date.day),
                        high=FHIRDate(year=end_date.year, month=end_date.month, day=end_date.day),
                        low_closed=True,
                        high_closed=True,
                    )
                )
                current_date = end_date + timedelta(days=1)

        # Handle decimal intervals
        elif isinstance(interval.low, Decimal | float) and isinstance(interval.high, Decimal | float):
            dec_low = Decimal(str(interval.low))
            dec_high = Decimal(str(interval.high))
            step_val = Decimal(str(step))

            if not interval.low_closed:
                dec_low += Decimal("0.00000001")
            if not interval.high_closed:
                dec_high -= Decimal("0.00000001")

            dec_current = dec_low
            while dec_current <= dec_high:
                dec_end = min(dec_current + step_val - Decimal(1), dec_high)
                result.append(CQLInterval(low=dec_current, high=dec_end, low_closed=True, high_closed=True))
                dec_current = dec_end + Decimal(1)

        else:
            # Unknown interval type, return as-is
            return [interval]

        return result if result else [interval]

    # =========================================================================
    # Clinical Handlers
    # =========================================================================

    def _eval_code_ref(self, node: dict[str, Any]) -> CQLCode | None:
        """Evaluate code reference."""
        name = node.get("name")
        if not name or not self._library:
            return None

        code_def = self._library.get_code(name)
        if not code_def:
            return None

        # Get code system
        system = ""
        if code_def.codeSystem:
            cs = self._library.get_codesystem(code_def.codeSystem.name)
            if cs:
                system = cs.id

        return CQLCode(code=code_def.id, system=system, display=code_def.display)

    def _eval_codesystem_ref(self, node: dict[str, Any]) -> str | None:
        """Evaluate code system reference."""
        name = node.get("name")
        if not name or not self._library:
            return None

        cs = self._library.get_codesystem(name)
        return cs.id if cs else None

    def _eval_valueset_ref(self, node: dict[str, Any]) -> str | None:
        """Evaluate value set reference."""
        name = node.get("name")
        if not name or not self._library:
            return None

        vs = self._library.get_valueset(name)
        return vs.id if vs else None

    def _eval_concept_ref(self, node: dict[str, Any]) -> CQLConcept | None:
        """Evaluate concept reference."""
        name = node.get("name")
        if not name or not self._library:
            return None

        concept_def = self._library.get_concept(name)
        if not concept_def:
            return None

        codes = []
        for code_ref in concept_def.code:
            code = self._eval_code_ref({"name": code_ref.name, "type": "CodeRef"})
            if code:
                codes.append(code)

        return CQLConcept(codes=tuple(codes), display=concept_def.display)

    def _eval_in_valueset(self, node: dict[str, Any]) -> bool | None:
        """Evaluate in valueset."""
        code = self.evaluate(node.get("code"))
        if code is None:
            return None

        # Get valueset URL
        valueset_ref = node.get("valuesetRef")
        valueset_url = None
        if valueset_ref:
            valueset_url = self._eval_valueset_ref(valueset_ref)
        else:
            valueset = self.evaluate(node.get("valueset"))
            if valueset:
                valueset_url = valueset

        if not valueset_url:
            return None

        # Check data source; membership testing is an optional capability, not part of the protocol.
        data_source: Any = self.context._data_source
        if data_source and hasattr(data_source, "in_valueset"):
            in_valueset: bool | None = data_source.in_valueset(code, valueset_url)
            return in_valueset

        return None

    def _eval_in_codesystem(self, node: dict[str, Any]) -> bool | None:
        """Evaluate in code system."""
        code = self.evaluate(node.get("code"))
        if code is None:
            return None

        # Get codesystem URL
        cs_ref = node.get("codesystemRef")
        cs_url = None
        if cs_ref:
            cs_url = self._eval_codesystem_ref(cs_ref)
        else:
            cs = self.evaluate(node.get("codesystem"))
            if cs:
                cs_url = cs

        if not cs_url:
            return None

        # Check if code system matches
        if isinstance(code, CQLCode):
            return code.system == cs_url

        return None

    def _eval_calculate_age(self, node: dict[str, Any]) -> int | None:
        """Calculate age from birthdate."""
        from datetime import date

        birthdate = self._get_unary_operand(node)
        if birthdate is None:
            return None

        precision = node.get("precision", "Year")
        today = date.today()

        if isinstance(birthdate, FHIRDate):
            birth_year = birthdate.year
            birth_month = birthdate.month or 1
            birth_day = birthdate.day or 1
        elif isinstance(birthdate, str):
            parsed = FHIRDate.parse(birthdate)
            if parsed is None:
                return None
            birth_year = parsed.year
            birth_month = parsed.month or 1
            birth_day = parsed.day or 1
        else:
            return None

        if precision.lower() == "year":
            age = today.year - birth_year
            if (today.month, today.day) < (birth_month, birth_day):
                age -= 1
            return age

        return None

    def _eval_calculate_age_at(self, node: dict[str, Any]) -> int | None:
        """Calculate age at a specific date.

        Args:
            node: ELM node with operands:
                - left: birthdate (FHIRDate or string)
                - right: as-of date (FHIRDate or string)

        Returns:
            Age in the specified precision unit at the given date
        """
        left, right = self._get_binary_operands(node)
        if left is None or right is None:
            return None

        precision = node.get("precision", "Year")

        # Parse birthdate
        if isinstance(left, FHIRDate):
            birth_year = left.year
            birth_month = left.month or 1
            birth_day = left.day or 1
        elif isinstance(left, str):
            parsed = FHIRDate.parse(left)
            if parsed is None:
                return None
            birth_year = parsed.year
            birth_month = parsed.month or 1
            birth_day = parsed.day or 1
        else:
            return None

        # Parse as-of date
        if isinstance(right, FHIRDate):
            as_of_year = right.year
            as_of_month = right.month or 1
            as_of_day = right.day or 1
        elif isinstance(right, str):
            parsed = FHIRDate.parse(right)
            if parsed is None:
                return None
            as_of_year = parsed.year
            as_of_month = parsed.month or 1
            as_of_day = parsed.day or 1
        elif hasattr(right, "year"):
            # datetime.date or similar
            as_of_year = right.year
            as_of_month = right.month
            as_of_day = right.day
        else:
            return None

        if precision.lower() == "year":
            age = as_of_year - birth_year
            if (as_of_month, as_of_day) < (birth_month, birth_day):
                age -= 1
            return age
        elif precision.lower() == "month":
            age_months = (as_of_year - birth_year) * 12 + (as_of_month - birth_month)
            if as_of_day < birth_day:
                age_months -= 1
            return age_months
        elif precision.lower() == "day":
            from datetime import date

            birth_date = date(birth_year, birth_month, birth_day)
            as_of_date = date(as_of_year, as_of_month, as_of_day)
            return (as_of_date - birth_date).days

        return None

    # =========================================================================
    # Message Handler
    # =========================================================================

    def _eval_message(self, node: dict[str, Any]) -> Any:
        """Evaluate CQL Message expression.

        The Message expression logs a message and returns the source value.

        CQL Spec:
            Message(source T, condition Boolean, code String, severity String, message String) T

        Severity levels (mapped to Python logging):
            - Trace -> DEBUG
            - Message -> INFO
            - Warning -> WARNING
            - Error -> ERROR
        """
        source = self.evaluate(node.get("source"))
        condition = self.evaluate(node.get("condition"))

        if condition is None or condition is True:
            message = self.evaluate(node.get("message"))
            severity = self.evaluate(node.get("severity"))
            code = self.evaluate(node.get("code"))

            # Build log message with optional code
            log_msg = str(message) if message else ""
            if code:
                log_msg = f"[{code}] {log_msg}"

            # Map CQL severity to Python log level
            severity_str = str(severity).lower() if severity else "message"
            if severity_str == "trace":
                cql_logger.debug(log_msg)
            elif severity_str == "warning":
                cql_logger.warning(log_msg)
            elif severity_str == "error":
                cql_logger.error(log_msg)
            else:  # "message" or default
                cql_logger.info(log_msg)

        return source

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_quantity(self, value: str) -> Quantity:
        """Parse a quantity string."""
        parts = value.split()
        if len(parts) == 2:
            return Quantity(value=Decimal(parts[0]), unit=parts[1])
        return Quantity(value=Decimal(value), unit="1")

    def _get_builtin_function(self, name: str) -> Callable[..., Any] | None:
        """Get a built-in function by name."""
        # Map function names to implementations
        builtins: dict[str, Callable[..., Any]] = {
            "ToString": lambda x: str(x) if x is not None else None,
            "ToInteger": lambda x: int(x) if x is not None else None,
            "ToDecimal": lambda x: Decimal(str(x)) if x is not None else None,
        }
        return builtins.get(name)
