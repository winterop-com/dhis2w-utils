"""The `ig/sushi-config.yaml` lines `fhir.toml` declares, and how a refresh lands them.

The guide's identity is stated once, in the `[ig]` table of `fhir.toml`, and `ig/sushi-config.yaml`
carries it: `id`, `canonical`, `name`, `title`, the description built from the title, `status`, the
publisher name, and the six `special-url` lines the `[generate] identifier_system_base` stem
addresses. Those lines are the scaffold's to write, so `d2w fhir init --refresh` substitutes the
rendered line into the file on disk and keeps every other line exactly as the project wrote it -
`releaseLabel`, `version`, the publisher home page, `copyrightYear`, the parameters, the menu and
the path-resource globs are the project's. `d2w fhir generate` reads the same lines back and says so
when the two files state different identities, which is what a run against an unrefreshed project
sees.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.scaffold import SUSHI_CONFIG_RELATIVE_PATH

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


#: Every single-line value of sushi-config that fhir.toml states, in the order the file writes them.
#:
#: `name` is matched at column 0 and the publisher's name at two spaces, so the two never take each
#: other's line, and a `menu:` entry - two spaces and a capitalised label - matches neither.
_OWNED_SCALAR_LINES: tuple[_OwnedScalarLine, ...] = (
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


class SushiConfigIdentityDisagreement(BaseModel):
    """One identity `fhir.toml` states and `ig/sushi-config.yaml` does not carry."""

    model_config = ConfigDict(frozen=True)

    key: str
    configured: str
    published: str


def adopt_scaffold_owned_lines(current: str, rendered: str) -> str:
    """Return `current` with every scaffold-owned sushi-config line replaced by the rendered one."""
    adopted = current
    for pattern in [owned_line.pattern for owned_line in _OWNED_SCALAR_LINES] + [_SPECIAL_URL_BLOCK_PATTERN]:
        rendered_match = re.search(pattern, rendered)
        if rendered_match is not None:
            adopted = _substitute_once(adopted, pattern, rendered_match.group(0))
    return adopted


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
        for owned_line, value in ((line, _published_value(published, line)) for line in _OWNED_SCALAR_LINES)
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
