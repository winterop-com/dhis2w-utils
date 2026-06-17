"""Head-to-head GENERAL-capability eval for local models: python + cli + tooling, objective pass/fail.

Axis 1 of model validation — the non-bridge axis (axis 2 is `bench_bridge_models.py`). Three suites,
all scored by execution or structural match, never by an AI judge:

  - python  : the model writes a function/class; we exec it and run hidden test cases.
  - cli     : the model writes a shell command for a goal; we run it in a curated-PATH tmp sandbox
              (only a small allowlist of safe tools is reachable, relative paths only) and check the
              effect (files created / stdout).
  - tooling : the model is given mock tool specs + a goal; we check it emits the right tool call with
              the right args — the function-calling foundation the bridge depends on.

There is no hardcoded roster — name the model(s) to benchmark explicitly on the command line. Set
`BENCH_CHAMPION=<key>` to designate an oracle: when that model is in the run, the harness asserts it
passed every task and flags SUSPECT tasks otherwise (an oracle failure means the TASK is mis-specified,
not the model). Per-model JSON is appended to `RESULTS`; a Markdown table is printed at the end.

CLI-sandbox threat model: commands run in a throwaway temp dir with `PATH` restricted to an allowlist
of read/format tools (no `rm`/`curl`/`sudo`/...) and absolute paths / `~` / `..` rejected before
execution. This bounds — it does not perfectly isolate — model-generated shell. Run it on a machine
you trust.

Prereqs: a running backend (LM Studio by default; `MODEL_BACKEND` to switch). The script loads/unloads
each model itself, one at a time.

Usage:
    uv run python infra/scripts/bench_general_models.py google/gemma-4-12b-qat            # one model
    uv run python infra/scripts/bench_general_models.py gemma-4-12b-qat gemma-4-e4b        # several
    BENCH_MAX_TOKENS=2048 uv run python infra/scripts/bench_general_models.py <model>      # tighter budget
    BENCH_CHAMPION=<key>  uv run python infra/scripts/bench_general_models.py <model> ...  # with an oracle
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_bench.backend import get_backend

#: Optional oracle model key (env `BENCH_CHAMPION`). When set and present in a run, the harness
#: asserts it passed every task and flags SUSPECT tasks otherwise. Unset -> no oracle check. There is
#: no hardcoded roster: the models to benchmark are named explicitly on the command line.
CHAMPION = os.environ.get("BENCH_CHAMPION", "").strip()

#: Local-inference backend (LM Studio by default; override with MODEL_BACKEND).
BACKEND = get_backend()
LM = BACKEND.chat_url
RESULTS = "/tmp/bench_general_results.jsonl"


def _env_int(name: str, default: int) -> int:
    """Read a positive int from env `name`; fall back to `default` when unset or invalid."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


#: Generation cap. Reasoning models spend a long chain-of-thought before the answer, so the cap must
#: leave room for the actual code/command after the thinking — too low truncates the closing fence.
#: The champion occasionally over-reasons on trivial tasks, so the default is deliberately generous.
#: Override with `BENCH_MAX_TOKENS` to probe how models degrade under a tighter token budget.
MAX_TOKENS = _env_int("BENCH_MAX_TOKENS", 16384)

PY_SYSTEM = (
    "You are an expert Python programmer. Reply with exactly one Python ```python code block defining "
    "the requested symbol, with no surrounding prose. It must be self-contained (import what it needs)."
)
CLI_SYSTEM = (
    "You are a shell expert. Reply with exactly one shell command on a single line inside a ```bash "
    "code block, no prose. Use only standard POSIX tools and relative paths in the current directory."
)
TOOL_SYSTEM = "Use the provided tools to accomplish the user's request. Call exactly one tool with concrete arguments."


# --- Response parsing -----------------------------------------------------------------------


class _ToolFunction(BaseModel):
    """The `function` block of an OpenAI tool call."""

    name: str = ""
    arguments: str = ""


class _ToolCallRaw(BaseModel):
    """One tool call in an OpenAI chat response. `id`/`type` are kept so the call can be echoed back."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    type: str = "function"
    function: _ToolFunction = Field(default_factory=_ToolFunction)


class _Message(BaseModel):
    """The assistant message of a chat choice."""

    content: str | None = None
    tool_calls: list[_ToolCallRaw] = Field(default_factory=list)


class _Choice(BaseModel):
    """One choice in a chat response."""

    message: _Message


class _Usage(BaseModel):
    """Token usage block."""

    completion_tokens: int = 0


class _ChatResponse(BaseModel):
    """Minimal projection of an OpenAI chat-completions response."""

    model_config = ConfigDict(extra="ignore")

    choices: list[_Choice]
    usage: _Usage = Field(default_factory=_Usage)


class ToolCall(BaseModel):
    """A parsed tool call: the tool name and its decoded arguments."""

    model_config = ConfigDict(frozen=True)

    name: str
    arguments: dict[str, object]


class CliRun(BaseModel):
    """The outcome of running a model's shell command in the sandbox."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    returncode: int
    stdout: str
    workdir: Path


# --- Task definitions -----------------------------------------------------------------------


class PythonTask(BaseModel):
    """A python task: prompt, the symbol (function/class) to extract, and a checker over it."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: str
    prompt: str
    symbol: str
    check: Callable[[object], list[bool]]


class CliTask(BaseModel):
    """A cli task: a goal, a sandbox-setup hook, and a checker over the run."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: str
    goal: str
    setup: Callable[[Path], None]
    check: Callable[[CliRun], list[bool]]


class ToolDef(BaseModel):
    """A mock tool: its name/description/JSON-schema params plus a handler that returns a canned result.

    The handler is what makes multi-turn possible — it feeds a realistic result back so the model can
    chain a second call on data it could only have learned from the first.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: dict[str, object]
    handler: Callable[[dict[str, object]], str]

    def spec(self) -> dict[str, object]:
        """Render this tool as an OpenAI function-tool spec."""
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


class ToolScenario(BaseModel):
    """A tooling scenario: a goal, the offered tools, and a checker over the FULL sequence of calls made.

    Scoring over the whole transcript (not just the first call) is what tests real agentic behaviour:
    strict multi-argument correctness, picking the right tool among confusable ones, and chaining.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: str
    goal: str
    tools: list[ToolDef]
    check: Callable[[list[ToolCall]], bool]
    max_steps: int = 4


# --- python suite checks --------------------------------------------------------------------


def _roman_cases(fn: object) -> list[bool]:
    """Hidden cases for int_to_roman."""
    call: Callable[[int], str] = fn  # type: ignore[assignment]
    try:
        return [call(4) == "IV", call(9) == "IX", call(58) == "LVIII", call(1994) == "MCMXCIV"]
    except Exception:
        return [False]


def _balanced_cases(fn: object) -> list[bool]:
    """Hidden cases for is_balanced (brackets)."""
    call: Callable[[str], bool] = fn  # type: ignore[assignment]
    try:
        return [call("()[]{}") is True, call("(]") is False, call("([{}])") is True, call("(") is False]
    except Exception:
        return [False]


def _merge_cases(fn: object) -> list[bool]:
    """Hidden cases for merge_intervals."""
    call: Callable[[list[list[int]]], list[list[int]]] = fn  # type: ignore[assignment]
    try:
        return [
            call([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]],
            call([[1, 4], [4, 5]]) == [[1, 5]],
            call([]) == [],
        ]
    except Exception:
        return [False]


def _top_word_cases(fn: object) -> list[bool]:
    """Hidden cases for top_word (most frequent word, lowercase, ties broken alphabetically)."""
    call: Callable[[str], str] = fn  # type: ignore[assignment]
    try:
        return [call("the cat the dog") == "the", call("a b a b") == "a", call("Hello hello world") == "hello"]
    except Exception:
        return [False]


def _lru_cases(cls: object) -> list[bool]:
    """Hidden cases for LRUCache(capacity) with get/put, get returning -1 on miss."""
    make = cast("Callable[[int], Any]", cls)
    try:
        cache = make(2)
        cache.put(1, 1)
        cache.put(2, 2)
        first = cache.get(1) == 1
        cache.put(3, 3)  # evicts key 2 (least-recently used)
        evicted = cache.get(2) == -1
        cache.put(4, 4)  # evicts key 1
        return [first, evicted, cache.get(1) == -1, cache.get(3) == 3, cache.get(4) == 4]
    except Exception:
        return [False]


def _lcs_cases(fn: object) -> list[bool]:
    """Hidden cases for lcs_length (longest common subsequence length)."""
    call: Callable[[str, str], int] = fn  # type: ignore[assignment]
    try:
        return [call("abcde", "ace") == 3, call("abc", "abc") == 3, call("abc", "def") == 0, call("", "x") == 0]
    except Exception:
        return [False]


def _two_sum_cases(fn: object) -> list[bool]:
    """Hidden cases for two_sum (return indices of the two values summing to target)."""
    call = cast("Callable[[list[int], int], object]", fn)

    def ok(nums: list[int], target: int) -> bool:
        result = call(nums, target)
        if not isinstance(result, list | tuple) or len(result) != 2:
            return False
        i, j = result
        return i != j and nums[int(i)] + nums[int(j)] == target

    try:
        return [ok([2, 7, 11, 15], 9), ok([3, 2, 4], 6), ok([3, 3], 6)]
    except Exception:
        return [False]


def _roman_to_int_cases(fn: object) -> list[bool]:
    """Hidden cases for roman_to_int."""
    call: Callable[[str], int] = fn  # type: ignore[assignment]
    try:
        return [call("IV") == 4, call("IX") == 9, call("LVIII") == 58, call("MCMXCIV") == 1994]
    except Exception:
        return [False]


def _palindrome_cases(fn: object) -> list[bool]:
    """Hidden cases for is_palindrome (alphanumeric only, case-insensitive)."""
    call: Callable[[str], bool] = fn  # type: ignore[assignment]
    try:
        return [
            call("A man, a plan, a canal: Panama") is True,
            call("race a car") is False,
            call(" ") is True,
            call("0P") is False,
        ]
    except Exception:
        return [False]


def _longest_unique_cases(fn: object) -> list[bool]:
    """Hidden cases for longest_unique (length of longest substring without repeating chars)."""
    call: Callable[[str], int] = fn  # type: ignore[assignment]
    try:
        return [call("abcabcbb") == 3, call("bbbbb") == 1, call("pwwkew") == 3, call("") == 0]
    except Exception:
        return [False]


def _rpn_cases(fn: object) -> list[bool]:
    """Hidden cases for rpn_eval (evaluate reverse-polish notation tokens; only + - *)."""
    call: Callable[[list[str]], int] = fn  # type: ignore[assignment]
    try:
        return [call(["2", "1", "+", "3", "*"]) == 9, call(["4", "5", "*"]) == 20, call(["7", "2", "-"]) == 5]
    except Exception:
        return [False]


def _min_coins_cases(fn: object) -> list[bool]:
    """Hidden cases for min_coins (fewest coins for amount, or -1 if impossible)."""
    call: Callable[[list[int], int], int] = fn  # type: ignore[assignment]
    try:
        return [call([1, 2, 5], 11) == 3, call([2], 3) == -1, call([1], 0) == 0, call([1, 2, 5], 100) == 20]
    except Exception:
        return [False]


def _word_break_cases(fn: object) -> list[bool]:
    """Hidden cases for word_break (can s be segmented into dictionary words)."""
    call: Callable[[str, list[str]], bool] = fn  # type: ignore[assignment]
    try:
        return [
            call("leetcode", ["leet", "code"]) is True,
            call("applepenapple", ["apple", "pen"]) is True,
            call("catsandog", ["cats", "dog", "sand", "and", "cat"]) is False,
        ]
    except Exception:
        return [False]


def _edit_distance_cases(fn: object) -> list[bool]:
    """Hidden cases for edit_distance (Levenshtein distance between two strings)."""
    call: Callable[[str, str], int] = fn  # type: ignore[assignment]
    try:
        return [
            call("horse", "ros") == 3,
            call("intention", "execution") == 5,
            call("", "abc") == 3,
            call("abc", "abc") == 0,
        ]
    except Exception:
        return [False]


PYTHON_TASKS: tuple[PythonTask, ...] = (
    PythonTask(
        key="int_to_roman",
        prompt="Write `def int_to_roman(num: int) -> str` converting an integer 1..3999 to a Roman numeral.",
        symbol="int_to_roman",
        check=_roman_cases,
    ),
    PythonTask(
        key="balanced",
        prompt=(
            "Write `def is_balanced(s: str) -> bool` returning True iff the brackets (), [], {} in s are "
            "correctly matched and nested."
        ),
        symbol="is_balanced",
        check=_balanced_cases,
    ),
    PythonTask(
        key="merge_intervals",
        prompt=(
            "Write `def merge_intervals(intervals: list[list[int]]) -> list[list[int]]` merging overlapping "
            "intervals, returned sorted by start. Touching intervals like [1,4],[4,5] merge into [1,5]."
        ),
        symbol="merge_intervals",
        check=_merge_cases,
    ),
    PythonTask(
        key="top_word",
        prompt=(
            "Write `def top_word(text: str) -> str` returning the most frequent word (case-insensitive, split "
            "on whitespace), breaking ties alphabetically."
        ),
        symbol="top_word",
        check=_top_word_cases,
    ),
    PythonTask(
        key="lru_cache",
        prompt=(
            "Write a class `LRUCache` with `__init__(self, capacity: int)`, `get(self, key) -> int` (returns -1 "
            "if absent), and `put(self, key, value)`. When full, evict the least-recently-used entry. get and "
            "put both count as a use."
        ),
        symbol="LRUCache",
        check=_lru_cases,
    ),
    PythonTask(
        key="lcs",
        prompt=(
            "Write `def lcs_length(a: str, b: str) -> int` returning the length of the longest common "
            "subsequence of a and b."
        ),
        symbol="lcs_length",
        check=_lcs_cases,
    ),
    PythonTask(
        key="two_sum",
        prompt=(
            "Write `def two_sum(nums: list[int], target: int) -> list[int]` returning the indices of the two "
            "numbers that add up to target (exactly one solution; do not reuse an index)."
        ),
        symbol="two_sum",
        check=_two_sum_cases,
    ),
    PythonTask(
        key="roman_to_int",
        prompt="Write `def roman_to_int(s: str) -> int` converting a Roman numeral string to its integer value.",
        symbol="roman_to_int",
        check=_roman_to_int_cases,
    ),
    PythonTask(
        key="palindrome",
        prompt=(
            "Write `def is_palindrome(s: str) -> bool` returning True iff s is a palindrome considering only "
            "alphanumeric characters and ignoring case."
        ),
        symbol="is_palindrome",
        check=_palindrome_cases,
    ),
    PythonTask(
        key="longest_unique",
        prompt=(
            "Write `def longest_unique(s: str) -> int` returning the length of the longest substring of s "
            "without repeating characters."
        ),
        symbol="longest_unique",
        check=_longest_unique_cases,
    ),
    PythonTask(
        key="rpn_eval",
        prompt=(
            "Write `def rpn_eval(tokens: list[str]) -> int` evaluating a reverse-polish-notation expression. "
            "Tokens are integers and the operators +, -, * (left operand pushed first)."
        ),
        symbol="rpn_eval",
        check=_rpn_cases,
    ),
    PythonTask(
        key="min_coins",
        prompt=(
            "Write `def min_coins(coins: list[int], amount: int) -> int` returning the fewest coins that sum to "
            "amount, or -1 if it cannot be made. Each coin may be used unlimited times."
        ),
        symbol="min_coins",
        check=_min_coins_cases,
    ),
    PythonTask(
        key="word_break",
        prompt=(
            "Write `def word_break(s: str, words: list[str]) -> bool` returning True iff s can be segmented into "
            "a space-separated sequence of one or more words from the list (words reusable)."
        ),
        symbol="word_break",
        check=_word_break_cases,
    ),
    PythonTask(
        key="edit_distance",
        prompt=(
            "Write `def edit_distance(a: str, b: str) -> int` returning the Levenshtein edit distance (min "
            "single-character insert/delete/replace edits) to turn a into b."
        ),
        symbol="edit_distance",
        check=_edit_distance_cases,
    ),
)


# --- cli suite (sandbox) --------------------------------------------------------------------

#: Tools reachable inside the cli sandbox — read/format only, no mutation-at-scale or network.
SANDBOX_TOOLS: tuple[str, ...] = (
    "echo", "printf", "cat", "ls", "wc", "sort", "head", "tail",
    "grep", "cut", "awk", "tr", "sed", "uniq", "mkdir", "touch", "python3",
)  # fmt: skip
#: Patterns that make a command unsafe to run even in the sandbox (absolute paths, escapes, danger tools).
_UNSAFE = re.compile(
    r"(^|[\s=><|])/|(?<![\w.])~|\.\.[/\s]|\b(rm|sudo|dd|mkfs|chmod|chown|curl|wget|nc|ssh|scp|kill|shutdown|reboot)\b"
)


def _is_safe_command(command: str) -> bool:
    """Return True when `command` is safe to run in the sandbox (no absolute paths / escapes / danger tools)."""
    return not _UNSAFE.search(command)


def _write_lines(path: Path, lines: Sequence[str]) -> None:
    """Write `lines` (newline-terminated) to `path`."""
    path.write_text("".join(f"{line}\n" for line in lines))


def _setup_data_txt(workdir: Path) -> None:
    """Create data.txt with five lines."""
    _write_lines(workdir / "data.txt", ["one", "two", "three", "four", "five"])


def _setup_csv(workdir: Path) -> None:
    """Create data.csv with three comma-separated rows."""
    _write_lines(workdir / "data.csv", ["a,1", "b,2", "c,3"])


def _setup_names(workdir: Path) -> None:
    """Create names.txt with three unsorted names."""
    _write_lines(workdir / "names.txt", ["charlie", "alice", "bob"])


def _check_count_lines(run: CliRun) -> list[bool]:
    """The command should print 5 (the line count of data.txt)."""
    return [run.returncode == 0 and run.stdout.split() == ["5"]]


def _check_second_column(run: CliRun) -> list[bool]:
    """The command should print the second column of each csv row."""
    return [run.returncode == 0 and [line for line in run.stdout.split()] == ["1", "2", "3"]]


def _check_sorted_names(run: CliRun) -> list[bool]:
    """The command should print the names sorted alphabetically."""
    return [run.returncode == 0 and run.stdout.split() == ["alice", "bob", "charlie"]]


CLI_TASKS: tuple[CliTask, ...] = (
    CliTask(
        key="count_lines",
        goal="Print the number of lines in the file data.txt, and nothing else.",
        setup=_setup_data_txt,
        check=_check_count_lines,
    ),
    CliTask(
        key="second_column",
        goal="Print the second comma-separated column of every row in data.csv, one value per line.",
        setup=_setup_csv,
        check=_check_second_column,
    ),
    CliTask(
        key="sort_names",
        goal="Print the lines of names.txt sorted alphabetically.",
        setup=_setup_names,
        check=_check_sorted_names,
    ),
)


# --- tooling suite (multi-turn agentic) -----------------------------------------------------


def _eval_arith(node: ast.AST) -> float:
    """Evaluate a constant arithmetic expression AST (no names/calls), for the calculator tool."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_arith(node.operand)
    if isinstance(node, ast.BinOp):
        left, right = _eval_arith(node.left), _eval_arith(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
    raise ValueError("unsupported expression")


def _str_arg(args: dict[str, object], key: str) -> str:
    """Read a string argument from a tool call's decoded arguments (empty string if absent)."""
    value = args.get(key)
    return value if isinstance(value, str) else ""


# --- tool handlers (return a canned JSON result the model can chain on) ---------------------


def _h_get_user(args: dict[str, object]) -> str:
    """Look up a user; returns an email the model must then use downstream."""
    name = _str_arg(args, "name").lower()
    email = "alice@example.com" if "alice" in name else ("bob@example.com" if "bob" in name else "carol@example.com")
    return json.dumps({"name": _str_arg(args, "name"), "email": email, "id": "u-42"})


def _h_send_email(args: dict[str, object]) -> str:
    """Pretend to send an email."""
    return json.dumps({"status": "sent", "to": _str_arg(args, "to")})


def _h_get_weather(args: dict[str, object]) -> str:
    """Canned weather for a city."""
    return json.dumps({"city": _str_arg(args, "city"), "temp_c": 18, "condition": "cloudy"})


def _h_get_time(args: dict[str, object]) -> str:
    """Canned local time for a timezone/city."""
    return json.dumps({"zone": _str_arg(args, "timezone") or _str_arg(args, "city"), "time": "14:30"})


def _h_search(args: dict[str, object]) -> str:
    """Canned web-search hit list."""
    return json.dumps([{"title": f"Result for {_str_arg(args, 'query')}", "url": "https://example.com/a"}])


def _h_read_file(args: dict[str, object]) -> str:
    """Return file contents — the word_count chain depends on the model passing this text on."""
    content = "the quick brown fox jumps over the lazy dog" if "report" in _str_arg(args, "path").lower() else "hello"
    return json.dumps({"path": _str_arg(args, "path"), "content": content})


def _h_word_count(args: dict[str, object]) -> str:
    """Count words in the supplied text (computed, so it actually works in a chain)."""
    return json.dumps({"count": len(_str_arg(args, "text").split())})


def _h_exchange_rate(args: dict[str, object]) -> str:
    """Canned FX rate; the model must feed it into the calculator."""
    return json.dumps({"base": _str_arg(args, "base"), "quote": _str_arg(args, "quote"), "rate": 0.92})


def _h_calculator(args: dict[str, object]) -> str:
    """Evaluate a constant arithmetic expression."""
    try:
        return json.dumps({"result": _eval_arith(ast.parse(_str_arg(args, "expression"), mode="eval").body)})
    except (ValueError, SyntaxError, ZeroDivisionError):
        return json.dumps({"error": "invalid expression"})


def _h_create_ticket(args: dict[str, object]) -> str:
    """Pretend to open a support ticket."""
    return json.dumps({"id": "TICK-1", "title": _str_arg(args, "title"), "status": "open"})


def _obj(props: dict[str, object], required: list[str]) -> dict[str, object]:
    """Build a JSON-Schema object spec for a tool's parameters."""
    return {"type": "object", "properties": props, "required": required}


_STR: dict[str, object] = {"type": "string"}

#: The mock toolbox offered across the tooling scenarios.
TOOLBOX: tuple[ToolDef, ...] = (
    ToolDef(name="get_user", description="Look up a user by name; returns their email address.",
            parameters=_obj({"name": _STR}, ["name"]), handler=_h_get_user),
    ToolDef(name="send_email", description="Send an email to a recipient.",
            parameters=_obj({"to": _STR, "subject": _STR, "body": _STR}, ["to", "subject"]), handler=_h_send_email),
    ToolDef(name="get_weather", description="Get the current weather for a city.",
            parameters=_obj({"city": _STR}, ["city"]), handler=_h_get_weather),
    ToolDef(name="get_time", description="Get the current local time for a timezone or city.",
            parameters=_obj({"timezone": _STR}, ["timezone"]), handler=_h_get_time),
    ToolDef(name="search", description="Search the web for information.",
            parameters=_obj({"query": _STR}, ["query"]), handler=_h_search),
    ToolDef(name="read_file", description="Read a text file and return its contents.",
            parameters=_obj({"path": _STR}, ["path"]), handler=_h_read_file),
    ToolDef(name="word_count", description="Count the number of words in a piece of text.",
            parameters=_obj({"text": _STR}, ["text"]), handler=_h_word_count),
    ToolDef(name="get_exchange_rate", description="Get the FX rate from one currency to another.",
            parameters=_obj({"base": _STR, "quote": _STR}, ["base", "quote"]), handler=_h_exchange_rate),
    ToolDef(name="calculator", description="Evaluate an arithmetic expression like '250 * 0.92'.",
            parameters=_obj({"expression": _STR}, ["expression"]), handler=_h_calculator),
    ToolDef(name="create_ticket", description="Open a support ticket assigned to an email address.",
            parameters=_obj({"title": _STR, "assignee_email": _STR}, ["title", "assignee_email"]),
            handler=_h_create_ticket),
)  # fmt: skip


def _called(calls: list[ToolCall], name: str, **needles: str) -> bool:
    """True if some call to `name` has every named arg containing its needle (case-insensitive)."""
    for call in calls:
        if call.name != name:
            continue
        if all(needle.lower() in _str_arg(call.arguments, key).lower() for key, needle in needles.items()):
            return True
    return False


def _not_called(calls: list[ToolCall], name: str) -> bool:
    """True if `name` was never called (tests not reaching for the wrong tool)."""
    return all(call.name != name for call in calls)


TOOL_SCENARIOS: tuple[ToolScenario, ...] = (
    # Single call, strict multi-argument correctness.
    ToolScenario(
        key="email_strict",
        goal="Email bob@example.com with the subject 'Lunch' and the body 'noon at the cafe?'.",
        tools=list(TOOLBOX),
        check=lambda c: _called(c, "send_email", to="bob@example.com", subject="lunch", body="noon"),
    ),
    # Pick the right tool among confusable ones (time, not weather).
    ToolScenario(
        key="confusable_time",
        goal="What time is it in Tokyo right now?",
        tools=list(TOOLBOX),
        check=lambda c: _called(c, "get_time", timezone="tokyo") and _not_called(c, "get_weather"),
    ),
    # Right tool, sensible query.
    ToolScenario(
        key="search_topic",
        goal="Find recent news about the Mars rover.",
        tools=list(TOOLBOX),
        check=lambda c: _called(c, "search", query="mars"),
    ),
    # Multi-turn: look up an email, then use it. The email only exists in get_user's result.
    ToolScenario(
        key="lookup_then_email",
        goal="Look up Alice's email address, then send her an email with the subject 'Hello'.",
        tools=list(TOOLBOX),
        check=lambda c: _called(c, "send_email", to="alice@example.com", subject="hello"),
    ),
    # Multi-turn: read a file, then count its words. The text only exists in read_file's result.
    ToolScenario(
        key="read_then_count",
        goal="Read the file report.txt and tell me how many words it contains. Use the tools.",
        tools=list(TOOLBOX),
        check=lambda c: _called(c, "read_file", path="report") and _called(c, "word_count", text="fox"),
    ),
    # Multi-turn: fetch an FX rate, then compute with it.
    ToolScenario(
        key="rate_then_calc",
        goal="How much is 250 USD in EUR? Fetch the exchange rate first, then calculate.",
        tools=list(TOOLBOX),
        check=lambda c: (
            _called(c, "get_exchange_rate", base="usd", quote="eur") and _called(c, "calculator", expression="250")
        ),
    ),
    # Multi-turn: look up Bob's email, then open a ticket assigned to it.
    ToolScenario(
        key="lookup_then_ticket",
        goal="Open a support ticket titled 'Login bug' assigned to Bob — look up his email first.",
        tools=list(TOOLBOX),
        check=lambda c: _called(c, "create_ticket", title="login", assignee_email="bob@example.com"),
    ),
)


# --- results --------------------------------------------------------------------------------


class TaskResult(BaseModel):
    """Outcome of one task for one model."""

    model_config = ConfigDict(frozen=True)

    suite: str
    key: str
    passed: int
    total: int
    seconds: float
    tokens: int


class ModelReport(BaseModel):
    """All task results for one model across the three suites."""

    model_config = ConfigDict(frozen=True)

    model: str
    results: list[TaskResult]

    def suite_score(self, suite: str) -> str:
        """passed/total across one suite."""
        rows = [result for result in self.results if result.suite == suite]
        return f"{sum(row.passed for row in rows)}/{sum(row.total for row in rows)}"

    @property
    def all_passed(self) -> bool:
        """True when every case in every suite passed (the oracle bar)."""
        return all(result.passed == result.total for result in self.results)


# --- model calls ----------------------------------------------------------------------------


async def _post_chat(http: httpx.AsyncClient, payload: dict[str, object]) -> httpx.Response:
    """POST to the chat endpoint, retrying a few times on a transient disconnect (model still alive)."""
    last: httpx.HTTPError | None = None
    for attempt in range(3):
        try:
            return await http.post(LM, json=payload, timeout=300.0)
        except httpx.HTTPError as exc:
            last = exc
            await asyncio.sleep(2.0 * (attempt + 1))
    raise last if last is not None else RuntimeError("chat post exhausted retries")


async def _chat(http: httpx.AsyncClient, model: str, system: str, prompt: str) -> tuple[str, float, int]:
    """One plain chat completion. Returns (content, seconds, completion_tokens)."""
    started = time.monotonic()
    response = await _post_chat(
        http,
        {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": MAX_TOKENS,
        },
    )
    elapsed = time.monotonic() - started
    parsed = _ChatResponse.model_validate(response.json())
    return (parsed.choices[0].message.content or "", elapsed, parsed.usage.completion_tokens)


def _parse_tool_call(raw: _ToolCallRaw) -> ToolCall:
    """Decode a raw tool call's JSON arguments into a typed `ToolCall`."""
    try:
        arguments = json.loads(raw.function.arguments or "{}")
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolCall(name=raw.function.name, arguments=arguments)


async def _run_tool_scenario(
    http: httpx.AsyncClient, model: str, scenario: ToolScenario
) -> tuple[list[ToolCall], float, int]:
    """Drive a multi-turn agent loop: call tools, feed back canned results, collect every call made.

    Returns (all tool calls in order, seconds, total completion tokens). Each round echoes the
    assistant's tool calls and appends each tool's handler result, so the model can chain.
    """
    specs = [tool.spec() for tool in scenario.tools]
    handlers = {tool.name: tool.handler for tool in scenario.tools}
    messages: list[dict[str, object]] = [
        {"role": "system", "content": TOOL_SYSTEM},
        {"role": "user", "content": scenario.goal},
    ]
    made: list[ToolCall] = []
    tokens = 0
    started = time.monotonic()
    for _ in range(scenario.max_steps):
        response = await _post_chat(http, {"model": model, "messages": messages, "tools": specs, "temperature": 0.2})
        parsed = _ChatResponse.model_validate(response.json())
        tokens += parsed.usage.completion_tokens
        message = parsed.choices[0].message
        if not message.tool_calls:
            break
        echoed: list[dict[str, object]] = []
        results: list[dict[str, object]] = []
        for index, raw in enumerate(message.tool_calls):
            call_id = raw.id or f"call_{len(made)}_{index}"
            call = _parse_tool_call(raw)
            made.append(call)
            echoed.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": raw.function.name, "arguments": raw.function.arguments or "{}"},
                }
            )
            handler = handlers.get(call.name)
            result = handler(call.arguments) if handler else json.dumps({"error": f"unknown tool {call.name}"})
            results.append({"role": "tool", "tool_call_id": call_id, "content": result})
        messages.append({"role": "assistant", "content": message.content or "", "tool_calls": echoed})
        messages.extend(results)
    return made, time.monotonic() - started, tokens


# --- suite runners --------------------------------------------------------------------------


def _extract_code(text: str, languages: tuple[str, ...]) -> str | None:
    """Return the first fenced code block (any of `languages`, or unlabelled), else None.

    Falls back to the text after the last opening fence when the closing fence is missing — a
    reasoning model that runs into the token cap mid-answer can leave the block unclosed.
    """
    langs = "|".join(languages)
    blocks = re.findall(r"```(?:" + langs + r")?\s*(.*?)```", text, re.DOTALL)
    if blocks:
        return str(blocks[0])
    unclosed = re.search(r"```(?:" + langs + r")?\s*\n(.*)$", text, re.DOTALL)
    return str(unclosed.group(1)) if unclosed else None


def _run_python(text: str, task: PythonTask) -> tuple[int, int]:
    """Extract + exec the symbol, run hidden cases. Returns (passed, total)."""
    code = _extract_code(text, ("python", "py"))
    if code is None or f"{task.symbol}" not in code:
        return (0, 1)
    namespace: dict[str, object] = {}
    try:
        exec(code, namespace)  # noqa: S102 — sandboxed eval of model output in a throwaway harness
        symbol = namespace.get(task.symbol)
        if symbol is None:
            return (0, 1)
        outcomes = task.check(symbol)
    except Exception:
        return (0, 1)
    return (sum(1 for ok in outcomes if ok), len(outcomes))


def _sandbox_bin(workdir: Path) -> Path | None:
    """Build a bin dir of symlinks to the allowlisted tools; None if the shell itself is missing."""
    if shutil.which("bash") is None:
        return None
    bindir = workdir / ".bin"
    bindir.mkdir()
    for tool in SANDBOX_TOOLS:
        resolved = shutil.which(tool)
        if resolved:
            (bindir / tool).symlink_to(resolved)
    return bindir


def _run_cli(text: str, task: CliTask) -> tuple[int, int]:
    """Extract the command, run it in a curated-PATH tmp sandbox, check the effect. Returns (passed, total)."""
    code = _extract_code(text, ("bash", "sh", "shell"))
    command = (code or text).strip().splitlines()
    command_line = command[0].strip() if command else ""
    if not command_line or not _is_safe_command(command_line):
        return (0, 1)
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        task.setup(workdir)
        bindir = _sandbox_bin(workdir)
        if bindir is None:
            return (0, 1)
        bash = shutil.which("bash") or "/bin/bash"
        try:
            proc = subprocess.run(
                [bash, "-c", command_line],
                cwd=workdir,
                env={"PATH": str(bindir)},
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return (0, 1)
        run = CliRun(returncode=proc.returncode, stdout=proc.stdout, workdir=workdir)
        outcomes = task.check(run)
    return (sum(1 for ok in outcomes if ok), len(outcomes))


async def _benchmark_model(model: str) -> ModelReport:
    """Run all three suites against one loaded model."""
    results: list[TaskResult] = []
    async with httpx.AsyncClient() as http:
        for py_task in PYTHON_TASKS:
            content, elapsed, tokens = await _chat(http, model, PY_SYSTEM, py_task.prompt)
            passed, total = _run_python(content, py_task)
            results.append(
                TaskResult(suite="python", key=py_task.key, passed=passed, total=total, seconds=elapsed, tokens=tokens)
            )
            print(f"  python {py_task.key}: {passed}/{total} {elapsed:.1f}s")
        for cli_task in CLI_TASKS:
            content, elapsed, tokens = await _chat(http, model, CLI_SYSTEM, cli_task.goal)
            passed, total = _run_cli(content, cli_task)
            results.append(
                TaskResult(suite="cli", key=cli_task.key, passed=passed, total=total, seconds=elapsed, tokens=tokens)
            )
            print(f"  cli {cli_task.key}: {passed}/{total} {elapsed:.1f}s")
        for scenario in TOOL_SCENARIOS:
            made, elapsed, tokens = await _run_tool_scenario(http, model, scenario)
            ok = scenario.check(made)
            results.append(
                TaskResult(suite="tooling", key=scenario.key, passed=int(ok), total=1, seconds=elapsed, tokens=tokens)
            )
            print(f"  tooling {scenario.key}: {int(ok)}/1 {elapsed:.1f}s ({len(made)} calls)")
    return ModelReport(model=model, results=results)


# --- orchestration --------------------------------------------------------------------------


def _load_model(model: str) -> None:
    """Make `model` the single loaded model on the backend."""
    BACKEND.load(model)


def _installed_models(requested: list[str]) -> list[str]:
    """Filter `requested` to models the backend has installed; log (don't fail on) the rest."""
    installed = set(BACKEND.list_installed())
    if not installed:
        return requested
    models: list[str] = []
    for model in requested:
        if model in installed:
            models.append(model)
        else:
            print(f"!!! skip {model}: not installed (run `lms get {model}` to add it)")
    return models


def _markdown_table(reports: Sequence[ModelReport]) -> str:
    """Render the comparison as a Markdown table: per-suite scores, total, and timing.

    Timing matters because correctness often ties at a generous token budget — `time` (total
    wall-clock across all tasks) and `tok/s` (completion throughput) are then the real separators.
    """
    lines = [
        "| model | python | cli | tooling | total | time | tok/s |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        passed = sum(result.passed for result in report.results)
        total = sum(result.total for result in report.results)
        secs = sum(result.seconds for result in report.results)
        tokens = sum(result.tokens for result in report.results)
        rate = f"{tokens / secs:.0f}" if secs else "-"
        lines.append(
            f"| `{report.model}` | {report.suite_score('python')} | {report.suite_score('cli')} "
            f"| {report.suite_score('tooling')} | **{passed}/{total}** | {secs:.0f}s | {rate} |"
        )
    return "\n".join(lines)


def _check_oracle(reports: Sequence[ModelReport]) -> None:
    """If an oracle (`BENCH_CHAMPION`) is set and ran, assert it passed; a failure flags a suspect task."""
    if not CHAMPION:
        return
    champion = next((report for report in reports if report.model == CHAMPION), None)
    if champion is None:
        return  # the named oracle wasn't part of this run — nothing to check
    if champion.all_passed:
        print(f"\nOracle OK: {CHAMPION} passed every task.")
        return
    failed = [f"{result.suite}:{result.key}" for result in champion.results if result.passed != result.total]
    print(
        f"\n!!! SUSPECT TASK(S): oracle {CHAMPION} FAILED {failed}. The oracle is the should-pass "
        "bar — fix the task(s) before trusting the weaker-model columns; an oracle failure usually "
        "means the task is mis-specified, not the model."
    )


def _require_models() -> list[str]:
    """Return the model keys to benchmark from argv; exit with the installed list when none given."""
    requested = sys.argv[1:]
    if not requested:
        installed = BACKEND.list_installed()
        listing = "\n  ".join(installed) if installed else "(none found)"
        print(
            "usage: bench_general_models.py <model-key> [<model-key> ...]\n"
            "no model defaults — name the model(s) explicitly. Installed:\n  " + listing,
            file=sys.stderr,
        )
        sys.exit(2)
    return requested


async def main() -> None:
    """Benchmark the models named on the command line across the three suites, then print the table."""
    models = _installed_models(_require_models())
    if not models:
        print("none of the requested models are installed", file=sys.stderr)
        return
    reports: list[ModelReport] = []
    failures: list[str] = []
    for model in models:
        print(f">>> {model}")
        _load_model(model)
        try:
            report = await _benchmark_model(model)
        except Exception as exc:  # noqa: BLE001 — isolate one model's failure so the run continues
            print(f"!!! {model} FAILED ({type(exc).__name__}: {exc}); skipping to the next model")
            failures.append(model)
            continue
        reports.append(report)
        # Persist after each model so a later crash never loses completed results.
        with open(RESULTS, "a") as handle:
            handle.write(report.model_dump_json() + "\n")
    BACKEND.unload_all()

    if reports:
        print("\n" + _markdown_table(reports))
    _check_oracle(reports)
    if failures:
        print(f"\n{len(failures)} model(s) failed and were skipped: {', '.join(failures)}")


if __name__ == "__main__":
    asyncio.run(main())
