"""Every ```d2ql / ```d2path fence in the query docs must parse with the real parser.

Untagged or ```text fences are treated as prose/pseudo-code and skipped, so authors opt a snippet
into validation by tagging it. Parsing the committed `examples/d2ql/*.d2ql` programs is already
covered by `test_parse_conformance.test_committed_example_programs_parse`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_ql import parse, parse_expression

# Doc pages, relative to the repo root, whose fenced d2ql/d2path snippets are validated.
_DOC_PAGES = (
    "docs/query/index.md",
    "docs/query/cookbook.md",
    "docs/query/semantics.md",
    "docs/query/d2path-examples.md",
    "docs/guides/d2ql-tutorial.md",
    "docs/guides/d2ql.md",
    "docs/guides/d2path.md",
)


class _Fence:
    """A fenced code block extracted from a markdown page: its tag, source, and 1-based line."""

    def __init__(self, page: Path, tag: str, source: str, line: int) -> None:
        """Bind the originating page, info-string tag, block body, and opening-fence line number."""
        self.page = page
        self.tag = tag
        self.source = source
        self.line = line

    def __repr__(self) -> str:
        """Identify the fence by page and line for readable test ids."""
        return f"{self.page.name}:{self.line}:{self.tag}"


def _repo_root() -> Path:
    """Walk up from this file until the directory holding `mkdocs.yml` and `docs/`."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "mkdocs.yml").is_file() and (candidate / "docs").is_dir():
            return candidate
    raise RuntimeError("could not locate the repo root (no mkdocs.yml + docs/ ancestor)")


def _extract_fences(page: Path) -> list[_Fence]:
    """Extract every ```d2ql / ```d2path fenced block from a markdown page."""
    fences: list[_Fence] = []
    lines = page.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("```"):
            tag = stripped[3:].strip()
            start = index
            body: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            if tag in ("d2ql", "d2path"):
                fences.append(_Fence(page, tag, "\n".join(body), start + 1))
        index += 1
    return fences


def _all_fences() -> list[_Fence]:
    """Collect the validated fences across every configured query doc page that exists."""
    root = _repo_root()
    fences: list[_Fence] = []
    for relative in _DOC_PAGES:
        page = root / relative
        if page.is_file():
            fences.extend(_extract_fences(page))
    return fences


_FENCES = _all_fences()


def test_generated_page_contributes_fences() -> None:
    # Guards against the walker silently finding nothing: the generated page always carries d2path fences.
    assert any(fence.tag == "d2path" for fence in _FENCES), "expected d2path fences from the generated page"


@pytest.mark.parametrize("fence", _FENCES, ids=[repr(fence) for fence in _FENCES])
def test_doc_fence_parses(fence: _Fence) -> None:
    if fence.tag == "d2path":
        parse_expression(fence.source)
    else:
        parse(fence.source)
