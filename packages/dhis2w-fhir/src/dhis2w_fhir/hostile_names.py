"""The decision one generate run takes about the DHIS2 names and codes a guide cannot carry as they stand.

A DHIS2 name carrying `<` reaches the published guide byte-true, and the IG publisher writes it
into pages it strict-parses after writing - so `make build` aborts in its last pass, once every
resource has already been rendered. The names are legitimate DHIS2 data: age bands read "5 to <
15 years, Female" and disaggregation cells read "Male, <15y".

A DHIS2 code carrying a space is legal FHIR - an R4 `code` admits single internal spaces - and it
is still a liability everywhere the guide is consumed: the publisher's anchor slug strips
whitespace, so "Pre eclampsia" and "Preeclampsia" render one anchor id (BUGS.md #107), and a URL,
a CQL quotation, and a terminology server each handle the space at their own discretion.

There are two honest answers, and this module is where a run picks one:

- **refuse** - write nothing and name the object, so the name is changed in DHIS2 (or the
  selection narrowed) before an hour of build time is spent. This is what the emit-site gates in
  `service.py` do on their own. Codes are published byte-true under this answer: a space is legal,
  so nothing about it is refused.
- **substitute** - publish the wording `substitute_build_aborting_text` produces and the code
  `substituted_code` produces, leaving the DHIS2 instance untouched. No UID is touched, every
  rewritten concept carries its DHIS2 code as a `dhis2-code` property and its DHIS2 name as a
  `dhis2-name` property, and the ConceptMaps keep taking a published concept back to its DHIS2 UID.

The gate applies both rewrites where DHIS2 metadata enters the emission inputs, so every target
downstream inherits them: the Questionnaire's question text, the concept displays of the data
dictionary, the category option combo vocabulary, the organisation unit registry, the identifier
CodeSystems, the ConceptMaps, and the narrative pages all read the same rewritten projection.

A name rewrite reaches the object's translations too. A DHIS2 NAME or FORM_NAME translation becomes
the `_title`, `_name`, `_text`, or designation sitting beside the very element the rewrite already
changed, so publishing one of the two byte-true would leave one resource stating two different names
for one object - and the untouched half would still carry the character the rewrite exists to
remove. Both halves take the same wording, and the instance's own spelling stays recoverable through
`original_name`, which the emitters state as the `dhis2-name` property or extension.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.coded import CodedProjectionIn, carries_substitutable_code, substituted_code
from dhis2w_fhir.config import HostileNamePosture
from dhis2w_fhir.i18n import FORM_NAME_PROPERTY, NAME_PROPERTY, TranslationIn
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, generate_note
from dhis2w_fhir.resources.questionnaires.schemas import ProgramRuleIn, ProgramRuleVariableIn
from dhis2w_fhir.validation.substitution import first_control_character, substitute_build_aborting_text

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "SUBSTITUTED_CODE_FIELD",
    "SUBSTITUTED_NAME_FIELDS",
    "SUBSTITUTED_TRANSLATION_PROPERTIES",
    "HostileNameGate",
    "HostileRewrite",
    "HostileRewriteConfirmation",
    "HostileRewriteSubject",
]

#: The projection fields a name rewrite reads, which are the fields that reach a position the IG
#: publisher strict-parses: `name` becomes a resource title, a concept display, and a question's
#: label, and `form_name` becomes the question's label where DHIS2 states one. Every other string a
#: projection carries lands on a `description` or an extension `valueString` - neither of which is a
#: name.
SUBSTITUTED_NAME_FIELDS = frozenset({"name", "form_name"})

#: Where the byte-true DHIS2 spelling of each rewritten name field is kept, so the guide can state it
#: beside the wording it publishes. Only `CodedProjectionIn` carries these fields.
_ORIGINAL_NAME_FIELDS: dict[str, str] = {"name": "original_name", "form_name": "original_form_name"}

#: The DHIS2 translation properties a name rewrite reads. A translated NAME becomes the `_title`,
#: `_name`, or concept designation beside the very name the rewrite already changed, and a translated
#: FORM_NAME becomes a question's `_text` - so leaving them byte-true would publish one resource
#: stating two different names for one object, in two different languages, one of them carrying the
#: character the rewrite exists to remove. Every other translated property (DESCRIPTION, the date
#: labels) lands on a `description` or an extension `valueString`, which is not a name.
SUBSTITUTED_TRANSLATION_PROPERTIES = frozenset({NAME_PROPERTY, FORM_NAME_PROPERTY})

#: The `TranslationIn` field a name rewrite reads on the properties above.
_TRANSLATION_VALUE_FIELD = "value"

#: The projection field a code rewrite reads. Only `CodedProjectionIn` carries it, which is exactly
#: the set of projections whose code a published concept, identifier, or identity stem is built from.
SUBSTITUTED_CODE_FIELD = "code"

#: The projections a rewrite leaves alone. A program rule's name and a rule variable's name are
#: read by the rule condition beside them - a condition tests `#{variable}` by that very spelling -
#: so rewriting one would leave the published rule naming a variable the published condition does
#: not. Neither reaches a page position the publisher strict-parses: both land on an extension
#: `valueString`.
_UNREWRITTEN_PROJECTIONS: frozenset[type[BaseModel]] = frozenset({ProgramRuleIn, ProgramRuleVariableIn})

HostileRewriteSubject = Literal["name", "code"]
"""Which of a DHIS2 object's two published strings one rewrite is about."""


class HostileRewrite(BaseModel):
    """One DHIS2 name or code the guide cannot carry as it stands, beside what is published in its place."""

    model_config = ConfigDict(frozen=True)

    subject: HostileRewriteSubject = "name"
    """Whether this rewrite is about the object's name or about its code."""

    original: str
    """The DHIS2 string byte-true, so a reader can search the instance for it."""

    rewritten: str
    """What the guide publishes instead. The DHIS2 instance keeps the original."""


class HostileRewriteConfirmation(Protocol):
    """Asks whoever started the run whether the guide may publish rewritten names and codes."""

    def __call__(self, rewrites: list[HostileRewrite]) -> bool:
        """Answer True to publish the rewrites, False to leave every name and code as DHIS2 states it."""
        ...


class _CodeSubstituter:
    """The published code every space-carrying DHIS2 code of one run takes, assigned once and held.

    Assignment is deterministic and independent of the order the projections are walked in: every
    code the run has observed is registered first, then the space-carrying ones are assigned in
    sorted order, each taking its hyphenated form unless another code already holds it - in which
    case it takes an ordinal suffix (`Pre-eclampsia-2`) and the next free ordinal after that.
    """

    def __init__(self) -> None:
        """Start a run that has observed no code and assigned none."""
        self._unassigned: set[str] = set()
        self._published: dict[str, str] = {}
        self._taken: set[str] = set()

    def observe(self, model: BaseModel) -> None:
        """Register every code one projection carries, so a later assignment can de-collide against it."""
        if isinstance(model, CodedProjectionIn) and model.code is not None:
            self._register(model.code)
        for field_name in type(model).model_fields:
            self._observe_value(getattr(model, field_name))

    def published_for(self, code: str) -> str:
        """The code the guide publishes in one DHIS2 code's place, byte-true unless it carries a space."""
        if not carries_substitutable_code(code):
            return code
        self._register(code)
        if code not in self._published:
            self._assign()
        return self._published[code]

    def _register(self, code: str) -> None:
        """Hold one observed code: a space-free one is a target nothing may be rewritten onto."""
        if carries_substitutable_code(code):
            if code not in self._published:
                self._unassigned.add(code)
        else:
            self._taken.add(code)

    def _observe_value(self, value: object) -> None:
        """Walk one field's value for nested projections, whatever container it arrives in."""
        if isinstance(value, BaseModel):
            self.observe(value)
        elif isinstance(value, list):
            for member in value:
                self._observe_value(member)
        elif isinstance(value, dict):
            for member in value.values():
                self._observe_value(member)

    def _assign(self) -> None:
        """Assign every space-carrying code still waiting, in sorted order rather than encounter order."""
        for original in sorted(self._unassigned):
            self._published[original] = self._free(substituted_code(original))
        self._unassigned.clear()

    def _free(self, candidate: str) -> str:
        """The candidate itself when nothing holds it, else the first free ordinal after it."""
        chosen = candidate
        ordinal = 1
        while chosen in self._taken:
            ordinal += 1
            chosen = f"{candidate}-{ordinal}"
        self._taken.add(chosen)
        return chosen


class _ProjectionRewriter:
    """Walks one emission input, rewriting every DHIS2 name and code the guide cannot carry as it stands.

    One walker per screening, holding the rewrites it made so the caller can count them, sample
    them for a prompt, and note them - which is why it is a walker with state rather than a
    function returning a pair. The code substituter it rewrites through belongs to the run, not to
    the walk, so two screenings of one run can never publish one DHIS2 code two ways.
    """

    def __init__(self, codes: _CodeSubstituter) -> None:
        """Start a walk that has rewritten nothing yet, assigning codes through the run's substituter."""
        self.rewrites: list[HostileRewrite] = []
        self._codes = codes

    def rewrite[ModelT: BaseModel](self, model: ModelT) -> ModelT:
        """One projection with every rewritable name and code in it rewritten, or the projection itself when clean."""
        if type(model) in _UNREWRITTEN_PROJECTIONS:
            return model
        coded = isinstance(model, CodedProjectionIn)
        translates_a_name = isinstance(model, TranslationIn) and model.property in SUBSTITUTED_TRANSLATION_PROPERTIES
        updates: dict[str, Any] = {}
        for field_name in type(model).model_fields:
            value = getattr(model, field_name)
            if field_name in SUBSTITUTED_NAME_FIELDS and isinstance(value, str):
                replaced = self._rewritten_name(value)
                if replaced != value:
                    updates[field_name] = replaced
                    if coded:
                        updates[_ORIGINAL_NAME_FIELDS[field_name]] = value
                continue
            if field_name == _TRANSLATION_VALUE_FIELD and translates_a_name and isinstance(value, str):
                replaced = self._rewritten_name(value)
                if replaced != value:
                    updates[field_name] = replaced
                continue
            if field_name == SUBSTITUTED_CODE_FIELD and coded and isinstance(value, str):
                published = self._rewritten_code(value)
                if published != value:
                    updates[field_name] = published
                    updates["original_code"] = value
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
            self.rewrites.append(HostileRewrite(subject="name", original=name, rewritten=rewritten))
        return rewritten

    def _rewritten_code(self, code: str) -> str:
        """The code published in one DHIS2 code's place, recorded as a rewrite when the two differ."""
        published = self._codes.published_for(code)
        if published != code:
            self.rewrites.append(HostileRewrite(subject="code", original=code, rewritten=published))
        return published


class HostileNameGate:
    """What one generate run does with the DHIS2 names and codes a published guide cannot carry as they stand.

    The posture is the answer a flag or `fhir.toml` already gave; with none, the run asks through
    `confirmation` the first time it meets such a name or code, and the answer stands for the whole
    run - a full generate asks once, not once per target. With no confirmation to ask either,
    the names and codes are left as DHIS2 states them, which is what the emit-site refusal then
    acts on.
    """

    def __init__(
        self, posture: HostileNamePosture | None = None, confirmation: HostileRewriteConfirmation | None = None
    ) -> None:
        """Build a gate from a preset posture, an asker for when there is none, or neither."""
        self._confirmation = confirmation
        self._substituting: bool | None = None if posture is None else posture is HostileNamePosture.SUBSTITUTE
        self._codes = _CodeSubstituter()

    def decide(self, *groups: Sequence[BaseModel]) -> None:
        """Settle the run's answer up front, over every projection the run is about to emit.

        A full generate calls this once with everything it fetched, so the question a person is
        asked states the whole run's count rather than the first target's share of it, and so the
        code substitution de-collides against every code the run holds rather than the first
        target's share of them.
        """
        rewriter = _ProjectionRewriter(self._observed(*groups))
        for group in groups:
            for model in group:
                rewriter.rewrite(model)
        if rewriter.rewrites:
            self._answer(rewriter.rewrites)

    def screen[ModelT: BaseModel](self, models: list[ModelT], notes: list[GenerateNote]) -> list[ModelT]:
        """The emission inputs this run publishes: rewritten under `substitute`, byte-true otherwise.

        Every rewrite lands as one note per distinct DHIS2 string, so the notes report says what
        the guide states that the instance does not, however many resources carry it.
        """
        rewriter = _ProjectionRewriter(self._observed(models))
        rewritten = [rewriter.rewrite(model) for model in models]
        if not rewriter.rewrites or not self._answer(rewriter.rewrites):
            return models
        notes.extend(_rewrite_notes(rewriter.rewrites))
        return rewritten

    def _observed(self, *groups: Sequence[BaseModel]) -> _CodeSubstituter:
        """The run's substituter, with every code the given projections carry registered on it."""
        for group in groups:
            for model in group:
                self._codes.observe(model)
        return self._codes

    def _answer(self, rewrites: list[HostileRewrite]) -> bool:
        """Whether this run publishes rewritten names and codes, asked once and then held for the whole run."""
        if self._substituting is None:
            self._substituting = False if self._confirmation is None else self._confirmation(rewrites)
        return self._substituting


def _rewrite_notes(rewrites: list[HostileRewrite]) -> list[GenerateNote]:
    """One note per distinct DHIS2 string rewritten, in the order the walk first reached each of them."""
    seen: dict[tuple[str, str], HostileRewrite] = {}
    for rewrite in rewrites:
        seen.setdefault((rewrite.subject, rewrite.original), rewrite)
    return [_name_note(rewrite) if rewrite.subject == "name" else _code_note(rewrite) for rewrite in seen.values()]


def _name_note(rewrite: HostileRewrite) -> GenerateNote:
    """The note one rewritten DHIS2 name lands in the report as, saying which of the two rewrites it took."""
    carried = (
        "a control character the published guide cannot carry as it stands"
        if first_control_character(rewrite.original) is not None
        else "a comparison the IG publisher's pages cannot carry as it stands"
    )
    return generate_note(
        GenerateNoteCategory.NAME_SUBSTITUTION,
        f"the DHIS2 name {rewrite.original!r} carries {carried}; the guide publishes {rewrite.rewritten!r}, "
        f"states {rewrite.original!r} as a `dhis2-name` property, and DHIS2 keeps the name it holds",
    )


def _code_note(rewrite: HostileRewrite) -> GenerateNote:
    """The note one rewritten DHIS2 code lands in the report as."""
    return generate_note(
        GenerateNoteCategory.CODE_SUBSTITUTION,
        f"the DHIS2 code {rewrite.original!r} carries a space, which the IG publisher's anchors and every "
        f"URL downstream of them handle at their own discretion; the guide publishes {rewrite.rewritten!r} "
        "and states the DHIS2 code beside it as a `dhis2-code` concept property",
    )
