"""Client: parse a d2ql program and evaluate a d2path expression locally (no server needed)."""

from __future__ import annotations

from _runner import run_example
from dhis2w_ql import Evaluator, parse, parse_expression


async def main() -> None:
    """Parse a d2ql pipeline and evaluate a d2path expression over a local document."""
    library = parse('dataElements | where domainType = "AGGREGATE" | select id, name as label | limit 5')
    assert library.terminal is not None
    print(f"stages: {[stage.kind for stage in library.terminal.stages]}")

    patient = {"name": [{"use": "official", "given": ["Ada", "Lovelace"], "family": "King"}]}
    family = Evaluator().evaluate(parse_expression('name.where(use = "official").family'), [patient])
    print(f"official family name: {family}")


if __name__ == "__main__":
    run_example(main)
