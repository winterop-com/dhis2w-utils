"""Render the d2path documentation catalog into `docs/query/d2path-examples.md`.

Reads `dhis2w_ql.doc_examples.DOC_EXAMPLES`, groups the entries by category, and emits one markdown
section per entry: the expression in a ```d2path fence, its input as a ```json fence (when present),
and the evaluated result as a ```json fence. Every entry is validated by
`packages/dhis2w-ql/tests/test_doc_examples.py`, so the page never drifts from the implementation.

Usage:
    uv run python infra/scripts/gen_d2path_examples.py

Chained into `make docs-build` via the `docs-d2path` target, so the reference stays current.
"""

from __future__ import annotations

import json
from pathlib import Path

from dhis2w_ql.doc_examples import DOC_EXAMPLES, FunctionExample, doc_examples_by_category

_OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docs" / "query" / "d2path-examples.md"

# Canonical page order: broad language surfaces first, then operators and the literal/navigation
# surface last. Categories outside this list sort after it, alphabetically, for deterministic output.
_CATEGORY_ORDER: tuple[str, ...] = (
    "Filtering & projection",
    "Existence & logic",
    "Subsetting & set operations",
    "Strings",
    "Math & aggregates",
    "Conversion & temporal",
    "Operators",
    "Literals & navigation",
)


def _category_sort_key(category: str) -> tuple[int, str]:
    """Order known categories by `_CATEGORY_ORDER`, then any unknown category alphabetically."""
    return (_CATEGORY_ORDER.index(category), "") if category in _CATEGORY_ORDER else (len(_CATEGORY_ORDER), category)


def _heading(function_or_topic: str) -> str:
    """Render a group heading — `where()` for a registry function, the slug for a topic."""
    return function_or_topic if "-" in function_or_topic else f"`{function_or_topic}()`"


def _json_fence(value: object) -> list[str]:
    """Render a JSON value as a fenced ```json block."""
    return ["```json", json.dumps(value, indent=2, ensure_ascii=False), "```", ""]


def _render_example(example: FunctionExample) -> list[str]:
    """Render one catalog entry — description, expression fence, input fence, result fence."""
    lines: list[str] = [example.description, ""]
    lines.extend(["```d2path", example.expression, "```", ""])
    if example.input is not None:
        lines.append("Input:")
        lines.extend(_json_fence(example.input))
    if example.expected_kind == "nondeterministic":
        lines.append("Result (varies at runtime; shape shown):")
    else:
        lines.append("Result:")
    lines.extend(_json_fence(example.expected))
    return lines


def render() -> str:
    """Render the whole catalog to markdown with stable ordering."""
    sections: list[str] = [
        "# d2path examples",
        "",
        "A validated gallery of d2path expressions grouped by category. Every expression, its input, "
        "and its result are checked by the test suite (`packages/dhis2w-ql/tests/test_doc_examples.py`) "
        "and rendered from `dhis2w_ql.doc_examples.DOC_EXAMPLES` — do not edit by hand. Rebuild via "
        "`make docs-d2path` (chained into `make docs-build`).",
        "",
        f"**Total examples**: {len(DOC_EXAMPLES)}.",
        "",
    ]
    grouped = doc_examples_by_category()
    for category in sorted(grouped, key=_category_sort_key):
        examples = grouped[category]
        sections.extend([f"## {category}", ""])
        last_group: str | None = None
        for example in examples:
            if example.function_or_topic != last_group:
                sections.extend([f"### {_heading(example.function_or_topic)}", ""])
                last_group = example.function_or_topic
            sections.extend(_render_example(example))
    return "\n".join(sections).rstrip("\n") + "\n"


def main() -> None:
    """Write the rendered catalog to the docs tree."""
    _OUTPUT_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {_OUTPUT_PATH.relative_to(Path.cwd())} ({len(DOC_EXAMPLES)} examples)")


if __name__ == "__main__":
    main()
