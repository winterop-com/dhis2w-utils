"""Option-set schemas: the emitter projections plus the `[generate.option_sets]` selection."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.attributes import AttributeValueIn
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.notes import GenerateNote


class OptionSetSelection(BaseModel):
    """Which DHIS2 option sets to generate - the `[generate.option_sets]` table of `fhir.toml`.

    UIDs only: names are not unique in DHIS2. An empty (or absent) list means all option sets.
    """

    include_ids: list[str] = Field(default_factory=list)


class OptionIn(BaseModel):
    """The option projection consumed by the emitter."""

    model_config = ConfigDict(frozen=True)

    uid: str
    code: str | None = None
    name: str
    sort_order: int | None = None
    translations: list[TranslationIn] = Field(default_factory=list)


class ConceptSourceIn(BaseModel):
    """A DHIS2 object whose ordered members become the concepts of one emitted CodeSystem.

    An option set and a category are the same shape - a named, coded, translated parent
    holding an ordered list of named, coded, translated members - so concept-code assignment
    is written once against this projection and every terminology emitter reads it.

    `source_label` and `member_label` are how a note names the source and one of its members,
    so a fall-back raised while assigning a category's codes reads `category` / `category option`
    rather than borrowing the option-set wording. Each concrete projection declares its own.
    """

    model_config = ConfigDict(frozen=True)

    source_label: ClassVar[str]
    member_label: ClassVar[str]

    uid: str
    code: str | None = None
    name: str
    description: str | None = None
    options: list[OptionIn] = Field(default_factory=list)
    translations: list[TranslationIn] = Field(default_factory=list)
    attribute_values: list[AttributeValueIn] = Field(default_factory=list)


class OptionSetIn(ConceptSourceIn):
    """The option-set projection consumed by the emitter, options included."""

    source_label: ClassVar[str] = "option set"
    member_label: ClassVar[str] = "option"


class ConceptAssignment(BaseModel):
    """One option's concept code, or no code at all when the set had none left to give it."""

    model_config = ConfigDict(frozen=True)

    option: OptionIn
    code: str | None = None
    from_dhis2_code: bool = False


class ConceptAssignmentPlan(BaseModel):
    """Every option of one set in emission order, its assigned concept code, and the notes assignment raised.

    The one place a concept code is decided: the terminology emitter writes its concepts from
    the plan and an example codes its answers from it, so an answer can only ever name a
    concept the emitted CodeSystem actually holds.
    """

    model_config = ConfigDict(frozen=True)

    assignments: list[ConceptAssignment] = Field(default_factory=list)
    notes: list[GenerateNote] = Field(default_factory=list)

    def code_for(self, option_uid: str) -> str | None:
        """The concept code one option received; None when it was skipped or belongs to another set."""
        return next((assignment.code for assignment in self.assignments if assignment.option.uid == option_uid), None)


class OptionSetIdentity(BaseModel):
    """One option set's emitted slug plus the FSH names and artifact ids derived from it.

    The narrative pages link an option set to its compiled `CodeSystem-<id>.html`, so the
    slug assignment - truncation, collision suffixes, and the id stem the naming tokens
    build - is computed once here and read by both the emitter and the pages. All three
    artifacts of one set - the CodeSystem, the ValueSet, and the ConceptMap taking their
    concept codes back to DHIS2 - take their id and their name from the same slug.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    slug: str
    fsh_name: str
    code_system_id: str
    value_set_id: str
    concept_map_id: str

    @property
    def code_system_name(self) -> str:
        """FSH name of the emitted CodeSystem (e.g. `D2OS_BirthType_CS`)."""
        return f"{self.fsh_name}_CS"

    @property
    def value_set_name(self) -> str:
        """FSH name of the emitted ValueSet (e.g. `D2OS_BirthType_VS`)."""
        return f"{self.fsh_name}_VS"

    @property
    def concept_map_name(self) -> str:
        """FSH name of the emitted ConceptMap (e.g. `D2OS_BirthType_CM`)."""
        return f"{self.fsh_name}_CM"


class OptionSetIdentityPlan(BaseModel):
    """Every option set's identity in emission order, with the notes the slug assignment raised.

    The plan is the boundary object every target reads option-set names from: the terminology
    emitter names its artifacts from it, the questionnaires bind `answerValueSet` to it, the
    examples code their answers from it, and the narrative pages link to it.
    """

    identities: list[OptionSetIdentity] = Field(default_factory=list)
    notes: list[GenerateNote] = Field(default_factory=list)


class OptionSetIdentityIndex(BaseModel):
    """One plan indexed by option-set UID, with a UID-derived entry for every bound set it omits.

    `unplanned_uids` names the option sets a question binds that the plan does not hold. The
    target closure puts every bound set into the selection, so the list is empty on a normal
    run and a target reports whatever lands in it rather than emitting a dangling name.
    """

    model_config = ConfigDict(frozen=True)

    identities: dict[str, OptionSetIdentity] = Field(default_factory=dict)
    unplanned_uids: list[str] = Field(default_factory=list)
