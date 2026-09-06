"""The scaffold lines `fhir.toml` declares, and how a refresh lands them.

The guide's identity is stated once, in the `[ig]` table of `fhir.toml`, and five scaffold-managed
files carry it: `ig/sushi-config.yaml` states it to the IG publisher, `fhir.toml.example` shows it
back as the catalog's own `[ig]` table, `ig/input/pagecontent/index.md` puts the title on the front
page, `ig/ig.ini` names the ImplementationGuide file by the guide's id, and `pyproject.toml` carries
that id as the uv project's PEP 508 name. Those lines are the
scaffold's to write, so `d2w fhir init --refresh` substitutes the rendered line into each file and
keeps every other line exactly as the project wrote it - a release label, a home page, a copyright
year, a menu entry, a paragraph of prose or a second heading are all the project's. `d2w fhir
generate` reads the published file back and says so when `fhir.toml` and `ig/sushi-config.yaml`
state different identities, which is what a run against an unrefreshed project sees.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.scaffold import (
    CONFIG_EXAMPLE_RELATIVE_PATH,
    IG_INI_RELATIVE_PATH,
    INDEX_PAGE_RELATIVE_PATH,
    PYPROJECT_RELATIVE_PATH,
    SUSHI_CONFIG_RELATIVE_PATH,
)

__all__ = [
    "SushiConfigIdentityDisagreement",
    "adopt_scaffold_owned_lines",
    "sushi_config_identity_disagreements",
]

#: The DHIS2 identifier namespaces the `special-url` block declares, in the order sushi-config lists them.
_SPECIAL_URL_SUFFIXES = (
    "option",
    "option-code",
    "category-option",
    "category-option-code",
    "category-option-combo",
    "category-option-combo-code",
)


class _OwnedScalarLine(BaseModel):
    """One scalar sushi-config line fhir.toml declares: the identity it carries and the line's pattern."""

    model_config = ConfigDict(frozen=True)

    key: str
    pattern: str


class _ScaffoldOwnedLines(BaseModel):
    """The lines of one scaffold file that fhir.toml declares, and the region of the file holding them.

    `region_pattern` narrows the substitution to one part of the file, for a key spelled the same way
    in more than one place: `fhir.toml.example` carries a `name = ` line in its `[ig]` table and
    another in each `[[serve.basemaps]]` entry, and only the first is the guide's.
    """

    model_config = ConfigDict(frozen=True)

    patterns: tuple[str, ...]
    region_pattern: str | None = None


class _FileRegion(BaseModel):
    """The part of a file its owned lines live in, and where it sits in the whole text."""

    model_config = ConfigDict(frozen=True)

    text: str
    start: int
    end: int


#: Every single-line value of sushi-config that fhir.toml states, in the order the file writes them.
#:
#: `name` is matched at column 0 and the publisher's name at two spaces, so the two never take each
#: other's line, and a `menu:` entry - two spaces and a capitalised label - matches neither.
_SUSHI_CONFIG_SCALAR_LINES: tuple[_OwnedScalarLine, ...] = (
    _OwnedScalarLine(key="id", pattern=r"(?m)^id:(?P<value>.*)$"),
    _OwnedScalarLine(key="canonical", pattern=r"(?m)^canonical:(?P<value>.*)$"),
    _OwnedScalarLine(key="name", pattern=r"(?m)^name:(?P<value>.*)$"),
    _OwnedScalarLine(key="title", pattern=r"(?m)^title:(?P<value>.*)$"),
    _OwnedScalarLine(key="description", pattern=r"(?m)^description:(?P<value>.*)$"),
    _OwnedScalarLine(key="status", pattern=r"(?m)^status:(?P<value>.*)$"),
    _OwnedScalarLine(key="publisher", pattern=r"(?m)^  name:(?P<value>.*)$"),
)

#: The whole six-line `special-url` block, matched as one unit so a partial block is left alone.
_SPECIAL_URL_BLOCK_PATTERN = "(?m)" + "\n".join(
    rf"^    - (?P<stem_{index}>\S+)/id/{re.escape(suffix)}$" for index, suffix in enumerate(_SPECIAL_URL_SUFFIXES)
)

#: The `[ig]` table of fhir.toml.example, from its header to the next table header or the end of the file.
_CONFIG_EXAMPLE_IG_TABLE_PATTERN = r"(?ms)^\[ig\]$.*?(?=^\[|\Z)"

#: The `[project]` table of pyproject.toml, whose `name` is the guide's id as a PEP 508 project name.
_PYPROJECT_TABLE_PATTERN = r"(?ms)^\[project\]$.*?(?=^\[|\Z)"

#: What each scaffold-managed file owes to fhir.toml, keyed by the file's path in the project.
_OWNED_LINES_BY_FILE: dict[str, _ScaffoldOwnedLines] = {
    SUSHI_CONFIG_RELATIVE_PATH: _ScaffoldOwnedLines(
        patterns=tuple(line.pattern for line in _SUSHI_CONFIG_SCALAR_LINES) + (_SPECIAL_URL_BLOCK_PATTERN,)
    ),
    CONFIG_EXAMPLE_RELATIVE_PATH: _ScaffoldOwnedLines(
        patterns=(
            r"(?m)^id = .*$",
            r"(?m)^canonical = .*$",
            r"(?m)^name = .*$",
            r"(?m)^title = .*$",
            r"(?m)^publisher = .*$",
            r"(?m)^status = .*$",
        ),
        region_pattern=_CONFIG_EXAMPLE_IG_TABLE_PATTERN,
    ),
    # The front page's title is its first line, so a heading the project writes further down is
    # never mistaken for it.
    INDEX_PAGE_RELATIVE_PATH: _ScaffoldOwnedLines(patterns=(r"(?m)\A# .*$",)),
    IG_INI_RELATIVE_PATH: _ScaffoldOwnedLines(
        patterns=(r"(?m)^ig = fsh-generated/resources/ImplementationGuide-.*\.json$",)
    ),
    PYPROJECT_RELATIVE_PATH: _ScaffoldOwnedLines(
        patterns=(r"(?m)^name = .*$",), region_pattern=_PYPROJECT_TABLE_PATTERN
    ),
}


class SushiConfigIdentityDisagreement(BaseModel):
    """One identity `fhir.toml` states and `ig/sushi-config.yaml` does not carry."""

    model_config = ConfigDict(frozen=True)

    key: str
    configured: str
    published: str


def adopt_scaffold_owned_lines(relative_path: str, current: str, rendered: str) -> str:
    """Return `current` with every line the scaffold owns in this file replaced by the rendered one.

    A file the scaffold owns no line of comes back untouched, and so does one whose owned region -
    the `[ig]` table of `fhir.toml.example` - the project has taken out of the file altogether.
    """
    owned = _OWNED_LINES_BY_FILE.get(relative_path)
    if owned is None:
        return current
    current_region = _owned_region(current, owned)
    rendered_region = _owned_region(rendered, owned)
    if current_region is None or rendered_region is None:
        return current
    adopted_region = current_region.text
    for pattern in owned.patterns:
        rendered_match = re.search(pattern, rendered_region.text)
        if rendered_match is not None:
            adopted_region = _substitute_once(adopted_region, pattern, rendered_match.group(0))
    return current[: current_region.start] + adopted_region + current[current_region.end :]


def sushi_config_identity_disagreements(project: FhirProject) -> list[SushiConfigIdentityDisagreement]:
    """List the identities the project's fhir.toml states that its sushi-config does not carry.

    A line the file does not hold in the shape the scaffold writes is passed over rather than
    reported, so a hand-shaped sushi-config raises nothing; a project with no readable sushi-config
    at all raises nothing either.
    """
    published = _read_sushi_config(project)
    if published is None:
        return []
    ig = project.config.ig
    configured = {
        "id": ig.id,
        "canonical": ig.canonical,
        "name": ig.name,
        "title": ig.title,
        "description": f"{ig.title}, generated from DHIS2 metadata by d2w fhir.",
        "status": ig.status,
        "publisher": ig.publisher,
    }
    disagreements = [
        SushiConfigIdentityDisagreement(key=owned_line.key, configured=configured[owned_line.key], published=value)
        for owned_line, value in ((line, _published_value(published, line)) for line in _SUSHI_CONFIG_SCALAR_LINES)
        if value is not None and value != configured[owned_line.key]
    ]
    stem = re.search(_SPECIAL_URL_BLOCK_PATTERN, published)
    configured_stem = project.config.generate.identifier_system_base
    if stem is not None and stem.group("stem_0") != configured_stem:
        disagreements.append(
            SushiConfigIdentityDisagreement(
                key="identifier_system_base", configured=configured_stem, published=stem.group("stem_0")
            )
        )
    return disagreements


def _owned_region(text: str, owned: _ScaffoldOwnedLines) -> _FileRegion | None:
    """The part of `text` the owned lines live in - the whole file, unless the owner names a region."""
    if owned.region_pattern is None:
        return _FileRegion(text=text, start=0, end=len(text))
    match = re.search(owned.region_pattern, text)
    return _FileRegion(text=match.group(0), start=match.start(), end=match.end()) if match else None


def _substitute_once(text: str, pattern: str, replacement: str) -> str:
    """Replace the first match of `pattern` in `text` with `replacement`, taken as literal text."""
    return re.sub(pattern, lambda _match: replacement, text, count=1)


def _published_value(published: str, owned_line: _OwnedScalarLine) -> str | None:
    """The value sushi-config carries on one owned line, or None when the file holds no such line."""
    match = re.search(owned_line.pattern, published)
    return match.group("value").strip() if match else None


def _read_sushi_config(project: FhirProject) -> str | None:
    """Read the project's sushi-config, treating an absent or unreadable file as nothing to compare."""
    path = project.project_root / SUSHI_CONFIG_RELATIVE_PATH
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
