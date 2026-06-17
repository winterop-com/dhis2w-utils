"""Long-context comprehension benchmark — needle-in-a-haystack retrieval at increasing lengths.

Measures a model's EFFECTIVE context: how many tokens of filler it can hold while still retrieving one
planted fact. The model is loaded at `BENCH_CONTEXT` (default 128k); for each target length we fill a
haystack to ~that many tokens, plant the needle in the middle, ask for it, and score retrieval. A
model's advertised max context (e.g. 256k) is the *capability*; this measures what it can actually use.

There is no hardcoded roster — name the model(s) explicitly. Set `BENCH_CHAMPION=<key>` for the oracle
check. Prereqs: a running backend (LM Studio by default).

Usage:
    uv run python -m dhis2w_bench.longcontext google/gemma-4-26b-a4b-qat
    BENCH_CONTEXT=131072 uv run python -m dhis2w_bench.longcontext <model> ...
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx
from pydantic import BaseModel, ConfigDict

from dhis2w_bench.backend import get_backend

BACKEND = get_backend()
LM = BACKEND.chat_url
RESULTS = "/tmp/bench_longcontext_results.jsonl"


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


#: Context length to load each model at (env `BENCH_CONTEXT`). Must exceed the largest haystack.
CONTEXT = _env_int("BENCH_CONTEXT", 131072)
#: Optional oracle (env `BENCH_CHAMPION`): when present in a run, must retrieve at every length.
CHAMPION = os.environ.get("BENCH_CHAMPION", "").strip()
#: Approximate haystack sizes in tokens (~4 chars/token). Lengths beyond CONTEXT are skipped.
LENGTHS: tuple[int, ...] = (2000, 16000, 64000, 100000)

#: The planted fact and its retrieval question. The secret never appears in the filler.
_NEEDLE_TAG = "Zephyr-9"
_NEEDLE_SECRET = "QX-4821-VAULT"
_NEEDLE = f"IMPORTANT FACT: the access code for vault {_NEEDLE_TAG} is {_NEEDLE_SECRET}."
_QUESTION = f"Using only the log above, what is the access code for vault {_NEEDLE_TAG}? Answer with only the code."
_SYSTEM = "You answer strictly from the provided text. If a fact is stated in it, report it exactly."


def _haystack(target_tokens: int, depth: float) -> str:
    """Build ~`target_tokens` of filler log lines with the needle planted at fractional `depth`."""
    target_chars = target_tokens * 4
    lines: list[str] = []
    chars = 0
    index = 0
    while chars < target_chars:
        line = f"Log entry {index:07d}: routine status nominal, no action required.\n"
        lines.append(line)
        chars += len(line)
        index += 1
    lines.insert(int(len(lines) * depth), _NEEDLE + "\n")
    return "".join(lines)


class _Message(BaseModel):
    """The assistant message of a chat choice."""

    model_config = ConfigDict(extra="ignore")

    content: str | None = None


class _Choice(BaseModel):
    """One chat-completion choice."""

    model_config = ConfigDict(extra="ignore")

    message: _Message


class _ChatResponse(BaseModel):
    """The chat-completions response, narrowed to the field this harness reads."""

    model_config = ConfigDict(extra="ignore")

    choices: list[_Choice]


class LengthResult(BaseModel):
    """Retrieval outcome at one haystack length."""

    model_config = ConfigDict(frozen=True)

    tokens: int
    ok: bool
    seconds: float
    note: str = ""


class ModelReport(BaseModel):
    """A model's needle-retrieval results across the length sweep."""

    model_config = ConfigDict(frozen=True)

    model: str
    results: list[LengthResult]

    @property
    def effective_context(self) -> int:
        """The largest length the model still retrieved at (0 if it failed the smallest)."""
        passed = [result.tokens for result in self.results if result.ok]
        return max(passed) if passed else 0

    @property
    def all_passed(self) -> bool:
        """True when the model retrieved at every attempted length (the oracle bar)."""
        return bool(self.results) and all(result.ok for result in self.results)


async def _ask(http: httpx.AsyncClient, model: str, prompt: str) -> tuple[str, float, str]:
    """One retrieval query. Returns (answer, seconds, note) — note flags a context overflow."""
    started = time.monotonic()
    try:
        response = await http.post(
            LM,
            json={
                "model": model,
                "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 64,
            },
            timeout=600.0,
        )
    except httpx.HTTPError as exc:
        return ("", time.monotonic() - started, f"request error: {type(exc).__name__}")
    elapsed = time.monotonic() - started
    if response.status_code != 200:
        body = response.text.lower()
        note = "context overflow" if "context" in body else f"http {response.status_code}"
        return ("", elapsed, note)
    parsed = _ChatResponse.model_validate(response.json())
    return (parsed.choices[0].message.content or "", elapsed, "")


async def _benchmark_model(http: httpx.AsyncClient, model: str) -> ModelReport:
    """Run the length sweep (needle at mid-depth) against one loaded model."""
    results: list[LengthResult] = []
    for tokens in LENGTHS:
        if tokens > CONTEXT - 2000:
            results.append(LengthResult(tokens=tokens, ok=False, seconds=0.0, note="exceeds load context"))
            print(f"  {tokens // 1000}k: SKIP (exceeds {CONTEXT // 1000}k load context)")
            continue
        prompt = _haystack(tokens, depth=0.5) + "\n\n" + _QUESTION
        answer, seconds, note = await _ask(http, model, prompt)
        ok = _NEEDLE_SECRET.lower() in answer.lower()
        results.append(LengthResult(tokens=tokens, ok=ok, seconds=seconds, note=note))
        print(f"  {tokens // 1000}k: {'PASS' if ok else 'FAIL'} {seconds:.1f}s{(' — ' + note) if note else ''}")
    return ModelReport(model=model, results=results)


def _markdown_table(reports: list[ModelReport]) -> str:
    """Render a model x length retrieval table plus each model's effective context."""
    header = "| model | " + " | ".join(f"{t // 1000}k" for t in LENGTHS) + " | effective |"
    divider = "| --- | " + " | ".join("---" for _ in LENGTHS) + " | --- |"
    lines = [header, divider]
    for report in reports:
        by_tokens = {result.tokens: result for result in report.results}
        cells = ["PASS" if by_tokens[t].ok else "FAIL" for t in LENGTHS]
        lines.append(f"| `{report.model}` | " + " | ".join(cells) + f" | {report.effective_context // 1000}k |")
    return "\n".join(lines)


def _check_oracle(reports: list[ModelReport]) -> None:
    """If an oracle (`BENCH_CHAMPION`) ran, it should retrieve at every length; warn loudly if not."""
    if not CHAMPION:
        return
    champion = next((report for report in reports if report.model == CHAMPION), None)
    if champion is None:
        return
    if champion.all_passed:
        print(f"\nOracle OK: {CHAMPION} retrieved at every length.")
    else:
        failed = [f"{result.tokens // 1000}k" for result in champion.results if not result.ok]
        print(f"\n!!! Oracle {CHAMPION} failed retrieval at {failed} — effective context below the sweep top.")


def _require_models() -> list[str]:
    """Return model keys from argv; exit with the installed list when none given."""
    requested = sys.argv[1:]
    if not requested:
        installed = "\n  ".join(BACKEND.list_installed()) or "(none found)"
        print("usage: python -m dhis2w_bench.longcontext <model-key> ...\ninstalled:\n  " + installed, file=sys.stderr)
        sys.exit(2)
    return requested


async def main() -> None:
    """Load each model at BENCH_CONTEXT, run the needle-in-a-haystack length sweep, print the table."""
    models = _require_models()
    installed = set(BACKEND.list_installed())
    models = [m for m in models if not installed or m in installed]
    if not models:
        print("none of the requested models are installed", file=sys.stderr)
        return
    reports: list[ModelReport] = []
    async with httpx.AsyncClient() as http:
        for model in models:
            print(f">>> {model} (loaded at {CONTEXT // 1024}K context)")
            BACKEND.load(model, CONTEXT)
            reports.append(await _benchmark_model(http, model))
    BACKEND.unload_all()
    with open(RESULTS, "a") as handle:
        for report in reports:
            handle.write(report.model_dump_json() + "\n")
    print("\n" + _markdown_table(reports))
    _check_oracle(reports)


if __name__ == "__main__":
    asyncio.run(main())
