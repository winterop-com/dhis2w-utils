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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _model_backend import get_backend  # noqa: E402 — sibling import needs the path-prepend above

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
    """One tool call in an OpenAI chat response."""

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


class ToolTask(BaseModel):
    """A tooling task: a goal, the offered tool specs, and a checker over the emitted call."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: str
    goal: str
    tools: list[dict[str, object]]
    check: Callable[[ToolCall | None], bool]


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


# --- tooling suite --------------------------------------------------------------------------

#: Mock tool specs offered to the model in the tooling suite (OpenAI function-tool shape).
TOOLING_TOOLS: list[dict[str, object]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to a recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the web for information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


def _arg_contains(call: ToolCall | None, name: str, key: str, needle: str) -> bool:
    """True when `call` is to `name` and its `key` argument contains `needle` (case-insensitive)."""
    if call is None or call.name != name:
        return False
    value = call.arguments.get(key)
    return isinstance(value, str) and needle.lower() in value.lower()


TOOL_TASKS: tuple[ToolTask, ...] = (
    ToolTask(
        key="weather",
        goal="What is the weather in Paris right now?",
        tools=TOOLING_TOOLS,
        check=lambda call: _arg_contains(call, "get_weather", "city", "paris"),
    ),
    ToolTask(
        key="email",
        goal="Send an email to alice@example.com with the subject Meeting telling her it is at 3pm.",
        tools=TOOLING_TOOLS,
        check=lambda call: (
            _arg_contains(call, "send_email", "to", "alice@example.com")
            and _arg_contains(call, "send_email", "subject", "meeting")
        ),
    ),
    ToolTask(
        key="search",
        goal="Find recent articles about quantum computing.",
        tools=TOOLING_TOOLS,
        check=lambda call: _arg_contains(call, "search", "query", "quantum"),
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


async def _chat(http: httpx.AsyncClient, model: str, system: str, prompt: str) -> tuple[str, float, int]:
    """One plain chat completion. Returns (content, seconds, completion_tokens)."""
    started = time.monotonic()
    response = await http.post(
        LM,
        json={
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": MAX_TOKENS,
        },
        timeout=300.0,
    )
    elapsed = time.monotonic() - started
    parsed = _ChatResponse.model_validate(response.json())
    return (parsed.choices[0].message.content or "", elapsed, parsed.usage.completion_tokens)


async def _chat_tools(
    http: httpx.AsyncClient, model: str, goal: str, tools: list[dict[str, object]]
) -> tuple[ToolCall | None, float, int]:
    """One tool-calling chat completion. Returns (first tool call or None, seconds, tokens)."""
    started = time.monotonic()
    response = await http.post(
        LM,
        json={
            "model": model,
            "messages": [{"role": "system", "content": TOOL_SYSTEM}, {"role": "user", "content": goal}],
            "tools": tools,
            "temperature": 0.2,
        },
        timeout=300.0,
    )
    elapsed = time.monotonic() - started
    parsed = _ChatResponse.model_validate(response.json())
    tokens = parsed.usage.completion_tokens
    calls = parsed.choices[0].message.tool_calls
    if not calls:
        return (None, elapsed, tokens)
    raw = calls[0].function
    try:
        arguments = json.loads(raw.arguments or "{}")
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return (ToolCall(name=raw.name, arguments=arguments), elapsed, tokens)


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
        for tool_task in TOOL_TASKS:
            call, elapsed, tokens = await _chat_tools(http, model, tool_task.goal, tool_task.tools)
            ok = tool_task.check(call)
            results.append(
                TaskResult(suite="tooling", key=tool_task.key, passed=int(ok), total=1, seconds=elapsed, tokens=tokens)
            )
            print(f"  tooling {tool_task.key}: {int(ok)}/1 {elapsed:.1f}s")
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
    """Render the comparison as a Markdown table, one column per suite plus a total."""
    lines = ["| model | python | cli | tooling | total |", "| --- | --- | --- | --- | --- |"]
    for report in reports:
        passed = sum(result.passed for result in report.results)
        total = sum(result.total for result in report.results)
        lines.append(
            f"| `{report.model}` | {report.suite_score('python')} | {report.suite_score('cli')} "
            f"| {report.suite_score('tooling')} | **{passed}/{total}** |"
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
    for model in models:
        print(f">>> {model}")
        _load_model(model)
        reports.append(await _benchmark_model(model))
    BACKEND.unload_all()

    with open(RESULTS, "a") as handle:
        for report in reports:
            handle.write(report.model_dump_json() + "\n")
    print("\n" + _markdown_table(reports))
    _check_oracle(reports)


if __name__ == "__main__":
    asyncio.run(main())
