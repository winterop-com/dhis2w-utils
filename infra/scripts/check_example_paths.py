"""Guard: the example tree stays version-neutral, and every example points at a path that exists.

Examples live at `examples/{cli,client,mcp}/` in one copy, with `examples/fhir/`
beside them and `examples/{surface}/v{N}/` holding only what one DHIS2 major has
and the others do not. Two ways that erodes, both caught here:

- A file resurrects the old per-version tree by naming `examples/v41|v42|v43/...`
  in a docstring, a usage line, or a link. Those paths do not exist.
- A file points at a sibling example that is not there — a rename that updated the
  file but not the three places naming it.

Run via `make check-examples` alongside the CLI / MCP reference check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples"
SUFFIXES = {".py", ".sh", ".md"}

_VERSION_TREE = re.compile(r"examples/v(?:4[123]|\{)")
_EXAMPLE_PATH = re.compile(r"examples/(?:cli|client|mcp|fhir)/[\w./-]*\.(?:py|sh)")


def _sources() -> list[Path]:
    """Every example source the guard reads, sorted by path."""
    return sorted(p for p in EXAMPLES.rglob("*") if p.suffix in SUFFIXES and "__pycache__" not in p.parts)


def main() -> int:
    """Report every resurrected version-tree path and every dangling example reference."""
    problems: list[str] = []
    for path in _sources():
        relative = path.relative_to(REPO_ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _VERSION_TREE.search(line):
                problems.append(f"{relative}:{number}: names the removed per-version tree — `{line.strip()}`")
            for reference in _EXAMPLE_PATH.findall(line):
                if not (REPO_ROOT / reference).exists():
                    problems.append(f"{relative}:{number}: points at `{reference}`, which does not exist")
    if problems:
        print("Example paths that do not resolve:")
        for line in problems:
            print(f"  - {line}")
        return 1
    print(f"example paths resolve: {len(_sources())} files checked, no per-version tree references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
