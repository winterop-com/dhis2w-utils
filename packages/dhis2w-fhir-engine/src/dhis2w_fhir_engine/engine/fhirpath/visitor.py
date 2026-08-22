"""FHIRPath ANTLR visitor for expression evaluation."""

# The generated ANTLR visitor carries no type information: its methods are unannotated, so a strict
# checker reads every return as `None` and every typed override in this module as incompatible with it.
# Suppress that one rule for the module; every other rule stays in force, and the parse-tree accessors
# are funnelled through the small typed helpers below rather than being silenced.
# pyright: reportIncompatibleMethodOverride=false

from decimal import Decimal
from typing import Any, cast

from antlr4 import ParserRuleContext  # type: ignore[import-untyped]
from antlr4.tree.Tree import ParseTree  # type: ignore[import-untyped]

from ...generated.fhirpath.fhirpathParser import fhirpathParser
from ...generated.fhirpath.fhirpathVisitor import fhirpathVisitor
from ..context import EvaluationContext
from ..functions import FunctionRegistry
from ..types import FHIRDate, FHIRDateTime, FHIRTime, Quantity


def _is_primitive(value: Any) -> bool:
    """Check if a value is a FHIR primitive type (not a complex type/dict)."""
    from decimal import Decimal as PyDecimal

    return isinstance(value, (bool, int, float, str, PyDecimal)) and not isinstance(value, dict)


def _node_text(node: Any) -> str:
    """Read the source text of a parse-tree node produced by the generated parser.

    Args:
        node: Parse-tree node or terminal token. The generated accessors that produce it are
            unannotated, so the parameter is dynamic and the text is bound to a typed local here.

    Returns:
        The source text the node spans.
    """
    text: str = node.getText()
    return text


def _get_identifier_text(identifier_ctx: Any) -> str:
    """Extract identifier text, stripping backticks from delimited identifiers.

    FHIRPath allows escaped identifiers using backticks: `given`, `class`, etc.
    This handles both regular identifiers and delimited ones.

    Args:
        identifier_ctx: Identifier subtree from the generated parser.

    Returns:
        The identifier name without its backtick delimiters.
    """
    text = _node_text(identifier_ctx)
    # Delimited identifiers are wrapped in backticks
    if text.startswith("`") and text.endswith("`"):
        return text[1:-1]
    return text


def _underlying_value(value: Any) -> Any:
    """Unwrap a FHIR primitive that carries extensions so comparisons act on the plain value."""
    if isinstance(value, _PrimitiveWithExtension):
        return value.value
    return value


def singleton_boolean(collection: list[Any] | None) -> bool | None:
    """Read a collection as a boolean under the FHIRPath singleton evaluation of collections rule.

    A single Boolean item evaluates to its own value, so `active` reads as false when the resource says
    `"active": false` - a FHIR primitive carrying its `_element` extensions counts as the boolean it wraps,
    not as "an item is present". A single item of any other type evaluates to true, and an empty collection
    evaluates to empty, which the callers spell as `None`.
    """
    if not collection:
        return None
    if len(collection) == 1:
        value = _underlying_value(collection[0])
        if isinstance(value, bool):
            return value
        return True
    return True


class _PrimitiveWithExtension:
    """Wrapper for FHIR primitive values from resources.

    In FHIR JSON, primitive values with extensions are represented as:
        {"birthDate": "1974-12-25", "_birthDate": {"extension": [...]}}

    This wrapper keeps the primitive value and extension data together
    so that the extension() function can access the extensions.
    It also tracks the element name to support type checking.
    """

    __slots__ = ("value", "extension_data", "element_name", "resource_type")

    def __init__(
        self,
        value: Any,
        extension_data: dict[str, Any] | None = None,
        element_name: str | None = None,
        resource_type: str | None = None,
    ):
        self.value = value
        self.extension_data = extension_data or {}
        self.element_name = element_name
        self.resource_type = resource_type

    def __eq__(self, other: Any) -> bool:
        """For comparison, use the underlying value."""
        equal: bool = self.value == _underlying_value(other)
        return equal

    def __hash__(self) -> int:
        """For hashing, use the underlying value."""
        return hash(self.value)

    def __repr__(self) -> str:
        return f"_PrimitiveWithExtension({self.value!r})"

    def __str__(self) -> str:
        return str(self.value)

    def __lt__(self, other: Any) -> bool:
        less_than: bool = self.value < _underlying_value(other)
        return less_than

    def __le__(self, other: Any) -> bool:
        less_or_equal: bool = self.value <= _underlying_value(other)
        return less_or_equal

    def __gt__(self, other: Any) -> bool:
        greater_than: bool = self.value > _underlying_value(other)
        return greater_than

    def __ge__(self, other: Any) -> bool:
        greater_or_equal: bool = self.value >= _underlying_value(other)
        return greater_or_equal


def unwrap_primitives(value: Any) -> Any:
    """Return a FHIRPath result with FHIR primitives replaced by their plain Python values.

    Evaluation carries a FHIR primitive together with the extensions declared on its `_element` sibling, so
    that `extension()` can reach them. Anything that displays or serialises a result wants the plain value.

    Args:
        value: A FHIRPath result: a single value, a list, or a dict of them

    Returns:
        The same shape with every wrapped primitive replaced by the value it wraps
    """
    if isinstance(value, _PrimitiveWithExtension):
        return value.value
    if isinstance(value, list):
        return [unwrap_primitives(item) for item in value]
    if isinstance(value, dict):
        return {key: unwrap_primitives(item) for key, item in value.items()}
    return value


class FHIRPathEvaluatorVisitor(fhirpathVisitor):
    """Visitor that evaluates FHIRPath expressions.

    All expressions return a list (collection) as per FHIRPath semantics.
    """

    def __init__(self, ctx: EvaluationContext, input_collection: list[Any]):
        """Initialize the visitor.

        Args:
            ctx: Evaluation context with resource and environment
            input_collection: Initial collection to evaluate against
        """
        self.ctx = ctx
        self.input_collection = input_collection
        # Initialize $this with the input collection (first element if singleton)
        if input_collection:
            initial_this = input_collection[0] if len(input_collection) == 1 else input_collection
            self.ctx.push_this(initial_this)

    def evaluate(self, tree: ParserRuleContext) -> list[Any]:
        """Evaluate the parse tree and return the result collection."""
        result = self._visit_child(tree)
        if result is None:
            return []
        if not isinstance(result, list):
            return [result]
        return result

    # ===== Expression visitors =====

    def visitTermExpression(self, ctx: fhirpathParser.TermExpressionContext) -> list[Any]:
        """Visit terminal expression (literal, invocation, etc.)."""
        result: list[Any] = self._visit_child(ctx.term())
        return result

    def visitInvocationExpression(self, ctx: fhirpathParser.InvocationExpressionContext) -> list[Any]:
        """Visit invocation expression (expr.member or expr.function())."""
        # Evaluate the left expression first
        left = self._visit_child(ctx.expression())
        if left is None:
            left = []

        # Now evaluate the invocation on the result
        return self._evaluate_invocation(left, ctx.invocation())

    def visitIndexerExpression(self, ctx: fhirpathParser.IndexerExpressionContext) -> list[Any]:
        """Visit indexer expression (expr[index])."""
        collection = self._visit_child(ctx.expression(0))
        if not collection:
            return []

        index_result = self._visit_child(ctx.expression(1))
        if not index_result:
            return []

        index = int(index_result[0])
        if 0 <= index < len(collection):
            return [collection[index]]
        return []

    def visitPolarityExpression(self, ctx: fhirpathParser.PolarityExpressionContext) -> list[Any]:
        """Visit polarity expression (+expr or -expr)."""
        result: list[Any] = self._visit_child(ctx.expression())
        if not result:
            return []

        value = result[0]
        # Exclude bool since it's a subclass of int in Python but shouldn't be negated
        if (
            _node_text(ctx.getChild(0)) == "-"
            and isinstance(value, (int, float, Decimal))
            and not isinstance(value, bool)
        ):
            return [-value]
        return result

    def visitMultiplicativeExpression(self, ctx: fhirpathParser.MultiplicativeExpressionContext) -> list[Any]:
        """Visit multiplicative expression (*, /, div, mod)."""
        left = self._visit_child(ctx.expression(0))
        right = self._visit_child(ctx.expression(1))

        if not left or not right:
            return []

        left_val = left[0]
        right_val = right[0]
        op = _node_text(ctx.getChild(1))

        # Handle Quantity arithmetic
        left_is_qty = isinstance(left_val, Quantity)
        right_is_qty = isinstance(right_val, Quantity)

        if left_is_qty or right_is_qty:
            return self._quantity_arithmetic(left_val, right_val, op, left_is_qty, right_is_qty)

        if not isinstance(left_val, (int, float, Decimal)) or not isinstance(right_val, (int, float, Decimal)):
            return []

        # Convert to Decimal for consistent arithmetic
        left_dec = Decimal(str(left_val))
        right_dec = Decimal(str(right_val))

        try:
            if op == "*":
                return [left_dec * right_dec]
            elif op == "/":
                if right_dec == 0:
                    return []
                return [left_dec / right_dec]
            elif op == "div":
                if right_dec == 0:
                    return []
                return [int(left_dec // right_dec)]
            elif op == "mod":
                if right_dec == 0:
                    return []
                return [left_dec % right_dec]
        except (ZeroDivisionError, ArithmeticError):
            return []

        return []

    def _quantity_arithmetic(
        self, left_val: Any, right_val: Any, op: str, left_is_qty: bool, right_is_qty: bool
    ) -> list[Any]:
        """Handle quantity arithmetic operations."""
        try:
            if op == "*":
                if left_is_qty and right_is_qty:
                    # Quantity * Quantity: combine units
                    left_qty: Quantity = left_val
                    right_qty: Quantity = right_val
                    # Try to convert right to left's unit for same-dimension quantities
                    from dhis2w_fhir_engine.engine.units import convert_quantity

                    converted = convert_quantity(right_qty.value, right_qty.unit, left_qty.unit)
                    if converted is not None:
                        # Same dimension - multiply values and square the unit
                        new_value = left_qty.value * Decimal(str(converted))
                        new_unit = left_qty.unit + "2"
                        return [Quantity(value=new_value, unit=new_unit)]
                    else:
                        # Different dimensions - combine units
                        new_value = left_qty.value * right_qty.value
                        new_unit = f"{left_qty.unit}.{right_qty.unit}"
                        return [Quantity(value=new_value, unit=new_unit)]
                elif left_is_qty:
                    # Quantity * number
                    qty: Quantity = left_val
                    num = Decimal(str(right_val))
                    return [Quantity(value=qty.value * num, unit=qty.unit)]
                else:
                    # number * Quantity
                    num = Decimal(str(left_val))
                    qty = right_val
                    return [Quantity(value=num * qty.value, unit=qty.unit)]

            elif op == "/":
                if left_is_qty and right_is_qty:
                    # Quantity / Quantity
                    left_qty = left_val
                    right_qty = right_val
                    if right_qty.value == 0:
                        return []
                    if left_qty.unit == right_qty.unit:
                        # Same unit - result is unitless
                        return [Quantity(value=left_qty.value / right_qty.value, unit="1")]
                    else:
                        # Different units - combine as division
                        new_value = left_qty.value / right_qty.value
                        new_unit = f"{left_qty.unit}/{right_qty.unit}"
                        return [Quantity(value=new_value, unit=new_unit)]
                elif left_is_qty:
                    # Quantity / number
                    qty = left_val
                    num = Decimal(str(right_val))
                    if num == 0:
                        return []
                    return [Quantity(value=qty.value / num, unit=qty.unit)]
                else:
                    # number / Quantity - not typically supported
                    return []

            # div and mod not supported for quantities
            return []
        except (ZeroDivisionError, ArithmeticError):
            return []

    def visitAdditiveExpression(self, ctx: fhirpathParser.AdditiveExpressionContext) -> list[Any]:
        """Visit additive expression (+, -, &)."""
        left = self._visit_child(ctx.expression(0))
        right = self._visit_child(ctx.expression(1))

        op = _node_text(ctx.getChild(1))

        # String concatenation with &
        if op == "&":
            left_str = str(left[0]) if left else ""
            right_str = str(right[0]) if right else ""
            return [left_str + right_str]

        if not left or not right:
            return []

        left_val = left[0]
        right_val = right[0]

        # Handle Quantity arithmetic
        if isinstance(left_val, Quantity) and isinstance(right_val, Quantity):
            if left_val.unit == right_val.unit:
                if op == "+":
                    return [Quantity(value=left_val.value + right_val.value, unit=left_val.unit)]
                elif op == "-":
                    return [Quantity(value=left_val.value - right_val.value, unit=left_val.unit)]
            return []

        # Handle date/datetime arithmetic with Quantity
        if isinstance(left_val, (FHIRDate, FHIRDateTime)) and isinstance(right_val, Quantity):
            result = self._date_add(left_val, right_val, op)
            return [result] if result else []

        # Handle string concatenation with +
        if isinstance(left_val, str) and isinstance(right_val, str):
            if op == "+":
                return [left_val + right_val]
            return []

        if not isinstance(left_val, (int, float, Decimal)) or not isinstance(right_val, (int, float, Decimal)):
            return []

        # Convert to Decimal for consistent arithmetic
        left_dec = Decimal(str(left_val))
        right_dec = Decimal(str(right_val))

        if op == "+":
            return [left_dec + right_dec]
        elif op == "-":
            return [left_dec - right_dec]

        return []

    def _date_add(
        self, date_val: FHIRDate | FHIRDateTime, quantity: Quantity, op: str
    ) -> FHIRDate | FHIRDateTime | None:
        """Add or subtract a duration from a date/datetime."""
        unit = quantity.unit.lower()
        amount = int(quantity.value)
        if op == "-":
            amount = -amount

        # Map common duration units (both UCUM codes and calendar duration names)
        unit_map = {
            # Calendar duration names (singular and plural)
            "year": "year",
            "years": "year",
            "month": "month",
            "months": "month",
            "day": "day",
            "days": "day",
            "week": "week",
            "weeks": "week",
            "hour": "hour",
            "hours": "hour",
            "minute": "minute",
            "minutes": "minute",
            "second": "second",
            "seconds": "second",
            "millisecond": "millisecond",
            "milliseconds": "millisecond",
            # UCUM codes
            "a": "year",
            "mo": "month",
            "d": "day",
            "wk": "week",
            "h": "hour",
            "min": "minute",
            "s": "second",
            "ms": "millisecond",
        }

        normalized_unit = unit_map.get(unit)
        if not normalized_unit:
            return None

        if isinstance(date_val, FHIRDate):
            return self._add_to_date(date_val, amount, normalized_unit)
        else:
            return self._add_to_datetime(date_val, amount, normalized_unit)

    def _add_to_date(self, date_val: FHIRDate, amount: int, unit: str) -> FHIRDate | None:
        """Add a duration to a FHIRDate."""
        year = date_val.year
        month = date_val.month
        day = date_val.day

        if unit == "year":
            year += amount
        elif unit == "month":
            if month is not None:
                month += amount
                while month > 12:
                    month -= 12
                    year += 1
                while month < 1:
                    month += 12
                    year -= 1
            else:
                return None
        elif unit == "week":
            if day is not None and month is not None:
                from datetime import date as py_date
                from datetime import timedelta

                d = py_date(year, month, day)
                d += timedelta(weeks=amount)
                return FHIRDate(year=d.year, month=d.month, day=d.day)
            return None
        elif unit == "day":
            if day is not None and month is not None:
                from datetime import date as py_date
                from datetime import timedelta

                d = py_date(year, month, day)
                d += timedelta(days=amount)
                return FHIRDate(year=d.year, month=d.month, day=d.day)
            return None
        else:
            return None  # Time units not applicable to Date

        return FHIRDate(year=year, month=month, day=day)

    def _add_to_datetime(self, dt_val: FHIRDateTime, amount: int, unit: str) -> FHIRDateTime | None:
        """Add a duration to a FHIRDateTime."""
        from datetime import timedelta

        year = dt_val.year
        month = dt_val.month
        day = dt_val.day
        hour = dt_val.hour
        minute = dt_val.minute
        second = dt_val.second
        millisecond = dt_val.millisecond

        if unit == "year":
            year += amount
        elif unit == "month":
            if month is not None:
                month += amount
                while month > 12:
                    month -= 12
                    year += 1
                while month < 1:
                    month += 12
                    year -= 1
            else:
                return None
        elif unit in ("week", "day", "hour", "minute", "second", "millisecond"):
            if month is None or day is None:
                return None
            py_dt = dt_val.to_datetime()
            if py_dt is None:
                return None

            if unit == "week":
                py_dt += timedelta(weeks=amount)
            elif unit == "day":
                py_dt += timedelta(days=amount)
            elif unit == "hour":
                py_dt += timedelta(hours=amount)
            elif unit == "minute":
                py_dt += timedelta(minutes=amount)
            elif unit == "second":
                py_dt += timedelta(seconds=amount)
            elif unit == "millisecond":
                py_dt += timedelta(milliseconds=amount)

            return FHIRDateTime(
                year=py_dt.year,
                month=py_dt.month,
                day=py_dt.day,
                hour=py_dt.hour if dt_val.hour is not None else None,
                minute=py_dt.minute if dt_val.minute is not None else None,
                second=py_dt.second if dt_val.second is not None else None,
                millisecond=py_dt.microsecond // 1000 if dt_val.millisecond is not None else None,
                tz_offset=dt_val.tz_offset,
            )
        else:
            return None

        return FHIRDateTime(
            year=year,
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            second=second,
            millisecond=millisecond,
            tz_offset=dt_val.tz_offset,
        )

    def visitUnionExpression(self, ctx: fhirpathParser.UnionExpressionContext) -> list[Any]:
        """Visit union expression (expr | expr)."""
        left = self._visit_child(ctx.expression(0)) or []
        right = self._visit_child(ctx.expression(1)) or []

        # Union combines and removes duplicates
        result = list(left)
        for item in right:
            if item not in result:
                result.append(item)
        return result

    def visitInequalityExpression(self, ctx: fhirpathParser.InequalityExpressionContext) -> list[Any]:
        """Visit inequality expression (<, >, <=, >=)."""
        left = self._visit_child(ctx.expression(0))
        right = self._visit_child(ctx.expression(1))

        if not left or not right:
            return []

        op = _node_text(ctx.getChild(1))
        comparison: list[Any] = FunctionRegistry.call(op, self.ctx, left, right)
        return comparison

    def visitEqualityExpression(self, ctx: fhirpathParser.EqualityExpressionContext) -> list[Any]:
        """Visit equality expression (=, !=, ~, !~)."""
        left = self._visit_child(ctx.expression(0))
        right = self._visit_child(ctx.expression(1))

        op = _node_text(ctx.getChild(1))
        equality: list[Any] = FunctionRegistry.call(op, self.ctx, left or [], right or [])
        return equality

    def visitMembershipExpression(self, ctx: fhirpathParser.MembershipExpressionContext) -> list[Any]:
        """Visit membership expression (in, contains)."""
        left = self._visit_child(ctx.expression(0)) or []
        right = self._visit_child(ctx.expression(1)) or []

        op = _node_text(ctx.getChild(1))

        if op == "in":
            # left in right: true if all elements of left are in right
            if not left:
                return [True]
            for item in left:
                if item not in right:
                    return [False]
            return [True]
        elif op == "contains":
            # left contains right: true if all elements of right are in left
            if not right:
                return [True]
            for item in right:
                if item not in left:
                    return [False]
            return [True]

        return []

    def visitAndExpression(self, ctx: fhirpathParser.AndExpressionContext) -> list[Any]:
        """Visit and expression."""
        left = self._visit_child(ctx.expression(0))
        right = self._visit_child(ctx.expression(1))

        left_bool = self._to_boolean(left)
        right_bool = self._to_boolean(right)

        # FHIRPath three-valued logic
        if left_bool is False or right_bool is False:
            return [False]
        if left_bool is None or right_bool is None:
            return []
        return [True]

    def visitOrExpression(self, ctx: fhirpathParser.OrExpressionContext) -> list[Any]:
        """Visit or/xor expression."""
        left = self._visit_child(ctx.expression(0))
        right = self._visit_child(ctx.expression(1))

        op = _node_text(ctx.getChild(1))

        left_bool = self._to_boolean(left)
        right_bool = self._to_boolean(right)

        if op == "or":
            if left_bool is True or right_bool is True:
                return [True]
            if left_bool is None or right_bool is None:
                return []
            return [False]
        elif op == "xor":
            if left_bool is None or right_bool is None:
                return []
            return [left_bool != right_bool]

        return []

    def visitImpliesExpression(self, ctx: fhirpathParser.ImpliesExpressionContext) -> list[Any]:
        """Visit implies expression."""
        left = self._visit_child(ctx.expression(0))
        right = self._visit_child(ctx.expression(1))

        left_bool = self._to_boolean(left)
        right_bool = self._to_boolean(right)

        # p implies q = not p or q
        # Truth table: F->? = T, ?->T = T, T->F = F, else empty
        if left_bool is False:
            return [True]
        if right_bool is True:
            return [True]
        # At this point: left is True or None, right is False or None
        if left_bool is None or right_bool is None:
            return []
        # left is True and right is False
        return [False]

    def visitTypeExpression(self, ctx: fhirpathParser.TypeExpressionContext) -> list[Any]:
        """Visit type expression (is, as)."""
        left: list[Any] = self._visit_child(ctx.expression())
        type_spec = _node_text(ctx.typeSpecifier())
        # Strip backticks from delimited identifiers (e.g., FHIR.`Patient` -> FHIR.Patient)
        type_spec = type_spec.replace("`", "")

        op = _node_text(ctx.getChild(1))

        if op == "is":
            if not left:
                return []  # Empty collection returns empty per FHIRPath spec
            return [self._is_type(left[0], type_spec)]
        elif op == "as":
            if not left:
                return []
            if self._is_type(left[0], type_spec):
                return left
            return []

        return []

    # ===== Term visitors =====

    def visitInvocationTerm(self, ctx: fhirpathParser.InvocationTermContext) -> list[Any]:
        """Visit invocation term (initial member or function)."""
        return self._evaluate_invocation(self.input_collection, ctx.invocation())

    def visitLiteralTerm(self, ctx: fhirpathParser.LiteralTermContext) -> list[Any]:
        """Visit literal term."""
        result: list[Any] = self._visit_child(ctx.literal())
        return result

    def visitExternalConstantTerm(self, ctx: fhirpathParser.ExternalConstantTermContext) -> list[Any]:
        """Visit external constant term (%name)."""
        result: list[Any] = self._visit_child(ctx.externalConstant())
        return result

    def visitParenthesizedTerm(self, ctx: fhirpathParser.ParenthesizedTermContext) -> list[Any]:
        """Visit parenthesized expression."""
        result: list[Any] = self._visit_child(ctx.expression())
        return result

    # ===== Literal visitors =====

    def visitNullLiteral(self, ctx: fhirpathParser.NullLiteralContext) -> list[Any]:
        """Visit null literal ({})."""
        return []

    def visitBooleanLiteral(self, ctx: fhirpathParser.BooleanLiteralContext) -> list[Any]:
        """Visit boolean literal."""
        return [ctx.getText() == "true"]

    def visitStringLiteral(self, ctx: fhirpathParser.StringLiteralContext) -> list[Any]:
        """Visit string literal."""
        text = ctx.getText()[1:-1]  # Remove quotes
        # Handle escape sequences
        text = self._unescape_string(text)
        return [text]

    def visitNumberLiteral(self, ctx: fhirpathParser.NumberLiteralContext) -> list[Any]:
        """Visit number literal."""
        text = ctx.getText()
        if "." in text:
            return [Decimal(text)]
        return [int(text)]

    def visitDateLiteral(self, ctx: fhirpathParser.DateLiteralContext) -> list[Any]:
        """Visit date literal (@YYYY-MM-DD)."""
        text = ctx.getText()[1:]  # Remove @
        parsed = FHIRDate.parse(text)
        return [parsed] if parsed else [text]

    def visitDateTimeLiteral(self, ctx: fhirpathParser.DateTimeLiteralContext) -> list[Any]:
        """Visit datetime literal (@YYYY-MM-DDThh:mm:ss)."""
        text = ctx.getText()[1:]  # Remove @
        parsed = FHIRDateTime.parse(text)
        return [parsed] if parsed else [text]

    def visitTimeLiteral(self, ctx: fhirpathParser.TimeLiteralContext) -> list[Any]:
        """Visit time literal (@Thh:mm:ss)."""
        text = ctx.getText()[1:]  # Remove @
        parsed = FHIRTime.parse(text)
        return [parsed] if parsed else [text]

    def visitQuantityLiteral(self, ctx: fhirpathParser.QuantityLiteralContext) -> list[Any]:
        """Visit quantity literal."""
        result: list[Any] = self._visit_child(ctx.quantity())
        return result

    def visitQuantity(self, ctx: fhirpathParser.QuantityContext) -> list[Any]:
        """Visit quantity."""
        number = _node_text(ctx.NUMBER())
        value = Decimal(number) if "." in number else int(number)

        unit = ""
        original_unit = None
        if ctx.unit():
            unit = _node_text(ctx.unit())
            if unit.startswith("'") and unit.endswith("'"):
                unit = unit[1:-1]
            else:
                # Convert calendar duration units to UCUM equivalents
                # Note: year/month are NOT converted because they have variable lengths
                # (calendar months/years differ from UCUM mo/a which are fixed averages)
                # Only exact-duration units are converted:
                calendar_to_ucum = {
                    "week": "wk",
                    "weeks": "wk",
                    "day": "d",
                    "days": "d",
                    "hour": "h",
                    "hours": "h",
                    "minute": "min",
                    "minutes": "min",
                    "second": "s",
                    "seconds": "s",
                    "millisecond": "ms",
                    "milliseconds": "ms",
                }
                if unit in calendar_to_ucum:
                    original_unit = unit  # Preserve original calendar duration name
                    unit = calendar_to_ucum[unit]

        return [Quantity(value=Decimal(str(value)), unit=unit, original_unit=original_unit)]

    def visitExternalConstant(self, ctx: fhirpathParser.ExternalConstantContext) -> list[Any]:
        """Visit external constant (%name)."""
        name = _get_identifier_text(ctx.identifier()) if ctx.identifier() else _node_text(ctx.STRING())[1:-1]

        value = self.ctx.get_constant(name)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    # ===== Invocation visitors =====

    def visitMemberInvocation(self, ctx: fhirpathParser.MemberInvocationContext) -> list[Any]:
        """Visit member invocation - handled via _evaluate_invocation."""
        # This should not be called directly
        return cast(list[Any], self.visitChildren(ctx))

    def visitFunctionInvocation(self, ctx: fhirpathParser.FunctionInvocationContext) -> list[Any]:
        """Visit function invocation - handled via _evaluate_invocation."""
        # This should not be called directly
        return cast(list[Any], self.visitChildren(ctx))

    def visitThisInvocation(self, ctx: fhirpathParser.ThisInvocationContext) -> list[Any]:
        """Visit $this invocation."""
        value = self.ctx.this
        if value is None:
            return []
        return [value] if not isinstance(value, list) else value

    def visitIndexInvocation(self, ctx: fhirpathParser.IndexInvocationContext) -> list[Any]:
        """Visit $index invocation."""
        index = self.ctx.index
        if index is None:
            return []
        return [index]

    def visitTotalInvocation(self, ctx: fhirpathParser.TotalInvocationContext) -> list[Any]:
        """Visit $total invocation."""
        total = self.ctx.total
        if total is None:
            return []
        return [total] if not isinstance(total, list) else total

    # ===== Helper methods =====

    def _visit_child(self, tree: ParseTree | None) -> Any:
        """Evaluate one child of the parse tree and return whatever collection it produced.

        Args:
            tree: Child subtree. The generated accessors declare it optional, while the grammar
                guarantees it is present at every call site here.

        Returns:
            The child's result, dynamic because the generated visitor declares no return type. A
            subtree the grammar left out yields the empty collection.
        """
        if tree is None:
            return []
        return self.visit(tree)

    def _evaluate_invocation(self, input_collection: list[Any], invocation_ctx: ParserRuleContext | None) -> list[Any]:
        """Evaluate an invocation on a collection."""
        if isinstance(invocation_ctx, fhirpathParser.MemberInvocationContext):
            return self._evaluate_member(input_collection, _get_identifier_text(invocation_ctx.identifier()))
        elif isinstance(invocation_ctx, fhirpathParser.FunctionInvocationContext):
            function_ctx = invocation_ctx.function()
            if function_ctx is None:
                return []
            return self._evaluate_function(input_collection, function_ctx)
        elif isinstance(invocation_ctx, fhirpathParser.ThisInvocationContext):
            value = self.ctx.this
            return [value] if value is not None else []
        elif isinstance(invocation_ctx, fhirpathParser.IndexInvocationContext):
            index = self.ctx.index
            return [index] if index is not None else []
        elif isinstance(invocation_ctx, fhirpathParser.TotalInvocationContext):
            total = self.ctx.total
            return [total] if total is not None else []

        return []

    def _evaluate_member(self, collection: list[Any], member_name: str) -> list[Any]:
        """Navigate to a member on each item in the collection."""
        result: list[Any] = []
        for item in collection:
            if isinstance(item, dict):
                # Check if member_name matches resourceType (type filter)
                # This handles expressions like "Patient.name" where Patient is the type
                resource_type = item.get("resourceType")
                if resource_type == member_name:
                    result.append(item)
                    continue

                # Standard property access
                value = item.get(member_name)
                if value is not None:
                    # Check for primitive extension in _memberName
                    underscore_key = f"_{member_name}"
                    extension_data = item.get(underscore_key)

                    if isinstance(value, list):
                        # Handle list of values
                        if extension_data and isinstance(extension_data, list):
                            for i, v in enumerate(value):
                                ext = extension_data[i] if i < len(extension_data) else None
                                if _is_primitive(v):
                                    # Wrap ALL FHIR primitives to mark them as FHIR values
                                    result.append(_PrimitiveWithExtension(v, ext or {}, member_name, resource_type))
                                else:
                                    result.append(v)
                        else:
                            for v in value:
                                if _is_primitive(v):
                                    result.append(_PrimitiveWithExtension(v, {}, member_name, resource_type))
                                else:
                                    result.append(v)
                    else:
                        if _is_primitive(value):
                            # Wrap ALL FHIR primitives to mark them as FHIR values
                            wrapped = _PrimitiveWithExtension(value, extension_data or {}, member_name, resource_type)
                            result.append(wrapped)
                        else:
                            result.append(value)
                else:
                    # Handle polymorphic/choice types (e.g., value -> valueQuantity, valueString, etc.)
                    # In FHIR, a choice type like value[x] can be valueQuantity, valueString, etc.
                    for key in item:
                        if key.startswith(member_name) and len(key) > len(member_name):
                            # Check if remaining part starts with uppercase (type name)
                            suffix = key[len(member_name) :]
                            if suffix[0].isupper():
                                poly_value = item[key]
                                # Mark the value with its FHIR type from the choice
                                if isinstance(poly_value, dict):
                                    poly_value["_fhir_type"] = suffix
                                    result.append(poly_value)
                                elif _is_primitive(poly_value):
                                    # Wrap primitive choice values with type info
                                    # Map suffix to lowercase FHIR type name
                                    fhir_type = suffix[0].lower() + suffix[1:]
                                    wrapped = _PrimitiveWithExtension(poly_value, {}, fhir_type, resource_type)
                                    result.append(wrapped)
                                elif isinstance(poly_value, list):
                                    result.extend(poly_value)
                                else:
                                    result.append(poly_value)
                                break  # Only one choice type can be present
        return result

    # Functions that need full collection arguments (not just first element)
    _COLLECTION_ARG_FUNCTIONS = frozenset(["union", "intersect", "exclude", "combine", "subsetOf", "supersetOf"])

    # Functions that take a type name as their first argument (not to be evaluated)
    _TYPE_ARG_FUNCTIONS = frozenset(["is", "as", "ofType"])

    def _evaluate_function(
        self, input_collection: list[Any], function_ctx: fhirpathParser.FunctionContext
    ) -> list[Any]:
        """Evaluate a function call."""
        func_name = _get_identifier_text(function_ctx.identifier())

        # Get arguments
        param_list = function_ctx.paramList()
        args: list[ParserRuleContext] = []
        if param_list:
            # Called without an index, the generated accessor returns every argument subtree.
            for expr in cast(list[ParserRuleContext], param_list.expression()):
                args.append(expr)  # Pass AST node, not evaluated result

        # Handle special functions that need AST evaluation
        if func_name in ("where", "select", "repeat", "all", "exists", "sort", "iif", "aggregate"):
            return self._evaluate_special_function(func_name, input_collection, args)

        # Handle type-checking functions where argument is a type name
        if func_name in self._TYPE_ARG_FUNCTIONS and args:
            # Extract the type name as a string instead of evaluating it
            type_name = _node_text(args[0])
            # Strip backticks from delimited identifiers
            type_name = type_name.replace("`", "")
            typed_result: list[Any] = FunctionRegistry.call(func_name, self.ctx, input_collection, type_name)
            return typed_result

        # Check if function needs full collection arguments
        needs_collection = func_name in self._COLLECTION_ARG_FUNCTIONS

        # For regular functions, evaluate arguments first
        evaluated_args: list[Any] = []
        for arg in args:
            # Create a sub-visitor with the input collection
            result = self._visit_child(arg)
            if result is None:
                result = []
            elif not isinstance(result, list):
                result = [result]

            if needs_collection:
                # Pass the full collection
                evaluated_args.append(result)
            else:
                # For most functions, we pass single values not lists
                if result:
                    evaluated_args.append(result[0])
                else:
                    evaluated_args.append(None)

        # Call the registered function
        function_result: list[Any] = FunctionRegistry.call(func_name, self.ctx, input_collection, *evaluated_args)
        return function_result

    def _evaluate_special_function(
        self, func_name: str, collection: list[Any], args: list[ParserRuleContext]
    ) -> list[Any]:
        """Evaluate functions that need special AST-based evaluation."""
        if func_name == "where":
            if not args:
                return collection
            return self._evaluate_where(collection, args[0])
        elif func_name == "select":
            if not args:
                return collection
            return self._evaluate_select(collection, args[0])
        elif func_name == "repeat":
            if not args:
                return collection
            return self._evaluate_repeat(collection, args[0])
        elif func_name == "all":
            if not args:
                return [True] if not collection else [all(bool(x) for x in collection)]
            return self._evaluate_all(collection, args[0])
        elif func_name == "exists":
            if not args:
                return [len(collection) > 0]
            return self._evaluate_exists(collection, args[0])
        elif func_name == "sort":
            if not args:
                # Sort by natural ordering
                try:
                    return sorted(collection, key=lambda x: (x is None, x))
                except TypeError:
                    return collection
            return self._evaluate_sort(collection, args)
        elif func_name == "iif":
            return self._evaluate_iif(collection, args)
        elif func_name == "aggregate":
            return self._evaluate_aggregate(collection, args)
        return []

    def _evaluate_where(self, collection: list[Any], criteria_ctx: ParserRuleContext) -> list[Any]:
        """Evaluate where() with criteria."""
        result = []
        for i, item in enumerate(collection):
            self.ctx.push_this(item)
            self.ctx.push_index(i)
            try:
                # Create visitor with item as single-element collection
                # Note: sub_visitor.__init__ also pushes $this, so we need to pop it after
                sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [item])
                try:
                    criteria_result = sub_visitor._visit_child(criteria_ctx)
                finally:
                    # Pop the $this that sub_visitor.__init__ pushed
                    self.ctx.pop_this()
                if self._to_boolean(criteria_result) is True:
                    result.append(item)
            finally:
                self.ctx.pop_this()
                self.ctx.pop_index()
        return result

    def _evaluate_select(self, collection: list[Any], projection_ctx: ParserRuleContext) -> list[Any]:
        """Evaluate select() with projection."""
        result = []
        for i, item in enumerate(collection):
            self.ctx.push_this(item)
            self.ctx.push_index(i)
            try:
                # Note: sub_visitor.__init__ also pushes $this, so we need to pop it after
                sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [item])
                try:
                    projection_result = sub_visitor._visit_child(projection_ctx)
                finally:
                    # Pop the $this that sub_visitor.__init__ pushed
                    self.ctx.pop_this()
                if projection_result:
                    result.extend(projection_result if isinstance(projection_result, list) else [projection_result])
            finally:
                self.ctx.pop_this()
                self.ctx.pop_index()
        return result

    def _evaluate_repeat(self, collection: list[Any], expr_ctx: ParserRuleContext) -> list[Any]:
        """Evaluate repeat() - recursively apply expression until no new items.

        Per FHIRPath spec: repeat() invokes the expression for each element in the
        input collection and adds all unique elements returned from the expression
        to the result. The process repeats on newly added elements until no new
        elements are added.

        Unlike select(), the input collection items are NOT included in the result,
        only items returned by the expression.
        """
        result = []
        seen: set[int] = set()
        work_list = list(collection)

        while work_list:
            item = work_list.pop(0)

            # Evaluate expression for this item
            self.ctx.push_this(item)
            try:
                # Note: sub_visitor.__init__ also pushes $this, so we need to pop it after
                sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [item])
                try:
                    new_items = sub_visitor._visit_child(expr_ctx)
                finally:
                    # Pop the $this that sub_visitor.__init__ pushed
                    self.ctx.pop_this()
                if new_items:
                    for new_item in new_items if isinstance(new_items, list) else [new_items]:
                        # Track uniqueness
                        item_id = id(new_item) if isinstance(new_item, dict) else hash(str(new_item))
                        if item_id not in seen:
                            seen.add(item_id)
                            result.append(new_item)
                            # Continue processing on new items
                            work_list.append(new_item)
            finally:
                self.ctx.pop_this()

        return result

    def _evaluate_all(self, collection: list[Any], criteria_ctx: ParserRuleContext) -> list[Any]:
        """Evaluate all() with criteria."""
        if not collection:
            return [True]

        for i, item in enumerate(collection):
            self.ctx.push_this(item)
            self.ctx.push_index(i)
            try:
                # Note: sub_visitor.__init__ also pushes $this, so we need to pop it after
                sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [item])
                try:
                    criteria_result = sub_visitor._visit_child(criteria_ctx)
                finally:
                    self.ctx.pop_this()
                if self._to_boolean(criteria_result) is not True:
                    return [False]
            finally:
                self.ctx.pop_this()
                self.ctx.pop_index()
        return [True]

    def _evaluate_exists(self, collection: list[Any], criteria_ctx: ParserRuleContext) -> list[Any]:
        """Evaluate exists() with criteria."""
        for i, item in enumerate(collection):
            self.ctx.push_this(item)
            self.ctx.push_index(i)
            try:
                # Note: sub_visitor.__init__ also pushes $this, so we need to pop it after
                sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [item])
                try:
                    criteria_result = sub_visitor._visit_child(criteria_ctx)
                finally:
                    self.ctx.pop_this()
                if self._to_boolean(criteria_result) is True:
                    return [True]
            finally:
                self.ctx.pop_this()
                self.ctx.pop_index()
        return [False]

    def _evaluate_sort(self, collection: list[Any], criteria_args: list[ParserRuleContext]) -> list[Any]:
        """Evaluate sort() with criteria expressions.

        Per FHIRPath spec:
        - Empty values sort first (at the start) for both ascending and descending
        - Non-empty values sort in ascending or descending order based on the criteria
        """
        if not collection:
            return []

        # Build list of (item, sort_keys) tuples
        items_with_keys: list[tuple[Any, list[tuple[Any, bool]]]] = []

        for i, item in enumerate(collection):
            self.ctx.push_this(item)
            self.ctx.push_index(i)
            try:
                keys: list[tuple[Any, bool]] = []
                for criteria_ctx in criteria_args:
                    # Check if this is a negated expression (descending sort)
                    descending = False
                    expr_to_eval = criteria_ctx

                    # Check if it's a polarity expression
                    text = _node_text(criteria_ctx)
                    if text.startswith("-"):
                        descending = True
                        # Visit the inner expression (skip the unary minus)
                        if hasattr(criteria_ctx, "expression"):
                            children = list(criteria_ctx.getChildren())
                            if len(children) > 1:
                                expr_to_eval = children[1]

                    # Note: sub_visitor.__init__ also pushes $this, so we need to pop it after
                    sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [item])
                    try:
                        key_result = sub_visitor._visit_child(expr_to_eval)
                    finally:
                        self.ctx.pop_this()

                    # Get the single value for the key
                    key_value = key_result[0] if key_result else None
                    keys.append((key_value, descending))

                items_with_keys.append((item, keys))
            finally:
                self.ctx.pop_this()
                self.ctx.pop_index()

        # Sort using functools.cmp_to_key for proper multi-key descending support
        import functools

        def compare_items(a: tuple[Any, list[tuple[Any, bool]]], b: tuple[Any, list[tuple[Any, bool]]]) -> int:
            """Compare two items by their sort keys."""
            _, keys_a = a
            _, keys_b = b

            # Both items carry one key per sort criterion, so the two key lists are the same length.
            for (val_a, desc), (val_b, _) in zip(keys_a, keys_b, strict=True):
                # Handle None/empty values - they sort first for both directions
                a_is_none = val_a is None
                b_is_none = val_b is None

                if a_is_none and b_is_none:
                    continue  # Both empty, move to next key
                if a_is_none:
                    return -1  # a (empty) comes first
                if b_is_none:
                    return 1  # b (empty) comes first, so a comes after

                # Both have values, compare them
                try:
                    if val_a < val_b:
                        cmp = -1
                    elif val_a > val_b:
                        cmp = 1
                    else:
                        cmp = 0
                except TypeError:
                    # Can't compare, treat as equal
                    cmp = 0

                if cmp != 0:
                    # For descending, reverse the comparison
                    return -cmp if desc else cmp

            return 0  # All keys equal

        try:
            sorted_items = sorted(items_with_keys, key=functools.cmp_to_key(compare_items))
        except TypeError:
            # Mixed types that can't be compared
            return collection

        return [item for item, _ in sorted_items]

    def _evaluate_iif(self, collection: list[Any], args: list[ParserRuleContext]) -> list[Any]:
        """Evaluate iif(criterion, true-result [, otherwise-result]).

        The criterion is evaluated with $this bound to each item in collection.
        Only the appropriate branch is evaluated (lazy evaluation).
        """
        if not args:
            return []

        criterion_ctx = args[0]
        true_ctx = args[1] if len(args) > 1 else None
        otherwise_ctx = args[2] if len(args) > 2 else None

        # For empty collection, evaluate criterion without $this
        if not collection:
            # Note: sub_visitor with empty input doesn't push $this
            sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [])
            criterion_result = sub_visitor._visit_child(criterion_ctx)
            condition = self._to_boolean(criterion_result)

            if condition is True and true_ctx:
                return sub_visitor._visit_child(true_ctx) or []
            elif otherwise_ctx:
                # Per FHIRPath spec: if criterion is empty (None) or False, return otherwise
                return sub_visitor._visit_child(otherwise_ctx) or []
            return []

        # For single item, evaluate criterion with $this bound
        if len(collection) == 1:
            item = collection[0]
            self.ctx.push_this(item)
            try:
                # Note: sub_visitor.__init__ also pushes $this, so we need to pop it after
                sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [item])
                try:
                    criterion_result = sub_visitor._visit_child(criterion_ctx)
                    condition = self._to_boolean(criterion_result)

                    if condition is True and true_ctx:
                        result = sub_visitor._visit_child(true_ctx)
                        return result if isinstance(result, list) else [result] if result is not None else []
                    elif otherwise_ctx:
                        # Per FHIRPath spec: if criterion is empty (None) or False, return otherwise
                        result = sub_visitor._visit_child(otherwise_ctx)
                        return result if isinstance(result, list) else [result] if result is not None else []
                    return []
                finally:
                    self.ctx.pop_this()
            finally:
                self.ctx.pop_this()

        # Multiple items in collection - this is an error per spec
        # For now, return empty
        return []

    def _evaluate_aggregate(self, collection: list[Any], args: list[ParserRuleContext]) -> list[Any]:
        """Evaluate aggregate(aggregator [, init]).

        Aggregates collection using aggregator expression with $this for current item
        and $total for accumulated value.
        """
        if not args:
            return []

        aggregator_ctx = args[0]
        init_ctx = args[1] if len(args) > 1 else None

        # Get initial value
        if init_ctx:
            init_visitor = FHIRPathEvaluatorVisitor(self.ctx, [])
            init_result = init_visitor._visit_child(init_ctx)
            total = init_result[0] if init_result else None
        else:
            total = None

        # Aggregate over collection
        for i, item in enumerate(collection):
            self.ctx.push_this(item)
            self.ctx.push_total(total)
            self.ctx.push_index(i)
            try:
                sub_visitor = FHIRPathEvaluatorVisitor(self.ctx, [item])
                try:
                    result = sub_visitor._visit_child(aggregator_ctx)
                    total = result[0] if result else None
                finally:
                    # Pop the $this that sub_visitor.__init__ pushed
                    self.ctx.pop_this()
            finally:
                self.ctx.pop_this()
                self.ctx.pop_total()
                self.ctx.pop_index()

        if total is None:
            return []
        return [total]

    def _to_boolean(self, collection: list[Any] | None) -> bool | None:
        """Read a collection as a boolean for `where()`, `iif()`, and the logical operators."""
        return singleton_boolean(collection)

    def _is_type(self, value: Any, type_name: str) -> bool:
        """Check if a value is of the specified type.

        Delegates to the filtering module's _is_type for proper FHIR type checking.
        """
        from .functions.filtering import _is_type as filtering_is_type

        return filtering_is_type(value, type_name)

    def _unescape_string(self, s: str) -> str:
        """Unescape a FHIRPath string literal."""
        result = []
        i = 0
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                next_char = s[i + 1]
                if next_char == "n":
                    result.append("\n")
                elif next_char == "r":
                    result.append("\r")
                elif next_char == "t":
                    result.append("\t")
                elif next_char == "f":
                    result.append("\f")
                elif next_char == "\\":
                    result.append("\\")
                elif next_char == "'":
                    result.append("'")
                elif next_char == "/":
                    result.append("/")
                elif next_char == "`":
                    result.append("`")
                elif next_char == "u" and i + 5 < len(s):
                    # Unicode escape
                    hex_str = s[i + 2 : i + 6]
                    try:
                        result.append(chr(int(hex_str, 16)))
                        i += 4
                    except ValueError:
                        result.append(s[i : i + 2])
                else:
                    result.append(s[i : i + 2])
                i += 2
            else:
                result.append(s[i])
                i += 1
        return "".join(result)
