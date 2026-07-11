"""Built-in function registry for the d2path expression layer.

Each implementation receives the evaluator, the call's focus collection, the unevaluated argument
expressions, and the active scope, so functions like `where`/`select` can rebind `$this` per item.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from dhis2w_ql.d2path.values import collapse, to_number, truthy
from dhis2w_ql.errors import EvaluationError

if TYPE_CHECKING:
    from dhis2w_ql.ast import Expr
    from dhis2w_ql.d2path.evaluator import EvalContext, Evaluator

FunctionImpl = Callable[["Evaluator", list[Any], "list[Expr]", "EvalContext"], list[Any]]

_REGISTRY: dict[str, FunctionImpl] = {}


def lookup(name: str) -> FunctionImpl | None:
    """Return the built-in implementation for `name`, or None when it is not built in."""
    return _REGISTRY.get(name)


def _register(name: str) -> Callable[[FunctionImpl], FunctionImpl]:
    def decorate(impl: FunctionImpl) -> FunctionImpl:
        _REGISTRY[name] = impl
        return impl

    return decorate


def _expect_argc(name: str, args: list[Expr], low: int, high: int | None = None) -> None:
    high = low if high is None else high
    if not (low <= len(args) <= high):
        want = f"{low}" if low == high else f"{low}-{high}"
        raise EvaluationError(f"{name}() expects {want} argument(s), got {len(args)}")


def _scalar(ev: Evaluator, arg: Expr, focus: list[Any], context: EvalContext) -> Any:
    return collapse(ev.evaluate(arg, focus, context))


def _string(focus: list[Any]) -> str | None:
    value = collapse(focus)
    return value if isinstance(value, str) else None


def _int_arg(ev: Evaluator, arg: Expr, focus: list[Any], context: EvalContext) -> int:
    value = _scalar(ev, arg, focus, context)
    if not isinstance(value, int) or isinstance(value, bool):
        raise EvaluationError("expected an integer argument")
    return value


def _distinct(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


# ------------------------------------------------------------------ filtering / projection


@_register("where")
def _where(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("where", args, 1)
    return [item for index, item in enumerate(focus) if truthy(ev.per_item(args[0], item, index, context))]


@_register("select")
def _select(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("select", args, 1)
    result: list[Any] = []
    for index, item in enumerate(focus):
        result.extend(ev.per_item(args[0], item, index, context))
    return result


@_register("exists")
def _exists(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("exists", args, 0, 1)
    if not args:
        return [len(focus) > 0]
    return [any(truthy(ev.per_item(args[0], item, index, context)) for index, item in enumerate(focus))]


@_register("all")
def _all(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("all", args, 1)
    return [all(truthy(ev.per_item(args[0], item, index, context)) for index, item in enumerate(focus))]


@_register("empty")
def _empty(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("empty", args, 0)
    return [len(focus) == 0]


@_register("iif")
def _iif(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("iif", args, 2, 3)
    if truthy(ev.evaluate(args[0], focus, context)):
        return ev.evaluate(args[1], focus, context)
    return ev.evaluate(args[2], focus, context) if len(args) == 3 else []


# ------------------------------------------------------------------ subsetting


@_register("first")
def _first(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("first", args, 0)
    return focus[:1]


@_register("last")
def _last(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("last", args, 0)
    return focus[-1:]


@_register("tail")
def _tail(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("tail", args, 0)
    return focus[1:]


@_register("skip")
def _skip(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("skip", args, 1)
    return focus[_int_arg(ev, args[0], focus, context) :]


@_register("take")
def _take(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("take", args, 1)
    count = _int_arg(ev, args[0], focus, context)
    return focus[:count] if count > 0 else []


@_register("count")
def _count(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("count", args, 0, 1)
    target = ev.evaluate(args[0], focus, context) if args else focus
    return [len(target)]


@_register("distinct")
def _distinct_fn(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("distinct", args, 0)
    return _distinct(focus)


@_register("isDistinct")
def _is_distinct(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("isDistinct", args, 0)
    return [len(focus) == len(_distinct(focus))]


@_register("union")
def _union(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("union", args, 1)
    return _distinct(focus + ev.evaluate(args[0], focus, context))


@_register("combine")
def _combine(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("combine", args, 1)
    return focus + ev.evaluate(args[0], focus, context)


# ------------------------------------------------------------------ boolean


@_register("not")
def _not(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("not", args, 0)
    return [not truthy(focus)]


# ------------------------------------------------------------------ strings


def _string_unary(name: str, transform: Callable[[str], Any]) -> None:
    @_register(name)
    def _impl(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
        _expect_argc(name, args, 0)
        text = _string(focus)
        return [] if text is None else [transform(text)]


_string_unary("upper", str.upper)
_string_unary("lower", str.lower)
_string_unary("length", len)
_string_unary("trim", str.strip)
_string_unary("toChars", list)


@_register("startsWith")
def _starts_with(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("startsWith", args, 1)
    text, prefix = _string(focus), _scalar(ev, args[0], focus, context)
    return [] if text is None or not isinstance(prefix, str) else [text.startswith(prefix)]


@_register("endsWith")
def _ends_with(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("endsWith", args, 1)
    text, suffix = _string(focus), _scalar(ev, args[0], focus, context)
    return [] if text is None or not isinstance(suffix, str) else [text.endswith(suffix)]


@_register("contains")
def _contains(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("contains", args, 1)
    text, needle = _string(focus), _scalar(ev, args[0], focus, context)
    return [] if text is None or not isinstance(needle, str) else [needle in text]


@_register("substring")
def _substring(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("substring", args, 1, 2)
    text = _string(focus)
    if text is None:
        return []
    start = _int_arg(ev, args[0], focus, context)
    if len(args) == 1:
        return [text[start:]]
    length = _int_arg(ev, args[1], focus, context)
    return [text[start : start + length]]


@_register("indexOf")
def _index_of(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("indexOf", args, 1)
    text, needle = _string(focus), _scalar(ev, args[0], focus, context)
    return [] if text is None or not isinstance(needle, str) else [text.find(needle)]


@_register("replace")
def _replace(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("replace", args, 2)
    text = _string(focus)
    pattern, replacement = _scalar(ev, args[0], focus, context), _scalar(ev, args[1], focus, context)
    if text is None or not isinstance(pattern, str) or not isinstance(replacement, str):
        return []
    return [text.replace(pattern, replacement)]


MAX_REGEX_PATTERN_LENGTH = 1000

#: Quantifiers that, applied to a group whose body already contains an unbounded quantifier, drive the
#: exponential backtracking `matches()` refuses (`(a+)+`, `(a*)*`, `(a+){2,}`).
_GROUP_QUANTIFIERS = frozenset({"+", "*", "{"})
#: Unbounded quantifiers whose presence inside a group makes re-quantifying that group catastrophic.
_INNER_QUANTIFIERS = frozenset({"+", "*"})


def _has_nested_quantifier(pattern: str) -> bool:
    """Linear scan: True when a quantified group contains an unbounded quantifier (the ReDoS shape).

    Detects `(a+)+`, `(a*)*`, `(a+)*`, `(a*)+`, and `(a+){2,}` — a group re-quantified while its body
    already repeats unboundedly. Respects backslash escapes and character classes (where `+`/`*`/`(`
    are literals), and treats a quantified subgroup as a quantifier within its parent so nested cases
    like `((a+)+)+` trip on the innermost pair. Bounded/optional inner quantifiers (`?`, `{n,m}`) do
    not trigger, so ordinary patterns like `(ab?c)+` pass.
    """
    body_has_quantifier: list[bool] = []  # one flag per open group on the stack
    index = 0
    length = len(pattern)
    in_class = False
    while index < length:
        char = pattern[index]
        if char == "\\":
            index += 2  # a backslash escapes the next char, so `\+` / `\(` are literals
            continue
        if in_class:
            in_class = char != "]"
            index += 1
            continue
        if char == "[":
            in_class = True
        elif char == "(":
            body_has_quantifier.append(False)
        elif char == ")":
            group_had_quantifier = body_has_quantifier.pop() if body_has_quantifier else False
            following = pattern[index + 1] if index + 1 < length else ""
            if following in _GROUP_QUANTIFIERS:
                if group_had_quantifier:
                    return True
                if body_has_quantifier:  # a quantified subgroup is itself a quantifier in its parent
                    body_has_quantifier[-1] = True
        elif char in _INNER_QUANTIFIERS and body_has_quantifier:
            body_has_quantifier[-1] = True
        index += 1
    return False


def _compile_pattern(name: str, pattern: str) -> re.Pattern[str]:
    """Compile a user-supplied regex, raising `EvaluationError` for over-long, catastrophic, or invalid patterns.

    Guards two ReDoS surfaces before handing the pattern to the stdlib `re` engine: an absolute length
    cap, and a linear pre-scan that rejects nested-quantifier constructs (`(a+)+` and kin) which cause
    catastrophic backtracking. This is a guardrail for well-meaning patterns, not a defence against a
    determined adversary — `matches()` is not intended for untrusted regex input.
    """
    if len(pattern) > MAX_REGEX_PATTERN_LENGTH:
        raise EvaluationError(
            f"{name}() pattern is {len(pattern)} characters long; the limit is {MAX_REGEX_PATTERN_LENGTH}"
        )
    if _has_nested_quantifier(pattern):
        raise EvaluationError(
            f"{name}() pattern {pattern!r} nests quantifiers (e.g. `(a+)+`), which risks catastrophic "
            f"backtracking; rewrite it without a quantified group whose body also repeats unboundedly"
        )
    try:
        return re.compile(pattern)
    except re.error as error:
        raise EvaluationError(f"{name}() pattern {pattern!r} is not a valid regular expression: {error}") from error


@_register("matches")
def _matches(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    """Test the focus string against a regular expression, compiled once with typed error wrapping.

    Guards against over-long and catastrophic-backtracking patterns (nested quantifiers like `(a+)+`)
    by raising a typed `EvaluationError`; it is a guardrail for honest mistakes, not a shield for
    adversarial regex input.
    """
    _expect_argc("matches", args, 1)
    text, pattern = _string(focus), _scalar(ev, args[0], focus, context)
    if text is None or not isinstance(pattern, str):
        return []
    return [_compile_pattern("matches", pattern).search(text) is not None]


@_register("split")
def _split(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("split", args, 1)
    text, separator = _string(focus), _scalar(ev, args[0], focus, context)
    return [] if text is None or not isinstance(separator, str) else text.split(separator)


@_register("join")
def _join(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("join", args, 0, 1)
    separator = _scalar(ev, args[0], focus, context) if args else ""
    parts = [str(item) for item in focus]
    return [str(separator).join(parts)]


# ------------------------------------------------------------------ math / aggregates


def _numbers(focus: list[Any]) -> list[float]:
    numbers = [to_number(item) for item in focus]
    if any(number is None for number in numbers):
        raise EvaluationError("aggregate requires a numeric collection")
    return [number for number in numbers if number is not None]


def _aggregate(name: str, reducer: Callable[[list[float]], float]) -> None:
    @_register(name)
    def _impl(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
        _expect_argc(name, args, 0, 1)
        target = ev.evaluate(args[0], focus, context) if args else focus
        numbers = _numbers(target)
        return [] if not numbers else [reducer(numbers)]


_aggregate("sum", sum)
_aggregate("min", min)
_aggregate("max", max)
_aggregate("avg", lambda numbers: sum(numbers) / len(numbers))


@_register("abs")
def _abs(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("abs", args, 0)
    number = to_number(collapse(focus))
    return [] if number is None else [abs(number)]


@_register("round")
def _round(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("round", args, 0, 1)
    number = to_number(collapse(focus))
    if number is None:
        return []
    precision = _int_arg(ev, args[0], focus, context) if args else 0
    return [round(number, precision)]


# ------------------------------------------------------------------ conversions / temporal


@_register("toInteger")
def _to_integer(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("toInteger", args, 0)
    number = to_number(collapse(focus))
    if number is None:
        return []
    try:
        return [int(number)]
    except (OverflowError, ValueError) as error:
        # int(inf) raises OverflowError and int(nan) raises ValueError — keep both inside the d2ql
        # error hierarchy instead of letting the raw exception escape.
        raise EvaluationError(f"toInteger() cannot convert {number!r} to an integer") from error


@_register("toDecimal")
def _to_decimal(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("toDecimal", args, 0)
    number = to_number(collapse(focus))
    return [] if number is None else [number]


@_register("toString")
def _to_string(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("toString", args, 0)
    value = collapse(focus)
    if value is None:
        return []
    if isinstance(value, bool):
        return ["true" if value else "false"]
    return [str(value)]


@_register("today")
def _today(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("today", args, 0)
    return [date.today().isoformat()]


@_register("now")
def _now(ev: Evaluator, focus: list[Any], args: list[Expr], context: EvalContext) -> list[Any]:
    _expect_argc("now", args, 0)
    return [datetime.now().isoformat()]
