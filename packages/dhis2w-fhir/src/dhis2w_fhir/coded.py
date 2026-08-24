"""The DHIS2 code one projection carries, and what a substitute-posture run publishes in its place.

An R4 `code` admits single internal spaces, so `Pre eclampsia` reaches a guide as a legal concept
code. It is still a liability everywhere downstream: the IG publisher's anchor slug strips
whitespace, so `Pre eclampsia` and `Preeclampsia` render one anchor id (BUGS.md #107); a URL has to
escape it; CQL has to quote it; a terminology server round-trips it at its own discretion. A
production deployment would clean the code in DHIS2, so the substitute posture publishes it clean
without touching DHIS2: every space becomes a hyphen.

The projection keeps both spellings. `code` is what the guide publishes, `original_code` is what
DHIS2 holds, and `dhis2_code` is the one a caller joins back to DHIS2 on - so the rewrite never
reaches a DHIS2 write, an import payload, or a `dhis2-code` concept property.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "CODE_SUBSTITUTION_SEPARATOR",
    "DHIS2_CODE_PROPERTY",
    "DHIS2_ID_PROPERTY",
    "CodeSubstitutions",
    "CodedProjectionIn",
    "carries_substitutable_code",
    "code_substitutions",
    "substituted_code",
]

#: What a space in a published code becomes. A hyphen is valid in every FHIR `code`, `id`, and URL
#: segment, so one separator serves the concept code, the identity stem, and the anchor alike.
CODE_SUBSTITUTION_SEPARATOR = "-"

#: The concept property carrying the DHIS2 code byte-true, whatever code the guide published for it.
DHIS2_CODE_PROPERTY = "dhis2-code"

#: The concept property carrying the DHIS2 UID, written when the concept code is the DHIS2 code.
DHIS2_ID_PROPERTY = "dhis2-id"


class CodedProjectionIn(BaseModel):
    """A DHIS2 projection whose code a substitute-posture run may publish in rewritten form."""

    code: str | None = None
    """The code the guide publishes, which is the DHIS2 code unless this run rewrote it."""

    original_code: str | None = None
    """The DHIS2 code byte-true, set only when this run published a rewritten code above it."""

    @property
    def dhis2_code(self) -> str | None:
        """The code DHIS2 holds: the original when this run rewrote it, else the published code."""
        return self.original_code if self.original_code is not None else self.code


def carries_substitutable_code(value: str | None) -> bool:
    """Whether one code carries a space, which is what the substitute posture rewrites."""
    return value is not None and " " in value


def substituted_code(code: str) -> str:
    """One code with every space hyphenated, before any de-collision the run has to apply."""
    return code.replace(" ", CODE_SUBSTITUTION_SEPARATOR)


class CodeSubstitutions(BaseModel):
    """Every DHIS2 code one run published in rewritten form, keyed by the code it published.

    The identifier terminology enumerates its concepts off the ConceptMaps rather than off the
    projections, so it reads this to state each rewritten concept's DHIS2 code beside it.
    """

    model_config = ConfigDict(frozen=True)

    originals_by_published: dict[str, str] = Field(default_factory=dict)

    def original_for(self, published: str) -> str | None:
        """The DHIS2 code behind one published code, or None when the run published it byte-true."""
        return self.originals_by_published.get(published)


def code_substitutions(models: Iterable[BaseModel]) -> CodeSubstitutions:
    """Collect every code rewrite the given projections carry, sorted by the published code."""
    gathered: dict[str, str] = {}
    for model in models:
        _gather(model, gathered)
    return CodeSubstitutions(originals_by_published=dict(sorted(gathered.items())))


def _gather(model: BaseModel, gathered: dict[str, str]) -> None:
    """Record one projection's own rewrite, then walk everything nested under it."""
    if isinstance(model, CodedProjectionIn) and model.code is not None and model.original_code is not None:
        gathered.setdefault(model.code, model.original_code)
    for field_name in type(model).model_fields:
        _gather_value(getattr(model, field_name), gathered)


def _gather_value(value: object, gathered: dict[str, str]) -> None:
    """Walk one field's value for nested projections, whatever container it arrives in."""
    if isinstance(value, BaseModel):
        _gather(value, gathered)
    elif isinstance(value, list):
        for member in value:
            _gather_value(member, gathered)
    elif isinstance(value, dict):
        for member in value.values():
            _gather_value(member, gathered)
