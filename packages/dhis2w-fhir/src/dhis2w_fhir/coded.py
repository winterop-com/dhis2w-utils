"""The DHIS2 code and name one projection carries, and what a substitute-posture run publishes instead.

An R4 `code` admits single internal spaces, so `Pre eclampsia` reaches a guide as a legal concept
code. It is still a liability everywhere downstream: the IG publisher's anchor slug strips
whitespace, so `Pre eclampsia` and `Preeclampsia` render one anchor id (BUGS.md #107); a URL has to
escape it; CQL has to quote it; a terminology server round-trips it at its own discretion. A
production deployment would clean the code in DHIS2, so the substitute posture publishes it clean
without touching DHIS2: every space becomes a hyphen.

The projection keeps both spellings, of the code and of the name alike. `code` and `name` are what
the guide publishes; `original_code`, `original_name`, and `original_form_name` are what DHIS2
holds; `dhis2_code`, `dhis2_name`, and `dhis2_form_name` are the ones a caller joins back to DHIS2
on - so a rewrite never reaches a DHIS2 write, an import payload, or the `dhis2-code`/`dhis2-name`
properties that state the instance's own spelling beside the published one.

That pair is the whole recoverability contract of the substitute posture: whatever the guide
publishes, the DHIS2 spelling behind it is one property away, machine-readable, in the same
document. The translation extension is not that carrier - it publishes the same rewrite the primary
element does, because a resource whose `title` and whose `_title` disagreed would be stating two
different names for one object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.r4 import Extension

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "CODE_SUBSTITUTION_SEPARATOR",
    "DHIS2_CODE_PROPERTY",
    "DHIS2_ID_PROPERTY",
    "DHIS2_NAME_PROPERTY",
    "CodeSubstitutions",
    "CodedProjectionIn",
    "carries_substitutable_code",
    "code_substitutions",
    "original_spelling_extensions",
    "substituted_code",
]

#: What a space in a published code becomes. A hyphen is valid in every FHIR `code`, `id`, and URL
#: segment, so one separator serves the concept code, the identity stem, and the anchor alike.
CODE_SUBSTITUTION_SEPARATOR = "-"

#: The concept property carrying the DHIS2 code byte-true, whatever code the guide published for it.
DHIS2_CODE_PROPERTY = "dhis2-code"

#: The concept property carrying the DHIS2 UID, written when the concept code is the DHIS2 code.
DHIS2_ID_PROPERTY = "dhis2-id"

#: The concept property carrying the DHIS2 name byte-true, written when the guide published a
#: rewritten display above it. The twin of `dhis2-code`, for the same reason: a consumer that reads
#: a rewritten spelling needs the instance's own spelling to search the instance for.
DHIS2_NAME_PROPERTY = "dhis2-name"


class CodedProjectionIn(BaseModel):
    """A DHIS2 projection whose code or name a substitute-posture run may publish in rewritten form."""

    code: str | None = None
    """The code the guide publishes, which is the DHIS2 code unless this run rewrote it."""

    original_code: str | None = None
    """The DHIS2 code byte-true, set only when this run published a rewritten code above it."""

    original_name: str | None = None
    """The DHIS2 name byte-true, set only when this run published rewritten wording above it."""

    original_form_name: str | None = None
    """The DHIS2 form name byte-true, set only when this run published rewritten wording above it."""

    @property
    def dhis2_code(self) -> str | None:
        """The code DHIS2 holds: the original when this run rewrote it, else the published code."""
        return self.original_code if self.original_code is not None else self.code

    @property
    def dhis2_name(self) -> str | None:
        """The name DHIS2 holds, or None when this run published the name byte-true."""
        return self.original_name

    @property
    def dhis2_form_name(self) -> str | None:
        """The form name DHIS2 holds, or None when this run published the form name byte-true."""
        return self.original_form_name


def original_spelling_extensions(property_base: str, projection: CodedProjectionIn) -> list[Extension]:
    """The `dhis2-code`/`dhis2-name` extensions one resource carries when the run rewrote its code or name.

    A concept states its instance spellings as concept properties; a resource whose whole identity
    is one DHIS2 object states them as extensions on the same URLs those properties declare, so one
    reader learns the contract once. Empty when the run published both spellings byte-true, which is
    every run under the `refuse` posture and most objects under `substitute`.
    """
    stated = ((DHIS2_CODE_PROPERTY, projection.original_code), (DHIS2_NAME_PROPERTY, projection.original_name))
    return [Extension(url=f"{property_base}/{code}", valueString=value) for code, value in stated if value is not None]


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
