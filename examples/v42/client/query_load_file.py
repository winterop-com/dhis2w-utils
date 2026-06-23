"""Client: load a `.d2ql` program file and introspect it with dhis2w_ql (no server needed)."""

from __future__ import annotations

from pathlib import Path

from _runner import run_example
from dhis2w_ql import parse


async def main() -> None:
    """Load a committed d2ql program from disk and print its definitions and terminal stages."""
    path = Path("examples/d2ql/immunisation-library.d2ql")
    library = parse(path.read_text(encoding="utf-8"))

    print(f"loaded {path.name}: {len(library.definitions)} definition(s)")
    for definition in library.definitions:
        print(f"  define {definition.name}")
    if library.terminal is not None:
        print(f"  terminal source: {library.terminal.source.kind}")
        print(f"  terminal stages: {[stage.kind for stage in library.terminal.stages]}")


if __name__ == "__main__":
    run_example(main)
