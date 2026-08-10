"""Questionnaire schemas: the target selection, the emitter projections, and the derived FSH names."""

from __future__ import annotations

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

if TYPE_CHECKING:
    from dhis2w_fhir.config import NamingConfig

#: The form kinds a Questionnaire is generated from, and the D2FormType code each carries.
FormKind = Literal["aggregate", "event", "tracker-event"]

#: The trailing token every organisation-unit assignment List id ends in, after the token and stem.
ASSIGNMENT_ID_SUFFIX = "org-units"


class FormKindProfile(BaseModel):
    """What one form kind contributes to its Questionnaire: identifier systems, subject type, and prose label.

    The identifier system is carried twice because the two emitters spell it differently and
    must never disagree: the FSH path writes the `$DHIS2-*` alias `foundation/d2-aliases.fsh`
    declares, and the JSON path writes the absolute URL that alias expands to,
    `{identifier_system_base}/id/{segment}`. A guard test renders the alias file and asserts
    every pair still resolves to the same system.
    """

    model_config = ConfigDict(frozen=True)

    identifier_system: str
    identifier_code_system: str
    identifier_segment: str
    code_identifier_segment: str
    subject_type: str
    label: str


#: The DHIS2 identifier systems, subject type, and prose label each form kind carries. An aggregate
#: or event form is reported for an organisation unit, while a tracker program stage captures one
#: enrolled person's visit, so the subject of the stage form is the patient.
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
    "tracker-event": FormKindProfile(
        identifier_system="$DHIS2-PS",
        identifier_code_system="$DHIS2-PS-CODE",
        identifier_segment="program-stage",
        code_identifier_segment="program-stage-code",
        subject_type="Patient",
        label="tracker program stage",
    ),
}


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
    """

    model_config = ConfigDict(frozen=True)

    title: str
    description: str
    code_property_description: str


#: The support pair over every data element the generated questionnaires ask a question from.
DATA_ELEMENT_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 Data Elements",
    description=(
        "DHIS2 data elements captured by the generated questionnaires. Concept codes are DHIS2 data element UIDs."
    ),
    code_property_description="DHIS2 data element code.",
)

#: The support pair over every category option combo the generated questionnaires disaggregate by.
CATEGORY_OPTION_COMBO_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 Category Option Combos",
    description=(
        "DHIS2 category option combos the generated questionnaires disaggregate by. "
        "Concept codes are DHIS2 category option combo UIDs."
    ),
    code_property_description="DHIS2 category option combo code.",
)

#: The description of the `domain` concept property, which only the data-element pair declares.
DOMAIN_PROPERTY_DESCRIPTION = "DHIS2 data element domain type."


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
    """One data element as a question: its value type, its domain, its option set, and its disaggregation.

    `domain_type` is the DHIS2 `AGGREGATE` / `TRACKER` split, carried as a concept property on
    the data-element support CodeSystem. It is empty when the instance sent none.

    A DHIS2 form makes a question mandatory at two grains, and the projection carries both:
    `compulsory` marks the data element itself, and `required_option_combo_uids` marks the
    single disaggregated cells a data set names through a compulsory operand.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    form_name: str | None = None
    value_type: str
    domain_type: str = ""
    option_set_uid: str | None = None
    compulsory: bool = False
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
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None


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
    names the tracker program the stage belongs to.

    `attribute_combo` is the data set's own category combo - the third key of every value it
    holds, beside the organisation unit and the period. Only an aggregate form carries one, and
    a non-default one is what makes the form publish an attribute-option-combo vocabulary and
    its responses name a combo out of it.
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
    sections: list[QuestionnaireSectionIn] = Field(default_factory=list)
    flat_items: list[QuestionnaireItemIn] = Field(default_factory=list)
    attribute_values: list[AttributeValueIn] = Field(default_factory=list)


def source_program(source: QuestionnaireSourceIn) -> ProgramContextIn:
    """The program a tracker program stage belongs to, refusing a stage that arrived without one."""
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
        if item.program is not None:
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
        """The naming token one form kind composes its name from (`DS`, `PR`, `PS`)."""
        return {"aggregate": self.data_set, "event": self.program, "tracker-event": self.program_stage}[kind]

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
