"""The decision one generate run takes about DHIS2 names the IG publisher's own build cannot survive.

A DHIS2 name carrying `<` reaches the published guide byte-true, and the IG publisher writes it
into pages it strict-parses after writing - so `make build` aborts in its last pass, once every
resource has already been rendered. The names are legitimate DHIS2 data: age bands read "5 to <
15 years, Female" and disaggregation cells read "Male, <15y".

There are two honest answers, and this module is where a run picks one:

- **refuse** - write nothing and name the object, so the name is changed in DHIS2 (or the
  selection narrowed) before an hour of build time is spent. This is what the emit-site gates in
  `service.py` do on their own.
- **substitute** - publish the wording `substitute_build_aborting_text` produces, leaving the
  DHIS2 instance untouched and every emitted identifier - codes, UIDs, and the ConceptMaps taking
  a published concept back to its DHIS2 object - exactly as it stands.

The gate applies the rewrite where DHIS2 metadata enters the emission inputs, so every target
downstream inherits it: the Questionnaire's question text, the concept displays of the data
dictionary, the category option combo vocabulary, the organisation unit registry, and the
narrative pages all read the same rewritten projection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.config import HostileNamePosture
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, generate_note
from dhis2w_fhir.resources.questionnaires.schemas import ProgramRuleIn, ProgramRuleVariableIn
from dhis2w_fhir.validation.substitution import substitute_build_aborting_text

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "SUBSTITUTED_NAME_FIELDS",
    "HostileNameConfirmation",
    "HostileNameGate",
    "HostileNameRewrite",
]

#: The projection fields a rewrite reads, which are the fields that reach a position the IG
#: publisher strict-parses: `name` becomes a resource title, a concept display, and a question's
#: label, and `form_name` becomes the question's label where DHIS2 states one. Every other string a
#: projection carries lands on a `description`, an extension `valueString`, or an identifier value -
#: none of which is a name, and the last of which is an identifier a consumer joins on.
SUBSTITUTED_NAME_FIELDS = frozenset({"name", "form_name"})

#: The projections a rewrite leaves alone. A program rule's name and a rule variable's name are
#: read by the rule condition beside them - a condition tests `#{variable}` by that very spelling -
#: so rewriting one would leave the published rule naming a variable the published condition does
#: not. Neither reaches a page position the publisher strict-parses: both land on an extension
#: `valueString`.
_UNREWRITTEN_PROJECTIONS: frozenset[type[BaseModel]] = frozenset({ProgramRuleIn, ProgramRuleVariableIn})


class HostileNameRewrite(BaseModel):
    """One DHIS2 name the publisher's build cannot survive, beside the wording published in its place."""

    model_config = ConfigDict(frozen=True)

    original: str
    """The DHIS2 name byte-true, so a reader can search the instance for it."""

    rewritten: str
    """What the guide publishes instead. The DHIS2 instance keeps the original."""


class HostileNameConfirmation(Protocol):
    """Asks whoever started the run whether the guide may publish rewritten names."""

    def __call__(self, rewrites: list[HostileNameRewrite]) -> bool:
        """Answer True to publish the rewrites, False to leave every name as DHIS2 states it."""
        ...


class _NameRewriter:
    """Walks one emission input, rewriting every DHIS2 name the publisher's build cannot survive.

    One walker per screening, holding the rewrites it made so the caller can count them, sample
    them for a prompt, and note them - which is why it is a walker with state rather than a
    function returning a pair.
    """

    def __init__(self) -> None:
        """Start a walk that has rewritten nothing yet."""
        self.rewrites: list[HostileNameRewrite] = []

    def rewrite[ModelT: BaseModel](self, model: ModelT) -> ModelT:
        """One projection with every build-aborting name in it rewritten, or the projection itself when clean."""
        if type(model) in _UNREWRITTEN_PROJECTIONS:
            return model
        updates: dict[str, Any] = {}
        for field_name in type(model).model_fields:
            value = getattr(model, field_name)
            if field_name in SUBSTITUTED_NAME_FIELDS and isinstance(value, str):
                replaced = self._rewritten_name(value)
                if replaced != value:
                    updates[field_name] = replaced
                continue
            nested = self._rewrite_value(value)
            if nested is not None:
                updates[field_name] = nested
        return model.model_copy(update=updates) if updates else model

    def _rewrite_value(self, value: object) -> object | None:
        """One field's value with every nested projection rewritten, or None when nothing under it changed."""
        if isinstance(value, BaseModel):
            rewritten = self.rewrite(value)
            return rewritten if rewritten is not value else None
        if isinstance(value, list):
            members = [self._rewrite_value(member) for member in value]
            if all(member is None for member in members):
                return None
            return [
                original if replaced is None else replaced for original, replaced in zip(value, members, strict=True)
            ]
        if isinstance(value, dict):
            entries = {key: self._rewrite_value(member) for key, member in value.items()}
            if all(member is None for member in entries.values()):
                return None
            return {key: value[key] if replaced is None else replaced for key, replaced in entries.items()}
        return None

    def _rewritten_name(self, name: str) -> str:
        """The wording published in one name's place, recorded as a rewrite when the two differ."""
        rewritten = substitute_build_aborting_text(name)
        if rewritten != name:
            self.rewrites.append(HostileNameRewrite(original=name, rewritten=rewritten))
        return rewritten


class HostileNameGate:
    """What one generate run does with the DHIS2 names the IG publisher's build cannot survive.

    The posture is the answer a flag or `fhir.toml` already gave; with none, the run asks through
    `confirmation` the first time it meets such a name, and the answer stands for the whole run -
    a full generate asks once, not once per target. With no confirmation to ask either, the names
    are left as DHIS2 states them, which is what the emit-site refusal then acts on.
    """

    def __init__(
        self, posture: HostileNamePosture | None = None, confirmation: HostileNameConfirmation | None = None
    ) -> None:
        """Build a gate from a preset posture, an asker for when there is none, or neither."""
        self._confirmation = confirmation
        self._substituting: bool | None = None if posture is None else posture is HostileNamePosture.SUBSTITUTE

    def decide(self, *groups: Sequence[BaseModel]) -> None:
        """Settle the run's answer up front, over every projection the run is about to emit.

        A full generate calls this once with everything it fetched, so the question a person is
        asked states the whole run's count rather than the first target's share of it.
        """
        rewriter = _NameRewriter()
        for group in groups:
            for model in group:
                rewriter.rewrite(model)
        if rewriter.rewrites:
            self._answer(rewriter.rewrites)

    def screen[ModelT: BaseModel](self, models: list[ModelT], notes: list[GenerateNote]) -> list[ModelT]:
        """The emission inputs this run publishes: rewritten under `substitute`, byte-true otherwise.

        Every rewrite lands as one note per distinct DHIS2 name, so the notes report says what the
        guide states that the instance does not, however many resources carry the name.
        """
        rewriter = _NameRewriter()
        rewritten = [rewriter.rewrite(model) for model in models]
        if not rewriter.rewrites or not self._answer(rewriter.rewrites):
            return models
        notes.extend(_rewrite_notes(rewriter.rewrites))
        return rewritten

    def _answer(self, rewrites: list[HostileNameRewrite]) -> bool:
        """Whether this run publishes rewritten names, asked once and then held for the whole run."""
        if self._substituting is None:
            self._substituting = False if self._confirmation is None else self._confirmation(rewrites)
        return self._substituting


def _rewrite_notes(rewrites: list[HostileNameRewrite]) -> list[GenerateNote]:
    """One note per distinct DHIS2 name rewritten, in the order the walk first reached each of them."""
    seen: dict[str, HostileNameRewrite] = {}
    for rewrite in rewrites:
        seen.setdefault(rewrite.original, rewrite)
    return [
        generate_note(
            GenerateNoteCategory.NAME_SUBSTITUTION,
            f"the DHIS2 name {rewrite.original!r} carries '<', which the IG publisher's build cannot survive; "
            f"the guide publishes {rewrite.rewritten!r} and DHIS2 keeps the name it holds",
        )
        for rewrite in seen.values()
    ]
