"""Questionnaire schemas: the target selection, the emitter projections, and the derived FSH names."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.attributes import AttributeValueIn
from dhis2w_fhir.names import (
    FHIR_ID_MAX_LENGTH,
    NamingSource,
    StemResolution,
    StemSubject,
    bounded_slug,
    join_id_tokens,
    join_name_segments,
    resolve_identity_stems,
)
from dhis2w_fhir.notes import GenerateNote
from dhis2w_fhir.r4 import DEFAULT_SUBJECT_RESOURCE_TYPE

if TYPE_CHECKING:
    from dhis2w_fhir.config import NamingConfig

#: The form kinds a Questionnaire is generated from, and the D2FormType code each carries.
FormKind = Literal["aggregate", "event", "tracker", "tracker-event"]

#: The DHIS2 object a form kind's questions are asked from, which decides the support CodeSystem
#: an item's `code` is drawn from: a data set, an event program, and a tracker program stage all
#: ask data elements, while a tracker registration form asks the program's tracked entity attributes.
QuestionSubject = Literal["data-element", "tracked-entity-attribute"]

#: The trailing token every organisation-unit assignment List id ends in, after the token and stem.
ASSIGNMENT_ID_SUFFIX = "org-units"


class FormKindProfile(BaseModel):
    """What one form kind contributes to its Questionnaire: identifier systems, subject type, and prose label.

    The identifier system is carried twice because the two emitters spell it differently and
    must never disagree: the FSH path writes the `$DHIS2-*` alias `foundation/d2-aliases.fsh`
    declares, and the JSON path writes the absolute URL that alias expands to,
    `{identifier_system_base}/id/{segment}`. A guard test renders the alias file and asserts
    every pair still resolves to the same system.

    `subject_type` is the resource type a form of this kind is answered about when the project
    says nothing else. It is the whole answer on the two organisation-unit kinds and the default
    on the two tracker kinds, where `[generate.tracked_entity_types]` maps a tracked entity type
    onto the resource type it really is; `form_subject_type` is where the two meet.
    """

    model_config = ConfigDict(frozen=True)

    identifier_system: str
    identifier_code_system: str
    identifier_segment: str
    code_identifier_segment: str
    subject_type: str
    label: str
    question_subject: QuestionSubject = "data-element"


#: The DHIS2 identifier systems, subject type, and prose label each form kind carries. An aggregate
#: or event form is reported for an organisation unit, while a tracker registration form enrols one
#: tracked entity and a tracker program stage captures that entity's visit, so the subject of both
#: tracker forms is whatever the program's tracked entity type is - a person unless the project
#: says otherwise. The registration form is the tracker program's own form, so it rides the
#: program's identifier systems - the very ones its stage forms carry as a grouping identifier.
FORM_KIND_PROFILES: dict[FormKind, FormKindProfile] = {
    "aggregate": FormKindProfile(
        identifier_system="$DHIS2-DS",
        identifier_code_system="$DHIS2-DS-CODE",
        identifier_segment="data-set",
        code_identifier_segment="data-set-code",
        subject_type="Location",
        label="data set",
    ),
    "event": FormKindProfile(
        identifier_system="$DHIS2-PROGRAM",
        identifier_code_system="$DHIS2-PROGRAM-CODE",
        identifier_segment="program",
        code_identifier_segment="program-code",
        subject_type="Location",
        label="event program",
    ),
    "tracker": FormKindProfile(
        identifier_system="$DHIS2-PROGRAM",
        identifier_code_system="$DHIS2-PROGRAM-CODE",
        identifier_segment="program",
        code_identifier_segment="program-code",
        subject_type=DEFAULT_SUBJECT_RESOURCE_TYPE,
        label="tracker program",
        question_subject="tracked-entity-attribute",
    ),
    "tracker-event": FormKindProfile(
        identifier_system="$DHIS2-PS",
        identifier_code_system="$DHIS2-PS-CODE",
        identifier_segment="program-stage",
        code_identifier_segment="program-stage-code",
        subject_type=DEFAULT_SUBJECT_RESOURCE_TYPE,
        label="tracker program stage",
    ),
}

#: The form kinds a capture server accepts a response for and the translator turns into a DHIS2
#: payload. Every generated kind is one: an aggregate response becomes a `/api/dataValueSets`
#: envelope, an event and a tracker-event response become one `/api/tracker` event each, and a
#: registration response becomes the `/api/tracker` tracked entity and enrollment it mints. The
#: tuple stays the single switch the capture surface keys off - serve's index, the conversion
#: gate, the `supportedProfile` declarations, `/metadata`, and the load set all read it.
CAPTURED_FORM_KINDS: tuple[FormKind, ...] = ("aggregate", "event", "tracker", "tracker-event")


class TargetSelection(BaseModel):
    """Which DHIS2 objects a data-definition target covers - one table per form kind.

    UIDs only: names are not unique in DHIS2. An empty (or absent) list means all, as it does
    for the terminology targets; a non-empty list filters. Three tables select the three form
    kinds: `[generate.data_sets]` picks data sets, `[generate.event_programs]` picks programs
    without registration, and `[generate.tracker_programs]` picks programs with registration.
    The whole-instance sweep routes each program to its table by its DHIS2 `programType`, so a
    program listed under the table its type does not belong to is refused by name.
    """

    include_ids: list[str] = Field(default_factory=list)


class SupportTerminologyProfile(BaseModel):
    """The fixed prose one data-dictionary support pair publishes under, shared by both emitters.

    The FSH target quotes these into `support-terminology.fsh.jinja` and the JSON target writes
    them onto the built `CodeSystem` and `ValueSet`, so the compiled guide and the served
    documents describe the same terminology in the same words.

    `value_type_property_description` is per-pair because the two pairs that declare a value type
    describe a different DHIS2 object; a pair whose concepts carry no value type never renders it.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    description: str
    code_property_description: str
    value_type_property_description: str = ""


#: The support pair over every data element the generated questionnaires ask a question from.
DATA_ELEMENT_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 data elements",
    description=(
        "DHIS2 data elements captured by the generated questionnaires. Concept codes are DHIS2 data element UIDs."
    ),
    code_property_description="DHIS2 data element code.",
    value_type_property_description="DHIS2 data element value type.",
)

#: The support pair over every tracked entity attribute the generated registration forms ask about.
TRACKED_ENTITY_ATTRIBUTE_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 tracked entity attributes",
    description=(
        "DHIS2 tracked entity attributes captured by the generated tracker registration forms. "
        "Concept codes are DHIS2 tracked entity attribute UIDs."
    ),
    code_property_description="DHIS2 tracked entity attribute code.",
    value_type_property_description="DHIS2 tracked entity attribute value type.",
)

#: The support pair over every category option combo the generated questionnaires disaggregate by.
CATEGORY_OPTION_COMBO_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 category option combos",
    description=(
        "DHIS2 category option combos the generated questionnaires disaggregate by. "
        "Concept codes are DHIS2 category option combo UIDs."
    ),
    code_property_description="DHIS2 category option combo code.",
)

#: The description of the `domain` concept property, which only the data-element pair declares.
DOMAIN_PROPERTY_DESCRIPTION = "DHIS2 data element domain type."

#: The description of the `unique` concept property, which only the attribute pair declares. A
#: unique tracked entity attribute is a business identifier - a national id, a case number - so a
#: consumer reading the vocabulary can tell which questions identify the person from which describe them.
UNIQUE_PROPERTY_DESCRIPTION = "Whether DHIS2 declares the tracked entity attribute unique."


class NumericBounds(BaseModel):
    """The inclusive range one DHIS2 numeric value type admits, either end open when DHIS2 leaves it open."""

    model_config = ConfigDict(frozen=True)

    minimum_value: int | None = None
    maximum_value: int | None = None


class CategoryOptionComboIn(BaseModel):
    """One category option combo of a data element's disaggregation."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None


class CategoryComboIn(BaseModel):
    """One DHIS2 category combo, its option combos included - a disaggregation or a data set's own key.

    A data element carries one to say how its question splits into cells; a data set carries one
    to say which attribute option combos its values are keyed under. `code` is the combo's DHIS2
    code, which the attribute-combo terminology resolves its identity stem from.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    is_default: bool = False
    option_combos: list[CategoryOptionComboIn] = Field(default_factory=list)


class QuestionnaireItemIn(BaseModel):
    """One data element or tracked entity attribute as a question: its value type, its option set, its disaggregation.

    `domain_type` is the DHIS2 `AGGREGATE` / `TRACKER` split a data element carries, emitted as a
    concept property on the data-element support CodeSystem. It is empty when the instance sent
    none, and a tracked entity attribute has no domain at all.

    `code` and `unique` are the tracked entity attribute's own facts: DHIS2 codes an attribute the
    way it codes every metadata object, and a unique attribute is a business identifier rather
    than a description. Both ride onto the attribute support CodeSystem as concept properties.

    `entity_level` is the fact about the *pair* - this attribute on this program's tracked entity
    type - that decides where DHIS2 imports the answer: True when the attribute is one of the
    type's own `trackedEntityTypeAttributes`, so its value belongs on the tracked entity, False
    when the program asks it and the type does not collect it, so its value belongs on the
    enrollment. None means the fetch could not say, and every consumer then reads the answer as
    entity-level, which is what a form published before the fact was fetched states.

    A DHIS2 form makes a question mandatory at two grains, and the projection carries both:
    `compulsory` marks the data element itself (a registration form's `mandatory` attribute lands
    here too), and `required_option_combo_uids` marks the single disaggregated cells a data set
    names through a compulsory operand.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    form_name: str | None = None
    value_type: str
    domain_type: str = ""
    option_set_uid: str | None = None
    compulsory: bool = False
    unique: bool = False
    entity_level: bool | None = None
    required_option_combo_uids: list[str] = Field(default_factory=list)
    category_combo: CategoryComboIn | None = None


class QuestionnaireSectionIn(BaseModel):
    """One section of a data-entry form, holding the data elements it groups."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    items: list[QuestionnaireItemIn] = Field(default_factory=list)


class ProgramContextIn(BaseModel):
    """The tracker program one stage belongs to.

    The identity its questionnaires carry in titles, identifiers, and intros. `code` is the
    program's DHIS2 code, which the stem plan resolves the program's directory segment from.
    `tracked_entity_type_uid` is what the program tracks, which is what decides the subject type
    of every stage form of the program - a stage captures a visit by the very entity the
    registration form enrolled, so the two forms state the same subject.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    tracked_entity_type_uid: str | None = None


class QuestionnaireSourceIn(BaseModel):
    """One DHIS2 data set, event program, or tracker program stage as the projection the emitter consumes.

    `sections` carries the form when it has them and `flat_items` carries the rest, so a
    sectioned form fills the first, an unsectioned form the second, and a form that mixes
    the two fills both (the service notes that). Both empty is a degenerate form with no
    data elements. `period_type` is the data set's DHIS2 reporting period type, which the
    example target resolves its periods from; a program form carries none. `description`
    is the DHIS2 free text, which the narrative pages carry into the form's intro.

    `program` is set exactly when `kind` is `tracker-event`: the source is then one program
    stage, so `uid`, `name`, `code`, and `description` are the stage's own and `program`
    names the tracker program the stage belongs to. A `tracker` source names no program because
    it *is* one: the registration form is the tracker program's own form, so `uid`, `name`, and
    `code` are the program's and its questions are the program's tracked entity attributes.

    `attribute_combo` is the data set's own category combo - the third key of every value it
    holds, beside the organisation unit and the period. Only an aggregate form carries one, and
    a non-default one is what makes the form publish an attribute-option-combo vocabulary and
    its responses name a combo out of it.

    `displays_incident_date` is the tracker program's `displayIncidentDate`, which says whether an
    enrollment states the date of the incident it tracks beside the date it began. Only a `tracker`
    source carries it, and it is what makes a registration response carry the incident-date extension.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    description: str | None = None
    kind: FormKind
    period_type: str | None = None
    program: ProgramContextIn | None = None
    attribute_combo: CategoryComboIn | None = None
    displays_incident_date: bool = False
    tracked_entity_type_uid: str | None = None
    """The DHIS2 tracked entity type a registration form enrols an entity as; None on every other kind.

    A stage form of the same program carries it on `program` instead, because a stage belongs to
    the program rather than being it; `form_tracked_entity_type_uid` reads whichever of the two
    a form holds.
    """

    sections: list[QuestionnaireSectionIn] = Field(default_factory=list)
    flat_items: list[QuestionnaireItemIn] = Field(default_factory=list)
    attribute_values: list[AttributeValueIn] = Field(default_factory=list)


class ReferencedObjects(BaseModel):
    """The DHIS2 objects one run's forms reference, gathered into the data dictionary both emitters publish.

    One entry per support pair: the data elements the questions are asked from, the tracked entity
    attributes the registration forms ask about, and the category option combos the aggregate
    forms disaggregate by. Each is keyed by UID and holds the first projection that named it, so
    a data element two data sets share becomes one concept rather than two.
    """

    data_elements: dict[str, QuestionnaireItemIn] = Field(default_factory=dict)
    tracked_entity_attributes: dict[str, QuestionnaireItemIn] = Field(default_factory=dict)
    option_combos: dict[str, CategoryOptionComboIn] = Field(default_factory=dict)


def source_program(source: QuestionnaireSourceIn) -> ProgramContextIn:
    """The tracker program one source belongs to: a registration form's own identity, else its stage's program."""
    if source.kind == "tracker":
        return ProgramContextIn(
            uid=source.uid,
            name=source.name,
            code=source.code,
            tracked_entity_type_uid=source.tracked_entity_type_uid,
        )
    if source.program is None:
        raise ValueError(
            f"tracker-event source {source.uid} carries no program context: a program stage is named, "
            "grouped, and filed under the tracker program it belongs to"
        )
    return source.program


def source_display_name(source: QuestionnaireSourceIn) -> str:
    """The name one form is shown under: a program stage carries both identities, everything else its own."""
    if source.program is None:
        return source.name
    return f"{source.program.name} - {source.name}"


def form_tracked_entity_type_uid(source: QuestionnaireSourceIn) -> str | None:
    """The DHIS2 tracked entity type one form is about: the registration form's own, else its program's."""
    if source.kind == "tracker":
        return source.tracked_entity_type_uid
    if source.kind == "tracker-event" and source.program is not None:
        return source.program.tracked_entity_type_uid
    return None


def form_subject_type(source: QuestionnaireSourceIn, tracked_entity_types: Mapping[str, str]) -> str:
    """The FHIR resource type one form's subject is, resolved once for every consumer of the form.

    A DHIS2 tracked entity type is whatever the project tracks - a person, a household, a
    building, a herd - so `[generate.tracked_entity_types]` maps the type's UID onto the R4
    resource type it really is and every form of every program tracking it follows. A type the
    project maps to nothing keeps the form kind's own subject: a `Patient` for the two tracker
    kinds, the reporting `Location` for the two organisation-unit kinds.

    The map is keyed by tracked entity type rather than by program because the type is what owns
    the nature of the thing: two programs tracking the same type agree by construction, and
    naming the type once is what makes a registration form and every stage form of that program
    state the same subject.
    """
    default = FORM_KIND_PROFILES[source.kind].subject_type
    uid = form_tracked_entity_type_uid(source)
    if uid is None:
        return default
    return tracked_entity_types.get(uid, default)


#: The surface label questionnaire-target stem notes and refusals name their offenders under.
QUESTIONNAIRE_STEM_SURFACE = "questionnaire target"

#: The surface label tracker-program stem notes and refusals name their offenders under.
TRACKER_PROGRAM_STEM_SURFACE = "tracker program"


class QuestionnaireStemPlan(BaseModel):
    """The resolved identity stems of one run's questionnaire surface.

    `targets` covers the forms themselves - each stem is the Questionnaire's resource id, its
    canonical URL segment, its file name, and (pascal-collapsed) its FSH name segment. `programs`
    covers the tracker programs the stage files nest under, whose stem is a directory name only.
    Every emitter that names a questionnaire artifact - the FSH target, the JSON documents, the
    examples, the pages - reads this one plan, so the two paths cannot disagree on an identity.
    """

    model_config = ConfigDict(frozen=True)

    targets: StemResolution
    programs: StemResolution

    @property
    def notes(self) -> list[GenerateNote]:
        """The notes resolution raised across both surfaces, targets first."""
        return [*self.targets.notes, *self.programs.notes]


def plan_questionnaire_stems(sources: list[QuestionnaireSourceIn], source: NamingSource) -> QuestionnaireStemPlan:
    """Resolve the questionnaire surface's identity stems once per run - the single source every emitter reads.

    The form targets and the tracker programs resolve as separate surfaces, each over its full
    subject list in one call so the collision scan sees every peer: a target stem is a resource
    id and must be unique among the run's Questionnaires - data sets, event programs, and
    tracker stages together - while a program stem only names the directory its stages are filed
    under. Both stems ride bare, so the budget is the R4 id limit itself - the same number
    validate states for these surfaces.
    """
    target_subjects = [StemSubject(uid=item.uid, code=item.code, label=source_display_name(item)) for item in sources]
    programs: dict[str, ProgramContextIn] = {}
    for item in sources:
        if item.kind == "tracker":
            programs.setdefault(item.uid, source_program(item))
        elif item.program is not None:
            programs.setdefault(item.program.uid, item.program)
    program_subjects = [
        StemSubject(uid=program.uid, code=program.code, label=program.name) for program in programs.values()
    ]
    return QuestionnaireStemPlan(
        targets=resolve_identity_stems(
            target_subjects, source, QUESTIONNAIRE_STEM_SURFACE, max_stem_length=FHIR_ID_MAX_LENGTH
        ),
        programs=resolve_identity_stems(
            program_subjects, source, TRACKER_PROGRAM_STEM_SURFACE, max_stem_length=FHIR_ID_MAX_LENGTH
        ),
    )


class QuestionnaireNaming(BaseModel):
    """Derived FSH names and ids for questionnaire artifacts under the configurable naming tokens.

    Holds the four tokens it needs rather than the whole `[generate.naming]` table, so the
    emitter stays a leaf of the config document instead of a dependency of it. The data-element
    and category-option-combo support terminology takes the registry's fixed `DE` / `COC`
    tokens under the same prefix. Option-set names are not here at all: they are decided by
    `option_set_identities` over the whole selection and read from the identity plan.
    """

    model_config = ConfigDict(frozen=True)

    prefix: str
    data_set: str
    program: str
    program_stage: str

    @classmethod
    def from_naming(cls, naming: NamingConfig) -> QuestionnaireNaming:
        """Project the `[generate.naming]` table onto the tokens questionnaire artifacts use."""
        return cls(
            prefix=naming.prefix,
            data_set=naming.data_set,
            program=naming.program,
            program_stage=naming.program_stage,
        )

    def source_token(self, kind: FormKind) -> str:
        """The naming token one form kind composes its name from (`DS`, `PR`, `PS`).

        A tracker registration form takes the program token, because the form it names *is* the
        program's own form - `D2PR_<program>` is the form of program X whichever kind of program
        X is, while `D2PS_<stage>` is one visit of a tracker program.
        """
        return {
            "aggregate": self.data_set,
            "event": self.program,
            "tracker": self.program,
            "tracker-event": self.program_stage,
        }[kind]

    def questionnaire_name(self, kind: FormKind, stem_segment: str) -> str:
        """Computational `Questionnaire.name` for one source (e.g. `D2DS_BfMAe6Itzgt`, `D2PS_A03MvHHogjR`).

        `stem_segment` is the FSH-name segment of the form's identity stem
        (`StemResolution.fsh_segment_for`): the DHIS2 id verbatim under `source = "id"`, the
        pascal-collapsed code where a code stem serves.
        """
        return join_name_segments(f"{self.prefix}{self.source_token(kind)}", stem_segment)

    def assignment_list_id(self, container_kind: str, stem: str, uid: str) -> str:
        """FHIR id of one form's assignment List (e.g. `d2-ds-BfMAe6Itzgt-org-units`).

        The List rides the stem of the object the assignment hangs on - the data set for an
        aggregate form, the program for an event form and for every stage of a tracker program -
        under that object's own naming token. An over-long code stem is truncated against the R4
        id limit and re-suffixed with the container UID, so the id stays legal and unique.
        """
        token = self.data_set if container_kind == "data-set" else self.program
        id_stem = join_id_tokens(self.prefix, token)
        slug = f"{stem}-{ASSIGNMENT_ID_SUFFIX}"
        budget = FHIR_ID_MAX_LENGTH - (len(id_stem) + 1 if id_stem else 0)
        if len(slug) > budget:
            slug = bounded_slug(slug, uid, budget)
        return f"{id_stem}-{slug}" if id_stem else slug

    @property
    def data_element_code_system(self) -> str:
        """FSH name of the data-element support CodeSystem (e.g. `D2DE_CS`)."""
        return f"{self.prefix}DE_CS"

    @property
    def data_element_code_system_id(self) -> str:
        """FHIR id of the data-element support CodeSystem (e.g. `d2-de-cs`)."""
        return join_id_tokens(self.prefix, "de", "cs")

    @property
    def data_element_value_set(self) -> str:
        """FSH name of the data-element support ValueSet (e.g. `D2DE_VS`)."""
        return f"{self.prefix}DE_VS"

    @property
    def data_element_value_set_id(self) -> str:
        """FHIR id of the data-element support ValueSet (e.g. `d2-de-vs`)."""
        return join_id_tokens(self.prefix, "de", "vs")

    @property
    def tracked_entity_attribute_code_system(self) -> str:
        """FSH name of the tracked-entity-attribute support CodeSystem (e.g. `D2TEA_CS`)."""
        return f"{self.prefix}TEA_CS"

    @property
    def tracked_entity_attribute_code_system_id(self) -> str:
        """FHIR id of the tracked-entity-attribute support CodeSystem (e.g. `d2-tea-cs`)."""
        return join_id_tokens(self.prefix, "tea", "cs")

    @property
    def tracked_entity_attribute_value_set(self) -> str:
        """FSH name of the tracked-entity-attribute support ValueSet (e.g. `D2TEA_VS`)."""
        return f"{self.prefix}TEA_VS"

    @property
    def tracked_entity_attribute_value_set_id(self) -> str:
        """FHIR id of the tracked-entity-attribute support ValueSet (e.g. `d2-tea-vs`)."""
        return join_id_tokens(self.prefix, "tea", "vs")

    @property
    def category_option_combo_code_system(self) -> str:
        """FSH name of the category-option-combo support CodeSystem (e.g. `D2COC_CS`)."""
        return f"{self.prefix}COC_CS"

    @property
    def category_option_combo_code_system_id(self) -> str:
        """FHIR id of the category-option-combo support CodeSystem (e.g. `d2-coc-cs`)."""
        return join_id_tokens(self.prefix, "coc", "cs")

    @property
    def category_option_combo_value_set(self) -> str:
        """FSH name of the category-option-combo support ValueSet (e.g. `D2COC_VS`)."""
        return f"{self.prefix}COC_VS"

    @property
    def category_option_combo_value_set_id(self) -> str:
        """FHIR id of the category-option-combo support ValueSet (e.g. `d2-coc-vs`)."""
        return join_id_tokens(self.prefix, "coc", "vs")
