"""The d2path expression evaluator: walks the AST with collection semantics.

Every expression evaluates to a Python list (a "collection"); a scalar is a length-1 list and the
empty collection models "no value". The evaluator is source-agnostic — nodes may be pydantic
models (DHIS2 wire models) or plain dicts (FHIR JSON), navigated uniformly via `values.member`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from dhis2w_ql.ast import (
    ArrayExpr,
    BinaryExpr,
    CallExpr,
    DefineFunction,
    Expr,
    IndexExpr,
    LiteralExpr,
    MemberExpr,
    NameExpr,
    ObjectExpr,
    UnaryExpr,
    VariableExpr,
)
from dhis2w_ql.d2path import functions as fn
from dhis2w_ql.d2path.values import (
    collapse,
    compare,
    flatten_member,
    like,
    loose_equal,
    to_number,
    truthy,
)
from dhis2w_ql.errors import EvaluationError, SemanticError

# Each user-function call costs several interpreter frames (the call plus its body's expression
# walk), so a chain of distinct functions calling each other must be bounded well below the
# interpreter's recursion limit. 32 levels of composition is far beyond any real library.
MAX_FUNCTION_CALL_DEPTH = 32


@runtime_checkable
class Resolver(Protocol):
    """Resolves library-level names referenced from inside expressions."""

    def resolve_variable(self, name: str) -> list[Any] | None:
        """Return a named scalar `define`'s value as a collection, or None when unknown."""
        ...

    def resolve_function(self, name: str) -> DefineFunction | None:
        """Return a user `define function` by name, or None when unknown."""
        ...


class EvalContext(BaseModel):
    """Lexical scope for one evaluation: `$this`, `$index`, and any bound function parameters."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    variables: dict[str, list[Any]] = {}

    def child(self, **updates: list[Any]) -> EvalContext:
        """Return a new context with the given variables overlaid on this one."""
        return EvalContext(variables={**self.variables, **updates})


class Evaluator:
    """Evaluates d2ql expressions against a focus collection."""

    def __init__(self, resolver: Resolver | None = None) -> None:
        """Bind an optional resolver for library-level variable/function references."""
        self._resolver = resolver
        self._active_functions: set[str] = set()

    def evaluate(self, expr: Expr, focus: list[Any], context: EvalContext | None = None) -> list[Any]:
        """Evaluate `expr` against `focus`, returning a collection (list of values)."""
        return self._eval(expr, focus, context or EvalContext())

    def call_function(
        self, definition: DefineFunction, args: list[list[Any]], focus: list[Any], context: EvalContext
    ) -> list[Any]:
        """Invoke a user-defined function, overlaying its params on the caller's scope.

        The caller context carries through so `$this`/`$index` stay visible inside an extracted
        helper; the function name is tracked to reject recursive calls instead of crashing.
        """
        if len(args) != len(definition.params):
            raise EvaluationError(
                f"function {definition.name!r} expects {len(definition.params)} argument(s), got {len(args)}"
            )
        if definition.name in self._active_functions:
            raise SemanticError(f"recursive function {definition.name!r}")
        if len(self._active_functions) >= MAX_FUNCTION_CALL_DEPTH:
            raise EvaluationError(f"function call chain exceeds {MAX_FUNCTION_CALL_DEPTH} levels")
        bound = dict(zip(definition.params, args, strict=True))
        self._active_functions.add(definition.name)
        try:
            return self._eval(definition.body, focus, context.child(**bound))
        finally:
            self._active_functions.discard(definition.name)

    def per_item(self, expr: Expr, item: Any, index: int, context: EvalContext) -> list[Any]:
        """Evaluate `expr` against a single item, binding `$this`/`$index` for that item."""
        scope = context.child(this=[item], index=[index])
        return self._eval(expr, [item], scope)

    # ------------------------------------------------------------------ dispatch

    def _eval(self, expr: Expr, focus: list[Any], context: EvalContext) -> list[Any]:
        match expr:
            case LiteralExpr():
                return [] if expr.value is None and expr.literal_type == "null" else [expr.value]
            case NameExpr():
                return flatten_member(focus, expr.name)
            case VariableExpr():
                return self._eval_variable(expr, context)
            case MemberExpr():
                return flatten_member(self._eval(expr.target, focus, context), expr.name)
            case IndexExpr():
                return self._eval_index(expr, focus, context)
            case CallExpr():
                return self._eval_call(expr, focus, context)
            case UnaryExpr():
                return self._eval_unary(expr, focus, context)
            case BinaryExpr():
                return self._eval_binary(expr, focus, context)
            case ObjectExpr():
                return [self.build_object(expr, focus, context)]
            case ArrayExpr():
                return [[collapse(self._eval(item, focus, context)) for item in expr.items]]

    def build_object(self, expr: ObjectExpr, focus: list[Any], context: EvalContext) -> dict[str, Any]:
        """Build a single dict from an object constructor, collapsing each field value."""
        return {field.name: collapse(self._eval(field.value, focus, context)) for field in expr.fields}

    def _eval_variable(self, expr: VariableExpr, context: EvalContext) -> list[Any]:
        if expr.name in context.variables:
            return context.variables[expr.name]
        if self._resolver is not None:
            resolved = self._resolver.resolve_variable(expr.name)
            if resolved is not None:
                return resolved
        raise EvaluationError(f"unknown variable ${expr.name}")

    def _eval_index(self, expr: IndexExpr, focus: list[Any], context: EvalContext) -> list[Any]:
        target = self._eval(expr.target, focus, context)
        index_values = self._eval(expr.index, focus, context)
        if not index_values:
            return []
        index = index_values[0]
        if isinstance(index, bool):
            raise EvaluationError("index must be an integer or a string key")
        if isinstance(index, int):
            return [target[index]] if -len(target) <= index < len(target) else []
        if isinstance(index, str):
            # A string subscript is member access by key, mirroring `.name` — this reaches fields
            # whose names aren't identifiers (hyphens, spaces, leading digits).
            return flatten_member(target, index)
        raise EvaluationError("index must be an integer or a string key")

    def _eval_call(self, expr: CallExpr, focus: list[Any], context: EvalContext) -> list[Any]:
        target_focus = self._eval(expr.target, focus, context) if expr.target is not None else focus
        builtin = fn.lookup(expr.name)
        if builtin is not None:
            return builtin(self, target_focus, expr.args, context)
        if self._resolver is not None:
            definition = self._resolver.resolve_function(expr.name)
            if definition is not None:
                args = [self._eval(arg, focus, context) for arg in expr.args]
                return self.call_function(definition, args, target_focus, context)
        raise EvaluationError(f"unknown function {expr.name!r}")

    def _eval_unary(self, expr: UnaryExpr, focus: list[Any], context: EvalContext) -> list[Any]:
        operand = self._eval(expr.operand, focus, context)
        if not operand:
            return []
        number = to_number(operand[0])
        if number is None:
            raise EvaluationError(f"unary {expr.op!r} requires a number")
        return [-number if expr.op == "-" else number]

    def _eval_binary(self, expr: BinaryExpr, focus: list[Any], context: EvalContext) -> list[Any]:
        if expr.op in ("and", "or", "xor", "implies"):
            return self._eval_logical(expr, focus, context)
        if expr.op == "is":
            return self._eval_is(expr, focus, context)
        left = self._eval(expr.left, focus, context)
        right = self._eval(expr.right, focus, context)
        if expr.op == "in":
            return [] if not left else [left[0] in _as_membership(right)]
        if expr.op == "contains":
            return self._eval_contains(left, right)
        if not left or not right:
            return []
        # Comparison/equality/match operators are existential over collections: a repeated field
        # like `name.given` matches if ANY of its values satisfies the operator (use `contains`/`in`
        # for explicit membership). Arithmetic stays scalar (operates on the first value).
        if expr.op in _EXISTENTIAL and (len(left) > 1 or len(right) > 1):
            return [_existential(expr.op, left, right)]
        return self._eval_scalar_binary(expr.op, left[0], right[0])

    def _eval_is(self, expr: BinaryExpr, focus: list[Any], context: EvalContext) -> list[Any]:
        # `is` takes a type name on the right — a bare identifier (`x is Integer`) or a string.
        left = self._eval(expr.left, focus, context)
        if not left:
            return []
        if isinstance(expr.right, NameExpr):
            type_name: Any = expr.right.name
        else:
            resolved = self._eval(expr.right, focus, context)
            type_name = resolved[0] if resolved else None
        return [_type_name(left[0]) == type_name]

    def _eval_logical(self, expr: BinaryExpr, focus: list[Any], context: EvalContext) -> list[Any]:
        # `and`/`or`/`implies` short-circuit so guarded predicates (`value != 0 and 1 / value > 0`)
        # exclude rows rather than raising; `xor` needs both sides.
        left = truthy(self._eval(expr.left, focus, context))
        match expr.op:
            case "and":
                return [False] if not left else [truthy(self._eval(expr.right, focus, context))]
            case "or":
                return [True] if left else [truthy(self._eval(expr.right, focus, context))]
            case "implies":
                return [True] if not left else [truthy(self._eval(expr.right, focus, context))]
            case _:  # xor
                return [left != truthy(self._eval(expr.right, focus, context))]

    def _eval_contains(self, left: list[Any], right: list[Any]) -> list[Any]:
        if len(left) == 1 and isinstance(left[0], str) and right and isinstance(right[0], str):
            return [right[0] in left[0]]
        return [] if not right else [right[0] in _as_membership(left)]

    def _eval_scalar_binary(self, op: str, left: Any, right: Any) -> list[Any]:
        match op:
            case "=":
                return [loose_equal(left, right)]
            case "!=":
                return [not loose_equal(left, right)]
            case "~":
                return [like(left, right)]
            case "!~":
                return [not like(left, right)]
            case "is":
                return [_type_name(left) == right]
            case "+":
                return [self._arithmetic_or_concat(left, right)]
            case "-" | "*" | "/" | "div" | "mod":
                return [self._arithmetic(op, left, right)]
            case "<" | "<=" | ">" | ">=":
                return self._relational(op, left, right)
            case _:
                raise EvaluationError(f"unsupported operator {op!r}")

    def _arithmetic_or_concat(self, left: Any, right: Any) -> Any:
        if isinstance(left, str) and isinstance(right, str):
            return left + right
        return self._arithmetic("+", left, right)

    def _arithmetic(self, op: str, left: Any, right: Any) -> float:
        left_number, right_number = to_number(left), to_number(right)
        if left_number is None or right_number is None:
            raise EvaluationError(f"operator {op!r} requires numbers")
        match op:
            case "+":
                return left_number + right_number
            case "-":
                return left_number - right_number
            case "*":
                return left_number * right_number
            case "/" | "div":
                if right_number == 0:
                    raise EvaluationError("division by zero")
                result = left_number / right_number
                if op != "div":
                    return result
                try:
                    return float(int(result))
                except (OverflowError, ValueError) as error:
                    # int() of a non-finite quotient (inf from an overflowing operand, nan) raises —
                    # keep it inside the d2ql error hierarchy rather than leaking the raw exception.
                    raise EvaluationError(f"div result is not a finite integer: {result!r}") from error
            case _:  # mod
                if right_number == 0:
                    raise EvaluationError("division by zero")
                return left_number % right_number

    def _relational(self, op: str, left: Any, right: Any) -> list[Any]:
        order = compare(left, right)
        if order is None:
            return []
        match op:
            case "<":
                return [order < 0]
            case "<=":
                return [order <= 0]
            case ">":
                return [order > 0]
            case _:  # >=
                return [order >= 0]


_EXISTENTIAL = frozenset({"=", "!=", "~", "!~", "<", "<=", ">", ">="})


def _existential(op: str, left: list[Any], right: list[Any]) -> bool:
    """Apply a comparison/equality/match operator existentially across two collections.

    `=`/`~`/`<`/… are true when any left-right pair satisfies them; `!=`/`!~` are the negation
    ("no pair is equal/matches"), which is the intuitive reading for a `where` over a repeated field.
    """
    pairs = [(item_left, item_right) for item_left in left for item_right in right]
    if op in ("=", "!="):
        matched = any(loose_equal(item_left, item_right) for item_left, item_right in pairs)
        return matched if op == "=" else not matched
    if op in ("~", "!~"):
        matched = any(like(item_left, item_right) for item_left, item_right in pairs)
        return matched if op == "~" else not matched
    return any(_relation_holds(op, item_left, item_right) for item_left, item_right in pairs)


def _relation_holds(op: str, left: Any, right: Any) -> bool:
    order = compare(left, right)
    if order is None:
        return False
    return {"<": order < 0, "<=": order <= 0, ">": order > 0, ">=": order >= 0}[op]


def _as_membership(values: list[Any]) -> list[Any]:
    """Unwrap an array literal into its members for `in`/`contains`: `[[a, b]]` -> `[a, b]`."""
    if len(values) == 1 and isinstance(values[0], list):
        return values[0]
    return values


def _type_name(value: Any) -> str:
    """Return the d2ql type label for an `is` test."""
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, float):
        return "Decimal"
    if isinstance(value, str):
        return "String"
    return "Object"
