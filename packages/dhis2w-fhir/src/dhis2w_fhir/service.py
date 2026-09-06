"""Service layer for the `fhir` plugin - project scaffolding and FSH generation (CLI + MCP share it)."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx
from dhis2w_client.errors import AuthenticationError, Dhis2ApiError

# The v41 generated OAS tree carries no import-summary, import-conflict, or import-count module, so
# the import-report shapes come from v42 on every major - they are the wire shape all three answer with.
from dhis2w_client.generated.v42.oas import (
    DataValueSet,
    ImportConflict,
    ImportSummary,
    TrackerEvent,
    TrackerImportError,
    TrackerImportReport,
)
from dhis2w_client.v42.aggregate import CompleteDataSetRegistration, CompleteDataSetRegistrations
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile, resolve
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
from dhis2w_fhir.config import (
    CorrectionPosture,
    FhirProject,
    GenerateConfig,
    HostileNamePosture,
    NoFhirProjectError,
    OverwritePosture,
    WithdrawalPosture,
    load_project,
)
from dhis2w_fhir.conversion.artifacts import (
    BoundQuestionUids,
    CompiledArtifacts,
    CompiledIgMissingError,
    ProgramRuleNames,
    SourcedDocument,
    bound_question_uids,
    build_project_context,
    collect_artifacts,
    load_compiled_artifacts,
    program_rule_names,
)
from dhis2w_fhir.conversion.payloads import receipt_event_uid
from dhis2w_fhir.conversion.schemas import (
    FORWARD_TARGET_ORDER,
    CodedAnswerMode,
    ConversionNaming,
    ConversionNote,
    ConversionRefusal,
    ConversionRefusalCategory,
    ConversionReport,
    ConversionResult,
    ConversionTargetKind,
)
from dhis2w_fhir.conversion.translator import translate_responses
from dhis2w_fhir.foundation import build_foundation_artifacts
from dhis2w_fhir.grouping import ReportedForm, group_data_values
from dhis2w_fhir.hostile_names import HostileNameGate
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.names import StemResolution, StemSubject, code_or_uid
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, aggregate_generate_note, generate_note, pluralize
from dhis2w_fhir.overwrite import (
    AggregateCell,
    ForwardedCellIndex,
    ForwardedSubmission,
    ForwardOverwrite,
    OverwrittenValue,
    aggregate_cells,
    build_forwarded_cell_index,
)
from dhis2w_fhir.period import parse_period, recent_periods
from dhis2w_fhir.r4 import QuestionnaireResponse
from dhis2w_fhir.resources.administrative_gender import (
    administrative_gender_map_file_prefix,
    build_administrative_gender_concept_map_artifacts,
)
from dhis2w_fhir.resources.attribute_combos import (
    ATTRIBUTE_COMBO_DIRECTORY,
    attribute_combo_concept_map_file_prefix,
    build_attribute_combo_artifacts,
    build_attribute_combo_concept_map_artifacts,
    build_attribute_combo_identifier_artifacts,
)
from dhis2w_fhir.resources.categories import (
    CATEGORY_DIRECTORY,
    build_category_artifacts,
    build_category_concept_map_artifacts,
    build_category_identifier_artifacts,
    category_concept_map_file_prefix,
)
from dhis2w_fhir.resources.categories.decomposition import build_category_decomposition
from dhis2w_fhir.resources.categories.schemas import CategoryIn, CategorySelection, is_default_category
from dhis2w_fhir.resources.examples import (
    COMPLETED_STATUS,
    EXAMPLES_DIRECTORY,
    build_example_artifacts,
    build_synthetic_responses,
    response_status_code,
)
from dhis2w_fhir.resources.examples.documents import build_example_documents
from dhis2w_fhir.resources.examples.schemas import (
    ExampleAnswerIn,
    ExampleResponseIn,
    ExampleSelection,
    SyntheticPlacement,
)
from dhis2w_fhir.resources.ips_sections import (
    build_section_concept_map_artifacts,
    section_map_file_prefix,
)
from dhis2w_fhir.resources.option_sets import (
    CONCEPT_MAP_DIRECTORY,
    TERMINOLOGY_DIRECTORY,
    build_option_set_artifacts,
    build_option_set_concept_map_artifacts,
    build_option_set_identifier_artifacts,
    option_set_concept_map_file_prefix,
    option_set_identities,
)
from dhis2w_fhir.resources.option_sets.schemas import (
    ConceptSourceIn,
    OptionIn,
    OptionSetIdentityPlan,
    OptionSetIn,
    OptionSetSelection,
)
from dhis2w_fhir.resources.organisation_units import (
    REGISTRY_DIRECTORY,
    build_organisation_unit_instances,
    build_organisation_unit_level_terminology,
    build_organisation_unit_profiles,
    build_organisation_unit_terminology,
    build_registry_examples,
    organisation_unit_stem_subjects,
    plan_organisation_unit_stems,
)
from dhis2w_fhir.resources.organisation_units.schemas import (
    GeoPoint,
    OrganisationUnitIn,
    OrganisationUnitLevelIn,
    OrganisationUnitLevelNames,
)
from dhis2w_fhir.resources.pages import (
    INTRO_SUFFIX,
    PAGES_BASE_SUBDIRECTORY,
    PAGES_DIRECTORY,
    build_page_artifacts,
)
from dhis2w_fhir.resources.pages.schemas import PagesIn
from dhis2w_fhir.resources.questionnaires import (
    QUESTIONNAIRE_DIRECTORIES,
    build_questionnaire_artifacts,
    link_id_collisions,
)
from dhis2w_fhir.resources.questionnaires.assignments import (
    ASSIGNMENT_DIRECTORY,
    AssignmentIndex,
    assignment_container_uid,
    build_assignment_artifacts,
)
from dhis2w_fhir.resources.questionnaires.documents import build_questionnaire_documents
from dhis2w_fhir.resources.questionnaires.schemas import (
    FORM_KIND_PROFILES,
    CategoryAxisIn,
    CategoryComboIn,
    CategoryOptionComboIn,
    FormKind,
    ProgramContextIn,
    ProgramRuleActionIn,
    ProgramRuleIn,
    ProgramRuleVariableIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
    QuestionnaireStemPlan,
    ordered_option_combos,
    plan_questionnaire_stems,
)
from dhis2w_fhir.scaffold import SUSHI_CONFIG_RELATIVE_PATH, build_scaffold_files
from dhis2w_fhir.scaffold.identity import sushi_config_identity_disagreements
from dhis2w_fhir.scaffold.project_templates import ProjectTemplate
from dhis2w_fhir.scaffold.schemas import InitOptions, ScaffoldReport
from dhis2w_fhir.spool import (
    IMPORT_REPORT_SUFFIX,
    ForwardRefusalRecord,
    QuarantinedFile,
    RefusalReason,
    SpooledReceipt,
    SpooledResponse,
    SpoolLayout,
    SpoolReadError,
    SpoolState,
    drain_lock,
    move_to_forwarded,
    move_to_received,
    move_to_rejected,
    move_to_withdrawn,
    read_import_reports,
    read_receipt,
    read_received_responses,
    read_refusal_record,
    read_spooled_receipts,
    record_refusal,
    sweep_orphan_temporary_files,
    write_import_report,
)
from dhis2w_fhir.validation import build_aborting_code, build_aborting_name, build_code_validation
from dhis2w_fhir.validation.schemas import (
    FhirValidationReport,
    MetadataCollectionIn,
    MetadataItemIn,
    ValidationScope,
)
from dhis2w_fhir.writer import (
    FshArtifact,
    JsonArtifact,
    JsonBuild,
    SyncReport,
    clean_generated_files,
    sync_artifacts,
    sync_json_artifacts,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from dhis2w_client import Dhis2Client
    from dhis2w_client.generated.v42.schemas import (
        Attribute,
        Category,
        DataElement,
        DataSet,
        DataSetElement,
        OptionSet,
        OrganisationUnit,
        OrganisationUnitLevel,
        Program,
        ProgramRule,
        TrackedEntityAttribute,
        TrackedEntityType,
    )
    from dhis2w_core.progress import ProgressReporter

_STREAM_PAGE_SIZE = 500
_TRANSLATION_FIELDS = "translations[locale,property,value]"

#: The attribute-value projection every metadata fetch carries: DHIS2 sends the attribute's UID
#: and the value alone, and the attribute's code is joined from `AttributeCodeIndex` at emit time.
_ATTRIBUTE_VALUE_FIELDS = "attributeValues[attribute[id],value]"

_OPTION_SET_FIELDS = (
    f"id,code,name,description,{_TRANSLATION_FIELDS},{_ATTRIBUTE_VALUE_FIELDS},"
    f"options[id,code,name,sortOrder,{_TRANSLATION_FIELDS}]"
)

#: The option-set projection the identity plan is assigned from - a slug needs the UID and the name alone.
_OPTION_SET_IDENTITY_FIELDS = "id,name"

#: The category projection the terminology target emits from. `categoryOptions` is a DHIS2 list
#: rather than a set, so the order the instance answers with is the category's own sort order.
_CATEGORY_FIELDS = (
    f"id,code,name,description,{_TRANSLATION_FIELDS},{_ATTRIBUTE_VALUE_FIELDS},"
    f"categoryOptions[id,code,name,{_TRANSLATION_FIELDS}]"
)
_ORGANISATION_UNIT_FIELDS = (
    "id,code,name,shortName,description,level,path,parent[id],geometry,contactPerson,email,phoneNumber,openingDate,"
    f"closedDate,{_TRANSLATION_FIELDS},{_ATTRIBUTE_VALUE_FIELDS}"
)
#: What the instance's own level table has to state for the level concepts to carry its names: the
#: depth, the name it gives that depth, and the translations of that name.
_ORGANISATION_UNIT_LEVEL_FIELDS = f"id,level,name,{_TRANSLATION_FIELDS}"
#: What a category combo has to state for its option combos to publish their own composition: the
#: ordered categories the combo splits over, and the category options each option combo is met from.
#: The UIDs alone - every name and every concept code the decomposition emits is joined from the
#: category projection the same run reads, so a combo says which options it is and nothing more.
#: Both arrays are ordered lists on the wire, unlike the `categoryOptionCombos` set beside them
#: (BUGS.md #63, #64): 25 consecutive reads of the local stack and 12 of play answered the same
#: order, and the order is not alphabetical. That is the order the DHIS2 data-entry app renders a
#: disaggregated section in, so `ordered_option_combos` lays the generated cells out by it.
_CATEGORY_COMBO_DECOMPOSITION_FIELDS = (
    "categories[id,categoryOptions[id]],categoryOptionCombos[id,name,code,categoryOptions[id]]"
)

#: The projection a disaggregation is read under, wherever one is read: the combo's own identity plus
#: what it decomposes into. Both places a question's cells can be disaggregated from ride it - the
#: data element's own combo and the data set element's override - so the two are the same shape and
#: an override naming the element's own combo resolves to the very same projection.
_DISAGGREGATION_COMBO_FIELDS = f"categoryCombo[id,name,isDefault,{_CATEGORY_COMBO_DECOMPOSITION_FIELDS}]"

#: The data-element projection every form kind's questions are built from. `code` rides it for the
#: data dictionary, which publishes the DHIS2 code of the object a question is asked from the way
#: the attribute dictionary publishes an attribute's - a data element DHIS2 left uncoded publishes
#: no code rather than its UID under a `dhis2-code` label.
_QUESTIONNAIRE_DATA_ELEMENT_FIELDS = (
    "dataElement[id,code,name,formName,description,valueType,domainType,optionSet[id],"
    f"{_TRANSLATION_FIELDS},"
    f"{_DISAGGREGATION_COMBO_FIELDS}]"
)

#: The tracked-entity-attribute projection every registration form's questions are built from.
#: `generated` and `pattern` are what say DHIS2 writes the value itself off a reserved-value
#: pattern, which is what makes the published question read-only; `description` is the guidance
#: the form shows beside it.
_QUESTIONNAIRE_TRACKED_ENTITY_ATTRIBUTE_FIELDS = (
    "trackedEntityAttribute[id,name,code,formName,description,valueType,unique,generated,pattern,"
    f"optionSet[id],{_TRANSLATION_FIELDS}]"
)

#: The data-set element projection: the data element the question is asked from, and the join's own
#: category combo. DHIS2 holds a disaggregation on the join as well as on the element, and the join's
#: is what the data set's cells are held over - a data element on the default combo carried by a data
#: set that overrides it to a four-way age split holds four cells there, not one. The override rides
#: the projection the elements already ride, so knowing it costs no second request, and
#: `_effective_category_combo` is the one place the two meet.
_DATA_SET_ELEMENT_FIELDS = f"{_QUESTIONNAIRE_DATA_ELEMENT_FIELDS},{_DISAGGREGATION_COMBO_FIELDS}"

#: The data set's own category combo - the attribute combo whose option combos are the third key
#: of every value it holds. It rides the very projection the disaggregation combos ride, so the
#: attribute-option-combo vocabulary is read on the metadata sweep the forms already cost rather
#: than on a request of its own.
_ATTRIBUTE_COMBO_FIELDS = f"categoryCombo[id,code,name,isDefault,{_CATEGORY_COMBO_DECOMPOSITION_FIELDS}]"

#: `greyedFields` is what a data set says its form never captures: an operand naming a data element
#: and a category option combo is a cell the DHIS2 data-entry app renders grey and refuses input on,
#: so the generated form must not ask it. It rides the section projection the form already reads.
_DATA_SET_FIELDS = (
    f"id,name,code,description,periodType,{_TRANSLATION_FIELDS},"
    f"sections[id,name,description,{_TRANSLATION_FIELDS},dataElements[id],"
    "greyedFields[dataElement[id],categoryOptionCombo[id]]],"
    f"{_ATTRIBUTE_VALUE_FIELDS},{_ATTRIBUTE_COMBO_FIELDS},"
    "compulsoryDataElementOperands[dataElement[id],categoryOptionCombo[id]],"
    f"dataSetElements[{_DATA_SET_ELEMENT_FIELDS}]"
)

#: The stage projection both program kinds read: an event program takes its single stage's questions,
#: a tracker program takes one Questionnaire per stage, so a stage carries its own identity, its own
#: attribute values, and the sort orders DHIS2 holds the stages and their questions in.
_PROGRAM_STAGE_FIELDS = (
    f"id,name,code,description,sortOrder,executionDateLabel,repeatable,"
    f"{_TRANSLATION_FIELDS},{_ATTRIBUTE_VALUE_FIELDS},"
    f"programStageSections[id,name,description,{_TRANSLATION_FIELDS},dataElements[id]],"
    f"programStageDataElements[compulsory,sortOrder,{_QUESTIONNAIRE_DATA_ELEMENT_FIELDS}]"
)
#: The registration projection a tracker program's own form is built from: the type of person it
#: enrols, whether its enrollments date the incident they follow, and the attributes it asks for.
#: `programTrackedEntityAttributes` is the join table, so `mandatory` and `sortOrder` sit on the
#: join while the question detail sits on the attribute it references - the very shape
#: `programStageDataElements` has, which is why the two read the same way.
#:
#: The tracked entity type carries its own join beside its UID, and that second join is what says
#: at which DHIS2 level an answer is imported: an attribute the type collects is stated on the
#: tracked entity, an attribute only the program asks is stated on the enrollment. It rides the
#: program read the form already costs, so knowing the level is worth no extra request.
#: `searchable` rides the same join for the same reason `mandatory` does: DHIS2 holds it there, so
#: whether a person can be found by an attribute is this program's answer and not the attribute's.
#: The tracked entity type's join carries `mandatory` too, and that second answer is the other half
#: of whether a registration question is required: DHIS2 asks the question for the entity whichever
#: program enrols it, so a type that requires the attribute requires it on every program's form,
#: whatever that program's own join says.
_PROGRAM_ATTRIBUTE_FIELDS = (
    "trackedEntityType[id,trackedEntityTypeAttributes[mandatory,trackedEntityAttribute[id]]],"
    "displayIncidentDate,enrollmentDateLabel,incidentDateLabel,"
    "programTrackedEntityAttributes[mandatory,searchable,displayInList,sortOrder,"
    f"{_QUESTIONNAIRE_TRACKED_ENTITY_ATTRIBUTE_FIELDS}]"
)

#: The tracked entity type projection a person-only registration form is built from: the type's own
#: identity, and the attributes it collects itself through the join that carries their order,
#: whether the type requires them, and whether DHIS2 will find a person by them.
_TRACKED_ENTITY_TYPE_FIELDS = (
    f"id,name,code,description,{_TRANSLATION_FIELDS},{_ATTRIBUTE_VALUE_FIELDS},"
    "trackedEntityTypeAttributes[mandatory,searchable,displayInList,sortOrder,"
    f"{_QUESTIONNAIRE_TRACKED_ENTITY_ATTRIBUTE_FIELDS}]"
)
#: The rule-variable projection, which rides the program read the forms already cost. DHIS2 holds
#: `programRuleVariables` as a collection on Program, so knowing which question a rule condition
#: reads is worth no extra request - unlike the rules themselves, which the Program schema does not
#: carry at all and which `_fetch_program_rules` therefore reads on their own.
_PROGRAM_RULE_VARIABLE_FIELDS = (
    "programRuleVariables[id,name,programRuleVariableSourceType,dataElement[id],trackedEntityAttribute[id]]"
)

_PROGRAM_FIELDS = (
    f"id,name,code,description,programType,{_TRANSLATION_FIELDS},"
    f"{_ATTRIBUTE_VALUE_FIELDS},{_PROGRAM_ATTRIBUTE_FIELDS},{_PROGRAM_RULE_VARIABLE_FIELDS},"
    f"programStages[{_PROGRAM_STAGE_FIELDS}]"
)

#: The program-rule projection: the expression the server evaluates, the rule's identity and its
#: translations, and every action it takes with whichever question the action lands on.
_PROGRAM_RULE_FIELDS = (
    f"id,name,description,condition,program[id],{_TRANSLATION_FIELDS},"
    "programRuleActions[programRuleActionType,dataElement[id],trackedEntityAttribute[id]]"
)

#: The attribute projection the emit-time join reads: an attribute's UID, its code, and whether
#: DHIS2 declares it unique - a unique value is a business identifier rather than an annotation.
_ATTRIBUTE_FIELDS = "id,code,unique"

#: The DHIS2 program types the questionnaire target maps, one selection table each.
_EVENT_PROGRAM_TYPE = "WITHOUT_REGISTRATION"
_TRACKER_PROGRAM_TYPE = "WITH_REGISTRATION"

#: Where an object DHIS2 sent no `sortOrder` for is placed: after every ordered peer, then by name and UID.
_UNORDERED_SORT_POSITION = 1_000_000_000

#: The event projection one example response is built from.
_EXAMPLE_EVENT_FIELDS = "event,orgUnit,occurredAt,status,dataValues[dataElement,value]"

#: The tracker-event projection: an event of a tracker program stage also names its enrollment and
#: the tracked entity enrolled, which the response carries as its subject and its enrollment extension.
_EXAMPLE_TRACKER_EVENT_FIELDS = "event,orgUnit,occurredAt,status,enrollment,trackedEntity,dataValues[dataElement,value]"

#: How many candidate periods the data-value discovery tries before giving a data set up.
_EXAMPLE_PERIOD_ATTEMPTS = 6

#: The tracked-entity projection one registration example is built from: the person's identity and
#: attribute values, plus the enrollments that registered them - one example response per enrollment.
_EXAMPLE_TRACKED_ENTITY_FIELDS = (
    "trackedEntity,attributes[attribute,value],enrollments[enrollment,enrolledAt,occurredAt,orgUnit,program]"
)

#: The envelope keys the tracker events endpoint has answered under.
_EVENT_ENVELOPE_KEYS = ("instances", "events")

#: The envelope keys the tracked entities endpoint has answered under.
_TRACKED_ENTITY_ENVELOPE_KEYS = ("instances", "trackedEntities")

#: Where the synthetic load set is written, relative to the project root. It is not IG input: the
#: files are a corpus to POST at a running `d2w fhir serve`, so they sit beside `ig/` rather than
#: inside it, and the target owns the directory outright.
_LOAD_DIRECTORY = "load"

#: How many synthetic responses each questionnaire target contributes to a load set by default -
#: enough that a seven-form instance yields a corpus worth measuring a POST loop against.
DEFAULT_LOAD_SET_PER_TARGET = 25

#: The id-only data-set projection the load set reads its capture constraints from - the units the
#: data set is assigned to. The attribute option combo a response is keyed under comes off the form
#: projection instead, which already carries the data set's own category combo.
_LOAD_SET_DATA_SET_FIELDS = "id,organisationUnits[id]"

#: The id-only program projection the load set reads its capture constraints from. DHIS2 hangs the
#: assignment on the program, so a tracker stage is placed by the program's units rather than its own.
_LOAD_SET_PROGRAM_FIELDS = "id,organisationUnits[id]"


class ProgramRuleIndex(BaseModel):
    """One run's program rules, keyed by the program each belongs to, in the order the instance returned them."""

    rules_by_program: dict[str, list[ProgramRuleIn]] = Field(default_factory=dict)


def grouped_count(count: int, noun: str) -> str:
    """A count with its noun, grouped for reading: `2,667 files`, `1 file`."""
    return f"{count:,}{pluralize(count, noun).removeprefix(str(count))}"


class GenerateSubject(BaseModel):
    """What a generate target covers, counted in the instance's own objects rather than in files."""

    model_config = ConfigDict(frozen=True)

    count: int
    noun: str
    plural: str | None = None

    def label(self) -> str:
        """The subject as one phrase, grouped for reading: `1,696 organisation units`, `1 option set`."""
        spelled = self.noun if self.count == 1 else self.plural
        if spelled is not None:
            return f"{self.count:,} {spelled}"
        return grouped_count(self.count, self.noun)


class GenerateReport(BaseModel):
    """Outcome of one `d2w fhir generate` target."""

    project_root: Path
    target_directory: str
    target_base: str = "ig/input/fsh"
    deleted_files: list[str] = Field(default_factory=list)
    written_files: list[str] = Field(default_factory=list)
    unchanged_count: int = 0
    option_set_count: int = 0
    category_count: int = 0
    questionnaire_count: int = 0
    assignment_count: int = 0
    attribute_combo_count: int = 0
    organisation_unit_count: int = 0
    position_count: int = 0
    boundary_count: int = 0
    example_count: int = 0
    page_count: int = 0
    intro_count: int = 0
    #: What this target covers - the count a reader compares with the instance, distinct from the
    #: files it wrote, since one covered object can ship as several files.
    subject: GenerateSubject | None = None
    notes: list[GenerateNote] = Field(default_factory=list)


class LoadSetReport(BaseModel):
    """Outcome of one load-set run: the synthetic QuestionnaireResponse corpus written to disk.

    `questionnaire_count` is how many targets the corpus actually covers, which is not always how
    many the selection holds: a target DHIS2 would refuse every response for is dropped with a note.
    """

    project_root: Path
    target_directory: str
    written_files: list[str] = Field(default_factory=list)
    unchanged_count: int = 0
    deleted_files: list[str] = Field(default_factory=list)
    response_count: int = 0
    questionnaire_count: int = 0
    #: What the corpus covers - the questionnaires it answers, distinct from the files it wrote.
    subject: GenerateSubject | None = None
    notes: list[GenerateNote] = Field(default_factory=list)


class GenerateFullReport(BaseModel):
    """Outcome of one whole-project generate run: the report each target produced."""

    foundation: GenerateReport
    option_sets: GenerateReport
    categories: GenerateReport
    questionnaires: GenerateReport
    examples: GenerateReport
    organisation_units: GenerateReport
    pages: GenerateReport

    def with_distinct_notes(self) -> GenerateFullReport:
        """This run with each note kept only on the first target that raised it.

        A full run hands one fetch's notes to every target that reads the same input, so the
        per-target reports repeat what solo runs of those targets would each say. A consumer
        reading the whole run - the notes file, the terminal count, the doctor findings - reads
        this view instead, so one decision is reported once. The fields are declared in run
        order, which is what makes "first target" well defined.
        """
        seen: set[GenerateNote] = set()
        reports: dict[str, GenerateReport] = {}
        for field_name in type(self).model_fields:
            report: GenerateReport = getattr(self, field_name)
            novel = [note for note in report.notes if note not in seen]
            seen.update(novel)
            reports[field_name] = report.model_copy(update={"notes": novel})
        return GenerateFullReport(**reports)


class UnsupportedProgramError(LookupError):
    """Raised when a configured event program is a shape the questionnaire target does not map.

    A `LookupError` so the CLI's error funnel renders it as a one-liner naming the program and
    the selection table it belongs under, rather than as a traceback.
    """


class BuildAbortingCodeError(LookupError):
    """Raised when a selected object's DHIS2 code would abort the IG publisher's own build.

    A DHIS2 code becomes an identifier value on the resources this plugin emits, and the IG
    publisher writes an identifier value into a table cell unescaped and then strict-parses the
    page it just wrote. A `<` opens a tag there, and the publisher dies on the malformed cell -
    in its final pass, after every resource has already been rendered, which on a real hierarchy
    is the better part of an hour thrown away.

    The whole run is refused rather than the one object skipped: a skipped option set leaves every
    Questionnaire that binds it pointing at a ValueSet nobody wrote, which is a broken guide
    published quietly instead of a build that failed loudly.

    A `LookupError` for the same reason `UnsupportedProgramError` is: the CLI's error funnel
    renders it as a one-liner naming the object and the code, rather than as a traceback.
    """


class BuildAbortingNameError(LookupError):
    """Raised when a selected object's DHIS2 name would abort the IG publisher's own build.

    A DHIS2 name stays byte-true on the emitted resource's `title` / `name` elements - escaping it
    would make the IG disagree with the instance about what the object is called - and the IG
    publisher writes those elements into pages it strict-parses after writing. A `<` opens a tag
    there, and the publisher dies on the malformed page in its final pass, after every resource has
    already been rendered.

    The whole run is refused rather than the one object skipped, for the same reason a
    build-aborting code refuses it: a build that fails loudly now beats one that fails an hour in,
    and a quietly skipped object leaves a guide that disagrees with its selection.

    A `LookupError` so the CLI's error funnel renders it as a one-liner naming the object and the
    name, rather than as a traceback.
    """


class _CodedObject(BaseModel):
    """One selected DHIS2 object as the code gate reads it, before any of it is emitted."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    uid: str
    name: str
    code: str | None = None

    @property
    def emitted_code(self) -> str:
        """The identifier value the object really emits - its DHIS2 code, or the UID standing in for it."""
        return code_or_uid(self.code, self.uid)


def _screening_gate(gate: HostileNameGate | None) -> HostileNameGate:
    """The gate one run screens its DHIS2 names through: the caller's, or one that rewrites nothing.

    A caller that hands none is a caller that never asked for a rewrite - a library build, a live
    serve, a forward - so the names reach the emitters exactly as DHIS2 states them and the
    build-aborting refusal below acts on them unchanged.
    """
    return gate if gate is not None else HostileNameGate()


def _refuse_build_aborting_objects(objects: list[_CodedObject]) -> None:
    """Refuse the run before a single file is written when an emitted code or name aborts the publisher's build."""
    for coded in objects:
        if build_aborting_code(coded.emitted_code):
            raise BuildAbortingCodeError(
                f"{coded.resource_type} {coded.name!r} ({coded.uid}) has code {coded.emitted_code!r}, which carries "
                "'<'. A DHIS2 code becomes an identifier value, which the IG publisher writes into a table cell "
                "unescaped and then strict-parses, so `make build` aborts with \"Unable to Parse HTML - node 'td' "
                'has unexpected content" in its last pass, once every resource has already been rendered. '
                "Change the code in DHIS2, then run `d2w fhir validate` for the full report."
            )
        if build_aborting_name(coded.name):
            raise BuildAbortingNameError(
                f"{coded.resource_type} {coded.name!r} ({coded.uid}) has a name carrying '<'. A DHIS2 name stays "
                "byte-true on the emitted resource's title, which the IG publisher writes into pages it "
                "strict-parses after writing, so `make build` aborts in its last pass, once every resource has "
                "already been rendered. Change the name in DHIS2, then run `d2w fhir validate` for the full report."
            )


def _refuse_build_aborting_member_names(sources: Sequence[ConceptSourceIn]) -> None:
    """Refuse the run when a concept source's member name aborts the publisher's build.

    Options and category options land in page tables and concept displays the instance sweep
    cannot see, which is why `d2w fhir validate` flags them through its own option pass - this is
    the generate-time half of the same finding.
    """
    for source in sources:
        for member in source.options:
            if not build_aborting_name(member.name):
                continue
            raise BuildAbortingNameError(
                f"{source.source_label} {source.name!r} ({source.uid}) has {source.member_label} "
                f"{member.name!r} ({member.uid}) whose name carries '<'. The IG publisher writes it into pages "
                "it strict-parses after writing, so `make build` aborts in its last pass, once every resource "
                "has already been rendered. Change the name in DHIS2, then run `d2w fhir validate` for the "
                "full report."
            )


#: The DHIS2 collection each form kind asks its questions from - the name a question gate's refusal
#: reports the object under, and the `ValidationScope` surface `d2w fhir validate` grades it against.
_QUESTION_COLLECTIONS: dict[str, str] = {
    "data-element": "dataElements",
    "tracked-entity-attribute": "trackedEntityAttributes",
}


#: What each question spelling becomes on disk, named in the refusal so a reader knows which of the
#: two DHIS2 fields to change. A name is the concept display of the data dictionary, and the question
#: text of every object DHIS2 gives no form name; a form name is the question text wherever DHIS2
#: states one, which is the input surface the name never reaches.
_QUESTION_NAME_SURFACES: dict[str, str] = {
    "name": "the question text and the data dictionary concept it publishes",
    "form name": "the question text of every form asking it",
}


def _refuse_build_aborting_question_names(sources: Sequence[QuestionnaireSourceIn]) -> None:
    """Refuse the run when a name or form name of a question one of these forms asks aborts the build.

    A data element's name is the `display` of its concept in `data-dictionary/data-elements.fsh` and
    the `text` of its question wherever DHIS2 states no form name; a tracked entity attribute's name
    is the same two places in the attribute half of the dictionary. A form name is the question text
    wherever DHIS2 states one - the input spelling, which the name never displaces. All of them stay
    byte-true DHIS2 data, and the publisher writes them into pages it strict-parses after writing, so
    a `<` in any of them aborts `make build` exactly as a data set's own name does.

    Only the two names are read. A question object is a concept inside the dictionary rather than an
    artifact of its own, so its DHIS2 code never becomes an identifier value - which is why
    `dataElements` and `trackedEntityAttributes` are absent from validate's code-identifier
    collections, and why gating their codes here would refuse runs validate calls clean.
    """
    for source in sources:
        collection = _QUESTION_COLLECTIONS[FORM_KIND_PROFILES[source.kind].question_subject]
        for item in _source_items(source):
            for field_label, spelling in (("name", item.name), ("form name", item.form_name)):
                if spelling is None or not build_aborting_name(spelling):
                    continue
                raise BuildAbortingNameError(
                    f"{collection} {item.name!r} ({item.uid}), asked by {_SOURCE_CODE_COLLECTIONS[source.kind]} "
                    f"{source.name!r} ({source.uid}), has a {field_label} carrying '<'. A DHIS2 {field_label} "
                    f"stays byte-true on {_QUESTION_NAME_SURFACES[field_label]}, which the IG publisher writes "
                    "into pages it strict-parses after writing, so `make build` aborts in its last pass, once "
                    "every resource has already been rendered. Change the "
                    f"{field_label} in DHIS2, then run `d2w fhir validate` for the full report."
                )


def _refuse_build_aborting_form_objects(sources: Sequence[QuestionnaireSourceIn]) -> None:
    """Refuse the run when any name or code the forms publish aborts the publisher's build.

    The whole gate one form-consuming target applies: the forms' own identities, then the questions
    they ask. Every target that writes a form's name to disk calls this, so `d2w fhir generate
    pages` refuses exactly what `d2w fhir generate questionnaires` refuses rather than writing a
    catalog row for a form the questionnaire target would not have emitted.
    """
    _refuse_build_aborting_objects([_coded_source(source) for source in sources])
    _refuse_build_aborting_question_names(sources)


@asynccontextmanager
async def _instance_connection(
    profile: Profile, client: Dhis2Client | None, *, timeout: float | None = None
) -> AsyncGenerator[Dhis2Client]:
    """The connection one capability reads DHIS2 through: the caller's when it holds one, else its own.

    `client` is the connection the caller holds open, and None in the command's own mode - the two
    are the same fact stated once, which is why the caller opens it rather than this function. A
    handed-in client is used as it stands and left open afterwards: its lifetime belongs to whoever
    entered it, so a caller making six calls over one connection makes one connection. With none
    handed in the `Profile` is the convenience wrapper every command uses, and the connection opens
    and closes inside the call.

    `timeout` is honoured only on the connection this function opens. A handed-in client already
    carries the caller's own read ceiling, and silently re-timing someone else's client would be a
    side effect on an object this call does not own.
    """
    if client is not None:
        yield client
        return
    async with open_client(profile, timeout=timeout) as opened:
        yield opened


#: How many steps `validate_codes` announces: connect, resolve the selection, sweep, read the
#: option sets, build the report.
VALIDATE_CODES_STEPS = 5

#: How many steps an offline generate target announces: the single emit.
GENERATE_FOUNDATION_STEPS = 1

#: How many steps one instance-backed generate target announces: the fetch, then the emit.
GENERATE_TARGET_STEPS = 2

#: How many steps `generate_full` announces: the single instance fetch plus one per target.
GENERATE_FULL_STEPS = 8


#: The label every fetch step is reported under, whichever command it belongs to.
_FETCH_LABEL = "instance metadata"


class _StepAnnouncer:
    """Announces a run's numbered steps to a progress reporter, or to nothing when none was passed.

    A step opens with `step`, narrates itself with as many `tick` captions as it likes, and closes
    with exactly one `complete`. A tick is a caption an animated display overwrites in place, so a
    fifty-page organisation-unit walk costs no more output than a one-page one and a plain reporter
    renders none of it; a completion is the durable `[k/N] label: summary` line, so it fires once
    per numbered step and never inside one - the counter an animated display advances on completion
    would otherwise run past the run's own length. `start`, `finish`, and `stop` bound the whole run
    and belong to the caller that built the reporter, not to the service.
    """

    def __init__(self, reporter: ProgressReporter | None = None, total: int = 0) -> None:
        """Store the reporter to announce to and how many steps the run holds."""
        self._reporter = reporter
        self._total = total
        self._index = 0
        self._label = ""

    def step(self, label: str, caption: str | None = None) -> None:
        """Open the next step: `label` names it in its completion line, `caption` in the live display."""
        self._index += 1
        self._label = label
        if self._reporter is not None:
            self._reporter.step(self._index, self._total, caption or label)

    def tick(self, caption: str) -> None:
        """Re-caption the step already running, with no durable line and no move of the counter."""
        if self._reporter is not None:
            self._reporter.step(self._index, self._total, caption)

    def complete(self, summary: str) -> None:
        """Close the step already running with the one-line outcome it is reported by."""
        if self._reporter is not None:
            self._reporter.complete(self._index, self._total, self._label, summary)


def _target_counts(report: GenerateReport) -> str:
    """One-line outcome of one generate target: what it covers, then what it wrote, left alone, removed, and noted."""
    parts = [] if report.subject is None else [report.subject.label()]
    parts += [
        f"{grouped_count(len(report.written_files), 'file')} written",
        f"{grouped_count(report.unchanged_count, 'file')} unchanged",
    ]
    if report.deleted_files:
        parts.append(f"{grouped_count(len(report.deleted_files), 'file')} deleted")
    if report.notes:
        parts.append(grouped_count(len(report.notes), "note"))
    return ", ".join(parts)


class GenerationProfile(BaseModel):
    """The resolved DHIS2 profile for a generate run, with display provenance."""

    model_config = ConfigDict(frozen=True)

    name: str
    origin: str
    profile: Profile


def resolve_generation_profile(project: FhirProject, explicit: str | None = None) -> GenerationProfile:
    """Resolve the profile for a generate run: explicit arg, then `DHIS2_PROFILE`, then fhir.toml, then default."""
    environment = os.environ.get("DHIS2_PROFILE")
    name = explicit or environment or project.config.profile
    resolved = resolve(name)
    if explicit or environment:
        origin = "--profile/DHIS2_PROFILE"
    elif project.config.profile:
        origin = "fhir.toml"
    else:
        origin = resolved.source
    return GenerationProfile(name=resolved.name, origin=origin, profile=resolved.profile)


class ValidationContext(BaseModel):
    """Resolved inputs for a validate run: the profile plus the effective generate config."""

    model_config = ConfigDict(frozen=True)

    generation: GenerationProfile
    config: GenerateConfig


def resolve_validation_context(explicit: str | None = None) -> ValidationContext:
    """Resolve profile + config for `fhir validate` - the FHIR project is optional, the instance is the target."""
    try:
        project = load_project()
    except NoFhirProjectError:
        environment = os.environ.get("DHIS2_PROFILE")
        resolved = resolve(explicit or environment)
        origin = "--profile/DHIS2_PROFILE" if (explicit or environment) else resolved.source
        generation = GenerationProfile(name=resolved.name, origin=origin, profile=resolved.profile)
        return ValidationContext(generation=generation, config=GenerateConfig())
    return ValidationContext(generation=resolve_generation_profile(project, explicit), config=project.config.generate)


#: Collections excluded from the instance-wide sweep: options get the deeper per-set pass.
_SWEEP_EXCLUDED_COLLECTIONS = frozenset({"options", "system"})

#: Every organisation unit emits an Organization and a Location, so the registry is twice the unit count.
_INSTANCES_PER_ORGANISATION_UNIT = 2

#: Registry instances past which the IG publisher's per-resource passes dominate the build. The
#: registry never reaches SUSHI - it ships as pre-built JSON - but the publisher still validates
#: and renders every resource, so the wall clock of `make build` tracks this count. Calibrated
#: against a timed build of the play 2.43 guide: its 2,664 registry instances carried a
#: multi-hour build (the measurements are in the FHIR design roadmap's build-facts section), so
#: a registry that size deserves the warning rather than sailing under it.
_REGISTRY_RENDER_COST_INSTANCES = 2_000

#: Read timeout for the validate sweep's single `/api/metadata` request. The client's 30 s default
#: is sized for an ordinary API read; a whole-instance metadata read is a different shape of request
#: and needs its own ceiling. Measured on a national instance: 13 MB over 58 s, so the default fails
#: it every time and `d2w fhir validate` cannot run at all against exactly the instances whose size
#: makes its findings worth having.
_SWEEP_TIMEOUT_SECONDS = 600.0

#: What the instance sweep asks of every collection at once. `formName` exists only on the two
#: collections a form asks its questions from; DHIS2's field filter answers the rest without it,
#: exactly as it already answers `code` for the collections that carry none.
_SWEEP_FIELDS = "id,name,formName,code"


def _sweep_collections(raw: dict[str, object]) -> list[MetadataCollectionIn]:
    """Wrap the raw instance-sweep body into typed sweep sources."""
    collections: list[MetadataCollectionIn] = []
    for resource, value in raw.items():
        if resource in _SWEEP_EXCLUDED_COLLECTIONS or not isinstance(value, list):
            continue
        items = [
            MetadataItemIn(
                uid=str(entry["id"]),
                name=entry.get("name"),
                form_name=entry.get("formName"),
                code=entry.get("code"),
            )
            for entry in value
            if isinstance(entry, dict) and entry.get("id")
        ]
        collections.append(MetadataCollectionIn(resource=resource, items=items))
    return collections


def resolve_code_source(config: GenerateConfig, override: str | None) -> Literal["id", "code"]:
    """Effective concept code source for a validate run: the CLI/MCP override, else the configured value."""
    if override is None:
        return config.concept_code_source
    if override == "id":
        return "id"
    if override == "code":
        return "code"
    raise ValueError(f"code_source must be 'id' or 'code', not {override!r}")


def resolve_hostile_names_posture(
    config: GenerateConfig, override: HostileNamePosture | None
) -> HostileNamePosture | None:
    """Effective hostile-names posture for a validate run: the CLI override, else the configured value.

    None all the way down is a posture of its own - the run asks, and a run with nothing to ask on
    refuses - which grades exactly as `refuse` does, so validate keeps it rather than folding it in.
    """
    return override or config.hostile_names


async def validate_codes(
    profile: Profile,
    config: GenerateConfig,
    code_source: str | None = None,
    hostile_names: HostileNamePosture | None = None,
    *,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
) -> FhirValidationReport:
    """Check the whole instance's codes (sweep) plus the option sets in depth, without writing anything.

    The run first resolves the configured selection into a `ValidationScope`, so every finding's
    severity means build impact on this project's IG rather than instance-wide alarm.

    `hostile_names` overrides the project's `[generate] hostile_names` for this run, which is the
    what-if reading `d2w fhir validate --hostile-names` asks for; with none the project's own
    posture decides how the name findings are graded.

    `client` is a connection the caller already holds open, which the run reads through and leaves
    open; with none, the profile opens one for the length of the call, under the sweep's own read
    ceiling rather than the client's ordinary one.
    """
    progress = _StepAnnouncer(reporter, VALIDATE_CODES_STEPS)
    progress.step("connecting")
    async with _instance_connection(profile, client, timeout=_SWEEP_TIMEOUT_SECONDS) as connection:
        progress.complete(profile.base_url)
        return await _validated_codes(connection, config, code_source, hostile_names, progress=progress)


async def validate_instance_codes(
    client: Dhis2Client,
    config: GenerateConfig,
    code_source: str | None = None,
    hostile_names: HostileNamePosture | None = None,
    *,
    scope: ValidationScope | None = None,
) -> FhirValidationReport:
    """The analysis `d2w fhir validate` runs, over a connection the caller already holds open.

    The same passes, the same graders, and the same severity grading as the command - what it drops
    is the command's own furniture: no profile to open a connection from, no progress reporter, and
    no report files. `d2w fhir serve`'s `/facade/metadata-health` is the caller this exists for, and a
    finding it answers with is a finding the command names in the same words.

    `scope` is a selection the caller already resolved through `resolve_validation_scope`, which
    saves resolving it twice where the caller needs the UID sets for something of its own; with none
    the run resolves its own, exactly as the command does.
    """
    return await _validated_codes(client, config, code_source, hostile_names, scope=scope)


async def _validated_codes(
    client: Dhis2Client,
    config: GenerateConfig,
    code_source: str | None,
    hostile_names: HostileNamePosture | None,
    *,
    scope: ValidationScope | None = None,
    progress: _StepAnnouncer | None = None,
) -> FhirValidationReport:
    """Resolve the selection, sweep the instance, read the option sets, and grade what came back."""
    announcer = progress if progress is not None else _StepAnnouncer()
    effective_source = resolve_code_source(config, code_source)
    effective_posture = resolve_hostile_names_posture(config, hostile_names)
    announcer.step("selection", "resolving the configured selection")
    resolved = scope if scope is not None else await resolve_validation_scope(client, config)
    announcer.complete(_scope_summary(resolved))
    announcer.step("instance sweep", "sweeping instance metadata (can take a minute on a large instance)")
    raw = await client.get_raw("/api/metadata", params={"fields": _SWEEP_FIELDS, "defaults": "EXCLUDE"})
    collections = _sweep_collections(raw)
    object_count = sum(len(collection.items) for collection in collections)
    announcer.complete(f"{len(collections):,} collections, {object_count:,} objects")
    announcer.step("option sets", "reading option sets")
    models = await client.resources.option_sets.list(fields=_OPTION_SET_FIELDS, order=["name:asc"], paging=False)
    announcer.complete(f"{len(models):,} read")
    announcer.step("findings", "building report")
    option_sets = [_option_set_input(model) for model in models]
    report = build_code_validation(
        option_sets, collections, config, effective_source, scope=resolved, hostile_names=effective_posture
    )
    announcer.complete(f"{len(report.findings):,} finding(s)")
    return report


#: The id-only data-set projection scope resolution reads: membership alone, no form detail.
_SCOPE_DATA_SET_FIELDS = "id,dataSetElements[dataElement[id,optionSet[id]]]"

#: The id-only program projection scope resolution reads: the routing type, the stages with each
#: stage's data-element references, and the tracked entity attributes a tracker program's
#: registration form asks - every one of them carrying the option set it binds, because the
#: option-set closure is the union of what the whole capture surface binds.
_SCOPE_PROGRAM_FIELDS = (
    "id,programType,trackedEntityType[id],"
    "programStages[id,programStageDataElements[dataElement[id,optionSet[id]]]],"
    "programTrackedEntityAttributes[trackedEntityAttribute[id,optionSet[id]]]"
)

#: The id-only tracked-entity-type projection scope resolution reads: the attributes a person-only
#: form asks, which are the questions whose names the generate gate refuses a `<` in.
_SCOPE_TRACKED_ENTITY_TYPE_FIELDS = "id,trackedEntityTypeAttributes[trackedEntityAttribute[id]]"


class _ScopeBindings(BaseModel):
    """The question objects the selected containers carry, and the option sets they and the attributes bind."""

    data_element_uids: set[str] = Field(default_factory=set)
    tracked_entity_attribute_uids: set[str] = Field(default_factory=set)
    option_set_uids: set[str] = Field(default_factory=set)

    def collect(self, reference: dict[str, object]) -> None:
        """Record one wire data-element reference: its UID plus the option set it binds, when it binds one."""
        uid = _optional_text(reference.get("id"))
        if uid is None:
            return
        self.data_element_uids.add(uid)
        self.collect_option_set(reference)

    def collect_attribute(self, reference: dict[str, object]) -> None:
        """Record one wire tracked-entity-attribute reference: its UID plus the option set it binds.

        An attribute is not a data element, so it lands on the `trackedEntityAttributes` surface
        rather than the `dataElements` one - the same split the generate gate reports a refused
        question name under.
        """
        uid = _optional_text(reference.get("id"))
        if uid is None:
            return
        self.tracked_entity_attribute_uids.add(uid)
        self.collect_option_set(reference)

    def collect_option_set(self, reference: dict[str, object]) -> None:
        """Record the option set one wire reference binds, when it binds one.

        A tracked entity attribute goes through here rather than through `collect`: it binds an
        option set the same way a data element does, but it is not a data element, and the
        `dataElements` scope surface answers for what `d2w fhir validate` grades as one.
        """
        option_set = reference.get("optionSet")
        if isinstance(option_set, dict):
            option_set_uid = _optional_text(option_set.get("id"))
            if option_set_uid is not None:
                self.option_set_uids.add(option_set_uid)


def _collect_stage_elements(stage: dict[str, object], bindings: _ScopeBindings) -> None:
    """Mine one wire program stage's data-element references into the scope bindings."""
    raw_elements = stage.get("programStageDataElements")
    for entry in raw_elements if isinstance(raw_elements, list) else []:
        if not isinstance(entry, dict):
            continue
        reference = _data_element_reference(entry)
        if reference is not None:
            bindings.collect(reference)


def _collect_registration_attributes(program: Program, bindings: _ScopeBindings) -> None:
    """Mine one tracker program's registration attributes into the scope bindings' attribute and set closures."""
    raw_attributes = program.programTrackedEntityAttributes
    for entry in raw_attributes if isinstance(raw_attributes, list) else []:
        if not isinstance(entry, dict):
            continue
        reference = _tracked_entity_attribute_reference(entry)
        if reference is not None:
            bindings.collect_attribute(reference)


def _collect_type_attributes(model: TrackedEntityType, bindings: _ScopeBindings) -> None:
    """Mine one tracked entity type's own attributes into the scope bindings - a person-only form's questions."""
    raw_attributes = model.trackedEntityTypeAttributes
    for entry in raw_attributes if isinstance(raw_attributes, list) else []:
        if not isinstance(entry, dict):
            continue
        reference = _tracked_entity_attribute_reference(entry)
        if reference is not None:
            bindings.collect_attribute(reference)


async def _resolve_scope_tracked_entity_types(
    client: Dhis2Client, config: GenerateConfig, tracked_by_programs: set[str], bindings: _ScopeBindings
) -> frozenset[str]:
    """Resolve the tracked entity types publishing a person-only form, mining their attributes on the way.

    The same selection `_fetch_tracked_entity_type_sources` applies - `[generate.tracked_entity_forms]`
    where it names anything, the types the selected tracker programs track where it does not - so a
    run naming neither costs no request at all, and neither does a table switched off.
    """
    if not config.tracked_entity_forms.enabled:
        return frozenset()
    selected = config.tracked_entity_forms.include_ids
    uids = selected or sorted(tracked_by_programs)
    if not uids:
        return frozenset()
    models: list[TrackedEntityType] = await client.resources.tracked_entity_types.list(
        fields=_SCOPE_TRACKED_ENTITY_TYPE_FIELDS,
        filters=[_uid_filter(uids)],
        paging=False,
    )
    resolved: set[str] = set()
    for model in models:
        if not model.id:
            continue
        resolved.add(model.id)
        _collect_type_attributes(model, bindings)
    return frozenset(resolved)


async def resolve_validation_scope(client: Dhis2Client, config: GenerateConfig) -> ValidationScope:
    """Resolve the UID sets the configured selection emits, from a handful of id-only reads.

    The same selection semantics `generate` applies - an empty table selects everything of its
    kind, the option sets add the closure the selected forms bind (through the
    `_selected_option_set_uids` helper both paths share), the organisation units go through the
    shared `_organisation_unit_selection_filters` - read in projections that carry little more
    than ids (the category read adds the name, the wire's one default-placeholder signal), so
    scoping a national instance costs five small requests rather than a second metadata sweep.

    A data element is in scope when a selected data set or a selected program's stage carries it;
    an event program contributes its single stage's elements (the stage itself is not a surface -
    only a tracker stage emits its own Questionnaire). A tracker program's tracked entity
    attributes land on the `trackedEntityAttributes` surface rather than the data-element one -
    a registration form asks them as questions, so their names reach the guide and the sets they
    bind are published, but an attribute is not a data element and `dataElements` is what that
    surface answers for. A program named under the selection table its type does not belong to
    contributes nothing here: that misconfiguration is generate's refusal to raise, not validate's.

    Every surface a `ValidationScope` carries is a surface the generate gate refuses a
    build-aborting name on, which is what keeps the parity two-way: the category options of the
    selected categories, the tracked entity types publishing a person-only form, and the
    attributes those forms ask are all resolved here for exactly that reason.
    """
    bindings = _ScopeBindings()
    data_set_ids = config.data_sets.include_ids
    data_set_models: list[DataSet] = []
    if config.data_sets.enabled:
        data_set_models = await client.resources.data_sets.list(
            fields=_SCOPE_DATA_SET_FIELDS,
            filters=[_uid_filter(data_set_ids)] if data_set_ids else None,
            paging=False,
        )
    data_sets: set[str] = set()
    for data_set in data_set_models:
        if not data_set.id:
            continue
        data_sets.add(data_set.id)
        for element in data_set.dataSetElements or []:
            if element.dataElement is not None:
                bindings.collect(element.dataElement.model_dump())
    event_ids = config.event_programs.include_ids if config.event_programs.enabled else []
    tracker_ids = config.tracker_programs.include_ids if config.tracker_programs.enabled else []
    program_models: list[Program] = []
    if config.event_programs.enabled or config.tracker_programs.enabled:
        # A filtered read serves the run only when every table still on names its programs; a table
        # on and empty means its whole program type, which only a sweep answers.
        every_table_named = (event_ids or not config.event_programs.enabled) and (
            tracker_ids or not config.tracker_programs.enabled
        )
        program_models = await client.resources.programs.list(
            fields=_SCOPE_PROGRAM_FIELDS,
            filters=[_uid_filter([*event_ids, *tracker_ids])] if every_table_named else None,
            paging=False,
        )
    programs: set[str] = set()
    tracker_programs: set[str] = set()
    program_stages: set[str] = set()
    tracked_by_programs: set[str] = set()
    for program in program_models:
        uid = program.id or ""
        if not uid:
            continue
        program_type = _program_type(program)
        stages = _program_stages(program)
        as_event = config.event_programs.enabled and (
            uid in event_ids if event_ids else program_type == _EVENT_PROGRAM_TYPE
        )
        as_tracker = config.tracker_programs.enabled and (
            uid in tracker_ids if tracker_ids else program_type == _TRACKER_PROGRAM_TYPE
        )
        if as_event and program_type == _EVENT_PROGRAM_TYPE:
            programs.add(uid)
            for stage in stages[:1]:
                _collect_stage_elements(stage, bindings)
        if as_tracker and program_type == _TRACKER_PROGRAM_TYPE:
            programs.add(uid)
            tracker_programs.add(uid)
            _collect_registration_attributes(program, bindings)
            tracked_type_uid = _tracked_entity_type_uid(program)
            if tracked_type_uid is not None:
                tracked_by_programs.add(tracked_type_uid)
            for stage in stages:
                stage_uid = _optional_text(stage.get("id"))
                if stage_uid is not None:
                    program_stages.add(stage_uid)
                _collect_stage_elements(stage, bindings)
    option_set_models: list[OptionSet] = await client.resources.option_sets.list(fields="id", paging=False)
    option_sets = _selected_option_set_uids(
        frozenset(model.id for model in option_set_models if model.id),
        frozenset(bindings.option_set_uids),
        config.option_sets,
    )
    category_ids = config.categories.include_ids
    # `id,name` rather than id-only: the name is the wire's one signal a category is DHIS2's
    # built-in default placeholder, which `_category_selected` keeps off the build path. The
    # category options ride along on the same read - they are the concepts the selected category
    # publishes, so their names are on the build path exactly as the category's own is.
    category_models: list[Category] = await client.resources.categories.list(
        fields="id,name,categoryOptions[id]",
        filters=[_uid_filter(category_ids)] if category_ids else None,
        paging=False,
    )
    selected_categories = [
        model
        for model in category_models
        if model.id and _category_selected(model.id, model.name or "", config.categories)
    ]
    tracked_entity_types = await _resolve_scope_tracked_entity_types(client, config, tracked_by_programs, bindings)
    return ValidationScope(
        option_sets=option_sets,
        categories=frozenset(model.id for model in selected_categories if model.id),
        category_options=frozenset(
            uid for model in selected_categories for uid in _reference_uid_list(model.categoryOptions)
        ),
        organisation_units=await _fetch_published_organisation_unit_uids(client, config),
        data_sets=frozenset(data_sets),
        programs=frozenset(programs),
        tracker_programs=frozenset(tracker_programs),
        program_stages=frozenset(program_stages),
        tracked_entity_types=tracked_entity_types,
        data_elements=frozenset(bindings.data_element_uids),
        tracked_entity_attributes=frozenset(bindings.tracked_entity_attribute_uids),
    )


def _scope_summary(scope: ValidationScope) -> str:
    """One line of in-scope set sizes - the durable outcome of the resolving-selection step."""
    return (
        f"{len(scope.data_sets):,} data sets, {len(scope.programs):,} programs, "
        f"{len(scope.program_stages):,} stages, {len(scope.data_elements):,} data elements, "
        f"{len(scope.option_sets):,} option sets, {len(scope.categories):,} categories, "
        f"{len(scope.organisation_units):,} organisation units"
    )


async def init_project(
    directory: Path, options: InitOptions, *, force: bool = False, template: ProjectTemplate | None = None
) -> ScaffoldReport:
    """Scaffold a SUSHI IG project into `directory`, skipping files that already exist unless `force`.

    `template` pre-populates the project from a guide already generated against a real DHIS2
    instance, so the tree that lands compiles and serves without reaching an instance at all. Its
    payload is reported apart from the scaffold's own files, which the payload never overwrites.
    """
    report = ScaffoldReport(directory=directory.resolve(), template=template.name if template else None)
    for scaffold_file in build_scaffold_files(options, template=template):
        destination = directory / scaffold_file.relative_path
        if destination.exists() and not force:
            skipped = report.skipped_template_files if scaffold_file.from_template else report.skipped_files
            skipped.append(scaffold_file.relative_path)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(scaffold_file.content, encoding="utf-8")
        created = report.template_files if scaffold_file.from_template else report.created_files
        created.append(scaffold_file.relative_path)
    return report


#: What SUSHI compiles the FSH sources into, under `ig/`. SUSHI writes that tree and recreates it
#: whole on every run; no other command in this toolchain writes a byte of it.
_COMPILED_DIRECTORY = "fsh-generated"


def _remove_stale_compile(project: FhirProject, *fsh_syncs: SyncReport) -> list[GenerateNote]:
    """Remove the compiled guide when this target rewrote the FSH sources SUSHI compiled it from.

    `ig/fsh-generated/` is SUSHI's output and nobody else's, so a run that rewrites a FSH source
    leaves it holding resources compiled from sources that no longer exist. Everything that reads
    the compiled tree - `d2w fhir check-artifacts`, `d2w fhir serve`, `d2w fhir forward`, `make
    build` - would read that mixture as the project's current state, and a substitution-changing
    regenerate makes it hundreds of files wide. Removing it leaves one of two honest states: a
    compile of these very sources, or no compile at all, which is what every reader of that tree
    already answers with `run d2w fhir generate, then make sushi`.

    `ig/temp/` and `ig/output/` stay. `temp/` is the IG publisher's own scratch - no command reads
    it between builds, and the scaffolded `make build` does not even ship it into the container -
    and `output/` is a published site, which is a thing to replace deliberately rather than to
    discard on a source edit.

    A target whose FSH syncs wrote and deleted nothing leaves the compile where it is, so a
    regenerate against unchanged metadata leaves a compiled project compiled. The returned note is
    the run's own account of the removal, carried on the report of the target that removed it - in
    a whole-run generate that is the first target to rewrite a source, since the targets after it
    find the tree already gone.
    """
    if not any(sync.written or sync.deleted for sync in fsh_syncs):
        return []
    compiled = project.ig_directory / _COMPILED_DIRECTORY
    if not compiled.is_dir():
        return []
    shutil.rmtree(compiled)
    return [
        generate_note(
            GenerateNoteCategory.COMPILE_REMOVED,
            f"removed ig/{_COMPILED_DIRECTORY}: it held SUSHI's compile of FSH sources this run rewrote, and "
            "check-artifacts, serve, forward and `make build` all read that tree. Run `make sushi` in the "
            "project to compile the sources this run wrote.",
        )
    ]


def _scaffold_identity_notes(project: FhirProject) -> list[GenerateNote]:
    """Say so when fhir.toml states an identity ig/sushi-config.yaml does not carry.

    The `[ig]` table is where the guide's id, address, name, title, publisher and status are
    stated, and `ig/sushi-config.yaml` is where the IG publisher reads them, so an edit to
    `fhir.toml` reaches the published guide's cover through `d2w fhir init --refresh`. This note is
    raised on the foundation target, the one target that reads nothing off the instance and runs
    first in every whole-run generate, so the file is read once per run.
    """
    disagreements = sushi_config_identity_disagreements(project)
    if not disagreements:
        return []
    keys = ", ".join(disagreement.key for disagreement in disagreements)
    return [
        generate_note(
            GenerateNoteCategory.SCAFFOLD_DRIFT,
            f"{SUSHI_CONFIG_RELATIVE_PATH} does not carry what fhir.toml states ({keys}): run "
            "`d2w fhir init --refresh` (or `make update` in a scaffolded project) to bring the "
            "scaffold-managed files up to date",
        )
    ]


async def generate_foundation(project: FhirProject, *, reporter: ProgressReporter | None = None) -> GenerateReport:
    """Generate the instance-independent `foundation/` artifacts: DHIS2 identifier aliases and D2Period."""
    return _emit_foundation(project, progress=_StepAnnouncer(reporter, GENERATE_FOUNDATION_STEPS))


def _emit_foundation(project: FhirProject, *, progress: _StepAnnouncer) -> GenerateReport:
    """Build and sync the foundation artifacts; the one target that reads nothing off the instance."""
    progress.step("foundation", "writing ig/input/fsh/foundation")
    artifacts = build_foundation_artifacts(
        project.config.generate, project.config.ig.canonical, ig_status=project.config.ig.status
    )
    sync = sync_artifacts(project.fsh_directory, "foundation", artifacts)
    report = GenerateReport(
        project_root=project.project_root,
        target_directory="foundation",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        notes=_scaffold_identity_notes(project) + _remove_stale_compile(project, sync),
    )
    progress.complete(_target_counts(report))
    return report


async def generate_option_sets(
    profile: Profile,
    project: FhirProject,
    *,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
    gate: HostileNameGate | None = None,
) -> GenerateReport:
    """Generate a CodeSystem/ValueSet pair per option set into `terminology/`, plus its ConceptMap.

    `client` is a connection the caller already holds open, which the run reads through and leaves
    open; with none, the profile opens one for the length of the call.

    `gate` is what the run does with a DHIS2 name the IG publisher's build cannot survive; with
    none, every name is published exactly as DHIS2 states it.
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[GenerateNote] = []
    progress.step(_FETCH_LABEL, "fetching option sets")
    async with _instance_connection(profile, client) as client:
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        sources = await _closure_sources(client, config)
        attribute_codes = await resolve_attribute_code_index(client)
    inputs = _selected_option_sets([_option_set_input(model) for model in models], sources, config, notes)
    inputs = _screening_gate(gate).screen(inputs, notes)
    progress.complete(f"{len(inputs):,} option set(s)")
    return _emit_option_sets(
        project, option_sets=inputs, attribute_codes=attribute_codes, notes=notes, progress=progress
    )


def _emit_option_sets(
    project: FhirProject,
    *,
    option_sets: list[OptionSetIn],
    attribute_codes: AttributeCodeIndex,
    notes: list[GenerateNote],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the terminology pairs and their ConceptMaps off a selected option-set list and sync both directories."""
    progress.step(
        "option sets",
        f"writing ig/input/resources/{TERMINOLOGY_DIRECTORY} and ig/input/resources/{CONCEPT_MAP_DIRECTORY}",
    )
    _refuse_build_aborting_objects(
        [
            _CodedObject(
                resource_type="optionSets", uid=option_set.uid, name=option_set.name, code=option_set.dhis2_code
            )
            for option_set in option_sets
        ]
    )
    _refuse_build_aborting_member_names(option_sets)
    build = build_option_set_artifacts(
        option_sets,
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
        attribute_codes=attribute_codes,
    )
    concept_maps = build_option_set_concept_map_artifacts(
        option_sets,
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
    )
    identifier_systems = build_option_set_identifier_artifacts(
        option_sets,
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
    )
    sync = sync_json_artifacts(
        project.resources_directory, TERMINOLOGY_DIRECTORY, [*build.artifacts, *identifier_systems]
    )
    concept_map_sync = sync_json_artifacts(
        project.resources_directory,
        CONCEPT_MAP_DIRECTORY,
        concept_maps,
        owned_prefix=option_set_concept_map_file_prefix(project.config.generate),
    )
    # The target writes JSON, so it also owns keeping its FSH directory empty of generated files: a
    # project whose terminology was written as FSH would otherwise hold both shapes, and SUSHI refuses
    # a definition that duplicates a pre-defined resource. Only header-bearing files are removed, so a
    # hand-authored file in that directory is left alone.
    superseded = clean_generated_files(project.fsh_directory / TERMINOLOGY_DIRECTORY)
    report = GenerateReport(
        project_root=project.project_root,
        target_base="ig/input",
        target_directory=f"resources/{TERMINOLOGY_DIRECTORY}, resources/{CONCEPT_MAP_DIRECTORY}",
        deleted_files=[*sync.deleted, *concept_map_sync.deleted, *superseded],
        written_files=[*sync.written, *concept_map_sync.written],
        unchanged_count=len(sync.unchanged) + len(concept_map_sync.unchanged),
        option_set_count=len(option_sets),
        subject=GenerateSubject(count=len(option_sets), noun="option set"),
        # The JSON this target writes is read straight off `ig/input/resources`, so only the
        # superseded FSH it swept is a change to what SUSHI compiles.
        notes=[*notes, *build.notes, *_remove_stale_compile(project, SyncReport(deleted=superseded))],
    )
    progress.complete(_target_counts(report))
    return report


async def generate_categories(
    profile: Profile,
    project: FhirProject,
    *,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
    gate: HostileNameGate | None = None,
) -> GenerateReport:
    """Generate one pre-built CodeSystem and ValueSet document per configured category into `categories/`.

    `client` is a connection the caller already holds open, which the run reads through and leaves
    open; with none, the profile opens one for the length of the call.

    `gate` is what the run does with a DHIS2 name the IG publisher's build cannot survive; with
    none, every name is published exactly as DHIS2 states it.
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[GenerateNote] = []
    progress.step(_FETCH_LABEL, "fetching categories")
    async with _instance_connection(profile, client) as client:
        inputs = await _fetch_categories(client, config, notes)
        attribute_codes = await resolve_attribute_code_index(client)
    inputs = _screening_gate(gate).screen(inputs, notes)
    progress.complete(f"{len(inputs):,} categor{'y' if len(inputs) == 1 else 'ies'}")
    return _emit_categories(project, categories=inputs, attribute_codes=attribute_codes, notes=notes, progress=progress)


def _emit_categories(
    project: FhirProject,
    *,
    categories: list[CategoryIn],
    attribute_codes: AttributeCodeIndex,
    notes: list[GenerateNote],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the category pairs and their ConceptMaps off a selected category list and sync both directories."""
    progress.step(
        "categories",
        f"writing ig/input/resources/{CATEGORY_DIRECTORY} and ig/input/resources/{CONCEPT_MAP_DIRECTORY}",
    )
    _refuse_build_aborting_objects(
        [
            _CodedObject(resource_type="categories", uid=category.uid, name=category.name, code=category.dhis2_code)
            for category in categories
        ]
    )
    _refuse_build_aborting_member_names(categories)
    build = build_category_artifacts(
        categories,
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
        attribute_codes=attribute_codes,
    )
    concept_maps = build_category_concept_map_artifacts(
        categories,
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
    )
    identifier_systems = build_category_identifier_artifacts(
        categories,
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
    )
    sync = sync_json_artifacts(project.resources_directory, CATEGORY_DIRECTORY, [*build.artifacts, *identifier_systems])
    concept_map_sync = sync_json_artifacts(
        project.resources_directory,
        CONCEPT_MAP_DIRECTORY,
        concept_maps,
        owned_prefix=category_concept_map_file_prefix(project.config.generate),
    )
    report = GenerateReport(
        project_root=project.project_root,
        target_base="ig/input",
        target_directory=f"resources/{CATEGORY_DIRECTORY}, resources/{CONCEPT_MAP_DIRECTORY}",
        deleted_files=[*sync.deleted, *concept_map_sync.deleted],
        written_files=[*sync.written, *concept_map_sync.written],
        unchanged_count=len(sync.unchanged) + len(concept_map_sync.unchanged),
        category_count=len(categories),
        subject=GenerateSubject(count=len(categories), noun="category", plural="categories"),
        notes=[*notes, *build.notes],
    )
    progress.complete(_target_counts(report))
    return report


async def _fetch_categories(client: Dhis2Client, config: GenerateConfig, notes: list[GenerateNote]) -> list[CategoryIn]:
    """Read the categories the run publishes: every one the instance holds, narrowed by the configuration.

    The one read behind both consumers - the category target's own pairs and the decomposition the
    combo vocabularies carry - so the two always agree on which categories are published and on the
    concept codes their options took.
    """
    models = await client.resources.categories.list(
        fields=_CATEGORY_FIELDS,
        order=["name:asc"],
        paging=False,
    )
    return _selected_categories([_category_input(model) for model in models], config, notes)


def _category_selected(uid: str, name: str, selection: CategorySelection) -> bool:
    """Whether one category clears the default-placeholder gate of the selection.

    The single statement of how DHIS2's built-in `default` category is treated, shared by the
    generate-time filter and the validation scope so the two can never disagree. The default
    category exchanges no information, so it is out unless `include_default` opts it back in or
    an `include_ids` entry names its UID outright - the most specific configuration statement
    wins over the economy default. Every other category clears the gate unconditionally;
    `include_ids` narrowing is the caller's own step.
    """
    if not is_default_category(name):
        return True
    return selection.include_default or uid in selection.include_ids


def _selected_categories(
    inputs: list[CategoryIn], config: GenerateConfig, notes: list[GenerateNote]
) -> list[CategoryIn]:
    """Filter categories by the configured UIDs, noting entries that matched nothing.

    An absent or empty `[generate.categories] include_ids` selects every category the instance
    holds, matching the option-set selection. A category is not pulled in by a closure the way
    an option set is: nothing generated today binds a category, so the list stands on its own.
    DHIS2's built-in `default` category is the exception `_category_selected` states: skipped
    unless `include_default` or an `include_ids` entry naming it asks for it.
    """
    selection = config.categories
    inputs = [item for item in inputs if _category_selected(item.uid, item.name, selection)]
    if not selection.include_ids:
        return inputs
    configured_ids = set(selection.include_ids)
    selected = [item for item in inputs if item.uid in configured_ids]
    selected_ids = {item.uid for item in selected}
    for uid in sorted(configured_ids - selected_ids):
        notes.append(
            generate_note(GenerateNoteCategory.SELECTION_MISMATCH, f"include_ids entry {uid!r} matched no category")
        )
    return selected


def _category_input(model: Category) -> CategoryIn:
    """Map a generated Category (with inline category-option dicts) into the emitter projection.

    DHIS2 holds `categoryOptions` as an ordered list, so each option's index in the answer is
    carried across as its sort order and the emitted concepts keep the category's own order.
    """
    options = [
        OptionIn(
            uid=str(raw["id"]),
            code=raw.get("code"),
            name=str(raw.get("name") or raw["id"]),
            sort_order=index,
            translations=_translation_inputs(raw.get("translations")),
        )
        for index, raw in enumerate(model.categoryOptions or [])
        if isinstance(raw, dict) and raw.get("id")
    ]
    uid = model.id or ""
    return CategoryIn(
        uid=uid,
        code=model.code,
        name=model.name or uid,
        description=model.description,
        options=options,
        translations=_translation_inputs(model.translations),
        attribute_values=_attribute_value_inputs(model.attributeValues),
    )


async def fetch_assignment_index(client: Dhis2Client, sources: list[QuestionnaireSourceIn]) -> AssignmentIndex:
    """Read the organisation units every selected data set and program is assigned to, id-only.

    The assignment artifact and the load set need the same fact, so both read it through the one
    id-only fetch `_fetch_load_set_assignments` makes: this projects that result onto the
    container-to-units index the assignment emitter consumes, which keeps the run at one read.
    """
    assignments = await _fetch_load_set_assignments(client, sources)
    return AssignmentIndex(
        organisation_units={uid: container.organisation_unit_uids for uid, container in assignments.items()}
    )


async def generate_questionnaires(
    profile: Profile,
    project: FhirProject,
    *,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
    gate: HostileNameGate | None = None,
) -> GenerateReport:
    """Generate one Questionnaire FSH file per selected data set, event program, and tracker program stage.

    `client` is a connection the caller already holds open, which the run reads through and leaves
    open; with none, the profile opens one for the length of the call.

    `gate` is what the run does with a DHIS2 name the IG publisher's build cannot survive. It
    screens the forms and the categories before a single identity is planned off them, so the
    question text, the data dictionary concepts, and the combo vocabularies all read one
    projection.
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    screening = _screening_gate(gate)
    notes: list[GenerateNote] = []
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets")
    async with _instance_connection(profile, client) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        attribute_codes = await resolve_attribute_code_index(client)
        # The option sets the forms bind, read here rather than only by the terminology target: a
        # program rule hiding a question on a coded answer names the concept code the bound
        # CodeSystem publishes for the option it compares to, which is decided from the options.
        option_sets = await _fetch_example_option_sets(client, sources)
        # The categories the run publishes, read in this target's own fetch phase: the combo
        # vocabularies decompose every option combo into them, so the concept codes and the
        # CodeSystem canonicals a coding names come from the very selection the category target
        # emits rather than from a shape guessed off the combo.
        categories = await _fetch_categories(client, config, notes)
        screening.decide(sources, option_sets, categories)
        sources = screening.screen(sources, notes)
        option_sets = screening.screen(option_sets, [])
        categories = screening.screen(categories, notes)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources, screening)
        # The questionnaire surface resolves before the registry read, so a `source = "code"`
        # refusal names this target's own offenders rather than the registry's.
        stem_plan = plan_questionnaire_stems(sources, config.naming.source)
        assignments = await fetch_assignment_index(client, sources)
        published_organisation_unit_stems = await _fetch_published_organisation_unit_stems(client, config)
    progress.complete(f"{len(sources):,} questionnaire target(s)")
    return _emit_questionnaires(
        project,
        sources=sources,
        option_set_plan=option_set_plan,
        option_sets=option_sets,
        attribute_codes=attribute_codes,
        categories=categories,
        stem_plan=stem_plan,
        assignments=assignments,
        published_organisation_unit_stems=published_organisation_unit_stems,
        notes=notes,
        progress=progress,
    )


def _emit_questionnaires(
    project: FhirProject,
    *,
    sources: list[QuestionnaireSourceIn],
    option_set_plan: OptionSetIdentityPlan,
    option_sets: list[OptionSetIn],
    attribute_codes: AttributeCodeIndex,
    categories: list[CategoryIn],
    stem_plan: QuestionnaireStemPlan,
    assignments: AssignmentIndex,
    published_organisation_unit_stems: StemResolution,
    notes: list[GenerateNote],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the Questionnaire FSH off already-fetched sources and sync each of its five directories.

    `stem_plan` is resolved by the caller at the fetch/plan level - under `source = "code"` an
    unusable code has therefore refused the run before this step opens - and the builder raises
    its code-or-id fall-back notes onto this target's report.

    The assignment Lists and the attribute-option-combo pairs are built first, because a form that
    publishes either one carries a reference to it on the Questionnaire: both emitters read the one
    plan each build returns, so the FSH source and the served document name the same artifacts.

    `categories` is the selection the category target publishes, which the combo vocabularies
    decompose their concepts into - one property per category axis, coded into that category's own
    CodeSystem. `option_sets` is the sets the forms bind, whose options decide the concept code a
    program rule's coded `enableWhen` answer names.
    """
    generate = project.config.generate
    canonical = project.config.ig.canonical
    ig_status = project.config.ig.status
    progress.step(
        "questionnaires",
        f"writing ig/input/fsh/{{{','.join(QUESTIONNAIRE_DIRECTORIES)}}} and "
        f"ig/input/resources/{{{ASSIGNMENT_DIRECTORY},{ATTRIBUTE_COMBO_DIRECTORY}}}",
    )
    _refuse_build_aborting_form_objects(sources)
    assignment_build = build_assignment_artifacts(
        sources,
        assignments,
        generate,
        published=published_organisation_unit_stems,
        stem_plan=stem_plan,
    )
    decomposition = build_category_decomposition(sources, categories, generate, canonical)
    attribute_combo_build = build_attribute_combo_artifacts(
        sources, generate, canonical, ig_status=ig_status, decomposition=decomposition
    )
    concept_maps = build_attribute_combo_concept_map_artifacts(sources, generate, canonical, ig_status=ig_status)
    build = build_questionnaire_artifacts(
        sources,
        generate,
        canonical,
        ig_status=ig_status,
        option_set_plan=option_set_plan,
        attribute_codes=attribute_codes,
        option_sets=option_sets,
        stem_plan=stem_plan,
        assignments=assignment_build.plan,
        attribute_combos=attribute_combo_build.plan,
        decomposition=decomposition,
    )
    syncs = [
        sync_artifacts(project.fsh_directory, directory, _artifacts_under(build.artifacts, directory))
        for directory in QUESTIONNAIRE_DIRECTORIES
    ]
    json_syncs = [
        sync_json_artifacts(project.resources_directory, ASSIGNMENT_DIRECTORY, assignment_build.artifacts),
        sync_json_artifacts(
            project.resources_directory,
            ATTRIBUTE_COMBO_DIRECTORY,
            [
                *attribute_combo_build.artifacts,
                *build_attribute_combo_identifier_artifacts(sources, generate, canonical, ig_status=ig_status),
            ],
        ),
        sync_json_artifacts(
            project.resources_directory,
            CONCEPT_MAP_DIRECTORY,
            concept_maps,
            owned_prefix=attribute_combo_concept_map_file_prefix(generate),
        ),
        # The identity map rides this target because the vocabulary it maps out of is this target's:
        # its source is one tracked entity attribute's value namespace, and `D2TEA_CS` is what
        # publishes that attribute. A project nominating no sex attribute produces no file, and the
        # sweep then deletes the one a project that used to nominate one left behind.
        sync_json_artifacts(
            project.resources_directory,
            CONCEPT_MAP_DIRECTORY,
            build_administrative_gender_concept_map_artifacts(
                project.config.ips.identity, generate, canonical, ig_status=ig_status
            ),
            owned_prefix=administrative_gender_map_file_prefix(generate),
        ),
        # The section map rides this target for the same reason the identity map does: what it maps
        # out of is the DHIS2 namespaces this target's own vocabularies publish. A project mapping
        # no section produces no file, and the sweep then deletes the one a project that used to map
        # one left behind.
        sync_json_artifacts(
            project.resources_directory,
            CONCEPT_MAP_DIRECTORY,
            build_section_concept_map_artifacts(project.config.ips.sections, generate, canonical, ig_status=ig_status),
            owned_prefix=section_map_file_prefix(generate),
        ),
    ]
    report = GenerateReport(
        project_root=project.project_root,
        target_base="ig/input",
        target_directory=f"{', '.join(f'fsh/{directory}' for directory in QUESTIONNAIRE_DIRECTORIES)}, "
        f"resources/{ASSIGNMENT_DIRECTORY}, resources/{ATTRIBUTE_COMBO_DIRECTORY}, "
        f"resources/{CONCEPT_MAP_DIRECTORY}",
        deleted_files=[
            *(name for sync in syncs for name in sync.deleted),
            *(name for sync in json_syncs for name in sync.deleted),
        ],
        written_files=[
            *(path for sync in syncs for path in sync.written),
            *(path for sync in json_syncs for path in sync.written),
        ],
        unchanged_count=sum(len(sync.unchanged) for sync in [*syncs, *json_syncs]),
        questionnaire_count=len(sources),
        subject=GenerateSubject(count=len(sources), noun="questionnaire"),
        assignment_count=len(assignment_build.artifacts),
        attribute_combo_count=len(attribute_combo_build.artifacts),
        notes=[
            *notes,
            *build.notes,
            *assignment_build.notes,
            *attribute_combo_build.notes,
            *decomposition.notes,
            *_remove_stale_compile(project, *syncs),
        ],
    )
    progress.complete(_target_counts(report))
    return report


async def generate_examples(
    profile: Profile,
    project: FhirProject,
    *,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
    gate: HostileNameGate | None = None,
) -> GenerateReport:
    """Generate one `Usage: #example` QuestionnaireResponse per configured example into `examples/`.

    `client` is a connection the caller already holds open, which the run reads through and leaves
    open; with none, the profile opens one for the length of the call.

    `gate` is what the run does with a DHIS2 name the IG publisher's build cannot survive; with
    none, every name is published exactly as DHIS2 states it.
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    screening = _screening_gate(gate)
    notes: list[GenerateNote] = []
    if config.examples.per_target <= 0:
        return await _emit_examples(
            None,
            project,
            sources=[],
            option_sets=[],
            option_set_plan=option_set_identities([], config),
            published_organisation_unit_uids=frozenset(),
            stem_plan=plan_questionnaire_stems([], config.naming.source),
            organisation_unit_stems=StemResolution(),
            notes=notes,
            progress=progress,
        )
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets and the option sets they bind")
    async with _instance_connection(profile, client) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        option_sets = await _fetch_example_option_sets(client, sources)
        screening.decide(sources, option_sets)
        sources = screening.screen(sources, notes)
        option_sets = screening.screen(option_sets, notes)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources, screening)
        organisation_unit_stems = await _fetch_published_organisation_unit_stems(client, config)
        progress.complete(f"{len(sources):,} questionnaire target(s), {len(option_sets):,} bound option set(s)")
        return await _emit_examples(
            client,
            project,
            sources=sources,
            option_sets=option_sets,
            option_set_plan=option_set_plan,
            published_organisation_unit_uids=frozenset(organisation_unit_stems.stems),
            stem_plan=plan_questionnaire_stems(sources, config.naming.source),
            organisation_unit_stems=organisation_unit_stems,
            notes=notes,
            progress=progress,
        )


async def _emit_examples(
    client: Dhis2Client | None,
    project: FhirProject,
    *,
    sources: list[QuestionnaireSourceIn],
    option_sets: list[OptionSetIn],
    option_set_plan: OptionSetIdentityPlan,
    published_organisation_unit_uids: frozenset[str],
    stem_plan: QuestionnaireStemPlan,
    organisation_unit_stems: StemResolution,
    notes: list[GenerateNote],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Read the example responses off the instance and sync one QuestionnaireResponse per example.

    The one emitter that still reads the instance during its own step: an instance-sourced
    example is a walk over `/api/dataValueSets` and `/api/tracker/events` per target, which no
    shared metadata fetch can stand in for. `client` is None only when `[generate.examples]`
    asks for no examples at all, where nothing is read and the target sweeps its directory.

    `published_organisation_unit_uids` is the registry's own selection, so an `ORGANISATION_UNIT`
    answer naming a unit the guide publishes no Location for is left unanswered rather than
    pointed at a resource no consumer can resolve. `stem_plan` and `organisation_unit_stems` are
    the run's identity resolutions - the file names and the `questionnaire` canonical follow the
    target's stem, every `Location/...` reference follows the registry's - and their fall-back
    notes stay on the targets that own those surfaces.
    """
    progress.step("examples", f"writing ig/input/fsh/{EXAMPLES_DIRECTORY}")
    _refuse_build_aborting_form_objects(sources)
    _refuse_build_aborting_objects(
        [
            _CodedObject(
                resource_type="optionSets", uid=option_set.uid, name=option_set.name, code=option_set.dhis2_code
            )
            for option_set in option_sets
        ]
    )
    _refuse_build_aborting_member_names(option_sets)
    artifacts: list[FshArtifact] = []
    example_count = 0
    if client is not None and project.config.generate.examples.per_target > 0:
        published_sources = _published_sources(sources)
        responses = await _example_responses(
            client, published_sources, option_sets, project.config.generate.examples, notes, progress
        )
        build = build_example_artifacts(
            published_sources,
            responses,
            option_sets,
            project.config.generate,
            project.config.ig.canonical,
            option_set_plan=option_set_plan,
            published_organisation_unit_uids=published_organisation_unit_uids,
            stem_plan=stem_plan,
            organisation_unit_stems=organisation_unit_stems,
            attribute_combos=build_attribute_combo_artifacts(
                published_sources,
                project.config.generate,
                project.config.ig.canonical,
                ig_status=project.config.ig.status,
            ).plan,
        )
        artifacts = build.artifacts
        notes.extend(build.notes)
        example_count = len(build.artifacts)
    sync = sync_artifacts(project.fsh_directory, EXAMPLES_DIRECTORY, artifacts)
    report = GenerateReport(
        project_root=project.project_root,
        target_directory=EXAMPLES_DIRECTORY,
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        example_count=example_count,
        subject=GenerateSubject(count=example_count, noun="example"),
        notes=[*notes, *_remove_stale_compile(project, sync)],
    )
    progress.complete(_target_counts(report))
    return report


async def generate_load_set(
    profile: Profile,
    project: FhirProject,
    *,
    per_target: int = DEFAULT_LOAD_SET_PER_TARGET,
    salt: str = "",
    output_directory: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> LoadSetReport:
    """Write `per_target` synthetic QuestionnaireResponse documents per questionnaire target into `load/`.

    The volume twin of `generate_examples`: the same fetch, the same seeded generator, and the
    same document builder the IG's examples are compiled from - only the count and the target
    differ. An IG publishes one example per form because more stop illustrating; a load set wants
    as many as a POST loop can chew through, so it is not bounded the way `[generate.examples]` is.

    The values are seeded from the target UID and the ordinal, so a rerun over unchanged metadata
    writes byte-identical files and reports every one of them unchanged. `output_directory`
    relocates the corpus off the project root, which is what a caller writing into a scratch
    directory passes.

    The references are drawn to be instance-valid, which is where it parts from the examples
    target. Each response is captured at a unit drawn from the intersection of the published
    registry selection and its target's own DHIS2 organisation-unit assignment, so DHIS2 has no
    `E1029` to raise; and a data set on a non-default category combo carries the attribute option
    combo its values are keyed under, drawn from the combos the data set really holds, so there is
    no `E8023` either. A target left with no published unit assigned to it is dropped with a note
    naming it: a corpus exists to be forwarded, and a response nobody can accept measures a
    refusal we already knew about.

    A tracker program's corpus is internally consistent for the same reason. The registration
    responses mint the tracked entity and enrollment identities, and the program's stage responses
    answer against those very identities rather than inventing pairs nothing creates - so a drain,
    which posts registrations before events, lands both. A `unique` tracked entity attribute is
    answered from the minting response's own identity, because DHIS2 refuses a second registration
    claiming one business identifier with `E1064` and takes its enrollment and events down with it.

    **A corpus imports once.** It mints the UIDs it names, so a second import of the same corpus is
    refused by DHIS2 on the identities themselves - `E1002` for the tracked entity and `E1080` for
    the enrollment - whatever the values say, because `importStrategy=CREATE` means create. `salt`
    is the answer to that: it moves every seeded draw of the run, so a salted run is a different
    corpus rather than a second copy of the same one.
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[GenerateNote] = []
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets and the option sets they bind")
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        option_sets = await _fetch_example_option_sets(client, sources)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources, HostileNameGate())
        organisation_unit_stems = await _fetch_published_organisation_unit_stems(client, config)
        root_uid = await _root_organisation_unit_uid(client)
        assignments = await _fetch_load_set_assignments(client, sources)
    progress.complete(f"{len(sources):,} questionnaire target(s)")
    progress.step("load set", f"writing {_LOAD_DIRECTORY}")
    documents: list[QuestionnaireResponse] = []
    covered_sources: list[QuestionnaireSourceIn] = []
    if root_uid is None:
        notes.append(
            generate_note(
                GenerateNoteCategory.EMPTY_SELECTION,
                "the instance has no level-1 organisation unit; no load set emitted",
            )
        )
    else:
        plan = _plan_load_set(sources, assignments, frozenset(organisation_unit_stems.stems))
        covered_sources = plan.sources
        notes.extend(plan.notes)
        synthetic = build_synthetic_responses(
            plan.sources,
            option_sets,
            per_target,
            root_uid,
            datetime.now(tz=UTC).date(),
            placements=plan.placements,
            registration_program_uids=plan.registration_program_uids,
            salt=salt,
        )
        notes.extend(synthetic.notes)
        build = build_example_documents(
            plan.sources,
            synthetic.responses,
            option_sets,
            config,
            project.config.ig.canonical,
            option_set_plan=option_set_plan,
            stem_plan=plan_questionnaire_stems(sources, config.naming.source),
            organisation_unit_stems=organisation_unit_stems,
            attribute_combos=build_attribute_combo_artifacts(
                sources, config, project.config.ig.canonical, ig_status=project.config.ig.status
            ).plan,
        )
        documents = build.responses
        notes.extend(build.notes)
    base_directory = output_directory or project.project_root
    sync = sync_json_artifacts(base_directory, _LOAD_DIRECTORY, [_load_artifact(document) for document in documents])
    subject = GenerateSubject(count=len(covered_sources), noun="questionnaire")
    report = LoadSetReport(
        project_root=project.project_root,
        target_directory=_LOAD_DIRECTORY,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        deleted_files=sync.deleted,
        response_count=len(documents),
        questionnaire_count=len(covered_sources),
        subject=subject,
        notes=notes,
    )
    progress.complete(
        f"{subject.label()}, {len(report.written_files):,} files written, {report.unchanged_count:,} files unchanged"
    )
    return report


class _ContainerAssignment(BaseModel):
    """What DHIS2 will accept a write against one data set or program: the units it is scoped to.

    A write at a unit outside `organisation_unit_uids` is `E1029`, which is what makes the load
    set place every response inside the assignment rather than at the registry root.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    organisation_unit_uids: frozenset[str] = frozenset()


class _LoadSetPlan(BaseModel):
    """The load-set targets a corpus covers, where each one is captured, and why the rest were dropped."""

    sources: list[QuestionnaireSourceIn] = Field(default_factory=list)
    placements: dict[str, SyntheticPlacement] = Field(default_factory=dict)
    notes: list[GenerateNote] = Field(default_factory=list)

    @property
    def registration_program_uids(self) -> frozenset[str]:
        """The tracker programs the corpus emits registrations for, whose stage events reuse those identities."""
        return frozenset(source.uid for source in self.sources if source.kind == "tracker")


async def _fetch_load_set_assignments(
    client: Dhis2Client, sources: list[QuestionnaireSourceIn]
) -> dict[str, _ContainerAssignment]:
    """Read the capture constraints of every container the selected targets report through.

    Two id-only reads at most - one over the selected data sets, one over the selected programs -
    filtered to the very UIDs the selection resolved to, in the shape `resolve_validation_scope`
    reads its own membership: fields carrying ids, unpaged, so scoping a national instance costs
    two small requests rather than a second metadata sweep. A tracker stage contributes its
    program's UID rather than its own, because DHIS2 hangs the assignment on the program.
    """
    assignments: dict[str, _ContainerAssignment] = {}
    data_set_uids = sorted({source.uid for source in sources if source.kind == "aggregate"})
    if data_set_uids:
        data_sets: list[DataSet] = await client.resources.data_sets.list(
            fields=_LOAD_SET_DATA_SET_FIELDS,
            filters=[_uid_filter(data_set_uids)],
            paging=False,
        )
        for data_set in data_sets:
            if data_set.id:
                assignments[data_set.id] = _ContainerAssignment(
                    uid=data_set.id,
                    organisation_unit_uids=_reference_uids(data_set.organisationUnits),
                )
    program_uids = sorted(
        {
            assignment_container_uid(source)
            for source in sources
            if source.kind != "aggregate" and FORM_KIND_PROFILES[source.kind].assigned
        }
    )
    if program_uids:
        programs: list[Program] = await client.resources.programs.list(
            fields=_LOAD_SET_PROGRAM_FIELDS,
            filters=[_uid_filter(program_uids)],
            paging=False,
        )
        for program in programs:
            if program.id:
                assignments[program.id] = _ContainerAssignment(
                    uid=program.id,
                    organisation_unit_uids=_reference_uids(program.organisationUnits),
                )
    return assignments


def _reference_uids(raw: object) -> frozenset[str]:
    """Every `id` a wire reference collection carries, which is all an id-only assignment read answers with."""
    uids: set[str] = set()
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, dict):
            uid = _optional_text(entry.get("id"))
            if uid is not None:
                uids.add(uid)
    return frozenset(uids)


def _plan_load_set(
    sources: list[QuestionnaireSourceIn],
    assignments: dict[str, _ContainerAssignment],
    published_organisation_unit_uids: frozenset[str],
) -> _LoadSetPlan:
    """Decide which targets the corpus covers and which published unit each one may be captured at.

    A target is placed on the intersection of the published registry selection and its own DHIS2
    assignment, sorted so the seeded pick is reproducible whatever order the instance answered in.
    One class is dropped rather than emitted: a target the intersection leaves empty, because every
    response would name a unit the container does not report for and DHIS2 refuses that with
    `E1029`. A load set is measured by what DHIS2 accepts, so a response nobody can accept is noise
    in the very number the corpus exists to produce.

    Every form kind is covered. A tracker program contributes its registration form and its stages
    together, and the stages answer against the very enrollments the registrations mint - which is
    what makes the corpus internally consistent, given that a drain posts registrations first.

    A data set on a non-default category combo is covered like any other. Its responses carry the
    `D2AttributeOptionCombo` extension, drawn from the attribute option combos the data set really
    holds, so the third key of the data value set is stated and DHIS2 has no `E8023` to raise.

    A person-only form is placed over the whole published registry, because DHIS2 hangs no
    assignment on a tracked entity type: there is no scope to intersect, so every unit the run
    publishes a Location for may register one.
    """
    plan = _LoadSetPlan()
    unplaced: list[str] = []
    for source in sources:
        if not FORM_KIND_PROFILES[source.kind].assigned:
            units = sorted(published_organisation_unit_uids)
            if units:
                plan.sources.append(source)
                plan.placements[source.uid] = SyntheticPlacement(organisation_unit_uids=tuple(units))
                continue
            unplaced.append(f"{source.name} ({source.uid})")
            continue
        assignment = assignments.get(assignment_container_uid(source))
        units = sorted(published_organisation_unit_uids & assignment.organisation_unit_uids) if assignment else []
        if not units:
            unplaced.append(f"{source.name} ({source.uid})")
            continue
        plan.sources.append(source)
        plan.placements[source.uid] = SyntheticPlacement(organisation_unit_uids=tuple(units))
    if unplaced:
        plan.notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.EMPTY_SELECTION,
                f"{len(unplaced)} questionnaire targets have no published organisation unit assigned to them; "
                "no load-set responses emitted for them",
                unplaced,
            )
        )
    return plan


def _load_artifact(response: QuestionnaireResponse) -> JsonArtifact:
    """One synthetic response as the load-set file holding it, named by the id it is served under."""
    return JsonArtifact(
        relative_path=f"{_LOAD_DIRECTORY}/{response.id}.json",
        content=f"{response.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
    )


async def _example_responses(
    client: Dhis2Client,
    sources: list[QuestionnaireSourceIn],
    option_sets: list[OptionSetIn],
    selection: ExampleSelection,
    notes: list[GenerateNote],
    progress: _StepAnnouncer,
) -> list[ExampleResponseIn]:
    """Collect the example responses from whichever source the project configured."""
    today = datetime.now(tz=UTC).date()
    root_uid = await _root_organisation_unit_uid(client)
    if root_uid is None:
        notes.append(
            generate_note(
                GenerateNoteCategory.EMPTY_SELECTION,
                "the instance has no level-1 organisation unit; no examples emitted",
            )
        )
        return []
    if selection.source == "instance":
        return await _fetch_instance_responses(client, sources, selection.per_target, root_uid, notes, progress)
    synthetic = build_synthetic_responses(sources, option_sets, selection.per_target, root_uid, today)
    notes.extend(synthetic.notes)
    return synthetic.responses


async def _root_organisation_unit_uid(client: Dhis2Client) -> str | None:
    """The instance's root organisation unit - the one every example is subject to."""
    roots = await client.resources.organisation_units.list(fields="id", filters=["level:eq:1"], paging=False)
    return next((model.id for model in roots if model.id), None)


async def _fetch_example_option_sets(client: Dhis2Client, sources: list[QuestionnaireSourceIn]) -> list[OptionSetIn]:
    """Fetch every option set the selected forms bind a question to, in the emitter's own projection.

    The examples target reads its concept codes out of the same assignment the terminology
    target emits from, so it fetches the same projection: the assignment sorts the options by
    DHIS2 sort order and names the set in its notes.
    """
    bound_ids = sorted(
        {item.option_set_uid for source in sources for item in _source_items(source) if item.option_set_uid}
    )
    if not bound_ids:
        return []
    models = await client.resources.option_sets.list(
        fields=_OPTION_SET_FIELDS,
        filters=[_uid_filter(bound_ids)],
        paging=False,
    )
    return [_option_set_input(model) for model in models if model.id]


async def _fetch_instance_responses(
    client: Dhis2Client,
    sources: list[QuestionnaireSourceIn],
    per_target: int,
    root_uid: str,
    notes: list[GenerateNote],
    progress: _StepAnnouncer,
) -> list[ExampleResponseIn]:
    """Read example responses off the instance: data value sets for data sets, tracker events for programs.

    Each target announces itself by name on the reporter's transient caption before it is read:
    a data set walks back through its recent periods, so a single target can hold the run for
    several requests and a caption naming it is what says the run is still moving.
    """
    today = datetime.now(tz=UTC).date()
    responses: list[ExampleResponseIn] = []
    empty_targets: list[str] = []
    for index, source in enumerate(sorted(sources, key=lambda item: (item.name, item.uid)), start=1):
        progress.tick(f"example responses: {source.name} ({index}/{len(sources)})")
        if source.kind == "aggregate":
            found = await _fetch_data_value_responses(client, source, per_target, root_uid, today)
        elif source.kind == "tracker":
            found = await _fetch_registration_responses(client, source, per_target)
        else:
            found = await _fetch_event_responses(client, source, per_target)
        if not found:
            empty_targets.append(f"{source.name} ({source.uid})")
        responses.extend(found)
    if empty_targets:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.INSTANCE_DATA_GAP,
                f"{len(empty_targets)} questionnaire targets hold no data on the instance; no examples emitted",
                empty_targets,
            )
        )
    return responses


async def _fetch_data_value_responses(
    client: Dhis2Client,
    source: QuestionnaireSourceIn,
    per_target: int,
    root_uid: str,
    today: date,
) -> list[ExampleResponseIn]:
    """Walk back through the data set's completed periods until one answers with data values."""
    for iso in recent_periods(source.period_type or "", _EXAMPLE_PERIOD_ATTEMPTS, today):
        raw = await client.get_raw(
            "/api/dataValueSets",
            params={"dataSet": source.uid, "orgUnit": root_uid, "children": "true", "period": iso},
        )
        groups = _example_groups(DataValueSet.model_validate(raw), iso)
        if groups:
            return [_data_value_response(group, source.uid) for group in groups[:per_target]]
    return []


def _example_groups(data_value_set: DataValueSet, requested_iso: str) -> list[ReportedForm]:
    """The forms one envelope reports, richest first and then by organisation unit - an example-picking order.

    The grouping itself is `dhis2w_fhir.grouping.group_data_values`, which the facade's data set
    read-back reads the same envelope through; the order is this target's own, because an example
    corpus wants the fullest form it can find and a served record wants a stable one. A form the
    envelope names no organisation unit for is left out: an example is subject to a Location, and
    there would be none to name.
    """
    groups = group_data_values(data_value_set, default_period_iso=requested_iso)
    reportable = [group for group in groups if group.organisation_unit_uid]
    return sorted(reportable, key=lambda group: (-len(group.values), group.organisation_unit_uid))


def _data_value_response(group: ReportedForm, data_set_uid: str) -> ExampleResponseIn:
    """Turn one grouped data value key into the example projection, resolving its period's dates.

    The attribute option combo travels on: it is the third of the three keys the group was formed
    on, so an instance-sourced example of a data set on a non-default category combo says which
    combo its values were captured under rather than dropping the fact the instance held.
    """
    try:
        period = parse_period(group.period_iso)
    except ValueError:
        period = None
    return ExampleResponseIn(
        instance_id=f"{data_set_uid}-{group.period_iso}-{group.organisation_unit_uid}",
        target_uid=data_set_uid,
        kind="aggregate",
        organisation_unit_uid=group.organisation_unit_uid,
        status_code=COMPLETED_STATUS,
        period=period,
        attribute_option_combo_uid=group.attribute_option_combo_uid,
        answers=[
            ExampleAnswerIn(
                data_element_uid=value.data_element_uid,
                category_option_combo_uid=value.category_option_combo_uid,
                value=value.value,
            )
            for value in group.values
        ],
    )


async def _fetch_event_responses(
    client: Dhis2Client, source: QuestionnaireSourceIn, per_target: int
) -> list[ExampleResponseIn]:
    """Read the most recent events of one event program or one tracker program stage as example responses.

    Both kinds are events of `/api/tracker/events`: an event program selects them by `program`,
    and a tracker program stage by `program` plus `programStage` - DHIS2 requires the program
    beside the stage even though the stage pins it (BUGS.md #67). A stage's events also carry the
    enrollment and the tracked entity, and an event the instance answered either of them for
    travels on with the UID it has - the emitter states which of them is missing rather than
    dropping the example.
    """
    tracker = source.kind == "tracker-event"
    selection: dict[str, object] = {"program": source.uid}
    if tracker and source.program is not None:
        selection = {"program": source.program.uid, "programStage": source.uid}
    raw = await client.get_raw(
        "/api/tracker/events",
        params={
            **selection,
            "pageSize": per_target,
            "order": "occurredAt:desc",
            "fields": _EXAMPLE_TRACKER_EVENT_FIELDS if tracker else _EXAMPLE_EVENT_FIELDS,
        },
    )
    responses: list[ExampleResponseIn] = []
    for entry in _event_entries(raw):
        event_uid = _optional_text(entry.get("event"))
        organisation_unit_uid = _optional_text(entry.get("orgUnit"))
        if event_uid is None or organisation_unit_uid is None:
            continue
        responses.append(
            ExampleResponseIn(
                instance_id=event_uid,
                target_uid=source.uid,
                kind=source.kind,
                organisation_unit_uid=organisation_unit_uid,
                status_code=response_status_code(_optional_text(entry.get("status"))),
                authored=_optional_text(entry.get("occurredAt")),
                tracked_entity_uid=_optional_text(entry.get("trackedEntity")),
                enrollment_uid=_optional_text(entry.get("enrollment")),
                answers=_event_answers(entry.get("dataValues")),
            )
        )
    return responses


async def _fetch_registration_responses(
    client: Dhis2Client, source: QuestionnaireSourceIn, per_target: int
) -> list[ExampleResponseIn]:
    """Read the most recently enrolled people of one tracker program as registration example responses.

    One response per enrollment rather than per tracked entity: a person may be enrolled in the
    same program twice, and each enrollment is one answer to the registration form. The attribute
    values ride on the tracked entity, so every enrollment of one person answers the same
    questions - which is exactly what DHIS2 holds, and what re-registering the person would send.
    """
    raw = await client.get_raw(
        "/api/tracker/trackedEntities",
        params={
            "program": source.uid,
            "pageSize": per_target,
            "order": "createdAt:desc",
            "fields": _EXAMPLE_TRACKED_ENTITY_FIELDS,
        },
    )
    responses: list[ExampleResponseIn] = []
    for entry in _tracked_entity_entries(raw):
        tracked_entity_uid = _optional_text(entry.get("trackedEntity"))
        if tracked_entity_uid is None:
            continue
        answers = _registration_answers(entry.get("attributes"))
        for enrollment in _program_enrollments(entry.get("enrollments"), source.uid):
            enrollment_uid = _optional_text(enrollment.get("enrollment"))
            organisation_unit_uid = _optional_text(enrollment.get("orgUnit"))
            enrolled_at = _optional_text(enrollment.get("enrolledAt"))
            incident_at = _optional_text(enrollment.get("occurredAt")) if source.displays_incident_date else None
            if enrollment_uid is None or organisation_unit_uid is None:
                continue
            responses.append(
                ExampleResponseIn(
                    instance_id=enrollment_uid,
                    target_uid=source.uid,
                    kind="tracker",
                    organisation_unit_uid=organisation_unit_uid,
                    status_code=COMPLETED_STATUS,
                    authored=enrolled_at,
                    tracked_entity_uid=tracked_entity_uid,
                    enrollment_uid=enrollment_uid,
                    enrolled_at=enrolled_at,
                    incident_at=incident_at,
                    answers=answers,
                )
            )
    return responses[:per_target]


def _tracked_entity_entries(raw: dict[str, object]) -> list[dict[str, object]]:
    """The tracked entity list of a tracker response, under whichever envelope key the instance answered with."""
    for key in _TRACKED_ENTITY_ENVELOPE_KEYS:
        entries = raw.get(key)
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]
    return []


def _program_enrollments(raw_enrollments: object, program_uid: str) -> list[dict[str, object]]:
    """One person's enrollments in the program the registration form was generated from, newest first.

    The program is filtered here rather than assumed: a person tracked in several programs
    carries an enrollment for each, and only the ones in this program answer this form. The
    order is the enrollment date and then the UID, so a regenerate of unchanged instance data
    picks the same enrollments whatever order DHIS2 answered in.
    """
    entries = [
        entry
        for entry in (raw_enrollments if isinstance(raw_enrollments, list) else [])
        if isinstance(entry, dict) and _optional_text(entry.get("program")) == program_uid
    ]
    entries.sort(key=_enrollment_sort_key, reverse=True)
    return entries


def _enrollment_sort_key(entry: dict[str, object]) -> tuple[str, str]:
    """The order one person's enrollments are read in: the enrollment date, then the enrollment UID."""
    return (_optional_text(entry.get("enrolledAt")) or "", _optional_text(entry.get("enrollment")) or "")


def _registration_answers(raw_attributes: object) -> list[ExampleAnswerIn]:
    """Map one tracked entity's attribute values into the example projection, keyed by attribute UID."""
    answers: list[ExampleAnswerIn] = []
    for entry in raw_attributes if isinstance(raw_attributes, list) else []:
        if not isinstance(entry, dict):
            continue
        attribute_uid = _optional_text(entry.get("attribute"))
        value = entry.get("value")
        if attribute_uid is None or not isinstance(value, str):
            continue
        answers.append(ExampleAnswerIn(data_element_uid=attribute_uid, value=value))
    return answers


def _event_entries(raw: dict[str, object]) -> list[dict[str, object]]:
    """The event list of a tracker response, under whichever envelope key the instance answered with."""
    for key in _EVENT_ENVELOPE_KEYS:
        entries = raw.get(key)
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]
    return []


def _event_answers(raw_values: object) -> list[ExampleAnswerIn]:
    """Map one event's data values into the example projection; events carry no category option combo."""
    answers: list[ExampleAnswerIn] = []
    for entry in raw_values if isinstance(raw_values, list) else []:
        if not isinstance(entry, dict):
            continue
        data_element_uid = _optional_text(entry.get("dataElement"))
        value = entry.get("value")
        if data_element_uid is None or not isinstance(value, str):
            continue
        answers.append(ExampleAnswerIn(data_element_uid=data_element_uid, value=value))
    return answers


#: The sweep collection each questionnaire form kind is reported under by `d2w fhir validate`, so the
#: generate refusal and the validation finding name one object the same way.
_SOURCE_CODE_COLLECTIONS: dict[str, str] = {
    "aggregate": "dataSets",
    "event": "programs",
    "tracker": "programs",
    "tracker-event": "programStages",
    "tracked-entity": "trackedEntityTypes",
}


def _coded_source(source: QuestionnaireSourceIn) -> _CodedObject:
    """One questionnaire target as the code gate reads it, named by the DHIS2 collection it came from."""
    return _CodedObject(
        resource_type=_SOURCE_CODE_COLLECTIONS[source.kind],
        uid=source.uid,
        name=source.name,
        code=source.dhis2_code,
    )


def _published_sources(sources: list[QuestionnaireSourceIn]) -> list[QuestionnaireSourceIn]:
    """The forms the questionnaire target really writes a Questionnaire for.

    A form that would emit one `linkId` twice is skipped whole by the questionnaire target, which
    says so once in its own report. Examples and pages read the same list and drop the same forms
    without a second note: an example declaring itself against a Questionnaire nobody wrote is an
    unresolvable canonical, and an intro page narrates an artifact the guide does not hold.
    """
    return [source for source in sources if not link_id_collisions(source)]


def _artifacts_under(artifacts: list[FshArtifact], directory: str) -> list[FshArtifact]:
    """The artifacts one sync directory owns - each directory is swept against its own files alone."""
    return [artifact for artifact in artifacts if artifact.relative_path.startswith(f"{directory}/")]


async def _fetch_organisation_units(
    client: Dhis2Client, config: GenerateConfig, tally: GeometryTally, today: date, progress: _StepAnnouncer
) -> list[OrganisationUnitIn]:
    """Page the configured slice of the DHIS2 hierarchy into the emitter projection, ordered by path.

    The longest single read of a generate run on a national hierarchy, so the running count goes
    onto the reporter's transient caption between pages and the total onto it once the walk ends.
    A caption is overwritten rather than printed, so a fifty-page walk is no more chatty than a
    one-page one, and the plain reporter renders no caption at all.
    """
    filters = _organisation_unit_selection_filters(config)
    organisation_units: list[OrganisationUnitIn] = []
    page = 1
    while True:
        models = await client.resources.organisation_units.list(
            fields=_ORGANISATION_UNIT_FIELDS,
            filters=filters or None,
            order=["path:asc"],
            page=page,
            page_size=_STREAM_PAGE_SIZE,
            paging=True,
        )
        for model in models:
            mapped = _organisation_unit_input(model, tally, today)
            if mapped is not None:
                organisation_units.append(mapped)
        if len(models) < _STREAM_PAGE_SIZE:
            break
        progress.tick(f"organisation units: {len(organisation_units):,} read...")
        page += 1
    progress.tick(f"organisation units: {len(organisation_units):,} read across {page} page(s)")
    return organisation_units


def _organisation_unit_selection_filters(config: GenerateConfig) -> list[str]:
    """The server-side filters `[generate.organisation_units]` narrows the hierarchy with."""
    selection = config.organisation_units
    filters: list[str] = []
    if selection.root is not None:
        filters.append(f"path:like:{selection.root}")
    if selection.max_level is not None:
        filters.append(f"level:le:{selection.max_level}")
    return filters


async def _fetch_organisation_unit_levels(client: Dhis2Client) -> list[OrganisationUnitLevelIn]:
    """Read what the instance calls each depth of its hierarchy - one unpaged read of the level table.

    A hierarchy is a handful of levels deep however many units hang off it, so the whole table
    comes back in a single request. A row stating no depth names nothing the guide can publish a
    concept under, so it is dropped.
    """
    models: list[OrganisationUnitLevel] = await client.resources.organisation_unit_levels.list(
        fields=_ORGANISATION_UNIT_LEVEL_FIELDS,
        paging=False,
    )
    return [
        OrganisationUnitLevelIn(
            level=model.level,
            name=model.name,
            uid=model.id,
            translations=_translation_inputs(model.translations),
        )
        for model in models
        if model.level is not None
    ]


async def _fetch_published_organisation_unit_uids(client: Dhis2Client, config: GenerateConfig) -> frozenset[str]:
    """Read the UID of every organisation unit the registry target publishes a Location for.

    The ids alone, unpaged, under the same filters the registry walk applies - a single small read
    even on a national hierarchy, which is what lets the validation scope apply the same
    out-of-selection guard the generate targets apply without repeating the registry's full walk.
    """
    models: list[OrganisationUnit] = await client.resources.organisation_units.list(
        fields="id",
        filters=_organisation_unit_selection_filters(config) or None,
        paging=False,
    )
    return frozenset(model.id for model in models if model.id)


async def _fetch_published_organisation_unit_stems(client: Dhis2Client, config: GenerateConfig) -> StemResolution:
    """Resolve the registry selection's identity stems off a light id/code/name read.

    The same selection filters the registry walk applies, in a projection carrying only what stem
    resolution reads, and resolved through the very `plan_organisation_unit_stems` call the
    registry resolves through - so the examples and load-set targets reference exactly the
    Location ids the registry writes without repeating its full hierarchy walk. The resolution's
    keys double as the published-unit set, and its fall-back notes belong to the registry
    target's report rather than to the caller's.
    """
    models: list[OrganisationUnit] = await client.resources.organisation_units.list(
        fields="id,code,name",
        filters=_organisation_unit_selection_filters(config) or None,
        paging=False,
    )
    subjects = [
        StemSubject(uid=model.id, code=model.code, label=model.name or model.id) for model in models if model.id
    ]
    return plan_organisation_unit_stems(subjects, config.naming.source)


def _registry_scale_notes(organisation_unit_count: int) -> list[GenerateNote]:
    """Warn while generating when the registry is large enough to dominate the publisher's rendering pass."""
    instance_count = organisation_unit_count * _INSTANCES_PER_ORGANISATION_UNIT
    if instance_count < _REGISTRY_RENDER_COST_INSTANCES:
        return []
    return [
        generate_note(
            GenerateNoteCategory.BUILD_COST,
            f"{organisation_unit_count} organisation units emit {instance_count} instances. They ship as "
            "pre-built JSON so SUSHI never compiles them, but the IG publisher validates and renders every "
            "resource, so they set the wall clock of `make build` - a registry this size is hours, not "
            "minutes. Narrow it with `[generate.organisation_units]` max_level or root if the build is "
            "longer than you want; serving needs no build at all.",
        )
    ]


async def generate_organisation_units(
    profile: Profile,
    project: FhirProject,
    *,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
    gate: HostileNameGate | None = None,
) -> GenerateReport:
    """Generate the profiles and terminology into `organization/`, and the instance registry into `registry/`.

    `client` is a connection the caller already holds open, which the run reads through and leaves
    open; with none, the profile opens one for the length of the call.

    `gate` is what the run does with a DHIS2 name the IG publisher's build cannot survive; with
    none, every name is published exactly as DHIS2 states it.
    """
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    tally = GeometryTally()
    today = datetime.now(tz=UTC).date()
    progress.step(_FETCH_LABEL, "fetching organisation units")
    async with _instance_connection(profile, client) as client:
        organisation_units = await _fetch_organisation_units(client, project.config.generate, tally, today, progress)
        level_rows = await _fetch_organisation_unit_levels(client)
        attribute_codes = await resolve_attribute_code_index(client)
    notes = tally.to_notes()
    # One gate for both reads, so a run asks its hostile-name question once over every name it is
    # about to publish - the units and the words the instance calls their depths.
    screening = _screening_gate(gate)
    organisation_units = screening.screen(organisation_units, notes)
    level_names = OrganisationUnitLevelNames(levels=screening.screen(level_rows, notes))
    progress.complete(f"{len(organisation_units):,} organisation unit(s)")
    return _emit_organisation_units(
        project,
        organisation_units=organisation_units,
        level_names=level_names,
        attribute_codes=attribute_codes,
        stems=plan_organisation_unit_stems(
            organisation_unit_stem_subjects(organisation_units), project.config.generate.naming.source
        ),
        notes=notes,
        progress=progress,
    )


def _emit_organisation_units(
    project: FhirProject,
    *,
    organisation_units: list[OrganisationUnitIn],
    level_names: OrganisationUnitLevelNames,
    attribute_codes: AttributeCodeIndex,
    stems: StemResolution,
    notes: list[GenerateNote],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the organisation-unit profiles, terminology, and registry off an already-paged hierarchy.

    `stems` is resolved by the caller at the fetch/plan level - under `source = "code"` an
    unusable code has therefore refused the run before this step opens - and the registry build
    raises its code-or-id fall-back notes onto this target's report.
    """
    progress.step(
        "organisation units", f"writing ig/input/fsh/organization and ig/input/resources/{REGISTRY_DIRECTORY}"
    )
    _refuse_build_aborting_objects(
        [
            _CodedObject(
                resource_type="organisationUnits",
                uid=organisation_unit.uid,
                name=organisation_unit.name,
                code=organisation_unit.dhis2_code,
            )
            for organisation_unit in organisation_units
        ]
    )
    selection = project.config.generate.organisation_units
    generate_config = project.config.generate
    ig_status = project.config.ig.status
    artifacts: list[FshArtifact] = [build_organisation_unit_profiles(generate_config, ig_status=ig_status)]
    registry: list[JsonArtifact] = []
    if organisation_units:
        artifacts.append(
            build_organisation_unit_level_terminology(
                [organisation_unit.level for organisation_unit in organisation_units],
                generate_config,
                level_names=level_names,
                ig_status=ig_status,
            )
        )
        instances = build_organisation_unit_instances(
            organisation_units,
            generate_config,
            project.config.ig.canonical,
            attribute_codes=attribute_codes,
            level_names=level_names,
            stems=stems,
        )
        registry = instances.artifacts
        notes.extend(instances.notes)
        examples = build_registry_examples(
            organisation_units, generate_config, level_names=level_names, ig_status=ig_status
        )
        if examples is not None:
            artifacts.append(examples)
        if selection.terminology:
            artifacts.append(
                build_organisation_unit_terminology(organisation_units, generate_config, ig_status=ig_status)
            )
    else:
        notes.append(
            generate_note(
                GenerateNoteCategory.EMPTY_SELECTION, "no organisation units matched the configured selection"
            )
        )
    notes.extend(_registry_scale_notes(len(organisation_units)))
    sync = sync_artifacts(project.fsh_directory, "organization", artifacts)
    registry_sync = sync_json_artifacts(project.resources_directory, REGISTRY_DIRECTORY, registry)
    notes.extend(_remove_stale_compile(project, sync))
    report = GenerateReport(
        project_root=project.project_root,
        target_base="ig/input",
        target_directory=f"fsh/organization, resources/{REGISTRY_DIRECTORY}",
        deleted_files=[*sync.deleted, *registry_sync.deleted],
        written_files=[*sync.written, *registry_sync.written],
        unchanged_count=len(sync.unchanged) + len(registry_sync.unchanged),
        organisation_unit_count=len(organisation_units),
        subject=GenerateSubject(count=len(organisation_units), noun="organisation unit"),
        position_count=sum(1 for organisation_unit in organisation_units if organisation_unit.latitude is not None),
        boundary_count=sum(
            1 for organisation_unit in organisation_units if organisation_unit.boundary_geojson is not None
        ),
        notes=notes,
    )
    progress.complete(_target_counts(report))
    return report


async def generate_pages(
    profile: Profile,
    project: FhirProject,
    *,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
    gate: HostileNameGate | None = None,
) -> GenerateReport:
    """Generate the narrative site pages and the per-artifact intros into `ig/input/pagecontent/`.

    `client` is a connection the caller already holds open, which the run reads through and leaves
    open; with none, the profile opens one for the length of the call.

    `gate` is what the run does with a DHIS2 name the IG publisher's build cannot survive; with
    none, every name is published exactly as DHIS2 states it.
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    screening = _screening_gate(gate)
    notes: list[GenerateNote] = []
    tally = GeometryTally()
    today = datetime.now(tz=UTC).date()
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets, option sets, and organisation units")
    async with _instance_connection(profile, client) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        organisation_units = await _fetch_organisation_units(client, config, tally, today, progress)
    option_sets = _selected_option_sets([_option_set_input(model) for model in models], sources, config, notes)
    screening.decide(sources, option_sets, organisation_units)
    sources = screening.screen(sources, notes)
    option_sets = screening.screen(option_sets, notes)
    organisation_units = screening.screen(organisation_units, notes)
    progress.complete(f"{len(sources):,} questionnaire target(s), {len(organisation_units):,} organisation unit(s)")
    return _emit_pages(
        project,
        sources=sources,
        option_sets=option_sets,
        organisation_units=organisation_units,
        stem_plan=plan_questionnaire_stems(sources, config.naming.source),
        organisation_unit_stems=plan_organisation_unit_stems(
            organisation_unit_stem_subjects(organisation_units), config.naming.source
        ),
        notes=notes,
        progress=progress,
    )


def _emit_pages(
    project: FhirProject,
    *,
    sources: list[QuestionnaireSourceIn],
    option_sets: list[OptionSetIn],
    organisation_units: list[OrganisationUnitIn],
    stem_plan: QuestionnaireStemPlan,
    organisation_unit_stems: StemResolution,
    notes: list[GenerateNote],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the narrative pages off what the other targets were built from - no second read of the instance.

    The forms are the ones the questionnaire target really writes: a form skipped for a `linkId`
    collision gets no catalog row and no intro, because the page would link an artifact the guide
    does not hold. `stem_plan` and `organisation_unit_stems` are the run's identity resolutions,
    so every artifact link and intro file name follows the ids the emitting targets wrote.
    """
    progress.step("pages", f"writing ig/{PAGES_BASE_SUBDIRECTORY}/{PAGES_DIRECTORY}")
    _refuse_build_aborting_form_objects(sources)
    _refuse_build_aborting_objects(
        [
            _CodedObject(
                resource_type="optionSets", uid=option_set.uid, name=option_set.name, code=option_set.dhis2_code
            )
            for option_set in option_sets
        ]
        + [
            _CodedObject(
                resource_type="organisationUnits",
                uid=organisation_unit.uid,
                name=organisation_unit.name,
                code=organisation_unit.dhis2_code,
            )
            for organisation_unit in organisation_units
        ]
    )
    _refuse_build_aborting_member_names(option_sets)
    pages = PagesIn(forms=_published_sources(sources), option_sets=option_sets, organisation_units=organisation_units)
    build = build_page_artifacts(
        pages,
        project.config.generate,
        project.config.ig.canonical,
        stem_plan=stem_plan,
        organisation_unit_stems=organisation_unit_stems,
    )
    sync = sync_artifacts(project.ig_directory / PAGES_BASE_SUBDIRECTORY, PAGES_DIRECTORY, build.artifacts)
    intro_count = sum(1 for artifact in build.artifacts if artifact.relative_path.endswith(INTRO_SUFFIX))
    report = GenerateReport(
        project_root=project.project_root,
        target_directory=PAGES_DIRECTORY,
        target_base=f"ig/{PAGES_BASE_SUBDIRECTORY}",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        page_count=len(build.artifacts) - intro_count,
        subject=GenerateSubject(count=len(build.artifacts) - intro_count, noun="page"),
        intro_count=intro_count,
        notes=[*notes, *build.notes],
    )
    progress.complete(_target_counts(report))
    return report


async def generate_full(
    profile: Profile,
    project: FhirProject,
    *,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
    gate: HostileNameGate | None = None,
) -> GenerateFullReport:
    """Generate every target off one connected client and one pass over the instance's metadata.

    The whole IG in a single run. The instance is read once - the questionnaire targets, every
    option set, the categories, the organisation-unit slice, and the run's attribute-code join -
    and each target then builds and syncs off that one result, so nothing is fetched a second
    time the way seven separate commands would fetch it. The foundation runs first because it
    reads nothing at all, and the pages run last because they narrate what the other targets
    wrote. Each target keeps every note its solo command would raise, so its report reads
    exactly as the solo command's does; a consumer reading the whole run takes
    `with_distinct_notes()` so a note shared across targets is reported once.

    `client` is a connection the caller already holds open, which the run reads through and leaves
    open; with none, the profile opens one for the length of the call.

    `gate` is what the run does with a DHIS2 name the IG publisher's build cannot survive. The
    whole run screens through one gate, so a run that asks asks once, over the count the whole
    instance read holds rather than the first target's share of it.
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_FULL_STEPS)
    progress.step(_FETCH_LABEL, "fetching instance metadata")
    async with _instance_connection(profile, client) as client:
        inputs = await fetch_live_ig_inputs(client, config, progress=progress, gate=gate)
        progress.complete(
            f"{len(inputs.sources):,} questionnaire target(s), {len(inputs.option_sets):,} option set(s), "
            f"{len(inputs.categories):,} categor{'y' if len(inputs.categories) == 1 else 'ies'}, "
            f"{len(inputs.organisation_units):,} organisation unit(s)"
        )
        foundation = _emit_foundation(project, progress=progress)
        option_sets = _emit_option_sets(
            project,
            option_sets=inputs.option_sets,
            attribute_codes=inputs.attribute_codes,
            notes=list(inputs.option_set_notes),
            progress=progress,
        )
        categories = _emit_categories(
            project,
            categories=inputs.categories,
            attribute_codes=inputs.attribute_codes,
            notes=list(inputs.category_notes),
            progress=progress,
        )
        questionnaires = _emit_questionnaires(
            project,
            sources=inputs.sources,
            option_set_plan=inputs.option_set_plan,
            option_sets=_bound_option_sets(inputs.sources, inputs.option_sets),
            attribute_codes=inputs.attribute_codes,
            categories=inputs.categories,
            stem_plan=inputs.questionnaire_stems,
            assignments=inputs.assignments,
            published_organisation_unit_stems=inputs.organisation_unit_stems,
            notes=list(inputs.source_notes),
            progress=progress,
        )
        examples = await _emit_examples(
            client,
            project,
            sources=inputs.sources,
            option_sets=_bound_option_sets(inputs.sources, inputs.option_sets),
            option_set_plan=inputs.option_set_plan,
            published_organisation_unit_uids=frozenset(
                organisation_unit.uid for organisation_unit in inputs.organisation_units
            ),
            stem_plan=inputs.questionnaire_stems,
            organisation_unit_stems=inputs.organisation_unit_stems,
            notes=list(inputs.source_notes),
            progress=progress,
        )
        organisation_units = _emit_organisation_units(
            project,
            organisation_units=inputs.organisation_units,
            level_names=inputs.organisation_unit_levels,
            attribute_codes=inputs.attribute_codes,
            stems=inputs.organisation_unit_stems,
            notes=list(inputs.geometry_notes),
            progress=progress,
        )
        pages = _emit_pages(
            project,
            sources=inputs.sources,
            option_sets=inputs.option_sets,
            organisation_units=inputs.organisation_units,
            stem_plan=inputs.questionnaire_stems,
            organisation_unit_stems=inputs.organisation_unit_stems,
            notes=[*inputs.source_notes, *inputs.option_set_notes],
            progress=progress,
        )
    return GenerateFullReport(
        foundation=foundation,
        option_sets=option_sets,
        categories=categories,
        questionnaires=questionnaires,
        examples=examples,
        organisation_units=organisation_units,
        pages=pages,
    )


def _bound_option_sets(sources: list[QuestionnaireSourceIn], option_sets: list[OptionSetIn]) -> list[OptionSetIn]:
    """The option sets the selected forms bind a question to - the slice the examples target reads.

    Always a subset of the selected sets: the selection carries the form closure alongside the
    configured UIDs, so an option set a question binds is in the list by construction.
    """
    bound_ids = _bound_option_set_uids(sources)
    return [option_set for option_set in option_sets if option_set.uid in bound_ids]


def _bound_option_set_uids(sources: list[QuestionnaireSourceIn]) -> set[str]:
    """The option sets the selected forms bind their data elements to."""
    return {
        item.option_set_uid for source in sources for item in _source_items(source) if item.option_set_uid is not None
    }


def _selected_option_set_uids(
    available: frozenset[str], bound: frozenset[str], selection: OptionSetSelection
) -> frozenset[str]:
    """The option-set UIDs one selection covers: every set when the table is empty, else configured plus closure.

    The single statement of what "a selected option set" means, shared by the generate-time
    filter and the validation scope so the two can never disagree.
    """
    if not selection.include_ids:
        return available
    return (frozenset(selection.include_ids) | bound) & available


class LiveIgInputs(BaseModel):
    """Every instance read the IG's resources are built from, fetched once off one connected client.

    The projection each generate target fetches for itself, gathered into a single result: the
    questionnaire targets, the selected option sets and their identity plan, the selected
    categories, the organisation-unit slice, and the run's attribute-code join. `notes` carries
    what the fetch itself raised - unmatched selection entries, the option-set closure, the
    geometry tally - for the caller to report alongside the notes its builders raise.

    The same notes are also split into the bucket each generate target owns, so a caller
    building every target off one fetch reports per target exactly what the solo command does:
    the closure belongs to the terminology target's report, the unmatched form UIDs to the
    questionnaire target's, and the geometry tally to the organisation-unit target's.
    """

    model_config = ConfigDict(frozen=True)

    sources: list[QuestionnaireSourceIn] = Field(default_factory=list)
    option_sets: list[OptionSetIn] = Field(default_factory=list)
    option_set_plan: OptionSetIdentityPlan
    categories: list[CategoryIn] = Field(default_factory=list)
    organisation_units: list[OrganisationUnitIn] = Field(default_factory=list)
    organisation_unit_levels: OrganisationUnitLevelNames = Field(default_factory=OrganisationUnitLevelNames)
    """What the instance calls each depth of its hierarchy - the display every level concept carries."""

    attribute_codes: AttributeCodeIndex
    assignments: AssignmentIndex = Field(default_factory=AssignmentIndex)
    """The organisation units each selected data set and program is assigned to, read id-only."""

    # W-2: identity-stem plans for the questionnaire and org-unit surfaces, resolved once per fetch.
    questionnaire_stems: QuestionnaireStemPlan
    organisation_unit_stems: StemResolution
    notes: list[GenerateNote] = Field(default_factory=list)
    source_notes: list[GenerateNote] = Field(default_factory=list)
    option_set_notes: list[GenerateNote] = Field(default_factory=list)
    category_notes: list[GenerateNote] = Field(default_factory=list)
    geometry_notes: list[GenerateNote] = Field(default_factory=list)


async def fetch_live_ig_inputs(
    client: Dhis2Client,
    config: GenerateConfig,
    *,
    progress: _StepAnnouncer | None = None,
    gate: HostileNameGate | None = None,
) -> LiveIgInputs:
    """Read the whole instance side of one IG build over a single client, in the generate targets' own projections.

    The shared fetch behind building the IG's documents without a disk round-trip: a caller
    passes the result straight to `build_questionnaire_documents`, `build_option_set_artifacts`,
    `build_category_artifacts`, and `build_organisation_unit_instances` and gets exactly what
    `d2w fhir generate full` would have written. The selection rules are the targets' own - each
    list is filtered by the configured UIDs, and the option sets additionally by the closure the
    selected forms bind - so the built resources agree with the compiled IG object for object.

    Every collection is read exactly once. The option-set identity plan is assigned off the same
    unfiltered read the terminology projection came from rather than a second narrower request,
    since a slug is decided by the UID and the name the first read already carries.

    `gate` is what the run does with a DHIS2 name the IG publisher's build cannot survive. This is
    the choke point every target of a full run inherits: the four projections are screened here,
    before a single identity, stem, or decomposition is planned off them, so the guide states one
    name for one DHIS2 object wherever it publishes it. A caller handing no gate - a live serve, a
    live forward - reads every name exactly as DHIS2 states it.
    """
    steps = progress if progress is not None else _StepAnnouncer()
    screening = _screening_gate(gate)
    source_notes: list[GenerateNote] = []
    option_set_notes: list[GenerateNote] = []
    category_notes: list[GenerateNote] = []
    tally = GeometryTally()
    today = datetime.now(tz=UTC).date()
    steps.tick("reading the questionnaire targets")
    sources = await _fetch_questionnaire_sources(client, config, source_notes)
    steps.tick("reading option sets")
    option_set_models = await client.resources.option_sets.list(
        fields=_OPTION_SET_FIELDS,
        order=["name:asc"],
        paging=False,
    )
    fetched_option_sets = [_option_set_input(model) for model in option_set_models]
    option_sets = _selected_option_sets(fetched_option_sets, sources, config, option_set_notes)
    steps.tick("reading categories")
    categories = await _fetch_categories(client, config, category_notes)
    organisation_units = await _fetch_organisation_units(client, config, tally, today, steps)
    level_rows = await _fetch_organisation_unit_levels(client)
    geometry_notes = tally.to_notes()
    # The one screening a full run takes: the answer is settled over every projection at once, so
    # a run that asks states the whole instance read's count, and each projection then carries its
    # rewrites into the notes of the target that owns it.
    screening.decide(sources, option_sets, categories, organisation_units, level_rows)
    sources = screening.screen(sources, source_notes)
    option_sets = screening.screen(option_sets, option_set_notes)
    categories = screening.screen(categories, category_notes)
    organisation_units = screening.screen(organisation_units, geometry_notes)
    organisation_unit_levels = OrganisationUnitLevelNames(levels=screening.screen(level_rows, geometry_notes))
    option_set_plan = _option_set_identity_plan(screening.screen(fetched_option_sets, []), config, sources)
    steps.tick("reading the attribute-code join")
    attribute_codes = await resolve_attribute_code_index(client)
    steps.tick("reading the organisation-unit assignments")
    assignments = await fetch_assignment_index(client, sources)
    # W-2: the identity stems resolve at the fetch/plan level, so a `source = "code"` refusal
    # raises here - before any target writes a file - and every consumer reads one resolution.
    questionnaire_stems = plan_questionnaire_stems(sources, config.naming.source)
    organisation_unit_stems = plan_organisation_unit_stems(
        organisation_unit_stem_subjects(organisation_units), config.naming.source
    )
    return LiveIgInputs(
        sources=sources,
        option_sets=option_sets,
        option_set_plan=option_set_plan,
        categories=categories,
        organisation_units=organisation_units,
        organisation_unit_levels=organisation_unit_levels,
        attribute_codes=attribute_codes,
        assignments=assignments,
        questionnaire_stems=questionnaire_stems,
        organisation_unit_stems=organisation_unit_stems,
        notes=[*source_notes, *option_set_notes, *category_notes, *geometry_notes],
        source_notes=source_notes,
        option_set_notes=option_set_notes,
        category_notes=category_notes,
        geometry_notes=geometry_notes,
    )


#: What a live-built Questionnaire names as its source in a diagnostic, where a compiled one names the
#: file it was read from. Every other live document is named by the path the build would have written.
_LIVE_ARTIFACT_SOURCE = "built live"


async def fetch_live_artifacts(
    client: Dhis2Client, project: FhirProject, *, progress: _StepAnnouncer | None = None
) -> CompiledArtifacts:
    """Build the artifacts the translator reads off the instance, for a project holding no compiled guide.

    The forward-side twin of `d2w fhir serve --live`. Both read the instance through
    `fetch_live_ig_inputs` and hand the result to the same document builders, so the forms a live
    capture UI served and the forms a live forward translates against are built by the same code
    from the same read - which is what makes a receipt captured without a build step forwardable
    without one.

    Only the five resource types `collect_artifacts` keeps are built, and only the builders that
    produce them: the Questionnaires a response answers, the option-set and category terminology a
    coded answer resolves against, the attribute-option-combo vocabulary an aggregate response is
    keyed by, the ConceptMaps that carry the DHIS2 spellings back under code-mode naming, and the
    Locations a `Location/<id>` reference resolves to an organisation unit UID through. The
    foundation terminology and the data dictionary a served store also holds say nothing the
    response direction reads, so a forward does not pay to build them.

    The cost is a full metadata read per drain, where a compiled guide is read from disk. That is
    the trade a project without a build step takes, and the caller narrates it.
    """
    config = project.config.generate
    canonical = project.config.ig.canonical
    ig_status = project.config.ig.status
    inputs = await fetch_live_ig_inputs(client, config, progress=progress)
    assignments = build_assignment_artifacts(
        inputs.sources,
        inputs.assignments,
        config,
        published=inputs.organisation_unit_stems,
        stem_plan=inputs.questionnaire_stems,
    )
    decomposition = build_category_decomposition(inputs.sources, inputs.categories, config, canonical)
    attribute_combos = build_attribute_combo_artifacts(
        inputs.sources, config, canonical, ig_status=ig_status, decomposition=decomposition
    )
    questionnaires = build_questionnaire_documents(
        inputs.sources,
        config,
        canonical,
        ig_status=ig_status,
        option_set_plan=inputs.option_set_plan,
        attribute_codes=inputs.attribute_codes,
        option_sets=_bound_option_sets(inputs.sources, inputs.option_sets),
        assignments=assignments.plan,
        attribute_combos=attribute_combos.plan,
    )
    json_builds: tuple[JsonBuild, ...] = (
        build_option_set_artifacts(
            inputs.option_sets, config, canonical, ig_status=ig_status, attribute_codes=inputs.attribute_codes
        ),
        JsonBuild(
            artifacts=build_option_set_concept_map_artifacts(inputs.option_sets, config, canonical, ig_status=ig_status)
        ),
        build_category_artifacts(
            inputs.categories, config, canonical, ig_status=ig_status, attribute_codes=inputs.attribute_codes
        ),
        JsonBuild(
            artifacts=build_category_concept_map_artifacts(inputs.categories, config, canonical, ig_status=ig_status)
        ),
        build_organisation_unit_instances(
            inputs.organisation_units,
            config,
            canonical,
            attribute_codes=inputs.attribute_codes,
            level_names=inputs.organisation_unit_levels,
        ),
        attribute_combos,
        JsonBuild(
            artifacts=build_attribute_combo_concept_map_artifacts(
                inputs.sources, config, canonical, ig_status=ig_status
            )
        ),
    )
    documents = [
        SourcedDocument(source=_LIVE_ARTIFACT_SOURCE, body=_wire_document(questionnaire))
        for questionnaire in questionnaires.questionnaires
    ]
    documents.extend(
        SourcedDocument(source=artifact.relative_path, body=json.loads(artifact.content))
        for build in json_builds
        for artifact in build.artifacts
    )
    return collect_artifacts(documents)


def _wire_document(resource: BaseModel) -> dict[str, Any]:
    """One built resource as the wire document a guide publishes it as, aliases applied and absences dropped."""
    return resource.model_dump(mode="json", by_alias=True, exclude_none=True)


def _selected_option_sets(
    inputs: list[OptionSetIn], sources: list[QuestionnaireSourceIn], config: GenerateConfig, notes: list[GenerateNote]
) -> list[OptionSetIn]:
    """Filter option sets by the configured UIDs plus the target closure, noting entries that matched nothing."""
    selection = config.option_sets
    if not selection.include_ids:
        return inputs
    wanted_ids = _selected_option_set_uids(
        frozenset(item.uid for item in inputs),
        frozenset(_option_set_closure(sources, config, notes)),
        selection,
    )
    selected = [item for item in inputs if item.uid in wanted_ids]
    selected_ids = {item.uid for item in selected}
    for uid in sorted(set(selection.include_ids) - selected_ids):
        notes.append(
            generate_note(GenerateNoteCategory.SELECTION_MISMATCH, f"include_ids entry {uid!r} matched no option set")
        )
    return selected


async def _fetch_option_set_identity_plan(
    client: Dhis2Client, config: GenerateConfig, sources: list[QuestionnaireSourceIn], gate: HostileNameGate
) -> OptionSetIdentityPlan:
    """Assign the option-set identities for one generate run, off the very selection the terminology target emits.

    A slug is assigned against its peers - truncation and collision suffixes both depend on the
    whole list - so every target that names an option set has to plan over the identical
    selection. The projection is narrower than the terminology target's because a slug is
    decided by the UID and the name alone. The selection notes belong to the terminology
    target's report, so they are not raised a second time here.

    The names are screened before a slug is read off them, so a form binding an `answerValueSet`
    names the ValueSet the terminology target really writes. The rewrite notes belong to that
    target's report too, which is why none is kept here.
    """
    models = await client.resources.option_sets.list(
        fields=_OPTION_SET_IDENTITY_FIELDS,
        order=["name:asc"],
        paging=False,
    )
    inputs = [OptionSetIn(uid=model.id or "", name=model.name or model.id or "") for model in models]
    return option_set_identities(gate.screen(_selected_option_sets(inputs, sources, config, []), []), config)


def _option_set_identity_plan(
    option_sets: list[OptionSetIn], config: GenerateConfig, sources: list[QuestionnaireSourceIn]
) -> OptionSetIdentityPlan:
    """Assign the option-set identities off an unfiltered list already read in the terminology projection.

    The plan `_fetch_option_set_identity_plan` reads a second, narrower request for, without the
    request: a slug is decided by the UID and the name alone, so the wider projection is narrowed
    here and planned over the identical selection. The selection notes belong to the terminology
    target's report and are not raised a second time.
    """
    inputs = [OptionSetIn(uid=option_set.uid, name=option_set.name) for option_set in option_sets]
    return option_set_identities(_selected_option_sets(inputs, sources, config, []), config)


async def resolve_attribute_code_index(client: Dhis2Client) -> AttributeCodeIndex:
    """Resolve the `uid -> code` join for every DHIS2 attribute, once per generate run.

    The projections carry an attribute value as the UID and value DHIS2 sent, so the index is
    what turns one into a coded emission. It is fetched the way the option-set identity plan is:
    once, off the whole instance, so every target of a run joins against the identical mapping.

    Unpaged: DHIS2 answers 50 attributes to a page by default, and an instance defining more
    than one page of them would otherwise lose the tail of the join silently. Attributes DHIS2
    left without a code are absent from the index - most instances code few of theirs.

    The same read carries `unique`, which decides whether an attribute's values are emitted as
    identifiers or as annotation extensions.
    """
    models: list[Attribute] = await client.resources.attributes.list(fields=_ATTRIBUTE_FIELDS, paging=False)
    return AttributeCodeIndex(
        codes={model.id: model.code for model in models if model.id and model.code},
        unique_uids=frozenset(model.id for model in models if model.id and model.unique),
    )


async def _closure_sources(client: Dhis2Client, config: GenerateConfig) -> list[QuestionnaireSourceIn]:
    """Fetch the questionnaire targets the option-set closure reads, or nothing when the closure is a no-op.

    An empty `[generate.option_sets] include_ids` already means every option set, so the
    closure is a no-op there and the targets are not fetched a second time.
    """
    if not config.option_sets.include_ids:
        return []
    return await _fetch_questionnaire_sources(client, config, [])


def _option_set_closure(
    sources: list[QuestionnaireSourceIn], config: GenerateConfig, notes: list[GenerateNote]
) -> set[str]:
    """Collect the option sets the selected forms bind their data elements to, noting the additions."""
    closure = _bound_option_set_uids(sources)
    added = sorted(closure - set(config.option_sets.include_ids))
    if added:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.SELECTION_CLOSURE,
                f"{len(added)} option sets added by the form closure - what the selected data sets, event "
                "programs, tracker registration forms, and tracker stages bind their questions to",
                added,
            )
        )
    return closure


async def _fetch_questionnaire_sources(
    client: Dhis2Client, config: GenerateConfig, notes: list[GenerateNote]
) -> list[QuestionnaireSourceIn]:
    """Fetch the selected data sets, programs, and tracked entity types as the Questionnaire projection.

    An absent or empty `include_ids` selects everything the instance holds of that table's kind,
    matching the terminology targets; a table with `enabled = false` selects nothing and is not
    read. Data sets come first, then the programs, then the tracked entity types - whose default
    is not the whole instance but the types the selected tracker programs track, so a project
    selecting one program publishes a person-only form for the kind of person that program
    registers rather than for every kind the instance knows.
    """
    sources: list[QuestionnaireSourceIn] = []
    if config.data_sets.enabled:
        data_set_ids = config.data_sets.include_ids
        data_sets = await client.resources.data_sets.list(
            fields=_DATA_SET_FIELDS,
            filters=[_uid_filter(data_set_ids)] if data_set_ids else None,
            order=["name:asc"],
            paging=False,
        )
        sources.extend(_data_set_source(model, notes) for model in data_sets)
        if data_set_ids:
            _note_unmatched(data_set_ids, {model.id for model in data_sets}, "data_sets", "data set", notes)
    sources.extend(await _fetch_program_sources(client, config, notes))
    sources.extend(await _fetch_tracked_entity_type_sources(client, config, sources, notes))
    return sources


async def _fetch_tracked_entity_type_sources(
    client: Dhis2Client,
    config: GenerateConfig,
    sources: list[QuestionnaireSourceIn],
    notes: list[GenerateNote],
) -> list[QuestionnaireSourceIn]:
    """Fetch the tracked entity types that publish a person-only registration form, in one read.

    The selection is `[generate.tracked_entity_forms] include_ids` where it names anything, and the
    types the run's tracker programs already track where it does not. Both are a filtered read, so
    a run selecting no tracker programs and naming no types costs no request at all, and neither
    does a table switched off.
    """
    if not config.tracked_entity_forms.enabled:
        return []
    selected = config.tracked_entity_forms.include_ids
    uids = selected or sorted(
        {uid for source in sources if source.kind == "tracker" and (uid := source.tracked_entity_type_uid)}
    )
    if not uids:
        return []
    models: list[TrackedEntityType] = await client.resources.tracked_entity_types.list(
        fields=_TRACKED_ENTITY_TYPE_FIELDS,
        filters=[_uid_filter(uids)],
        order=["name:asc"],
        paging=False,
    )
    if selected:
        _note_unmatched(selected, {model.id for model in models}, "tracked_entity_forms", "tracked entity type", notes)
    return [_tracked_entity_type_source(model, notes) for model in models]


async def _fetch_program_sources(
    client: Dhis2Client, config: GenerateConfig, notes: list[GenerateNote]
) -> list[QuestionnaireSourceIn]:
    """Fetch the programs of both selection tables: one source per event program, one per tracker stage.

    Each table is read on its own terms. A non-empty `include_ids` is a filtered fetch whose
    every member is routed to that table's program type - a program of the other type is refused
    by name, pointing at the table it belongs under. An empty table means every program of its
    type, read off one unfiltered fetch and split by `programType`. With both tables empty a
    single sweep serves both, and the program types neither table maps are collected into one note.
    A table with `enabled = false` contributes nothing and is not read; with both off, the program
    rules are not read either, since no form is left for them to reach.
    """
    events_enabled = config.event_programs.enabled
    trackers_enabled = config.tracker_programs.enabled
    if not events_enabled and not trackers_enabled:
        return []
    event_ids = config.event_programs.include_ids
    tracker_ids = config.tracker_programs.include_ids
    variables: dict[str, list[ProgramRuleVariableIn]] = {}
    if events_enabled and trackers_enabled and not event_ids and not tracker_ids:
        swept = await _list_programs(client, None)
        variables.update({model.id or "": _program_rule_variable_inputs(model) for model in swept})
        return _with_program_rules(_swept_program_sources(swept, notes), await _fetch_program_rules(client), variables)
    sources: list[QuestionnaireSourceIn] = []
    if events_enabled and event_ids:
        selected = await _list_programs(client, event_ids)
        sources.extend(_event_program_source(model, notes) for model in selected)
        variables.update({model.id or "": _program_rule_variable_inputs(model) for model in selected})
        _note_unmatched(event_ids, {model.id for model in selected}, "event_programs", "event program", notes)
    elif events_enabled:
        swept = await _list_programs(client, None)
        events = [model for model in swept if _program_type(model) == _EVENT_PROGRAM_TYPE]
        sources.extend(_event_program_source(model, notes) for model in events)
        variables.update({model.id or "": _program_rule_variable_inputs(model) for model in events})
    if trackers_enabled and tracker_ids:
        selected = await _list_programs(client, tracker_ids)
        for model in selected:
            sources.extend(_tracker_program_sources(model, notes))
            variables[model.id or ""] = _program_rule_variable_inputs(model)
        _note_unmatched(tracker_ids, {model.id for model in selected}, "tracker_programs", "tracker program", notes)
    elif trackers_enabled:
        swept = await _list_programs(client, None)
        for model in swept:
            if _program_type(model) == _TRACKER_PROGRAM_TYPE:
                sources.extend(_tracker_program_sources(model, notes))
                variables[model.id or ""] = _program_rule_variable_inputs(model)
    return _with_program_rules(sources, await _fetch_program_rules(client), variables)


async def _fetch_program_rules(client: Dhis2Client) -> ProgramRuleIndex:
    """Read every program rule the instance holds, in one request, indexed by the program it belongs to.

    The one read this target adds. `programRuleVariables` is a collection on Program and rides the
    program projection the forms already cost, but `programRules` is not on the Program schema at
    all - DHIS2 drops the field from the projection without complaint rather than answering it - so
    the rules cost a request of their own. Unfiltered, because a run selecting no program at all
    still costs one request and the rules of every published program then need no second read.
    """
    models: list[ProgramRule] = await client.resources.program_rules.list(
        fields=_PROGRAM_RULE_FIELDS, order=["name:asc"], paging=False
    )
    index = ProgramRuleIndex()
    for model in models:
        program_uid = _referenced_uid(model.program)
        if program_uid is None:
            continue
        index.rules_by_program.setdefault(program_uid, []).append(_program_rule_input(model))
    return index


def _program_rule_input(model: ProgramRule) -> ProgramRuleIn:
    """Map one wire program rule onto the projection the emitters read it through."""
    uid = model.id or ""
    return ProgramRuleIn(
        uid=uid,
        name=model.name or uid,
        description=model.description,
        condition=model.condition or "",
        translations=_translation_inputs(model.translations),
        actions=[
            ProgramRuleActionIn(
                action_type=_optional_text(action.get("programRuleActionType")) or "",
                data_element_uid=_referenced_uid(action.get("dataElement")),
                tracked_entity_attribute_uid=_referenced_uid(action.get("trackedEntityAttribute")),
            )
            for action in model.programRuleActions or []
            if isinstance(action, dict)
        ],
    )


def _program_rule_variable_inputs(model: Program) -> list[ProgramRuleVariableIn]:
    """The rule variables one program declares, read off the program projection they ride in on."""
    return [
        ProgramRuleVariableIn(
            name=_optional_text(variable.get("name")) or "",
            source_type=_optional_text(variable.get("programRuleVariableSourceType")) or "",
            data_element_uid=_referenced_uid(variable.get("dataElement")),
            tracked_entity_attribute_uid=_referenced_uid(variable.get("trackedEntityAttribute")),
        )
        for variable in model.programRuleVariables or []
        if isinstance(variable, dict)
    ]


def _referenced_uid(reference: object) -> str | None:
    """The UID one wire reference names, whichever shape it arrives in, or None where DHIS2 sent none.

    A projection the generated model declares - `ProgramRule.program` - arrives as a typed
    `Reference`, and one it does not - a rule action's data element, nested inside a collection the
    model leaves loose - arrives as the raw object. Both are the same DHIS2 fact, so both are read
    here rather than at each call site.
    """
    uid = reference.get("id") if isinstance(reference, dict) else getattr(reference, "id", None)
    return _optional_text(uid)


def _with_program_rules(
    sources: list[QuestionnaireSourceIn],
    rules: ProgramRuleIndex,
    variables: dict[str, list[ProgramRuleVariableIn]],
) -> list[QuestionnaireSourceIn]:
    """Carry each program's rules and rule variables onto every form that program publishes.

    A rule is the program's rather than one stage's, so a stage form, its siblings, and the
    registration form beside them all state the same list: a consumer holding one form learns from
    that form alone which rules the server may refuse its answers under.
    """
    carried: list[QuestionnaireSourceIn] = []
    for source in sources:
        program_uid = source.program.uid if source.kind == "tracker-event" and source.program else source.uid
        carried.append(
            source.model_copy(
                update={
                    "program_rules": rules.rules_by_program.get(program_uid, []),
                    "program_rule_variables": variables.get(program_uid, []),
                }
            )
        )
    return carried


async def _list_programs(client: Dhis2Client, uids: list[str] | None) -> list[Program]:
    """Read the programs of one selection table, by name, filtered to `uids` when the table names any."""
    models: list[Program] = await client.resources.programs.list(
        fields=_PROGRAM_FIELDS,
        filters=[_uid_filter(uids)] if uids else None,
        order=["name:asc"],
        paging=False,
    )
    return models


def _swept_program_sources(models: list[Program], notes: list[GenerateNote]) -> list[QuestionnaireSourceIn]:
    """Route every program of a whole-instance sweep to its form kind, noting the types neither table maps."""
    sources: list[QuestionnaireSourceIn] = []
    unmapped: list[str] = []
    for model in models:
        program_type = _program_type(model)
        if program_type == _EVENT_PROGRAM_TYPE:
            sources.append(_event_program_source(model, notes))
        elif program_type == _TRACKER_PROGRAM_TYPE:
            sources.extend(_tracker_program_sources(model, notes))
        else:
            unmapped.append(f"{model.name or model.id or ''} ({model.id or ''})")
    if unmapped:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.REFUSED_FORM,
                f"{len(unmapped)} programs have a programType the questionnaire target does not map; skipped",
                unmapped,
            )
        )
    return sources


def _program_type(model: Program) -> str:
    """The program's live `programType`, or `unknown` when the instance sent none."""
    return str(model.programType) if model.programType is not None else "unknown"


def _program_stages(model: Program) -> list[dict[str, object]]:
    """The program's stages as the wire sends them."""
    return [stage for stage in model.programStages or [] if isinstance(stage, dict)]


def _sort_order(raw: dict[str, object]) -> int:
    """One wire object's DHIS2 `sortOrder`, placing an object the instance sent none for after its peers."""
    value = raw.get("sortOrder")
    if isinstance(value, bool) or not isinstance(value, int):
        return _UNORDERED_SORT_POSITION
    return value


def _stage_sort_key(stage: dict[str, object]) -> tuple[int, str, str]:
    """The order one tracker program's stages are emitted in: DHIS2 sort order, then name, then UID."""
    uid = _optional_text(stage.get("id")) or ""
    return (_sort_order(stage), _optional_text(stage.get("name")) or uid, uid)


def _uid_filter(uids: list[str]) -> str:
    """The DHIS2 metadata filter selecting exactly the configured UIDs."""
    return f"id:in:[{','.join(uids)}]"


def _note_unmatched(
    configured_ids: list[str], found_ids: set[str | None], table: str, label: str, notes: list[GenerateNote]
) -> None:
    """Note the configured UIDs the instance answered nothing for, rather than dropping them silently."""
    missing = [uid for uid in configured_ids if uid not in found_ids]
    if missing:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.SELECTION_MISMATCH,
                f"{len(missing)} [generate.{table}] include_ids entries matched no {label}",
                missing,
            )
        )


def _data_set_source(model: DataSet, notes: list[GenerateNote]) -> QuestionnaireSourceIn:
    """Map a generated DataSet into the Questionnaire projection, joining sections to their data elements.

    `dataSetElements` is a Java `Set` with no sort order, and DHIS2 serialises it in a different
    order on every request (BUGS.md #63), so the members are ordered here by name and UID. Two
    things depend on that: a regenerate of an unchanged data set produces an unchanged file, and
    the example responses - fetched by a separate request - answer the questionnaire's items in
    the questionnaire's own order, which the FHIR validator requires. Section membership is
    joined by UID and keeps the section's own sort order, which DHIS2 does hold.

    `compulsoryDataElementOperands` is what makes a data set's questions mandatory, at either of
    two grains: an operand naming a data element alone requires the whole element, an operand
    naming a category option combo too requires that single disaggregated cell.

    `sections[].greyedFields` is the opposite operand list - the cells the data set never captures -
    and those cells are dropped rather than published, because a form must not ask a question the
    instance refuses an answer to.
    """
    uid = model.id or ""
    compulsory = _compulsory_operands(model)
    greyed = _greyed_operand_keys(model)
    items: list[QuestionnaireItemIn] = []
    dropped: list[str] = []
    for element in model.dataSetElements or []:
        item = _data_set_item(element, compulsory)
        if item is None:
            continue
        published = _without_greyed_cells(item, greyed)
        dropped.extend(_dropped_cell_keys(item, published))
        if published is not None:
            items.append(published)
    items.sort(key=lambda item: (item.name, item.uid))
    if dropped:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.FORM_STRUCTURE,
                f"data set {model.name or uid!r} ({uid}) greys out {len(dropped)} disaggregated cells, which "
                "are not published; a response answering one would not be of the form",
                sorted(dropped),
            )
        )
    return _questionnaire_source(
        uid=uid,
        name=model.name or uid,
        code=model.code,
        description=model.description,
        translations=_translation_inputs(model.translations),
        kind="aggregate",
        period_type=str(model.periodType) if model.periodType is not None else None,
        items=items,
        raw_sections=model.sections,
        attribute_values=_attribute_value_inputs(model.attributeValues),
        attribute_combo=_category_combo_input(_attribute_combo_wire(model)),
        notes=notes,
    )


def _data_set_item(element: DataSetElement, compulsory: _CompulsoryOperands) -> QuestionnaireItemIn | None:
    """One data-set element as a question, disaggregated by the combo that data set holds its cells over.

    The combo is resolved before the compulsory operands are carried, because an operand naming a
    single cell names it by the option combo of the disaggregation the data set actually holds.
    A join carrying no data element is no question, and answers None.
    """
    reference = element.dataElement
    if reference is None or not reference.id:
        return None
    item = _questionnaire_item(reference.model_dump(), compulsory=False)
    combo = _effective_category_combo(element, item.category_combo)
    return _marked_required(item.model_copy(update={"category_combo": combo}), compulsory)


def _effective_category_combo(
    element: DataSetElement, data_element_combo: CategoryComboIn | None
) -> CategoryComboIn | None:
    """The disaggregation one data set holds an element's cells over: the join's combo, else the element's own.

    This is the single resolution point for a data-set cell's category combo, and every reader of one
    is downstream of it: the questionnaire's per-option-combo child items and their `<dataElement>
    .<categoryOptionCombo>` link ids, the `D2COC_CS` concepts and the category decomposition they
    state their axes from, the example responses and the load set that answer those cells, and the
    conversion that writes each answer back under its own `categoryOptionCombo`.

    A data set that restates nothing sends no join combo and the element's own stands. A data set
    that restates an element to the combo it already carries resolves to the same projection, so
    an override that changes nothing changes nothing.
    """
    override = element.categoryCombo
    if override is None:
        return data_element_combo
    return _category_combo_input(override.model_dump()) or data_element_combo


def _attribute_combo_wire(model: DataSet) -> object:
    """One data set's own category combo as the wire dict the combo projection reads.

    The generated `DataSet.categoryCombo` is a reference model rather than the inline shape the
    data-element path already parses, so it is dumped back to the wire dict both paths share.
    """
    combo = model.categoryCombo
    return None if combo is None else combo.model_dump()


class _CompulsoryOperands(BaseModel):
    """One data set's compulsory operands, split by the grain each of them makes mandatory.

    `data_element_uids` holds the operands naming a data element alone - the whole question is
    mandatory, every disaggregated cell of it included. `operand_keys` holds the operands that
    also name a category option combo, keyed `<dataElementUid>.<categoryOptionComboUid>` - the
    very `linkId` the questionnaire gives that cell - so only that one child question is.
    """

    model_config = ConfigDict(frozen=True)

    data_element_uids: frozenset[str] = frozenset()
    operand_keys: frozenset[str] = frozenset()


def _compulsory_operands(model: DataSet) -> _CompulsoryOperands:
    """Read a data set's compulsory operands off the wire, split by whether they name an option combo."""
    data_element_uids: set[str] = set()
    operand_keys: set[str] = set()
    for operand in model.compulsoryDataElementOperands or []:
        if not isinstance(operand, dict):
            continue
        reference = operand.get("dataElement")
        data_element_uid = _optional_text(reference.get("id")) if isinstance(reference, dict) else None
        if data_element_uid is None:
            continue
        option_combo = operand.get("categoryOptionCombo")
        option_combo_uid = _optional_text(option_combo.get("id")) if isinstance(option_combo, dict) else None
        if option_combo_uid is None:
            data_element_uids.add(data_element_uid)
        else:
            operand_keys.add(f"{data_element_uid}.{option_combo_uid}")
    return _CompulsoryOperands(data_element_uids=frozenset(data_element_uids), operand_keys=frozenset(operand_keys))


def _marked_required(item: QuestionnaireItemIn, compulsory: _CompulsoryOperands) -> QuestionnaireItemIn:
    """Carry a data set's compulsory operands onto one question: the whole element, or single cells of it."""
    category_combo = item.category_combo
    option_combos = category_combo.option_combos if category_combo is not None else []
    if item.uid in compulsory.data_element_uids:
        return item.model_copy(
            update={
                "compulsory": True,
                "required_option_combo_uids": [option_combo.uid for option_combo in option_combos],
            }
        )
    required_uids = [
        option_combo.uid
        for option_combo in option_combos
        if f"{item.uid}.{option_combo.uid}" in compulsory.operand_keys
    ]
    return item.model_copy(update={"required_option_combo_uids": required_uids}) if required_uids else item


def _event_program_source(model: Program, notes: list[GenerateNote]) -> QuestionnaireSourceIn:
    """Map a program without registration onto one Questionnaire source, built from its single stage.

    A WITHOUT_REGISTRATION program holds exactly one stage by construction, so the program is
    the form and its stage supplies the questions and the sections.
    """
    uid = model.id or ""
    name = model.name or uid
    program_type = _program_type(model)
    if program_type == _TRACKER_PROGRAM_TYPE:
        raise UnsupportedProgramError(
            f"program {name!r} ({uid}) has programType WITH_REGISTRATION; a tracker program is selected "
            "under [generate.tracker_programs], which emits one Questionnaire per stage"
        )
    if program_type != _EVENT_PROGRAM_TYPE:
        raise UnsupportedProgramError(
            f"program {name!r} ({uid}) has programType {program_type}; [generate.event_programs] selects "
            "WITHOUT_REGISTRATION programs and [generate.tracker_programs] selects WITH_REGISTRATION programs"
        )
    stages = _program_stages(model)
    items: list[QuestionnaireItemIn] = []
    raw_sections: object = None
    event_date_label: str | None = None
    date_label_translations: list[TranslationIn] = []
    if stages:
        stage = stages[0]
        items = _stage_items(stage)
        raw_sections = stage.get("programStageSections")
        # The label rides the stage even here: an event program's own form captures its single
        # stage's events, so the words the instance puts on the event date are the stage's.
        event_date_label = _optional_text(stage.get("executionDateLabel"))
        date_label_translations = _translation_inputs(stage.get("translations"))
    return _questionnaire_source(
        uid=uid,
        name=name,
        code=model.code,
        description=model.description,
        translations=_translation_inputs(model.translations),
        kind="event",
        items=items,
        raw_sections=raw_sections,
        attribute_values=_attribute_value_inputs(model.attributeValues),
        notes=notes,
        event_date_label=event_date_label,
        date_label_translations=date_label_translations,
    )


def _tracker_program_sources(model: Program, notes: list[GenerateNote]) -> list[QuestionnaireSourceIn]:
    """Map a program with registration onto its registration form plus one source per stage, in stage order.

    A tracker program captures at two grains, so it publishes two kinds of form. The registration
    form is the program's own: it asks the program's tracked entity attributes, and answering it
    is what enrols a person. Each stage is then a visit of that enrollment, carrying the program
    as the context its name, its grouping identifier, and its file path are built from.
    """
    uid = model.id or ""
    name = model.name or uid
    program_type = _program_type(model)
    if program_type != _TRACKER_PROGRAM_TYPE:
        raise UnsupportedProgramError(
            f"program {name!r} ({uid}) has programType {program_type}; a WITHOUT_REGISTRATION program is "
            "selected under [generate.event_programs]"
        )
    program = ProgramContextIn(
        uid=uid,
        name=name,
        code=model.code,
        translations=_translation_inputs(model.translations),
        tracked_entity_type_uid=_tracked_entity_type_uid(model),
    )
    sources: list[QuestionnaireSourceIn] = [_registration_source(model, notes)]
    for stage in sorted(_program_stages(model), key=_stage_sort_key):
        stage_uid = _optional_text(stage.get("id")) or ""
        sources.append(
            _questionnaire_source(
                uid=stage_uid,
                name=_optional_text(stage.get("name")) or stage_uid,
                code=_optional_text(stage.get("code")),
                description=_optional_text(stage.get("description")),
                translations=_translation_inputs(stage.get("translations")),
                kind="tracker-event",
                items=_stage_items(stage),
                raw_sections=stage.get("programStageSections"),
                attribute_values=_attribute_value_inputs(stage.get("attributeValues")),
                notes=notes,
                program=program,
                event_date_label=_optional_text(stage.get("executionDateLabel")),
                date_label_translations=_translation_inputs(stage.get("translations")),
                repeatable=bool(stage.get("repeatable")),
            )
        )
    return sources


def _registration_source(model: Program, notes: list[GenerateNote]) -> QuestionnaireSourceIn:
    """Map a tracker program onto its registration form - the program's own identity, its attributes as questions.

    The form is the program, so it takes the program's UID, name, code, description, and
    annotating attribute values. What it adds is the enrollment context a client needs before it
    can answer: the type of person it enrols, and whether an enrollment of this program dates the
    incident it follows.
    """
    uid = model.id or ""
    return _questionnaire_source(
        uid=uid,
        name=model.name or uid,
        code=model.code,
        description=model.description,
        translations=_translation_inputs(model.translations),
        kind="tracker",
        items=_registration_items(model),
        raw_sections=None,
        attribute_values=_attribute_value_inputs(model.attributeValues),
        notes=notes,
        displays_incident_date=bool(model.displayIncidentDate),
        enrollment_date_label=_optional_text(model.enrollmentDateLabel),
        incident_date_label=_optional_text(model.incidentDateLabel),
        date_label_translations=_translation_inputs(model.translations),
        tracked_entity_type_uid=_tracked_entity_type_uid(model),
    )


def _tracked_entity_type_source(model: TrackedEntityType, notes: list[GenerateNote]) -> QuestionnaireSourceIn:
    """Map a tracked entity type onto its person-only registration form - the form that enrols nobody.

    The form is the type, so it takes the type's UID, name, code, description, and annotating
    attribute values, and its subject is whatever `[generate.tracked_entity_types]` says the type
    is. Its questions are the attributes the type itself collects, which is why every one of them
    states `D2EntityLevel` true: there is no enrollment for an answer to land on.
    """
    uid = model.id or ""
    return _questionnaire_source(
        uid=uid,
        name=model.name or uid,
        code=model.code,
        description=model.description,
        translations=_translation_inputs(model.translations),
        kind="tracked-entity",
        items=_tracked_entity_type_items(model),
        raw_sections=None,
        attribute_values=_attribute_value_inputs(model.attributeValues),
        notes=notes,
        tracked_entity_type_uid=uid,
    )


def _tracked_entity_type_items(model: TrackedEntityType) -> list[QuestionnaireItemIn]:
    """One tracked entity type's questions, ordered by DHIS2 sort order then attribute name and UID.

    `trackedEntityTypeAttributes` is the join between the type and its attributes, holding exactly
    what a program's join holds - whether the question is mandatory, whether a person is found by
    it, where it sits in the form - so a type's attributes read the way a program's do.
    """
    raw_attributes = model.trackedEntityTypeAttributes
    entries = [
        entry
        for entry in (raw_attributes if isinstance(raw_attributes, list) else [])
        if isinstance(entry, dict) and _tracked_entity_attribute_reference(entry) is not None
    ]
    entries.sort(key=_registration_item_sort_key)
    return [
        _tracked_entity_attribute_item(
            reference,
            mandatory=bool(entry.get("mandatory")),
            searchable=bool(entry.get("searchable")),
            display_in_list=bool(entry.get("displayInList")),
            entity_level=True,
        )
        for entry in entries
        if (reference := _tracked_entity_attribute_reference(entry)) is not None
    ]


def _tracked_entity_type_uid(model: Program) -> str | None:
    """The DHIS2 tracked entity type a program enrols a person as, or None when the instance sent none."""
    reference = model.trackedEntityType
    return _optional_text(reference.id) if reference is not None else None


class _TrackedEntityTypeAttributes(BaseModel):
    """What a program's tracked entity type says about the attributes it collects itself.

    Two facts ride the same join, and a registration form reads both: `uids` decides the DHIS2
    level an answer is imported at, and `mandatory_uids` is the other half of whether the question
    is required - the type asks the question for the entity whichever program enrols it, so a type
    that requires the attribute requires it on every program's registration form.
    """

    model_config = ConfigDict(frozen=True)

    uids: frozenset[str] = frozenset()
    mandatory_uids: frozenset[str] = frozenset()


def _tracked_entity_type_attributes(model: Program) -> _TrackedEntityTypeAttributes | None:
    """The attributes a program's tracked entity type collects itself, or None when the instance sent none.

    DHIS2 asks its registration questions at two levels: a `trackedEntityTypeAttribute` is
    collected for the entity whichever program enrols it, while an attribute only
    `programTrackedEntityAttributes` names is the program's own. An empty join is a type that
    collects nothing, so every question of the program is program-only; None is a program the
    read answered no type join for, and the form then states no level at all.
    """
    reference = model.trackedEntityType
    if reference is None:
        return None
    raw_attributes = (reference.model_extra or {}).get("trackedEntityTypeAttributes")
    if not isinstance(raw_attributes, list):
        return None
    uids: set[str] = set()
    mandatory_uids: set[str] = set()
    for entry in raw_attributes:
        if not isinstance(entry, dict):
            continue
        attribute = _tracked_entity_attribute_reference(entry)
        uid = _optional_text(attribute.get("id")) if attribute is not None else None
        if uid is None:
            continue
        uids.add(uid)
        if entry.get("mandatory"):
            mandatory_uids.add(uid)
    return _TrackedEntityTypeAttributes(uids=frozenset(uids), mandatory_uids=frozenset(mandatory_uids))


def _registration_items(model: Program) -> list[QuestionnaireItemIn]:
    """One tracker program's registration questions, ordered by DHIS2 sort order then attribute name and UID.

    `programTrackedEntityAttributes` is the join between the program and its attributes, and it
    holds exactly what a stage's `programStageDataElements` join holds: whether the question is
    mandatory on this program, and where it sits in the form. So the two read the same way, and
    an attribute is projected onto the very question shape a data element is.

    The tracked entity type's own join decides two things the program's join cannot: whether the
    answer is imported onto the tracked entity or onto the enrollment, and whether the type itself
    requires the attribute. A question is required when either join says so - the type asks it for
    the entity whichever program enrols it, so a program that leaves its own `mandatory` off does
    not make an attribute the type requires optional.
    """
    raw_attributes = model.programTrackedEntityAttributes
    entries = [
        entry
        for entry in (raw_attributes if isinstance(raw_attributes, list) else [])
        if isinstance(entry, dict) and _tracked_entity_attribute_reference(entry) is not None
    ]
    entries.sort(key=_registration_item_sort_key)
    type_attributes = _tracked_entity_type_attributes(model)
    items: list[QuestionnaireItemIn] = []
    for entry in entries:
        reference = _tracked_entity_attribute_reference(entry)
        if reference is None:
            continue
        uid = _optional_text(reference.get("id"))
        items.append(
            _tracked_entity_attribute_item(
                reference,
                mandatory=bool(entry.get("mandatory"))
                or (type_attributes is not None and uid in type_attributes.mandatory_uids),
                searchable=bool(entry.get("searchable")),
                display_in_list=bool(entry.get("displayInList")),
                entity_level=None if type_attributes is None else uid in type_attributes.uids,
            )
        )
    return items


def _tracked_entity_attribute_reference(entry: dict[str, object]) -> dict[str, object] | None:
    """The tracked entity attribute one `programTrackedEntityAttribute` references, or None when it names none."""
    reference = entry.get("trackedEntityAttribute")
    if not isinstance(reference, dict) or not reference.get("id"):
        return None
    return reference


def _registration_item_sort_key(entry: dict[str, object]) -> tuple[int, str, str]:
    """The order a registration form's questions are emitted in: sort order, then the attribute's name and UID."""
    reference = _tracked_entity_attribute_reference(entry) or {}
    uid = _optional_text(reference.get("id")) or ""
    return (_sort_order(entry), _optional_text(reference.get("name")) or uid, uid)


def _tracked_entity_attribute_item(
    raw: dict[str, object],
    *,
    mandatory: bool,
    searchable: bool,
    display_in_list: bool,
    entity_level: bool | None,
) -> QuestionnaireItemIn:
    """Map one wire tracked entity attribute into the question projection both emitters consume.

    `mandatory`, `searchable`, `display_in_list`, and `entity_level` come off the join rather than
    off the attribute, because all four are facts about this form asking this attribute rather than
    about the attribute itself. `generated`, `pattern`, and `description` are the attribute's own:
    DHIS2 mints a generated attribute's value from its reserved-value pattern, so the fact holds in
    every form that asks it.

    DHIS2 sends an empty `pattern` for an attribute nobody generates, so the projection carries a
    pattern only where there is a value to state.
    """
    uid = _optional_text(raw.get("id")) or ""
    option_set = raw.get("optionSet")
    option_set_uid = _optional_text(option_set.get("id")) if isinstance(option_set, dict) else None
    generated = bool(raw.get("generated"))
    return QuestionnaireItemIn(
        uid=uid,
        name=_optional_text(raw.get("name")) or uid,
        code=_optional_text(raw.get("code")),
        form_name=_optional_text(raw.get("formName")),
        description=_optional_text(raw.get("description")),
        value_type=_optional_text(raw.get("valueType")) or "",
        option_set_uid=option_set_uid,
        compulsory=mandatory,
        unique=bool(raw.get("unique")),
        searchable=searchable,
        generated=generated,
        pattern=_optional_text(raw.get("pattern")) if generated else None,
        display_in_list=display_in_list,
        entity_level=entity_level,
        translations=_translation_inputs(raw.get("translations")),
    )


def _stage_items(stage: dict[str, object]) -> list[QuestionnaireItemIn]:
    """One program stage's questions, ordered by DHIS2 sort order and then by data element name and UID.

    `programStageDataElements` is a Java `Set`, so the wire order is not the form's order and is
    not stable across requests; the stage's own `sortOrder` is what the data-entry app renders by.
    """
    raw_elements = stage.get("programStageDataElements")
    entries = [
        entry
        for entry in (raw_elements if isinstance(raw_elements, list) else [])
        if isinstance(entry, dict) and _data_element_reference(entry) is not None
    ]
    entries.sort(key=_stage_element_sort_key)
    return [
        _questionnaire_item(reference, compulsory=bool(entry.get("compulsory")))
        for entry in entries
        if (reference := _data_element_reference(entry)) is not None
    ]


def _data_element_reference(entry: dict[str, object]) -> dict[str, object] | None:
    """The data element one `programStageDataElement` references, or None when it names none."""
    reference = entry.get("dataElement")
    if not isinstance(reference, dict) or not reference.get("id"):
        return None
    return reference


def _stage_element_sort_key(entry: dict[str, object]) -> tuple[int, str, str]:
    """The order one stage's questions are emitted in: DHIS2 sort order, then the element's name and UID."""
    reference = _data_element_reference(entry) or {}
    uid = _optional_text(reference.get("id")) or ""
    return (_sort_order(entry), _optional_text(reference.get("name")) or uid, uid)


#: The prose each form kind is named by in the notes the projection raises.
_SOURCE_LABELS_BY_KIND = {
    "aggregate": "data set",
    "event": "event program",
    "tracker": "tracker program registration",
    "tracker-event": "tracker program stage",
    "tracked-entity": "tracked entity type registration",
}


def _questionnaire_source(
    uid: str,
    name: str,
    code: str | None,
    description: str | None,
    kind: FormKind,
    items: list[QuestionnaireItemIn],
    raw_sections: object,
    attribute_values: list[AttributeValueIn],
    notes: list[GenerateNote],
    translations: list[TranslationIn],
    period_type: str | None = None,
    program: ProgramContextIn | None = None,
    attribute_combo: CategoryComboIn | None = None,
    displays_incident_date: bool = False,
    enrollment_date_label: str | None = None,
    incident_date_label: str | None = None,
    event_date_label: str | None = None,
    date_label_translations: list[TranslationIn] | None = None,
    repeatable: bool | None = None,
    tracked_entity_type_uid: str | None = None,
) -> QuestionnaireSourceIn:
    """Split one form's data elements into its sections plus whatever the sections leave out."""
    sections = _questionnaire_sections(raw_sections, items)
    sectioned_ids = {item.uid for section in sections for item in section.items}
    flat_items = [item for item in items if item.uid not in sectioned_ids]
    if sections and flat_items:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.FORM_STRUCTURE,
                f"{_SOURCE_LABELS_BY_KIND[kind]} {name!r} ({uid}) has {len(flat_items)} data elements outside "
                "its sections; emitted after the sectioned ones",
                [f"{item.name} ({item.uid})" for item in flat_items],
            )
        )
    return QuestionnaireSourceIn(
        uid=uid,
        name=name,
        code=code,
        description=description,
        translations=translations,
        kind=kind,
        period_type=period_type,
        program=program,
        attribute_combo=attribute_combo,
        displays_incident_date=displays_incident_date,
        enrollment_date_label=enrollment_date_label,
        incident_date_label=incident_date_label,
        event_date_label=event_date_label,
        date_label_translations=date_label_translations or [],
        repeatable=repeatable,
        tracked_entity_type_uid=tracked_entity_type_uid,
        sections=sections,
        flat_items=flat_items,
        attribute_values=attribute_values,
    )


def _questionnaire_sections(raw_sections: object, items: list[QuestionnaireItemIn]) -> list[QuestionnaireSectionIn]:
    """Join the wire sections, which reference data elements by id alone, to the fetched item detail."""
    if not isinstance(raw_sections, list):
        return []
    items_by_uid = {item.uid: item for item in items}
    sections: list[QuestionnaireSectionIn] = []
    for raw in raw_sections:
        if not isinstance(raw, dict):
            continue
        uid = _optional_text(raw.get("id"))
        if uid is None:
            continue
        members = raw.get("dataElements")
        member_ids = (
            [_optional_text(entry.get("id")) for entry in members if isinstance(entry, dict)]
            if isinstance(members, list)
            else []
        )
        sections.append(
            QuestionnaireSectionIn(
                uid=uid,
                name=_optional_text(raw.get("name")) or uid,
                description=_optional_text(raw.get("description")),
                translations=_translation_inputs(raw.get("translations")),
                items=[items_by_uid[member_id] for member_id in member_ids if member_id in items_by_uid],
            )
        )
    return sections


def _greyed_operand_keys(model: DataSet) -> frozenset[str]:
    """Every `<dataElementUid>.<categoryOptionComboUid>` cell one data set's sections grey out.

    DHIS2 renders a greyed cell in the data-entry app and refuses input on it, so it is a cell the
    instance does not hold values for. The generated form must not ask it: a response answering a
    never-published cell is not of the form, and the value behind it would be refused on import.
    """
    keys: set[str] = set()
    for raw in model.sections or []:
        if not isinstance(raw, dict):
            continue
        greyed = raw.get("greyedFields")
        for operand in greyed if isinstance(greyed, list) else []:
            if not isinstance(operand, dict):
                continue
            reference = operand.get("dataElement")
            option_combo = operand.get("categoryOptionCombo")
            if not isinstance(reference, dict) or not isinstance(option_combo, dict):
                continue
            data_element_uid = _optional_text(reference.get("id"))
            option_combo_uid = _optional_text(option_combo.get("id"))
            if data_element_uid is not None and option_combo_uid is not None:
                keys.add(f"{data_element_uid}.{option_combo_uid}")
    return frozenset(keys)


def _without_greyed_cells(item: QuestionnaireItemIn, greyed: frozenset[str]) -> QuestionnaireItemIn | None:
    """One question with its greyed cells dropped, or None when the data set greys every cell it has.

    Dropping the cells here rather than at emit time is what keeps every consumer agreed: the
    published items, the `D2COC_CS` concepts and their category axes, the example responses, the
    load set, and the conversion that writes an answer back all read this one projection.
    """
    combo = item.category_combo
    if combo is None or combo.is_default or not greyed:
        return item
    kept = [option_combo for option_combo in combo.option_combos if f"{item.uid}.{option_combo.uid}" not in greyed]
    if len(kept) == len(combo.option_combos):
        return item
    if not kept:
        return None
    return item.model_copy(update={"category_combo": combo.model_copy(update={"option_combos": kept})})


def _dropped_cell_keys(item: QuestionnaireItemIn, published: QuestionnaireItemIn | None) -> list[str]:
    """The `<dataElement>.<categoryOptionCombo>` link ids one question lost to its data set's greyed fields."""
    combo = item.category_combo
    if combo is None:
        return []
    kept = published.category_combo.option_combos if published is not None and published.category_combo else []
    kept_uids = {option_combo.uid for option_combo in kept}
    return [
        f"{item.uid}.{option_combo.uid}" for option_combo in combo.option_combos if option_combo.uid not in kept_uids
    ]


def _questionnaire_item(raw: dict[str, object], *, compulsory: bool) -> QuestionnaireItemIn:
    """Map one wire data element into the question projection the emitter consumes."""
    uid = _optional_text(raw.get("id")) or ""
    option_set = raw.get("optionSet")
    option_set_uid = _optional_text(option_set.get("id")) if isinstance(option_set, dict) else None
    return QuestionnaireItemIn(
        uid=uid,
        name=_optional_text(raw.get("name")) or uid,
        code=_optional_text(raw.get("code")),
        form_name=_optional_text(raw.get("formName")),
        description=_optional_text(raw.get("description")),
        value_type=_optional_text(raw.get("valueType")) or "",
        domain_type=_optional_text(raw.get("domainType")) or "",
        option_set_uid=option_set_uid,
        compulsory=compulsory,
        category_combo=_category_combo_input(raw.get("categoryCombo")),
        translations=_translation_inputs(raw.get("translations")),
    )


def _category_combo_input(raw: object) -> CategoryComboIn | None:
    """Map one wire category combo, option combos included; None when the data element carries none."""
    if not isinstance(raw, dict):
        return None
    uid = _optional_text(raw.get("id"))
    if uid is None:
        return None
    combo = CategoryComboIn(
        uid=uid,
        name=_optional_text(raw.get("name")) or uid,
        code=_optional_text(raw.get("code")),
        is_default=bool(raw.get("isDefault")),
        categories=_category_axis_inputs(raw.get("categories")),
        option_combos=_option_combo_inputs(raw.get("categoryOptionCombos")),
    )
    return combo.model_copy(update={"option_combos": ordered_option_combos(combo)})


def _category_axis_inputs(raw_categories: object) -> list[CategoryAxisIn]:
    """One category combo's axes, each carrying the category options DHIS2 declares it in order.

    Both arrays are ordered lists on the wire, so this is where the declared grid order enters the
    projection: the axes in the combo's own order, the options in each category's own order.
    """
    axes: list[CategoryAxisIn] = []
    for entry in raw_categories if isinstance(raw_categories, list) else []:
        if not isinstance(entry, dict):
            continue
        uid = _optional_text(entry.get("id"))
        if uid is None:
            continue
        axes.append(CategoryAxisIn(uid=uid, option_uids=_reference_uid_list(entry.get("categoryOptions"))))
    return axes


def _reference_uid_list(raw_references: object) -> list[str]:
    """The UIDs of one wire reference list, in the order DHIS2 answered with, skipping malformed entries.

    A category combo's `categories` is an ordered list rather than a set, so the order carries the
    disaggregation's own reading order - location then age group for "Fixed, <1y".
    """
    uids: list[str] = []
    for entry in raw_references if isinstance(raw_references, list) else []:
        if not isinstance(entry, dict):
            continue
        uid = _optional_text(entry.get("id"))
        if uid is not None:
            uids.append(uid)
    return uids


def _option_combo_inputs(raw_combos: object) -> list[CategoryOptionComboIn]:
    """Map one category combo's wire option combos into the projection, ordered by name and UID.

    `CategoryCombo.categoryOptionCombos` is a Java `Set` with no sort order, and DHIS2
    serialises it in a different order on every request (BUGS.md #64), so the wire order is
    thrown away here. `_category_combo_input` then lays the cells out in the declared axis
    order its categories state, and this ordering is what remains as the tie-break between two
    cells the declared arrays cannot separate. Every consumer reads the result - the
    questionnaire's option-combo child items, the example responses answering them, and the
    `D2COC_CS` support concepts - so a regenerate of an unchanged form produces an unchanged
    file, and the examples, fetched by a separate request, answer the questionnaire's items in
    the questionnaire's own order, which the FHIR validator requires.
    """
    option_combos: list[CategoryOptionComboIn] = []
    for entry in raw_combos if isinstance(raw_combos, list) else []:
        if not isinstance(entry, dict):
            continue
        combo_uid = _optional_text(entry.get("id"))
        if combo_uid is None:
            continue
        option_combos.append(
            CategoryOptionComboIn(
                uid=combo_uid,
                name=_optional_text(entry.get("name")) or combo_uid,
                code=_optional_text(entry.get("code")),
                category_option_uids=sorted(_reference_uid_list(entry.get("categoryOptions"))),
            )
        )
    option_combos.sort(key=lambda option_combo: (option_combo.name, option_combo.uid))
    return option_combos


def _optional_text(value: object) -> str | None:
    """The wire value when it is a non-empty string, else None."""
    return value if isinstance(value, str) and value else None


def _source_items(source: QuestionnaireSourceIn) -> list[QuestionnaireItemIn]:
    """Every question one source carries, sectioned and unsectioned alike."""
    return [item for section in source.sections for item in section.items] + list(source.flat_items)


def _translation_inputs(raw_translations: object) -> list[TranslationIn]:
    """Wrap the raw DHIS2 translation dicts into the shared projection, dropping entries missing any key."""
    if not isinstance(raw_translations, list):
        return []
    translations: list[TranslationIn] = []
    for raw in raw_translations:
        if not isinstance(raw, dict):
            continue
        locale, property_name, value = raw.get("locale"), raw.get("property"), raw.get("value")
        if not isinstance(locale, str) or not isinstance(property_name, str) or not isinstance(value, str):
            continue
        translations.append(TranslationIn(locale=locale, property=property_name, value=value))
    return translations


def _attribute_value_inputs(raw_attribute_values: object) -> list[AttributeValueIn]:
    """Wrap the raw DHIS2 attribute values into the shared projection, dropping entries missing either half.

    DHIS2 nests the attribute under `attribute[id]` and sends every value as a string, whatever
    the attribute's declared value type, so the projection reads the UID out of the nested
    reference and takes the value as it stands.

    An entry arrives either as the wire dict or as a typed model: the three generated schema trees
    type `attributeValues` differently - v41 as `list[AttributeValue]`, v42 and v43 as `Any` - and
    this is the single place that absorbs that, dumping a model back to its wire shape first.
    """
    if not isinstance(raw_attribute_values, list):
        return []
    attribute_values: list[AttributeValueIn] = []
    for entry in raw_attribute_values:
        raw = entry.model_dump() if isinstance(entry, BaseModel) else entry
        if not isinstance(raw, dict):
            continue
        attribute = raw.get("attribute")
        attribute_uid = _optional_text(attribute.get("id")) if isinstance(attribute, dict) else None
        value = raw.get("value")
        if attribute_uid is None or not isinstance(value, str):
            continue
        attribute_values.append(AttributeValueIn(attribute_uid=attribute_uid, value=value))
    return attribute_values


def _option_set_input(model: OptionSet) -> OptionSetIn:
    """Map a generated OptionSet (with inline option dicts) into the emitter projection."""
    options = [
        OptionIn(
            uid=str(raw["id"]),
            code=raw.get("code"),
            name=str(raw.get("name") or raw["id"]),
            sort_order=raw.get("sortOrder"),
            translations=_translation_inputs(raw.get("translations")),
        )
        for raw in model.options or []
        if isinstance(raw, dict) and raw.get("id")
    ]
    uid = model.id or ""
    return OptionSetIn(
        uid=uid,
        code=model.code,
        name=model.name or uid,
        description=model.description,
        options=options,
        translations=_translation_inputs(model.translations),
        attribute_values=_attribute_value_inputs(model.attributeValues),
    )


#: Below this absolute shoelace area a ring is degenerate and its vertices are simply averaged.
_DEGENERATE_RING_AREA = 1e-12

#: Emitted coordinates are rounded to this many decimals - roughly 0.1 m at the equator.
_POSITION_PRECISION = 6


def _walk_positions(node: object, positions: list[GeoPoint]) -> None:
    """Collect every [longitude, latitude] pair from arbitrarily nested GeoJSON coordinates."""
    if not isinstance(node, list):
        return
    if len(node) >= 2 and all(isinstance(value, int | float) for value in node[:2]):
        positions.append(GeoPoint(longitude=float(node[0]), latitude=float(node[1])))
        return
    for child in node:
        _walk_positions(child, positions)


def _outer_rings(geometry_type: str, coordinates: object) -> list[list[GeoPoint]]:
    """Collect the outer ring of every polygon: `coordinates[0]` for Polygon, per-polygon for MultiPolygon."""
    if not isinstance(coordinates, list) or not coordinates:
        return []
    if geometry_type == "Polygon":
        raw_rings = [coordinates[0]]
    else:
        raw_rings = [polygon[0] for polygon in coordinates if _non_empty(polygon)]
    rings: list[list[GeoPoint]] = []
    for raw_ring in raw_rings:
        ring: list[GeoPoint] = []
        _walk_positions(raw_ring, ring)
        if ring:
            rings.append(ring)
    return rings


def _non_empty(value: object) -> bool:
    """Check that a nested GeoJSON coordinate entry is a list with at least one element."""
    return isinstance(value, list) and len(value) > 0


def _ring_centroid(ring: list[GeoPoint]) -> GeoPoint:
    """Area-weighted (shoelace) centroid of one closed ring, falling back to the vertex mean when degenerate."""
    doubled_area = 0.0
    longitude_moment = 0.0
    latitude_moment = 0.0
    for index, current in enumerate(ring):
        following = ring[(index + 1) % len(ring)]
        cross = current.longitude * following.latitude - following.longitude * current.latitude
        doubled_area += cross
        longitude_moment += (current.longitude + following.longitude) * cross
        latitude_moment += (current.latitude + following.latitude) * cross
    area = doubled_area / 2
    if abs(area) < _DEGENERATE_RING_AREA:
        return _vertex_mean(ring)
    return GeoPoint(longitude=longitude_moment / (6 * area), latitude=latitude_moment / (6 * area))


def _vertex_mean(ring: list[GeoPoint]) -> GeoPoint:
    """Arithmetic mean of a ring's vertices - the centroid of a zero-area ring."""
    return GeoPoint(
        longitude=sum(vertex.longitude for vertex in ring) / len(ring),
        latitude=sum(vertex.latitude for vertex in ring) / len(ring),
    )


def _polygon_centroid(geometry_type: str, coordinates: object, positions: list[GeoPoint]) -> GeoPoint:
    """Centroid of the outer ring with the largest absolute area, rounded to the emitted precision."""
    rings = _outer_rings(geometry_type, coordinates) or [positions]
    largest = max(rings, key=_absolute_ring_area)
    centroid = _ring_centroid(largest)
    return GeoPoint(
        longitude=round(centroid.longitude, _POSITION_PRECISION),
        latitude=round(centroid.latitude, _POSITION_PRECISION),
    )


def _absolute_ring_area(ring: list[GeoPoint]) -> float:
    """Absolute shoelace area of one closed ring."""
    doubled_area = 0.0
    for index, current in enumerate(ring):
        following = ring[(index + 1) % len(ring)]
        doubled_area += current.longitude * following.latitude - following.longitude * current.latitude
    return abs(doubled_area / 2)


class GeometryTally(BaseModel):
    """Per-run tally of the geometry outcomes worth a note: no position, or nothing usable at all.

    Point and Polygon/MultiPolygon geometry is nominal - a position (the coordinates, or the
    shoelace centroid) plus the boundary extension - and the report's position and boundary
    counters already say how many units took that path, so neither raises a note.
    """

    other_geometry_units: list[str] = Field(default_factory=list)
    other_geometry_types: set[str] = Field(default_factory=set)
    malformed_units: list[str] = Field(default_factory=list)

    def to_notes(self) -> list[GenerateNote]:
        """Roll the tally up into one aggregate note per noteworthy geometry outcome."""
        notes: list[GenerateNote] = []
        if self.other_geometry_units:
            type_names = ", ".join(sorted(self.other_geometry_types))
            notes.append(
                aggregate_generate_note(
                    GenerateNoteCategory.INSTANCE_DATA_GAP,
                    f"{len(self.other_geometry_units)} organisation units have {type_names} geometry; embedded "
                    "without position",
                    self.other_geometry_units,
                )
            )
        if self.malformed_units:
            notes.append(
                aggregate_generate_note(
                    GenerateNoteCategory.INSTANCE_DATA_GAP,
                    f"{len(self.malformed_units)} organisation units have malformed geometry; no position or "
                    "boundary emitted",
                    self.malformed_units,
                )
            )
        return notes


def _geometry_positions(geometry: dict[str, object]) -> list[GeoPoint]:
    """Collect every position in a GeoJSON geometry, descending into GeometryCollection members."""
    positions: list[GeoPoint] = []
    if geometry.get("type") == "GeometryCollection":
        members = geometry.get("geometries")
        if isinstance(members, list):
            for member in members:
                if isinstance(member, dict):
                    positions.extend(_geometry_positions(member))
        return positions
    _walk_positions(geometry.get("coordinates"), positions)
    return positions


def _boundary_feature(geometry: dict[str, object], uid: str, name: str, level: int) -> str:
    """Wrap a GeoJSON geometry in the compact Feature the boundary extension carries."""
    feature = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {"dhis2Id": uid, "name": name, "level": level},
    }
    return json.dumps(feature, separators=(",", ":"), sort_keys=True)


def _is_closed(model: OrganisationUnit, today: date) -> bool:
    """Check whether the unit's DHIS2 `closedDate` has passed - DHIS2 sends a date at midnight."""
    closed_date = model.closedDate
    return closed_date is not None and closed_date.date() <= today


def _organisation_unit_input(
    model: OrganisationUnit,
    tally: GeometryTally,
    today: date,
) -> OrganisationUnitIn | None:
    """Map a generated OrganisationUnit into the emitter projection; None when it lacks a UID."""
    uid = model.id
    if not uid:
        return None
    name = model.name or uid
    label = f"{name} ({uid})"
    path = model.path or f"/{uid}"
    level = model.level if model.level is not None else len([part for part in path.split("/") if part])
    position: GeoPoint | None = None
    boundary_geojson: str | None = None
    geometry = model.geometry
    if isinstance(geometry, dict):
        geometry_type = str(geometry.get("type"))
        positions = _geometry_positions(geometry)
        if not positions:
            tally.malformed_units.append(label)
        else:
            boundary_geojson = _boundary_feature(geometry, uid, name, level)
            if geometry_type == "Point":
                position = positions[0]
            elif geometry_type in {"Polygon", "MultiPolygon"}:
                position = _polygon_centroid(geometry_type, geometry.get("coordinates"), positions)
            else:
                tally.other_geometry_units.append(label)
                tally.other_geometry_types.add(geometry_type)
    return OrganisationUnitIn(
        uid=uid,
        name=name,
        short_name=model.shortName,
        code=model.code,
        description=model.description,
        level=level,
        path=path,
        parent_uid=model.parent.id if model.parent is not None else None,
        latitude=position.latitude if position is not None else None,
        longitude=position.longitude if position is not None else None,
        boundary_geojson=boundary_geojson,
        contact_person=model.contactPerson,
        email=model.email,
        phone_number=model.phoneNumber,
        closed=_is_closed(model, today),
        translations=_translation_inputs(model.translations),
        attribute_values=_attribute_value_inputs(model.attributeValues),
    )


#: How many steps `forward_responses` announces: read the spool, read the guide, read the value types,
#: translate, post, register the completed reports, file what each response became.
FORWARD_STEPS = 7

#: The `/api/dataValueSets` endpoint one aggregate response is imported through.
_DATA_VALUE_SETS_PATH = "/api/dataValueSets"

#: The `/api/completeDataSetRegistrations` endpoint a `completed` aggregate response is registered
#: complete through, once DHIS2 has taken its values.
_COMPLETE_DATA_SET_REGISTRATIONS_PATH = "/api/completeDataSetRegistrations"

#: The `/api/tracker` endpoint both event kinds and every registration are imported through.
_TRACKER_PATH = "/api/tracker"

#: The `/api/tracker` bundle key each payload kind rides under: an event, the tracked entity a
#: registration creates with its enrollment nested inside it, or - for a registration enrolling a
#: person the instance already holds - that enrollment on its own at the top level. The third key
#: is what keeps the person untouched: an enrollment nested in a `trackedEntities` entry needs
#: `CREATE_AND_UPDATE`, and that rewrites the person's owning organisation unit (BUGS.md 73).
_TRACKER_EVENTS_KEY = "events"
_TRACKER_TRACKED_ENTITIES_KEY = "trackedEntities"
_TRACKER_ENROLLMENTS_KEY = "enrollments"

#: Which of those keys each `/api/tracker` target kind's payload rides under. The aggregate kind is
#: absent because it posts to an endpoint of its own with no bundle around it at all.
_TRACKER_KEYS_BY_TARGET_KIND: dict[ConversionTargetKind, str] = {
    ConversionTargetKind.TRACKED_ENTITY: _TRACKER_TRACKED_ENTITIES_KEY,
    ConversionTargetKind.TRACKER: _TRACKER_TRACKED_ENTITIES_KEY,
    ConversionTargetKind.TRACKER_ENROLLMENT: _TRACKER_ENROLLMENTS_KEY,
    ConversionTargetKind.EVENT: _TRACKER_EVENTS_KEY,
    ConversionTargetKind.TRACKER_EVENT: _TRACKER_EVENTS_KEY,
}

#: What a dry run adds to an aggregate post. v42 spells validate-only on this endpoint as `dryRun`,
#: and the import runs every rule it would run for real while committing nothing.
_DATA_VALUE_SETS_DRY_RUN_PARAMS = {"dryRun": "true"}

#: The parameters every forwarded event is posted under. Every payload names its own receipt-derived
#: uid, and CREATE is what makes a re-forwarded receipt collide loudly instead of updating in place;
#: `async=false` makes the answer the import report itself rather than a job reference to poll.
_TRACKER_PARAMS = {"importStrategy": "CREATE", "async": "false"}

#: What a dry run adds to a tracker post. v42 has no `dryRun` on `/api/tracker`; the endpoint's own
#: validate-only mode is `importMode=VALIDATE`, which runs the whole validation pass and persists nothing.
_TRACKER_DRY_RUN_PARAMS = {"importMode": "VALIDATE"}

#: The projection the value-type read asks for - the one fact the compiled IG cannot carry, because
#: R4 spells `BOOLEAN` and `TRUE_ONLY` as the same `#boolean` item type. The same two fields answer
#: for both objects a question is asked from, so one shape serves both reads.
_VALUE_TYPE_FIELDS = "id,valueType"

#: How many UIDs one `id:in:[...]` filter carries before the value-type read is split across requests.
_VALUE_TYPE_BATCH_SIZE = 200

#: The status both endpoint report shapes spell an outright refusal as.
_ERROR_IMPORT_STATUS = "ERROR"

#: The fields only an `/api/dataValueSets` ImportSummary carries, which is how one is recognised
#: whether it arrived inside a `WebMessage.response` or bare.
_DATA_VALUE_SET_REPORT_KEYS = frozenset({"importCount", "conflicts", "responseType", "dataSetComplete"})

#: The fields only an `/api/tracker` TrackerImportReport carries. The endpoint answers a refusal with
#: this document **bare** - no `WebMessage` around it - so recognising it by shape is the whole trick.
_TRACKER_REPORT_KEYS = frozenset({"validationReport", "stats", "bundleReport"})

#: The backtick-quoted identifiers DHIS2 embeds in a validation message. Generalising them is what makes
#: two hundred rejections of one rule roll up into one cause rather than two hundred distinct sentences.
_QUOTED_IDENTIFIER = re.compile(r"`[^`]*`")

#: How often the posting step re-captions itself, so a 300-response drain narrates without one line each.
_POST_TICK_INTERVAL = 10

#: The status at and above which an answer is about the instance rather than about the payload. DHIS2
#: states a verdict on a payload with 409 and its own import report; a 5xx is the instance failing to
#: reach a verdict at all, and reading one as "your payload was refused" would file a receipt under a
#: rejection DHIS2 never made.
_SERVER_ERROR_STATUS = 500

#: The status the client raises an authentication failure on rather than handing the body back.
_UNAUTHORIZED_STATUS = 401

#: The two codes DHIS2 answers a tracker event whose enrollment it cannot find with: `E1313` for the
#: enrollment nobody has, and the `E1079` program mismatch it asserts against that same absent
#: enrollment (BUGS.md 68). A rejection carrying only these is the whole shape a dry run cannot check.
_ABSENT_ENROLLMENT_ERROR_CODES = frozenset({"E1079", "E1313"})

#: What a dry run can and cannot say about a completeness registration it did not make. The endpoint
#: has a `dryRun` of its own, but a dry run wrote no values for it to be a claim about, so the honest
#: statement is what would be registered rather than a validation of the tuple.
_COMPLETENESS_DRY_RUN_REASON = (
    "A dry run writes no values, so there is nothing for a completeness registration to be a claim about "
    "and none is posted. What the run states is the tuple each `completed` response would register - the "
    "data set, period, organisation unit, and attribute option combo its values ride under. Whether DHIS2 "
    "accepts that write is checked by the import, which registers only after it has taken the values."
)

#: What a dry run says about a stage event whose enrollment only a registration of the same run creates.
_UNVERIFIABLE_IN_DRY_RUN_REASON = (
    "The enrollment this event answers into is created by a registration validated in the same run. A dry "
    "run writes nothing to the instance, so there is no enrollment for DHIS2 to check the event against. "
    "An import posts registrations first, and the event is checked against the enrollment one created."
)


class ForwardOutcomeKind(StrEnum):
    """What became of one spooled response in a forward run."""

    #: The response never reached DHIS2, and the receipt stays in `received/` for the next drain to
    #: retry - a committing drain writing its refusal record beside it so the listing can say so.
    #: Two things refuse a response. The translator would not read it whole, which is the ordinary
    #: case, and is terminal where the refusal is one nothing can fix - see
    #: `TERMINAL_REFUSAL_CATEGORIES` - in which case an import files it to `rejected/` instead. Or
    #: the drain runs under `[forward] overwrites = "refuse"` and the payload holds an aggregate
    #: value a forwarded receipt already sent, which `ForwardOutcome.overwrite_refused` says.
    REFUSED = "refused"

    #: DHIS2 took the payload - imported it, or validated it on a dry run.
    ACCEPTED = "accepted"

    #: DHIS2 was given the payload and refused it; the import report says why.
    REJECTED = "rejected"

    #: A dry run could not check the payload, because what it answers into is created by the same run.
    UNVERIFIABLE = "unverifiable"

    #: The drain stopped before this receipt's turn, so DHIS2 was never asked about it and it stays put.
    NOT_POSTED = "not-posted"


#: The refusal categories that no change to the guide and no change to the instance could ever
#: resolve, so a receipt carrying one is filed to `rejected/` instead of being retried by every drain
#: for the rest of the project's life. The discriminator is stated as a set rather than as a flag on
#: a refusal, because membership is a doctrine about what this toolchain builds rather than a
#: property of the response: `entered-in-error` asks for a withdrawal, withdrawal is a deletion, and
#: this toolchain imports - see `docs/fhir/design/data-lifecycle.md`. Every other refusal has a fix
#: somewhere, so every other refusal stays in the queue.
TERMINAL_REFUSAL_CATEGORIES = frozenset({ConversionRefusalCategory.ENTERED_IN_ERROR_IS_A_DELETION})

#: What the refusal record beside an overwrite-refused receipt calls the refusal. A category of its
#: own rather than a `ConversionRefusalCategory`, because the translator read this response whole -
#: what refused it is the spool's own record of what this project has already sent.
OVERWRITE_REFUSAL_CATEGORY = "overwrite-refused"

#: What the sidecar of a terminally refused receipt states in place of a DHIS2 answer. DHIS2 was
#: never asked, so the status is the forwarder's own word for what happened.
_TERMINAL_REFUSAL_STATUS = "REFUSED"

#: The doctrine the sidecar of a terminally refused receipt writes down, so a person reading
#: `rejected/` cold learns why the receipt is there without a drain report in front of them.
_TERMINAL_REFUSAL_MESSAGE = (
    "The translator will never convert this response, whatever changes in the guide or in the data, so it is "
    "filed here rather than retried by every drain. A drain imports; retracting what one already imported is "
    "`d2w fhir withdraw <response id>`, naming the forwarded receipt to take back rather than this one - see "
    "docs/fhir/design/data-lifecycle.md. `d2w fhir requeue` puts the receipt back in the queue for an operator "
    "who wants it tried again."
)


class ForwardCompletenessKind(StrEnum):
    """What became of one aggregate response's completeness claim."""

    #: DHIS2 took the registration: the data set is complete for the tuple the values landed under.
    REGISTERED = "registered"

    #: A dry run states the tuple a `completed` response would register, and posts nothing.
    WOULD_REGISTER = "would-register"

    #: The response reports itself `in-progress`, so its values imported and it claims nothing.
    NOT_CLAIMED = "not-claimed"

    #: The values imported and DHIS2 refused the registration; the values stay imported.
    REFUSED = "refused"

    #: The run was told not to register completeness, so a `completed` response claims and posts nothing.
    NOT_REGISTERED = "not-registered"

    #: The values landed and the registration did not: the claim is owed, and the next drain posts it.
    PENDING = "pending"


class ForwardEndpointAnswer(BaseModel):
    """One import endpoint's HTTP answer, as the projection that reads it is handed it.

    The body is a raw JSON object because the two endpoints disagree about what wraps their report,
    and each projection unwraps its own - so this is the parse boundary, and the dict goes no
    further than the projection that reads it. The status rides beside it because a body alone
    cannot say whether the endpoint answered at all: an authentication gateway's `403` and DHIS2's
    own `409` both arrive as JSON objects.

    `status_code` is None for an answer the client did not raise on, which is every 2xx. The client
    parses a successful body without carrying its status back, and no drain acts on the difference
    between a 200 and a 201 - a stop names the status only when there was a failing one to name.
    """

    model_config = ConfigDict(frozen=True)

    body: dict[str, Any]
    status_code: int | None = None


class ForwardCompletenessRetry(BaseModel):
    """One completeness claim an earlier drain left owed, and what this drain's registration answered.

    A retry is about a receipt that is already in `forwarded/`, so it is no part of this run's
    spool: the values it claims completeness for landed in an earlier drain, and only the
    registration is outstanding.
    """

    model_config = ConfigDict(frozen=True)

    response_id: str
    outcome: ForwardCompletenessOutcome


class ForwardImportVerdict(StrEnum):
    """What one HTTP answer from an import endpoint says about the payload that was posted to it."""

    #: The endpoint's own import report arrived and names no refusal: DHIS2 took the payload.
    ACCEPTED = "accepted"

    #: The endpoint's own import report arrived and refuses the payload, by status or by named rows.
    REJECTED = "rejected"

    #: Nothing that reads as the endpoint's import report arrived, so the answer is about the run.
    NONE = "none"


class ForwardImportIssue(BaseModel):
    """One row DHIS2 named as a reason it would not take the payload, from either report shape.

    `/api/dataValueSets` names them `response.conflicts[]` (`errorCode`, `object`, `value`) and
    `/api/tracker` names them `validationReport.errorReports[]` (`errorCode`, `uid`, `message`). One
    shape, because a reader of either wants the same three things: which rule, which object, what it said.
    """

    model_config = ConfigDict(frozen=True)

    error_code: str | None = None
    subject: str | None = None
    """The object the row is about - the DHIS2 UID a tracker error names, or the conflicting object."""

    message: str | None = None

    @property
    def line(self) -> str:
        """The row as one readable line, which is what a report file and a terminal cell both want."""
        parts = [self.error_code, self.subject, self.message]
        return " ".join(part for part in parts if part) or "no reason given"

    @property
    def reason(self) -> str:
        """What the row says, falling back to the code when DHIS2 gave no message at all."""
        return self.message or self.error_code or "no reason given"


class ForwardCompletenessOutcome(BaseModel):
    """The tuple one aggregate response claims complete, and what DHIS2 said about the claim.

    The four keys are named here rather than left to the import summary because a completeness
    registration is DHIS2's one write with no identity of its own: there is no UID to look it up by,
    only the tuple, so a reader who wants to check it needs the tuple written down.
    """

    model_config = ConfigDict(frozen=True)

    kind: ForwardCompletenessKind
    data_set: str | None = None
    period: str | None = None
    organisation_unit: str | None = None
    attribute_option_combo: str | None = None
    """Unset where the data set rides the default category combo, which is what DHIS2 files it under."""

    date: str | None = None
    message: str | None = None
    """What DHIS2 said when it refused the registration, which is the only thing a refusal can be acted on."""

    issues: tuple[ForwardImportIssue, ...] = ()

    @property
    def tuple_line(self) -> str:
        """The four keys as the one cell a report shows, since the registration has no other name."""
        parts = [self.data_set, self.period, self.organisation_unit, self.attribute_option_combo]
        return " / ".join(part for part in parts if part) or "no tuple"

    @property
    def reason(self) -> str:
        """Why a refused registration was refused, as the one line a table cell and a report both want."""
        lines = [issue.line for issue in self.issues]
        return "; ".join(lines) if lines else (self.message or "DHIS2 gave no reason")


class ForwardImportOutcome(BaseModel):
    """One DHIS2 import answer, projected out of whichever of the two endpoint report shapes carried it.

    `/api/dataValueSets` answers with an `ImportSummary` - an `importCount` and a flat `conflicts` list -
    and `/api/tracker` answers with a `TrackerImportReport` - `stats` and a `validationReport`. The two
    have no shape in common, so this is what both fold into for counting and rendering, with the
    endpoint's own generated report riding alongside untouched for anyone who needs the detail.
    """

    model_config = ConfigDict(frozen=True)

    status: str | None = None
    message: str | None = None
    created: int = 0
    updated: int = 0
    ignored: int = 0
    deleted: int = 0
    issues: tuple[ForwardImportIssue, ...] = ()
    """Every row DHIS2 named as a reason, in the order the report listed them."""

    data_value_summary: ImportSummary | None = None
    tracker_report: TrackerImportReport | None = None

    http_status: int | None = None
    """The failing HTTP status the answer arrived under; None for a 2xx and for a locally made outcome."""

    report_recognised: bool = False
    """Whether the answer carried the import report of the endpoint it was posted to.

    A verdict is a report, not a status line. An authentication gateway, a reverse proxy, and a
    rate limiter all answer JSON of their own, and `{"message": "Forbidden"}` says nothing about
    an import - so what makes an answer a verdict is the endpoint's own report shape being in it.
    """

    @property
    def verdict(self) -> ForwardImportVerdict:
        """Whether this answer accepted the payload, refused it, or reached no verdict about it at all."""
        if not self.report_recognised:
            return ForwardImportVerdict.NONE
        return ForwardImportVerdict.REJECTED if self.is_rejected else ForwardImportVerdict.ACCEPTED

    @property
    def is_accepted(self) -> bool:
        """Whether DHIS2 took the payload: its own import report arrived, and that report names no refusal."""
        return self.verdict is ForwardImportVerdict.ACCEPTED

    @property
    def is_rejected(self) -> bool:
        """Whether DHIS2 refused the payload: an error status, or any row it named against the payload."""
        return self.status == _ERROR_IMPORT_STATUS or bool(self.issues)

    @property
    def counts_line(self) -> str:
        """What the import did, as the one cell a per-response table shows when there is no reason to show."""
        return f"{self.created} created, {self.updated} updated, {self.ignored} ignored"


class ForwardImportRecord(ForwardImportOutcome):
    """The sidecar beside a drained receipt: DHIS2's own answer, plus which payload was posted.

    One shape for both drained states. `rejected/<id>.report.json` says why DHIS2 refused the payload;
    `forwarded/<id>.report.json` says what it did with the one it took, which is the import counts -
    a receipt filed with nothing beside it makes "how much of this landed" a question the spool cannot
    answer, and the number is the same one an operator chases when a report comes out short.

    The target kind is what tells an operator reading either file cold which of the tracker shapes
    DHIS2 was given - a person and their enrollment, or the enrollment alone for a person the instance
    already held - without opening the receipt beside it and reading its extensions back.

    An aggregate payload also records the cells it landed on and the day its receipt arrived, which is
    what makes `forwarded/` answerable about a value a later drain sends again. Identity only, never
    the numbers: what a payload landed on is the spool's business and what it landed is the receipt's.
    """

    target_kind: ConversionTargetKind | None = None
    received_at: str | None = None
    """When the receipt this payload came off was captured, so a later drain can say when it was sent."""

    cells: tuple[AggregateCell, ...] = ()
    """Every aggregate value this payload named, by identity; empty for every tracker payload."""

    completeness: ForwardCompletenessOutcome | None = None
    """What became of this response's completeness claim, and None where it made none.

    Written twice on the way through: `pending` as the receipt is filed, and then the answer once
    the registration has been posted. The pending write is what makes the claim survive a drain that
    dies between the two - the values are in DHIS2 and the registration is not, and this sidecar is
    the only place that fact can live once the receipt has left the queue.
    """


class ForwardRejectionReason(BaseModel):
    """One cause a run's rejections roll up into, and how many responses met it.

    DHIS2 states a rule once and then names the objects that broke it, so two hundred rejections are
    usually a handful of causes. Grouping is on the error code, which is the stable name of a rule -
    the wording DHIS2 wraps it in differs between majors, so grouping on the message would split one
    rule into a row per version. `reason` is the first message the group met, with its quoted UIDs
    generalised away, kept as the sample a reader acts on. A row DHIS2 gave no code for groups on
    that generalised message instead, since it is the only name the rule has.
    """

    model_config = ConfigDict(frozen=True)

    error_code: str | None = None
    reason: str
    responses: int


class ForwardUnverifiableReason(BaseModel):
    """One cause a dry run could not check a payload against, and how many responses met it.

    Separate from `ForwardRejectionReason` because it is a different claim about the run: a rejection
    says the payload is wrong, and this says the run could not tell either way.
    """

    model_config = ConfigDict(frozen=True)

    reason: str
    responses: int


class ForwardStop(BaseModel):
    """Why a drain stopped posting before it had been through everything it translated.

    A stop is the instance failing rather than a payload being refused: a 5xx, or a connection that
    never completed. Neither says anything about the receipt that met it, so the receipt is left in
    the queue for the next drain along with everything behind it - and the run says so, because a
    drain that quietly posted half a spool and reported success is the one failure mode that costs
    data the operator does not know to go looking for.
    """

    model_config = ConfigDict(frozen=True)

    response_id: str
    """The receipt whose post met the failure, which is the one the next drain tries first."""

    status_code: int | None = None
    """The HTTP status the instance answered with, or None when the request never got an answer."""

    reason: str


class ForwardFilingIssue(BaseModel):
    """One receipt whose file was already gone when the drain went to move it.

    A lost race rather than a failure: something else - a second operator, a hand-run `mv` - moved
    the file between the read that listed it and the rename that would have filed it. DHIS2 has
    already answered about the payload either way, so the answer is kept and the run says the file
    was not where it left it, rather than aborting a drain that has done its work.
    """

    model_config = ConfigDict(frozen=True)

    response_id: str
    reason: str


class ForwardOutcome(BaseModel):
    """What one spooled response became: a DHIS2 import answer, or the reasons it never reached DHIS2."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    questionnaire: str | None = None
    target_kind: ConversionTargetKind | None = None
    kind: ForwardOutcomeKind
    notes: tuple[ConversionNote, ...] = ()
    refusals: tuple[ConversionRefusal, ...] = ()
    import_outcome: ForwardImportOutcome | None = None
    completeness: ForwardCompletenessOutcome | None = None
    """What became of an aggregate response's completeness claim; unset for every other payload kind."""

    overwritten_values: tuple[OverwrittenValue, ...] = ()
    """Every value this response sent that a forwarded receipt had already sent, and which receipt sent it.

    Carried only where DHIS2 took the payload, because a payload the instance refused replaced
    nothing. A dry run carries them as the prediction they are: what an import of this spool would
    replace, stated while there is still something to be done about it. Under
    `[forward] overwrites = "refuse"` they are what the drain refused over, and nothing was sent.
    """

    overwrite_refused: bool = False
    """Whether the drain would not post this payload because it holds a value an earlier submission sent.

    Only ever true under `[forward] overwrites = "refuse"`, and only of an aggregate payload. The
    values it was refused over are `overwritten_values`, and the receipt is still in the queue.
    """

    spool_path: str
    """Where the receipt sits now, relative to the project root - unmoved on a dry run and on a refusal."""

    submitted_by: str | None = None
    """The DHIS2 username the facade validated the capture under, carried through from the receipt.

    Facade-side provenance and nothing more. The values this drain posts reach DHIS2 as the
    forwarding profile, and `storedBy` on the instance is DHIS2's own stamp of that profile - so the
    receipt is where "who captured this" is answered, and this field is that answer travelling.
    """


class ForwardReport(BaseModel):
    """The outcome of draining one project's capture spool into DHIS2, in the order it was drained.

    `outcomes` is in spool order, which is not the posting order: payloads go to DHIS2 in
    `FORWARD_TARGET_ORDER`, people first and then the payloads that create an enrollment, so a
    person exists before a registration of the same drain enrols them and an enrollment exists
    before the stage events of the same drain answer against it. The two orders are deliberately
    separate - a report reads back as the spool it drained, and the posting order is a fact about
    the run rather than about any one receipt.
    """

    model_config = ConfigDict(frozen=True)

    project_root: Path
    dry_run: bool
    coded_answer_mode: CodedAnswerMode
    register_completeness: bool = True
    """Whether the run registered completeness for the `completed` aggregate responses DHIS2 took."""

    overwrite_posture: OverwritePosture = OverwritePosture.ALLOW
    """What the run did with an aggregate value a forwarded receipt already sent - post it, or refuse it."""

    correction_posture: CorrectionPosture = CorrectionPosture.OFF
    """What this project does with a submission that names a receipt it corrects, as the run resolved it.

    Stated rather than acted on by the drain, because the two dials that govern a marked submission
    are the deployment's posture rather than one run's: an operator reading a report has to be able
    to see which posture the drain ran under without opening `fhir.toml` beside it.
    """

    withdrawal_posture: WithdrawalPosture = WithdrawalPosture.OFF
    """Whether this project retracts what it forwarded, which is what `d2w fhir withdraw` requires."""

    spooled: int = 0
    outcomes: tuple[ForwardOutcome, ...] = ()
    unreadable_artifacts: tuple[str, ...] = ()
    """Every published non-form document the R4 models could not read, and so translated against nothing."""

    stopped: ForwardStop | None = None
    """Why the drain stopped short, when it did; None is a run that was through the whole spool."""

    quarantined: tuple[QuarantinedFile, ...] = ()
    """Every file in `received/` that would not read as a receipt, moved to `malformed/` and named here."""

    filing_issues: tuple[ForwardFilingIssue, ...] = ()
    """Every receipt whose file had already moved when the drain went to file it."""

    program_rule_names: ProgramRuleNames = Field(default_factory=ProgramRuleNames)
    """The rules the guide publishes, which is what lets a refusal name the rule rather than a UID."""

    completeness_retries: tuple[ForwardCompletenessRetry, ...] = ()
    """Every completeness claim an earlier drain left owed that this drain posted again.

    Values already in DHIS2 whose report was never registered complete. The claim rides in the
    forwarded receipt's own sidecar, so a drain finds it there rather than by re-posting values.
    """

    forwarded_without_values: int = 0
    """Receipts DHIS2 accepted whose sidecar records no values, so this run cannot say what they sent.

    Zero for every spool this toolchain filled, since a drain records an aggregate payload's cells as
    it files the receipt. A count above zero is a spool something else wrote into, and it is stated
    rather than swallowed: those receipts are the ones an overwrite could hide behind.
    """

    @property
    def refused(self) -> tuple[ForwardOutcome, ...]:
        """Every response this run would not send, which is every response that stayed put in the queue."""
        return tuple(outcome for outcome in self.outcomes if outcome.kind == ForwardOutcomeKind.REFUSED)

    @property
    def translator_refused(self) -> tuple[ForwardOutcome, ...]:
        """Every response the translator would not read whole, which is the refusal a guide or a fix answers."""
        return tuple(outcome for outcome in self.refused if not outcome.overwrite_refused)

    @property
    def overwrite_refused(self) -> tuple[ForwardOutcome, ...]:
        """Every response this run would not send because it holds a value an earlier submission already sent.

        Empty under `[forward] overwrites = "allow"`, which posts such a value and names it.
        """
        return tuple(outcome for outcome in self.refused if outcome.overwrite_refused)

    @property
    def accepted(self) -> tuple[ForwardOutcome, ...]:
        """Every response DHIS2 took."""
        return tuple(outcome for outcome in self.outcomes if outcome.kind == ForwardOutcomeKind.ACCEPTED)

    @property
    def rejected(self) -> tuple[ForwardOutcome, ...]:
        """Every response DHIS2 was given and refused."""
        return tuple(outcome for outcome in self.outcomes if outcome.kind == ForwardOutcomeKind.REJECTED)

    @property
    def unverifiable(self) -> tuple[ForwardOutcome, ...]:
        """Every response this dry run could not check, because the run itself would create what it needs."""
        return tuple(outcome for outcome in self.outcomes if outcome.kind == ForwardOutcomeKind.UNVERIFIABLE)

    @property
    def not_posted(self) -> tuple[ForwardOutcome, ...]:
        """Every response the drain stopped short of, which is every response still waiting its turn."""
        return tuple(outcome for outcome in self.outcomes if outcome.kind == ForwardOutcomeKind.NOT_POSTED)

    @property
    def translated_count(self) -> int:
        """How many responses produced a payload.

        An overwrite-refused response produced one and was then not sent, so it counts as translated
        and as refused both - the two numbers answer different questions about the same receipt.
        """
        return self.spooled - len(self.translator_refused)

    @property
    def posted_count(self) -> int:
        """How many payloads were posted to DHIS2."""
        return len(self.accepted) + len(self.rejected) + len(self.unverifiable)

    @property
    def counts_line(self) -> str:
        """The whole run in one line, which is what a progress reporter and a summary hint both want.

        The not-posted clause is stated only by a run that stopped short. It is not a count every run
        has a zero for - it is the shape of a run that ended early, and a reader who sees it needs to
        read no further to know the spool still holds work. The unverifiable clause is stated the same
        way - only by a dry run that had any, since only a dry run can produce the outcome - and the
        mode rides the posted count, so a committed line can never claim a dry run.

        The refused count is every response that stayed in the queue, whether the translator would
        not read it or the run would not overwrite what it holds. One number, because the operator
        reading this line is asking how much of the spool is still waiting; which refusal each one
        met is the report's business, not the summary's.
        """
        posted = f"{self.posted_count:,} posted (validate only)" if self.dry_run else f"{self.posted_count:,} posted"
        line = (
            f"{self.spooled:,} spooled, {self.translated_count:,} translated, {len(self.refused):,} refused, "
            f"{posted}, {len(self.accepted):,} accepted, {len(self.rejected):,} rejected"
        )
        if self.unverifiable:
            line += f", {len(self.unverifiable):,} unverifiable"
        return f"{line}, {len(self.not_posted):,} not posted" if self.stopped is not None else line

    @property
    def completeness_outcomes(self) -> tuple[ForwardCompletenessOutcome, ...]:
        """What every aggregate response of the run said about completeness, in spool order."""
        return tuple(outcome.completeness for outcome in self.outcomes if outcome.completeness is not None)

    def completeness_of(self, kind: ForwardCompletenessKind) -> tuple[ForwardCompletenessOutcome, ...]:
        """Every completeness outcome of one kind, which is what the counts and the report sections read."""
        return tuple(outcome for outcome in self.completeness_outcomes if outcome.kind == kind)

    @property
    def completeness_line(self) -> str:
        """The run's completeness in one line, or nothing at all when no aggregate response claimed any."""
        outcomes = self.completeness_outcomes
        if not outcomes:
            return ""
        counted = Counter(outcome.kind for outcome in outcomes)
        return ", ".join(f"{counted[kind]:,} {kind}" for kind in ForwardCompletenessKind if counted[kind])

    @property
    def completeness_retry_line(self) -> str:
        """The claims earlier drains left owed in one line, or nothing at all when this run met none."""
        if not self.completeness_retries:
            return ""
        counted = Counter(retry.outcome.kind for retry in self.completeness_retries)
        stated = ", ".join(f"{counted[kind]:,} {kind}" for kind in ForwardCompletenessKind if counted[kind])
        return f"{len(self.completeness_retries):,} claim(s) owed by an earlier drain: {stated}"

    @property
    def overwrites(self) -> tuple[ForwardOverwrite, ...]:
        """Every response of the run that sent a value an earlier submission had already sent, in spool order."""
        return tuple(
            ForwardOverwrite(response_id=outcome.response_id, values=outcome.overwritten_values)
            for outcome in self.outcomes
            if outcome.overwritten_values
        )

    @property
    def overwritten_value_count(self) -> int:
        """How many values of the run an earlier submission had already sent."""
        return sum(len(outcome.overwritten_values) for outcome in self.outcomes)

    @property
    def overwrite_line(self) -> str:
        """The run's replaced values in one line, or nothing at all when it sent none a receipt had sent."""
        overwrites = self.overwrites
        if not overwrites:
            return ""
        return f"{self.overwritten_value_count:,} value(s) across {len(overwrites):,} response(s)"

    @property
    def completeness_dry_run_reason(self) -> str:
        """What this dry run could not check about the completeness it would register, or nothing at all."""
        if not self.dry_run or not self.completeness_of(ForwardCompletenessKind.WOULD_REGISTER):
            return ""
        return _COMPLETENESS_DRY_RUN_REASON

    @property
    def rejection_reasons(self) -> tuple[ForwardRejectionReason, ...]:
        """Every rejection of the run rolled up by cause, commonest first, so a wall of them reads as a few.

        A response counts once per distinct cause it met, however many rows named that cause, so
        `E1029` against two different pairs of objects is one cause of the run rather than two. The
        message shown for a cause is the first one the run met, with the quoted UIDs DHIS2 embeds in
        it generalised away.
        """
        counted: Counter[tuple[str | None, str]] = Counter()
        samples: dict[tuple[str | None, str], str] = {}
        for outcome in self.rejected:
            imported = outcome.import_outcome
            issues = imported.issues if imported is not None else ()
            causes: dict[tuple[str | None, str], str] = {}
            for issue in issues:
                reason = _generalised_reason(issue.reason, self.program_rule_names)
                causes.setdefault(_rejection_cause_key(issue.error_code, reason), reason)
            if not causes:
                message = (imported.message or "DHIS2 gave no reason") if imported is not None else ""
                causes[(None, message)] = message
            counted.update(causes.keys())
            for key, reason in causes.items():
                samples.setdefault(key, reason)
        ordered = sorted(counted.items(), key=lambda item: (-item[1], item[0][0] or "", item[0][1]))
        return tuple(
            ForwardRejectionReason(error_code=key[0], reason=samples[key], responses=responses)
            for key, responses in ordered
        )

    @property
    def unverifiable_reasons(self) -> tuple[ForwardUnverifiableReason, ...]:
        """What the run could not check and why, as the section a reader acts on without knowing DHIS2 codes."""
        if not self.unverifiable:
            return ()
        return (
            ForwardUnverifiableReason(
                reason=_UNVERIFIABLE_IN_DRY_RUN_REASON,
                responses=len(self.unverifiable),
            ),
        )


def _compiled_artifacts_or_none(project: FhirProject) -> CompiledArtifacts | None:
    """The project's compiled guide, or None when it holds none and the live build stands in for it.

    Absence of the compiled tree is the whole trigger - a project that has run SUSHI reads its own
    build, and one that never has had nothing to read. `[forward] live = false` turns the stand-in
    off, and the refusal naming the two commands that produce a build is then what a drain answers.
    """
    try:
        return load_compiled_artifacts(project)
    except CompiledIgMissingError:
        if not project.config.forward.live:
            raise
        return None


def _artifacts_completion(artifacts: CompiledArtifacts) -> str:
    """What one guide amounted to, however it was read: the resources kept, the forms among them."""
    unreadable = f", {len(artifacts.unreadable_resources):,} unreadable" if artifacts.unreadable_resources else ""
    return f"{artifacts.resource_count:,} resource(s), {len(artifacts.questionnaires):,} form(s){unreadable}"


async def forward_responses(
    profile: Profile,
    project: FhirProject,
    *,
    import_responses: bool | None = None,
    coded_answer_mode: CodedAnswerMode | None = None,
    register_completeness: bool | None = None,
    overwrites: OverwritePosture | None = None,
    corrections: CorrectionPosture | None = None,
    withdrawals: WithdrawalPosture | None = None,
    reporter: ProgressReporter | None = None,
    client: Dhis2Client | None = None,
) -> ForwardReport:
    """Drain a project's capture spool into DHIS2: translate every receipt, post it, and file what it became.

    THE SIX DIALS ARE RESOLVED HERE, so the CLI and the MCP tool cannot resolve them differently.
    `import_responses`, `register_completeness`, `overwrites`, `corrections`, `withdrawals`, and
    `coded_answer_mode` are each None for "the caller stated nothing", and each falls to what
    `fhir.toml` says - `[forward] import`, `[forward] register_completeness`, `[forward] overwrites`,
    `[forward] corrections`, `[forward] withdrawals`, and `[serve] strict_codes` - which in turn fall
    to the defaults those keys carry.

    A **dry run is the default**. Every payload still goes to the real endpoint against the real
    instance, under that endpoint's own validate-only mode - `dryRun=true` for `/api/dataValueSets`,
    `importMode=VALIDATE` for `/api/tracker` - so the whole loop is exercised, DHIS2's own rules
    decide the answer, and nothing is written and nothing is moved. `import_responses=True` commits,
    and only then does the spool move: an accepted receipt to `forwarded/`, a rejected one to
    `rejected/` beside a `<id>.report.json` holding its outcome. A conversion-refused receipt stays
    in `received/` whichever mode ran, because the fix for it is in the guide or in the data and the
    next run is the retry.

    One client serves the run. It reads the DHIS2 value types behind the questions the published forms
    bind - the one fact the compiled IG cannot carry, since R4 spells `BOOLEAN` and `TRUE_ONLY` as the
    same `#boolean` item type - and then posts every translated payload through the same connection.
    `client` is that connection when the caller already holds one, which the drain reads and posts
    through and leaves open; with none, the profile opens one for the length of the drain.

    A guide reaches the run one of two ways, and the project decides which by what it holds. A
    compiled `ig/fsh-generated/resources` is read off disk. A project that has never run SUSHI - which
    is every project captured through `d2w fhir serve --live` - has that guide built off the instance
    instead, by the very builders the live facade serves from, so a receipt captured without a build
    step forwards without one. The cost is a full metadata read per drain and the progress step says
    so. `[forward] live = false` turns the stand-in off and restores the refusal naming
    `d2w fhir generate` and `make sushi`.

    Registrations post first. A tracker program's registration response creates the enrollment its
    stage responses answer against, and a client captures both in one sitting, so a drain holding
    the pair posts the tracked entity before the events - otherwise DHIS2 refuses each event with
    `E1313` for an enrollment that does not exist yet. Nothing tracks which event belongs to which
    registration: the ordering is by payload kind, and a registration DHIS2 rejects leaves its
    events to fail as they would have anyway, for the next drain to retry.

    A dry run cannot prove one thing an import can. `importMode=VALIDATE` writes nothing, so the
    enrollment a registration of the same run mints does not exist when the stage event naming it is
    checked, and DHIS2 answers that event `E1313` plus the `E1079` program mismatch it asserts against
    the absent enrollment. Those responses are counted `unverifiable` rather than `rejected`: the
    enrollment they name is one this run's registrations mint, and an import posts registrations
    first. An event naming an enrollment no registration of the run mints is a rejection either way.

    An aggregate response reporting itself `completed` also registers completeness - the data set is
    marked complete for the very tuple its values landed under. That is a second write to a second
    resource (`/api/completeDataSetRegistrations`), and it happens **only after DHIS2 has taken the
    values**: a completeness claim about data the instance refused would be a lie. A response
    reporting itself `in-progress` imports its values and registers nothing, and a run under
    `register_completeness=False` registers nothing at all. A registration DHIS2 refuses does not
    un-import the values - they stay imported, and the response is still `accepted` - so the refusal
    is carried on the outcome and stated in the report rather than folded into the import answer.

    A CLAIM THAT NEVER LANDED IS OWED, AND A LATER DRAIN PAYS IT. The receipt is filed the moment
    DHIS2 takes the values, with its own sidecar recording the completeness claim as `pending`, and
    the registration writes the answer over that. A drain that is killed between the two, or whose
    registration times out, therefore leaves the claim written down in `forwarded/<id>.report.json`
    rather than nowhere. An importing run scans the forwarded sidecars for those claims and posts
    them again, on their own - the values are already in the instance and not one of them is sent a
    second time - and it does so even when the queue is empty, because an empty queue is exactly the
    state a drain that finished its posting leaves behind. Registering a tuple DHIS2 already holds
    is an update rather than a conflict, so a claim that turns out to have landed costs nothing.

    AN AGGREGATE VALUE A FORWARDED RECEIPT ALREADY SENT IS NAMED IN THE REPORT. DHIS2 replaces such a
    value in place and counts the write exactly as it counts a first entry, so no import summary can
    separate the two - and this run therefore says which is which, off the spool's own record of what
    each forwarded receipt landed. The run names the value, the receipt that sent it before, and when
    that receipt arrived, and it says the same thing on a dry run, where it is a prediction there is
    still time to act on.

    `overwrites` decides what the run then does about it. `"allow"` - the default - posts the value
    and names it, which is DHIS2's own last-write-wins semantics stated as a chosen posture: the
    instance holds what the newest submission carried, and the run is what says so. `"refuse"` posts
    no payload holding such a value at all. The refusal is per response and never per value - a
    payload half posted would tear one submission across two postures - and it is not terminal: the
    receipt stays in `received/` with an `<id>.refusal.json` naming every covered value and the
    receipt that sent it, so `d2w fhir spool` shows it as refused-but-queued and the next drain
    posts it once the dial is flipped or `d2w fhir requeue` has been used. A dry run under `"refuse"`
    states what it would refuse and files nothing, exactly as it moves nothing.

    `corrections` and `withdrawals` are the deployment's posture towards a *marked* submission, where
    `overwrites` is its posture towards an unmarked one, and the run states both rather than acting
    on either: a drain neither amends nor retracts, and `d2w fhir withdraw` is what reads
    `withdrawals`. They are resolved here so that the posture a report names is the posture every
    surface of this project resolves, and so a deployment can see its own dial being read before the
    capability it gates arrives.

    `coded_answer_mode` defaults to what `[serve] strict_codes` says, so a project that captures
    strictly forwards strictly without stating it twice.

    The spool this drains is the one `[serve] spool_dir` names, read through the same resolution the
    server writes it through - so a project that moved its receipt tree moved it for both halves of
    the loop at once.

    ONE DRAIN AT A TIME, AND EACH RECEIPT FILED THE MOMENT ITS VERDICT IS KNOWN. The run holds an
    exclusive lock on the spool root for its whole length, so a second drain of the same project
    fails at once naming the process that holds it rather than posting every payload twice. Inside
    the run, a receipt moves to `forwarded/` or `rejected/` beside its report as soon as DHIS2 has
    answered about it - not in a pass at the end - so a drain that is killed halfway leaves every
    already-posted receipt filed with what DHIS2 said and every unposted one untouched in the queue.

    A file in `received/` that does not read as a receipt is moved to `malformed/` with its reason
    beside it and named in the report; the drain proceeds with the rest.
    """
    mode = coded_answer_mode if coded_answer_mode is not None else _configured_coded_answer_mode(project)
    forward_config = project.config.forward
    importing = import_responses if import_responses is not None else forward_config.import_responses
    registering = register_completeness if register_completeness is not None else forward_config.register_completeness
    posture = overwrites if overwrites is not None else forward_config.overwrites
    correcting = corrections if corrections is not None else forward_config.corrections
    withdrawing = withdrawals if withdrawals is not None else forward_config.withdrawals
    with drain_lock(spool_layout(project)):
        return await _drain_spool(
            profile,
            project,
            mode=mode,
            import_responses=importing,
            register_completeness=registering,
            overwrites=posture,
            corrections=correcting,
            withdrawals=withdrawing,
            reporter=reporter,
            client=client,
        )


async def _drain_spool(
    profile: Profile,
    project: FhirProject,
    *,
    mode: CodedAnswerMode,
    import_responses: bool,
    register_completeness: bool,
    overwrites: OverwritePosture,
    corrections: CorrectionPosture,
    withdrawals: WithdrawalPosture,
    reporter: ProgressReporter | None,
    client: Dhis2Client | None = None,
) -> ForwardReport:
    """Run one drain, with the spool lock already held - the body `forward_responses` documents."""
    progress = _StepAnnouncer(reporter, FORWARD_STEPS)
    progress.step("spool", "reading the capture spool")
    layout = spool_layout(project)
    sweep_orphan_temporary_files(layout)
    reading = read_received_responses(layout)
    spooled = reading.responses
    quarantined_note = f", {len(reading.quarantined):,} moved to malformed/" if reading.quarantined else ""
    progress.complete(f"{len(spooled):,} pending response(s){quarantined_note}")

    compiled = _compiled_artifacts_or_none(project)
    if compiled is not None:
        progress.step("guide", "reading the published guide")
        progress.complete(_artifacts_completion(compiled))

    naming = ConversionNaming.from_config(project.config.generate, project.config.ig.canonical)
    dry_run = not import_responses
    owed = _owed_completeness_claims(layout) if register_completeness and not dry_run else ()
    if not spooled:
        # Nothing to translate ends the run here, before a client is opened. The reads past this
        # point exist to translate receipts - the guide off the instance when this project holds no
        # compiled one, then the value type of every question the forms bind - and against a large
        # instance that is thousands of resources fetched to answer a report that says zero. The
        # spool is read first and the compiled guide off disk, so a receipt this run cannot read
        # still raises, and a project with no build still hears about it.
        retries: tuple[ForwardCompletenessRetry, ...] = ()
        if owed:
            progress.step("completeness", "registering the reports an earlier drain left owed")
            async with _instance_connection(profile, client) as connection:
                retries = await _retry_owed_completeness(connection, layout, owed, progress)
            progress.complete(_completeness_retry_completion(retries))
        report = ForwardReport(
            project_root=project.project_root,
            dry_run=dry_run,
            coded_answer_mode=mode,
            register_completeness=register_completeness,
            overwrite_posture=overwrites,
            correction_posture=corrections,
            withdrawal_posture=withdrawals,
            unreadable_artifacts=() if compiled is None else compiled.unreadable_resources,
            quarantined=reading.quarantined,
            completeness_retries=retries,
        )
        progress.complete(report.counts_line)
        return report
    async with _instance_connection(profile, client) as client:
        if compiled is None:
            progress.step("guide", "building the guide off the instance, this project holding no compiled one")
            artifacts = await fetch_live_artifacts(client, project, progress=progress)
            progress.complete(_artifacts_completion(artifacts))
        else:
            artifacts = compiled
        bound = bound_question_uids(artifacts, naming)

        progress.step("value types", "reading the value types the forms bind")
        value_types = await _fetch_value_types(client, bound, progress=progress)
        progress.complete(f"{len(value_types):,} of {bound.total:,} question object(s) typed")

        context = build_project_context(
            project,
            artifacts,
            value_types_by_data_element=value_types,
            coded_answer_mode=mode,
        )
        progress.step("translate", "translating the spooled responses")
        conversion = translate_responses([entry.response for entry in spooled], context)
        progress.complete(f"{len(conversion.translated):,} translated, {len(conversion.refused):,} refused")

        terminal = _file_terminal_refusals(spooled, conversion, moving=import_responses)
        _record_refusals(spooled, conversion, moving=import_responses)
        overwrite_index = _forwarded_cell_index(layout, conversion)

        progress.step("post", _post_caption(0, len(conversion.translated), dry_run=dry_run))
        posted = await _post_translations(
            client,
            spooled,
            conversion,
            dry_run=dry_run,
            moving=import_responses,
            overwrite_index=overwrite_index,
            overwrites=overwrites,
            registering=register_completeness,
            progress=progress,
        )
        stopped_note = f", stopped: {posted.stopped.reason}" if posted.stopped is not None else ""
        refused_note = (
            f", {len(posted.overwrite_refused):,} refused as an overwrite" if posted.overwrite_refused else ""
        )
        progress.complete(
            f"{len(posted.imports):,} payload(s) posted{' (validate only)' if dry_run else ''}"
            f"{refused_note}{stopped_note}"
        )

        progress.step("completeness", "registering the completed reports")
        completeness_retries = await _retry_owed_completeness(client, layout, owed, progress)
        completeness = await _register_completeness(
            client,
            layout,
            spooled,
            conversion,
            posted.imports,
            dry_run=dry_run,
            registering=register_completeness,
            overwrite_refused=posted.overwrite_refused,
            progress=progress,
        )
        retry_note = _completeness_retry_note(completeness_retries)
        progress.complete(
            _completeness_completion(completeness, dry_run=dry_run, registering=register_completeness) + retry_note
        )

    progress.step("spool", "stating what each response became")
    minted_enrollments = _minted_enrollment_uids(conversion) if dry_run else frozenset[str]()
    filed = {**terminal.paths, **posted.filed}
    outcomes = _collect_outcomes(
        spooled,
        conversion,
        posted.imports,
        completeness,
        project.project_root,
        filed=filed,
        minted_enrollments=minted_enrollments,
        overwritten=posted.overwritten,
        overwrite_refused=posted.overwrite_refused,
    )
    report = ForwardReport(
        project_root=project.project_root,
        dry_run=dry_run,
        coded_answer_mode=mode,
        register_completeness=register_completeness,
        overwrite_posture=overwrites,
        correction_posture=corrections,
        withdrawal_posture=withdrawals,
        spooled=len(spooled),
        outcomes=outcomes,
        unreadable_artifacts=artifacts.unreadable_resources,
        stopped=posted.stopped,
        quarantined=reading.quarantined,
        filing_issues=(*terminal.issues, *posted.filing_issues),
        program_rule_names=program_rule_names(artifacts, naming),
        completeness_retries=completeness_retries,
        forwarded_without_values=overwrite_index.receipts_without_values,
    )
    progress.complete(report.counts_line)
    return report


def _forwarded_cell_index(layout: SpoolLayout, conversion: ConversionReport) -> ForwardedCellIndex:
    """Read what this spool has already landed in DHIS2, and only when this drain could land on it again.

    A drain carrying no aggregate payload cannot replace an aggregate value, so it reads nothing at
    all - `forwarded/` is unbounded, and a tracker run has no reason to pay for a directory it cannot
    collide with. A drain that does carry one pays a single pass: see `dhis2w_fhir.overwrite`.
    """
    if not any(result.payload_of(DataValueSet) is not None for result in conversion.translated):
        return ForwardedCellIndex()
    return build_forwarded_cell_index(layout)


def _configured_coded_answer_mode(project: FhirProject) -> CodedAnswerMode:
    """The coded-answer dial a project forwards under, which is the one it captures under."""
    return CodedAnswerMode.STRICT if project.config.serve.strict_codes else CodedAnswerMode.LENIENT


def spool_layout(project: FhirProject) -> SpoolLayout:
    """Where this project's receipts live, off the `[serve] spool_dir` the server writes them under."""
    return SpoolLayout.resolve(project.project_root, project.config.serve.spool_dir)


async def _fetch_value_types(
    client: Dhis2Client,
    bound: BoundQuestionUids,
    *,
    progress: _StepAnnouncer,
) -> dict[str, str]:
    """Read the DHIS2 value type of every object the published forms ask a question from, in id-only batches.

    Two reads over one table. A link id names a data element on three form kinds and a tracked
    entity attribute on the registration one, and the two live behind different endpoints - but a
    UID identifies exactly one DHIS2 object, so both answers land in the single
    `value_types_by_data_element` map the translation context takes.
    """
    value_types: dict[str, str] = {}
    for batch in _uid_batches(bound.data_element_uids):
        progress.tick(_value_type_caption(len(value_types) + len(batch), bound.total))
        data_elements: list[DataElement] = await client.resources.data_elements.list(
            fields=_VALUE_TYPE_FIELDS, filters=[_uid_filter(batch)], paging=False
        )
        for data_element in data_elements:
            if data_element.id and data_element.valueType is not None:
                value_types[data_element.id] = data_element.valueType.value
    for batch in _uid_batches(bound.tracked_entity_attribute_uids):
        progress.tick(_value_type_caption(len(value_types) + len(batch), bound.total))
        attributes: list[TrackedEntityAttribute] = await client.resources.tracked_entity_attributes.list(
            fields=_VALUE_TYPE_FIELDS, filters=[_uid_filter(batch)], paging=False
        )
        for attribute in attributes:
            if attribute.id and attribute.valueType is not None:
                value_types[attribute.id] = attribute.valueType.value
    return value_types


def _uid_batches(uids: Sequence[str]) -> list[list[str]]:
    """Split one read's UIDs into the batches an `id:in:[...]` filter carries without growing unbounded."""
    return [list(uids[start : start + _VALUE_TYPE_BATCH_SIZE]) for start in range(0, len(uids), _VALUE_TYPE_BATCH_SIZE)]


def _value_type_caption(read: int, total: int) -> str:
    """The live caption the value-type step re-writes itself with as the two reads drain."""
    return f"reading value types ({min(read, total):,}/{total:,})"


def _post_caption(posted: int, total: int, *, dry_run: bool) -> str:
    """The live caption the posting step re-writes itself with as the batch drains."""
    verb = "validating" if dry_run else "importing"
    return f"{verb} payloads ({posted:,}/{total:,})"


class _FiledReceipts(BaseModel):
    """Where the receipts one pass filed now sit, and every move that found nothing to move."""

    model_config = ConfigDict(frozen=True)

    paths: dict[str, Path] = Field(default_factory=dict)
    """Where each filed receipt landed, keyed by response id; a receipt that stayed put is absent."""

    issues: tuple[ForwardFilingIssue, ...] = ()


class _PostedPayloads(BaseModel):
    """What one drain's posting pass got through, and why it stopped if it did not get through it all."""

    model_config = ConfigDict(frozen=True)

    imports: dict[str, ForwardImportOutcome] = Field(default_factory=dict)
    """DHIS2's answer per receipt, holding an entry only for the receipts that were actually posted."""

    filed: dict[str, Path] = Field(default_factory=dict)
    """Where each posted receipt was filed as its verdict arrived; empty on a dry run, which moves nothing."""

    overwritten: dict[str, tuple[OverwrittenValue, ...]] = Field(default_factory=dict)
    """Per receipt, the values it sent that an earlier submission had already sent; absent where it sent none."""

    overwrite_refused: frozenset[str] = frozenset()
    """Which receipts the pass would not post at all, because `overwrites = "refuse"` and they held one."""

    filing_issues: tuple[ForwardFilingIssue, ...] = ()
    stopped: ForwardStop | None = None


async def _post_translations(
    client: Dhis2Client,
    spooled: Sequence[SpooledResponse],
    conversion: ConversionReport,
    *,
    dry_run: bool,
    moving: bool,
    overwrite_index: ForwardedCellIndex,
    overwrites: OverwritePosture,
    registering: bool,
    progress: _StepAnnouncer,
) -> _PostedPayloads:
    """Post every translated payload one at a time, filing each receipt as soon as DHIS2 answers about it.

    One payload per POST is what makes the outcome attributable: DHIS2 answers a bundle with one
    report for the bundle, and a spool whose receipts move individually needs one answer each.

    The order is `FORWARD_TARGET_ORDER` first, which is what makes one drain internally consistent:
    a person-only capture creates the person a registration captured seconds later enrols, a
    registration creates the enrollment a stage event captured seconds later answers against, and
    DHIS2 refuses an event naming an enrollment it cannot find with `E1313`. Posting by kind is the
    whole of the coordination - there is no dependency graph, and a registration DHIS2 rejects still
    leaves its stage events to fail `E1313`, which the next drain retries once the cause is fixed.

    Inside one kind the order is arrival, `received_at` then the receipt id. DHIS2 replaces an
    aggregate value in place, so the instance holds whatever was posted last, and posting the oldest
    submission of a cell last would leave it holding the oldest number. Arrival order is also what
    `dhis2w_fhir.overwrite` reads the forwarded index by, so the drain and the index name the same
    receipt as the sender of each cell.

    **The receipt is filed the instant its verdict is known**, sidecar first and then the rename, so
    the disk agrees with DHIS2 at every point of the loop rather than only at the end of it. A drain
    that is killed, loses its terminal, or meets an unwell instance leaves everything it posted in
    `forwarded/` or `rejected/` with the report beside it, and everything it had not reached
    untouched in `received/`. A dry run files nothing, because it wrote nothing.

    **An answer that reaches no verdict stops the drain too.** A receipt only leaves `received/` on
    the endpoint's own import report - the shape only `/api/dataValueSets` or `/api/tracker` answers
    with. A `401`, a `403`, a `404`, a `429`, or a success carrying some other document is whatever
    stands in front of the instance answering instead of it, and filing a receipt on one would drop
    a submission out of the queue that DHIS2 never saw. So the drain stops naming the status, the
    receipt keeps its place, and the next drain posts it again.

    **An instance that fails mid-drain stops the drain.** A 5xx or a connection that never completed
    is the instance being unwell, not a verdict on the payload that met it, and the two things that
    must not happen next are posting the remaining two hundred payloads into it and filing the
    receipt that met it as though DHIS2 had refused it. So the pass stops where it is and answers
    with the outcomes it did get; the receipts already filed stay filed, everything from the failure
    onwards is untouched in `received/`, and the report names what stopped it.

    **An aggregate payload is read against what this spool has already landed, before it is sent.**
    DHIS2 replaces a value it already holds without saying so, so the index answers the question the
    import summary cannot: which of these values a forwarded receipt already sent, and which one. The
    reading is taken before the post and kept only where DHIS2 took the payload - a refused payload
    replaced nothing - and each taken payload then joins the index, so two captures of one value
    inside a single drain are the same finding as two captures a week apart.

    **Under `overwrites = "refuse"` such a payload is not sent at all, and the whole response is what
    is refused.** A payload holding one covered value among ten fresh ones is still one submission,
    and posting the nine while refusing the one would tear a single form across two postures and
    leave the instance holding a report nobody filled in. So the response is refused whole, it keeps
    its place in `received/`, and a committing run writes the refusal record beside it. Nothing joins
    the index either: a payload that was never sent landed nothing.
    """
    translated = sorted(
        ((entry, result) for entry, result in zip(spooled, conversion.results, strict=True) if not result.is_refused),
        key=lambda pair: (_post_order(pair[1]), pair[0].received_at, pair[0].response_id),
    )
    imports: dict[str, ForwardImportOutcome] = {}
    filed: dict[str, Path] = {}
    overwritten: dict[str, tuple[OverwrittenValue, ...]] = {}
    refused: set[str] = set()
    issues: list[ForwardFilingIssue] = []
    refused_at = _utc_instant()
    for posted, (entry, result) in enumerate(translated, start=1):
        envelope = result.payload_of(DataValueSet)
        cells = aggregate_cells(envelope) if envelope is not None else ()
        already_sent = overwrite_index.already_sent(cells)
        if already_sent and overwrites is OverwritePosture.REFUSE:
            overwritten[entry.response_id] = already_sent
            refused.add(entry.response_id)
            _record_overwrite_refusal(entry, already_sent, refused_at=refused_at, moving=moving)
        else:
            try:
                imported = await _post_result(client, result, dry_run=dry_run)
            except (Dhis2ApiError, AuthenticationError, httpx.HTTPError) as error:
                return _PostedPayloads(
                    imports=imports,
                    filed=filed,
                    overwritten=overwritten,
                    overwrite_refused=frozenset(refused),
                    filing_issues=tuple(issues),
                    stopped=_forward_stop(entry, error),
                )
            if imported.verdict is ForwardImportVerdict.NONE:
                return _PostedPayloads(
                    imports=imports,
                    filed=filed,
                    overwritten=overwritten,
                    overwrite_refused=frozenset(refused),
                    filing_issues=tuple(issues),
                    stopped=_non_verdict_stop(entry, imported),
                )
            imports[entry.response_id] = imported
            if cells and imported.is_accepted:
                if already_sent:
                    overwritten[entry.response_id] = already_sent
                overwrite_index.record(
                    cells, ForwardedSubmission(response_id=entry.response_id, received_at=entry.received_at)
                )
            if moving:
                _file_now(
                    entry,
                    imported,
                    result.target_kind,
                    cells,
                    filed,
                    issues,
                    completeness=_owed_claim_outcome(result, imported, registering=registering),
                )
        if posted % _POST_TICK_INTERVAL == 0 or posted == len(translated):
            progress.tick(_post_caption(posted, len(translated), dry_run=dry_run))
    return _PostedPayloads(
        imports=imports,
        filed=filed,
        overwritten=overwritten,
        overwrite_refused=frozenset(refused),
        filing_issues=tuple(issues),
    )


def _owed_claim_outcome(
    result: ConversionResult, imported: ForwardImportOutcome, *, registering: bool
) -> ForwardCompletenessOutcome | None:
    """The completeness a receipt is filed owing, which is what makes the claim survive the drain.

    A claim is owed the moment DHIS2 takes the values and until the registration is posted, so the
    sidecar records it as `pending` at filing time and the registration step overwrites it with the
    answer. A run that registers nothing owes nothing, and neither does a response that claimed none
    or a payload DHIS2 refused.
    """
    claim = result.completeness
    if claim is None or not registering or not imported.is_accepted:
        return None
    return _completeness_outcome(ForwardCompletenessKind.PENDING, claim)


def _file_now(
    entry: SpooledResponse,
    imported: ForwardImportOutcome,
    target_kind: ConversionTargetKind | None,
    cells: tuple[AggregateCell, ...],
    filed: dict[str, Path],
    issues: list[ForwardFilingIssue],
    *,
    completeness: ForwardCompletenessOutcome | None = None,
) -> None:
    """Move one receipt into the state DHIS2 just put it in, its import report written down first.

    Only an answer that reached a verdict gets here: `forwarded/` for the payload DHIS2's own import
    report says it took, `rejected/` for the one that report refuses. An answer carrying no import
    report at all stops the drain instead, with the receipt left in `received/`.

    A receipt whose file has already gone is graded rather than raised: DHIS2 has answered about the
    payload, and losing the rest of the drain over a rename that lost a race would throw that answer
    away along with every receipt still queued behind it.

    The report carries the cells an aggregate payload named and the day the receipt arrived, which is
    what lets the next drain say that a value it is about to send is one this receipt already sent.
    """
    record = ForwardImportRecord(
        **dict(imported),
        target_kind=target_kind,
        received_at=entry.received_at or None,
        cells=cells,
        completeness=completeness,
    )
    try:
        filed[entry.response_id] = (
            move_to_forwarded(entry, record) if imported.is_accepted else move_to_rejected(entry, record)
        )
    except FileNotFoundError as error:
        issues.append(
            ForwardFilingIssue(
                response_id=entry.response_id,
                reason=f"{entry.path} was gone when the drain went to file it ({error}); DHIS2's answer is in "
                f"this report and the receipt is wherever whatever moved it put it",
            )
        )


def _file_terminal_refusals(
    spooled: Sequence[SpooledResponse], conversion: ConversionReport, *, moving: bool
) -> _FiledReceipts:
    """File every receipt whose refusal nothing can fix, so no drain ever translates it again.

    `TERMINAL_REFUSAL_CATEGORIES` is the whole of the judgment, and the sidecar states it in the
    receipt's own directory so the file explains itself. A dry run files nothing, exactly as it moves
    nothing else, and `d2w fhir requeue` is the way back for an operator who disagrees.
    """
    if not moving:
        return _FiledReceipts()
    paths: dict[str, Path] = {}
    issues: list[ForwardFilingIssue] = []
    for entry, result in zip(spooled, conversion.results, strict=True):
        if not _is_terminally_refused(result):
            continue
        record = ForwardImportRecord(
            status=_TERMINAL_REFUSAL_STATUS,
            message=_TERMINAL_REFUSAL_MESSAGE,
            issues=tuple(
                ForwardImportIssue(error_code=refusal.category.value, subject=refusal.element, message=refusal.reason)
                for refusal in result.refusals
            ),
            target_kind=result.target_kind,
        )
        try:
            paths[entry.response_id] = move_to_rejected(entry, record)
        except FileNotFoundError as error:
            issues.append(
                ForwardFilingIssue(
                    response_id=entry.response_id,
                    reason=f"{entry.path} was gone when the drain went to file it ({error})",
                )
            )
    return _FiledReceipts(paths=paths, issues=tuple(issues))


def _is_terminally_refused(result: ConversionResult) -> bool:
    """Whether a refusal is one no change to the guide and no change to the data could ever resolve."""
    return any(refusal.category in TERMINAL_REFUSAL_CATEGORIES for refusal in result.refusals)


def _record_refusals(spooled: Sequence[SpooledResponse], conversion: ConversionReport, *, moving: bool) -> None:
    """Write the refusal record beside every receipt this committing drain refused and left queued.

    The receipt stays in `received/` for the next drain to retry, and until now it read in a
    listing exactly like one no drain had touched. The record beside it - the drain's instant, how
    many drains have refused it so far, and why - is what lets `/facade/spool` and `d2w fhir spool` say
    the difference. A dry run writes nothing, exactly as it moves nothing; a terminal refusal is
    filed to `rejected/` instead - see `_file_terminal_refusals`.
    """
    if not moving:
        return
    refused_at = _utc_instant()
    for entry, result in zip(spooled, conversion.results, strict=True):
        if not result.is_refused or _is_terminally_refused(result):
            continue
        previous = read_refusal_record(entry.path.parent, entry.response_id)
        record_refusal(
            entry,
            ForwardRefusalRecord(
                refused_at=refused_at,
                attempt_count=1 if previous is None else previous.attempt_count + 1,
                reasons=tuple(
                    RefusalReason(category=refusal.category.value, element=refusal.element, reason=refusal.reason)
                    for refusal in result.refusals
                ),
            ),
        )


def _record_overwrite_refusal(
    entry: SpooledResponse, values: Sequence[OverwrittenValue], *, refused_at: str, moving: bool
) -> None:
    """Write the refusal record beside one receipt this committing drain would not overwrite with.

    The same sidecar a translator refusal writes, under a category of its own, because the receipt
    ends in the same place: still in `received/`, still drainable, and now carrying the reason. Each
    value it was refused over is a reason of its own, naming the cell, the receipt that sent it, and
    when that receipt arrived - which is what an operator needs to decide between flipping the dial
    and going back to the earlier submission. The attempt count carries over from whatever record was
    already there, so a receipt three drains have refused says three whichever refusal it met.

    A dry run writes nothing, exactly as it moves nothing: it says what it would refuse and leaves
    the queue as it found it.
    """
    if not moving:
        return
    previous = read_refusal_record(entry.path.parent, entry.response_id)
    record_refusal(
        entry,
        ForwardRefusalRecord(
            refused_at=refused_at,
            attempt_count=1 if previous is None else previous.attempt_count + 1,
            reasons=tuple(
                RefusalReason(category=OVERWRITE_REFUSAL_CATEGORY, element=value.cell.data_element, reason=value.line)
                for value in values
            ),
        ),
    )


def _utc_instant() -> str:
    """The current instant as a FHIR `instant` - UTC, seconds precision, `Z`-suffixed."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _non_verdict_stop(entry: SpooledResponse, imported: ForwardImportOutcome) -> ForwardStop:
    """Name the answer that was about the run rather than about the payload, so the operator reads a status.

    Whatever answered was not the import endpoint reaching a verdict, so the receipt is left in
    `received/` exactly as a 5xx leaves it and every receipt behind it keeps its turn. The status is
    the whole of the lead: a 401 or a 403 is a credential, a 404 is a path or a proxy, a 429 is a
    rate limiter, and a success carrying no report is an endpoint answering something else entirely.
    """
    answered = f"answered {imported.http_status}" if imported.http_status is not None else "answered a success status"
    stated = f": {imported.message}" if imported.message else ""
    return ForwardStop(
        response_id=entry.response_id,
        status_code=imported.http_status,
        reason=f"the instance {answered} with no import report, which is no verdict about the payload{stated}",
    )


def _forward_stop(entry: SpooledResponse, error: Dhis2ApiError | AuthenticationError | httpx.HTTPError) -> ForwardStop:
    """Name what stopped one drain, in the terms the operator has to act on."""
    if isinstance(error, AuthenticationError):
        return ForwardStop(
            response_id=entry.response_id,
            status_code=_UNAUTHORIZED_STATUS,
            reason=f"the instance answered {_UNAUTHORIZED_STATUS} and took no payload: {error}",
        )
    if isinstance(error, Dhis2ApiError):
        return ForwardStop(
            response_id=entry.response_id,
            status_code=error.status_code,
            reason=f"the instance answered {error.status_code} rather than an import report: {error.message}",
        )
    return ForwardStop(response_id=entry.response_id, reason=f"the instance could not be reached: {error}")


class _OwedCompletenessClaim(BaseModel):
    """One forwarded receipt whose values landed and whose completeness registration did not."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    claim: CompleteDataSetRegistration


def _forwarded_import_record(layout: SpoolLayout, response_id: str) -> ForwardImportRecord | None:
    """One forwarded receipt's sidecar, or None when there is none to read or it will not parse."""
    for filed_id, text in read_import_reports(layout, SpoolState.FORWARDED):
        if filed_id != response_id:
            continue
        try:
            return ForwardImportRecord.model_validate_json(text)
        except (ValidationError, ValueError):
            return None
    return None


def _owed_completeness_claims(layout: SpoolLayout) -> tuple[_OwedCompletenessClaim, ...]:
    """Every completeness claim `forwarded/` records as still owed, in the order the directory reads.

    One pass over the sidecars, which is the same pass `build_forwarded_cell_index` takes and the
    price of a claim that survives the drain that made it. A sidecar that will not read is left out
    rather than raised: one unreadable file must not cost the other claims their retry.
    """
    owed: list[_OwedCompletenessClaim] = []
    for response_id, text in read_import_reports(layout, SpoolState.FORWARDED):
        try:
            record = ForwardImportRecord.model_validate_json(text)
        except (ValidationError, ValueError):
            continue
        outcome = record.completeness
        if outcome is None or outcome.kind is not ForwardCompletenessKind.PENDING:
            continue
        if not outcome.data_set or not outcome.period or not outcome.organisation_unit:
            continue
        owed.append(
            _OwedCompletenessClaim(
                response_id=response_id,
                claim=CompleteDataSetRegistration(
                    dataSet=outcome.data_set,
                    period=outcome.period,
                    organisationUnit=outcome.organisation_unit,
                    attributeOptionCombo=outcome.attribute_option_combo,
                    date=outcome.date,
                    completed=True,
                ),
            )
        )
    return tuple(owed)


async def _retry_owed_completeness(
    client: Dhis2Client,
    layout: SpoolLayout,
    owed: Sequence[_OwedCompletenessClaim],
    progress: _StepAnnouncer,
) -> tuple[ForwardCompletenessRetry, ...]:
    """Post every registration an earlier drain left owed, without posting a single value again.

    The values are in DHIS2 already - what is missing is the second write that says the report is
    complete - so the claim is rebuilt from the tuple its own sidecar recorded and posted on its
    own. Registering a tuple DHIS2 already holds is an update rather than a conflict, so a claim
    that turns out to have landed after all costs nothing.
    """
    retries: list[ForwardCompletenessRetry] = []
    for posted, owing in enumerate(owed, start=1):
        progress.tick(f"registering reports an earlier drain left owed ({posted:,})")
        outcome = await _completeness_answer(client, owing.claim)
        _record_completeness_in_sidecar(layout, owing.response_id, outcome)
        retries.append(ForwardCompletenessRetry(response_id=owing.response_id, outcome=outcome))
    return tuple(retries)


async def _register_completeness(
    client: Dhis2Client,
    layout: SpoolLayout,
    spooled: Sequence[SpooledResponse],
    conversion: ConversionReport,
    imports: dict[str, ForwardImportOutcome],
    *,
    dry_run: bool,
    registering: bool,
    overwrite_refused: frozenset[str],
    progress: _StepAnnouncer,
) -> dict[str, ForwardCompletenessOutcome]:
    """Register the data set complete for every `completed` aggregate response DHIS2 has just taken.

    The order is the whole safety property: this runs after `_post_translations`, and a response is
    only registered when its own import answer says DHIS2 took the values. A response the instance
    rejected registers nothing, because completeness is a claim about data that landed - and DHIS2
    itself is looser than that, registering off `/api/dataValueSets`' own `completeDate` even when
    every value in the envelope was refused and even under `dryRun=true` (BUGS.md 78, 79), which is
    exactly why the forwarder never writes that field and states the claim here instead.

    A dry run posts nothing. The endpoint has a `dryRun` of its own, but a dry run wrote no values for
    the claim to be about, so the honest outcome is the tuple that would be registered.

    A refusal is recorded and does not change what the response became. The values are imported and
    stay imported; unwinding them over a failed second write would turn one refused claim into a lost
    report. Registering a tuple twice is an update rather than a conflict, so a claim that did not
    land can simply be posted again.

    A registration that never reaches the instance at all - a timeout, a dropped connection, an
    answer carrying no import summary - is caught per claim and recorded as `pending` rather than
    left to escape the run. The values are in DHIS2 either way, and an exception here would take the
    whole drain's report down over a second write it has already made durable: every filed receipt's
    sidecar records the claim as `pending` from the moment it is filed, and the answer is written
    over it here, so `_owed_completeness_claims` finds whatever this run did not finish.

    A response the run refused as an overwrite claims nothing at all, on a dry run as much as on an
    import: it was never sent, so there is no report for a completeness claim to be about.
    """
    claims = [
        (entry, result)
        for entry, result in zip(spooled, conversion.results, strict=True)
        if result.completeness is not None or result.payload_of(DataValueSet) is not None
    ]
    outcomes: dict[str, ForwardCompletenessOutcome] = {}
    posted = 0
    for entry, result in claims:
        if entry.response_id in overwrite_refused:
            continue
        claim = result.completeness
        if claim is None:
            outcomes[entry.response_id] = ForwardCompletenessOutcome(kind=ForwardCompletenessKind.NOT_CLAIMED)
            continue
        if not registering:
            outcomes[entry.response_id] = _completeness_outcome(ForwardCompletenessKind.NOT_REGISTERED, claim)
            continue
        if dry_run:
            outcomes[entry.response_id] = _completeness_outcome(ForwardCompletenessKind.WOULD_REGISTER, claim)
            continue
        imported = imports.get(entry.response_id)
        if imported is None or not imported.is_accepted:
            continue
        posted += 1
        progress.tick(f"registering completed reports ({posted:,})")
        outcome = await _completeness_answer(client, claim)
        outcomes[entry.response_id] = outcome
        _record_completeness_in_sidecar(layout, entry.response_id, outcome)
    return outcomes


async def _completeness_answer(client: Dhis2Client, claim: CompleteDataSetRegistration) -> ForwardCompletenessOutcome:
    """Post one registration and answer with what became of the claim, an unreachable instance included.

    A registration is a second write about values that are already in DHIS2, so nothing it meets is
    worth losing the run over. What the instance never answered is a claim still owed, which is what
    `pending` says and what the next drain acts on.
    """
    try:
        return await _post_completeness(client, claim)
    except (Dhis2ApiError, AuthenticationError, httpx.HTTPError) as error:
        return _completeness_outcome(
            ForwardCompletenessKind.PENDING,
            claim,
            message=f"the registration did not reach the instance ({error}), so the report is not registered",
        )


def _record_completeness_in_sidecar(layout: SpoolLayout, response_id: str, outcome: ForwardCompletenessOutcome) -> None:
    """Write what became of one claim into the forwarded receipt's own import report.

    The sidecar is the only durable place the claim can live once the receipt has left the queue,
    and a receipt whose file has moved on is graded rather than raised: DHIS2 has answered, and
    losing the run over a sidecar nobody can find would throw that answer away.
    """
    record = _forwarded_import_record(layout, response_id)
    if record is None:
        return
    write_import_report(layout, SpoolState.FORWARDED, response_id, record.model_copy(update={"completeness": outcome}))


async def _post_completeness(client: Dhis2Client, claim: CompleteDataSetRegistration) -> ForwardCompletenessOutcome:
    """POST one completeness registration and project DHIS2's answer onto the outcome the report reads.

    The answer is `/api/dataValueSets`' own envelope - a `WebMessage` wrapping an `ImportSummary` - so
    the aggregate projection reads it unchanged. A registration DHIS2 has already stored counts
    `updated` rather than conflicting, which is what makes forwarding the same tuple twice safe.

    The three verdicts are the same three a value import gets. Only an answer carrying the endpoint's
    own import summary registers the tuple; a summary that refuses it is a refusal; and anything else
    - a gateway's `403`, a proxy's `404`, a rate limiter's `429`, a success carrying some other
    document - registered nothing, so the claim stays pending and the next drain posts it again.
    """
    body = CompleteDataSetRegistrations(completeDataSetRegistrations=[claim]).model_dump(
        by_alias=True, exclude_none=True, mode="json"
    )
    answer = _aggregate_import_outcome(await _post_body(client, _COMPLETE_DATA_SET_REGISTRATIONS_PATH, body, {}))
    if answer.verdict is ForwardImportVerdict.NONE:
        return _completeness_outcome(ForwardCompletenessKind.PENDING, claim, message=_no_verdict_message(answer))
    if answer.is_rejected:
        return _completeness_outcome(
            ForwardCompletenessKind.REFUSED, claim, message=answer.message, issues=answer.issues
        )
    return _completeness_outcome(ForwardCompletenessKind.REGISTERED, claim)


def _no_verdict_message(answer: ForwardImportOutcome) -> str:
    """Why one answer registered nothing, when what answered was not the endpoint reaching a verdict."""
    answered = f"answered {answer.http_status}" if answer.http_status is not None else "answered a success status"
    stated = f": {answer.message}" if answer.message else ""
    return f"the instance {answered} with no import summary, so the registration is not known to have landed{stated}"


def _completeness_outcome(
    kind: ForwardCompletenessKind,
    claim: CompleteDataSetRegistration,
    *,
    message: str | None = None,
    issues: tuple[ForwardImportIssue, ...] = (),
) -> ForwardCompletenessOutcome:
    """One claim as the outcome the report reads, carrying its four keys however the claim ended."""
    return ForwardCompletenessOutcome(
        kind=kind,
        data_set=claim.dataSet,
        period=claim.period,
        organisation_unit=claim.organisationUnit,
        attribute_option_combo=claim.attributeOptionCombo,
        date=claim.date,
        message=message,
        issues=issues,
    )


def _completeness_completion(
    completeness: dict[str, ForwardCompletenessOutcome], *, dry_run: bool, registering: bool
) -> str:
    """What the completeness step announces when it finishes, in the terms of the mode that ran."""
    if not completeness:
        return "no aggregate response to register"
    if not registering:
        return f"{len(completeness):,} aggregate response(s), completeness registration off"
    counted = Counter(outcome.kind for outcome in completeness.values())
    claimed = len(completeness) - counted[ForwardCompletenessKind.NOT_CLAIMED]
    if dry_run:
        return f"{claimed:,} report(s) would be registered complete (validate only)"
    return (
        f"{counted[ForwardCompletenessKind.REGISTERED]:,} report(s) registered complete, "
        f"{counted[ForwardCompletenessKind.REFUSED]:,} refused"
    )


def _completeness_retry_completion(retries: Sequence[ForwardCompletenessRetry]) -> str:
    """What a run with nothing to drain announces about the claims it found owed and posted again."""
    counted = Counter(retry.outcome.kind for retry in retries)
    registered = counted[ForwardCompletenessKind.REGISTERED]
    return f"{registered:,} of {len(retries):,} owed report(s) registered complete"


def _completeness_retry_note(retries: Sequence[ForwardCompletenessRetry]) -> str:
    """What a drain adds to its completeness line about the claims an earlier drain left owed."""
    return f", {_completeness_retry_completion(retries)}" if retries else ""


def _post_order(result: ConversionResult) -> int:
    """Where one translated payload sits in the posting order its target kind gives it."""
    if result.target_kind is None or result.target_kind not in FORWARD_TARGET_ORDER:
        return len(FORWARD_TARGET_ORDER)
    return FORWARD_TARGET_ORDER.index(result.target_kind)


async def _post_result(client: Dhis2Client, result: ConversionResult, *, dry_run: bool) -> ForwardImportOutcome:
    """Post one translated payload to the endpoint its target kind names, and project DHIS2's answer."""
    payload = result.payload
    if payload is None or result.target_kind is None:
        # `ConversionResult.payload` answers None for a refused response alone, and a refused response
        # never reaches the posting loop - so this is the case the type system cannot exclude.
        raise ValueError("a translated result carries no payload at all")
    body = payload.model_dump(by_alias=True, exclude_none=True, mode="json")
    if result.target_kind is ConversionTargetKind.DATA_VALUE_SET:
        aggregate_params = dict(_DATA_VALUE_SETS_DRY_RUN_PARAMS) if dry_run else {}
        return _aggregate_import_outcome(await _post_body(client, _DATA_VALUE_SETS_PATH, body, aggregate_params))
    tracker_params = {**_TRACKER_PARAMS, **(_TRACKER_DRY_RUN_PARAMS if dry_run else {})}
    bundle = {_TRACKER_KEYS_BY_TARGET_KIND[result.target_kind]: [body]}
    return _tracker_import_outcome(await _post_body(client, _TRACKER_PATH, bundle, tracker_params))


async def _post_body(
    client: Dhis2Client,
    path: str,
    body: dict[str, Any],
    params: dict[str, str],
) -> ForwardEndpointAnswer:
    """POST one payload and answer with DHIS2's own JSON body under the status it arrived with.

    A refused import is `409 Conflict` carrying the endpoint's report, so a rejection is an outcome to
    record rather than an error to raise. The body is passed on **raw** rather than parsed here, because
    the two endpoints do not agree on whether the report is wrapped: `/api/dataValueSets` answers a
    `WebMessage` whose `response` is the `ImportSummary`, and `/api/tracker` answers the
    `TrackerImportReport` bare, with no envelope around it at all - so the one shape that can carry both
    is the body itself, and each family unwraps its own. Anything the error carries no JSON object for -
    an authentication failure, an unreachable instance - is about the run and not about one response,
    and is raised.

    A 5xx is raised whatever it carries. DHIS2 and the proxies in front of it answer a server error with
    a `WebMessage` of their own, `status` and all, and reading that as the endpoint's verdict would
    project `status=ERROR` into a rejection and file the receipt under a refusal DHIS2 never made. The
    status is what separates the two: 409 is the endpoint reaching a verdict, 500 is it failing to.

    The status rides along with the body because a status below 500 does not make an answer a
    verdict either: a 401, a 403, a 404 and a 429 all carry JSON of their own from whatever answered
    instead of the endpoint, and the projection that reads the body says so in the status it carries.
    """
    try:
        return ForwardEndpointAnswer(body=await client.post_raw(path, body, params=params))
    except Dhis2ApiError as error:
        if error.status_code >= _SERVER_ERROR_STATUS:
            raise
        if isinstance(error.body, dict):
            return ForwardEndpointAnswer(status_code=error.status_code, body=error.body)
        raise


def _aggregate_import_outcome(answer: ForwardEndpointAnswer) -> ForwardImportOutcome:
    """Project an `/api/dataValueSets` answer: the import counts, every conflict it named, and its status."""
    body = answer.body
    envelope = _envelope(body)
    summary = _report_model(ImportSummary, _report_body(body, _DATA_VALUE_SET_REPORT_KEYS))
    counts = summary.importCount if summary is not None else None
    status = summary.status.value if summary is not None and summary.status is not None else envelope.get("status")
    conflicts = summary.conflicts if summary is not None else None
    return ForwardImportOutcome(
        status=_text(status),
        message=(summary.description if summary is not None else None) or _text(envelope.get("message")),
        created=counts.imported or 0 if counts is not None else 0,
        updated=counts.updated or 0 if counts is not None else 0,
        ignored=counts.ignored or 0 if counts is not None else 0,
        deleted=counts.deleted or 0 if counts is not None else 0,
        issues=tuple(_conflict_issue(conflict) for conflict in conflicts or []),
        data_value_summary=summary,
        http_status=answer.status_code,
        report_recognised=_carries_report(body, _DATA_VALUE_SET_REPORT_KEYS),
    )


def _tracker_import_outcome(answer: ForwardEndpointAnswer) -> ForwardImportOutcome:
    """Project an `/api/tracker` answer: the stats, every validation error it reported, and its status."""
    body = answer.body
    envelope = _envelope(body)
    report = _report_model(TrackerImportReport, _report_body(body, _TRACKER_REPORT_KEYS))
    stats = report.stats if report is not None else None
    status = report.status.value if report is not None and report.status is not None else envelope.get("status")
    validation = report.validationReport if report is not None else None
    errors = validation.errorReports if validation is not None else None
    return ForwardImportOutcome(
        status=_text(status),
        message=(report.message if report is not None else None) or _text(envelope.get("message")),
        created=stats.created or 0 if stats is not None else 0,
        updated=stats.updated or 0 if stats is not None else 0,
        ignored=stats.ignored or 0 if stats is not None else 0,
        deleted=stats.deleted or 0 if stats is not None else 0,
        issues=tuple(_tracker_issue(error) for error in errors or []),
        tracker_report=report,
        http_status=answer.status_code,
        report_recognised=_carries_report(body, _TRACKER_REPORT_KEYS),
    )


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    """The `WebMessage` fields of an answer, which are the body's own when no envelope wrapped the report."""
    return body


def _carries_report(body: dict[str, Any], keys: frozenset[str]) -> bool:
    """Whether one answer carries the import report of the endpoint it came from, wrapped or bare.

    The same reading `_report_body` takes, as the claim on its own: the fields only that endpoint's
    report has are in the body, or in the `WebMessage.response` an envelope wrapped it in. A body
    that has neither is some other party's answer, whatever HTTP status it arrived under.
    """
    nested = body.get("response")
    return bool(keys & body.keys()) or (isinstance(nested, dict) and bool(keys & nested.keys()))


def _report_body(body: dict[str, Any], keys: frozenset[str]) -> dict[str, Any] | None:
    """The endpoint's own report, wherever it arrived: inside a `WebMessage.response`, or bare as the body.

    `keys` are the fields only that endpoint's report carries, so the choice is made on what the document
    holds rather than on which HTTP status brought it - the same 409 body arrives wrapped from one
    endpoint and bare from the other.
    """
    nested = body.get("response")
    if isinstance(nested, dict) and keys & nested.keys():
        return nested
    if keys & body.keys():
        return body
    return nested if isinstance(nested, dict) else None


def _report_model[T: BaseModel](model: type[T], report_body: dict[str, Any] | None) -> T | None:
    """Validate one endpoint's report against its generated schema, keeping None when there is nothing to read.

    A report the generated model cannot read costs its own detail and nothing else: the run still records
    the rejection, and the endpoint said something this client's schema does not describe, which is a note
    for `BUGS.md` rather than a reason to lose the other two hundred outcomes.
    """
    if not report_body:
        return None
    try:
        return model.model_validate(report_body)
    except ValidationError:
        return None


def _text(value: object) -> str | None:
    """One wire field as the string a report carries it as, or None when DHIS2 sent nothing."""
    return str(value) if value is not None else None


def _conflict_issue(conflict: ImportConflict) -> ForwardImportIssue:
    """One `/api/dataValueSets` conflict as the row both report shapes fold into."""
    return ForwardImportIssue(
        error_code=conflict.errorCode,
        subject=conflict.object or conflict.property,
        message=conflict.value,
    )


def _tracker_issue(error: TrackerImportError) -> ForwardImportIssue:
    """One `/api/tracker` validation error as the row both report shapes fold into."""
    return ForwardImportIssue(error_code=error.errorCode, subject=error.uid, message=error.message)


def _generalised_reason(reason: str, rule_names: ProgramRuleNames) -> str:
    """One DHIS2 message read back for a person: a published rule by name, every other UID generalised away.

    DHIS2 names the program rule that refused an import by UID alone (`E1300`), and the guide
    published that UID beside the rule's own name, so the roll-up says which rule refused rather
    than which twelve characters did. Every other quoted identifier still generalises, because two
    rejections of one rule against two different objects are one cause of the run. The UID itself is
    untouched on the response's own report, which is where a reader goes for the object.
    """

    def _read(match: re.Match[str]) -> str:
        name = rule_names.name_for(match.group(0).strip("`"))
        return f"`{name}`" if name is not None else "`...`"

    return _QUOTED_IDENTIFIER.sub(_read, reason)


def _rejection_cause_key(error_code: str | None, generalised_reason: str) -> tuple[str | None, str]:
    """What a rejection rolls up under: the error code alone, or the generalised message when there is no code.

    An error code names a DHIS2 rule identically on every major, while the wording around it drifts, so
    a coded row carries no message in its key and a codeless one has nothing else to be named by.
    """
    return (error_code, "") if error_code else (None, generalised_reason)


def _collect_outcomes(
    spooled: Sequence[SpooledResponse],
    conversion: ConversionReport,
    imports: dict[str, ForwardImportOutcome],
    completeness: dict[str, ForwardCompletenessOutcome],
    project_root: Path,
    *,
    filed: dict[str, Path],
    minted_enrollments: frozenset[str],
    overwritten: dict[str, tuple[OverwrittenValue, ...]],
    overwrite_refused: frozenset[str],
) -> tuple[ForwardOutcome, ...]:
    """Pair every receipt with what DHIS2 said about it, and with where the run left its file.

    Nothing moves here. The renames happened as the verdicts arrived, so this states the spool as it
    now is: a receipt the run filed is named at its new path, and one nothing was decided about -
    refused, unverifiable, or never reached - is named where the run found it.

    `minted_enrollments` is empty on an import run, which is what keeps the unverifiable reading a
    dry-run reading: an import creates the enrollments it posts, so nothing it rejects goes unchecked.
    """
    outcomes: list[ForwardOutcome] = []
    for entry, result in zip(spooled, conversion.results, strict=True):
        imported = imports.get(entry.response_id)
        refused_over_an_overwrite = entry.response_id in overwrite_refused
        kind = _outcome_kind(result, imported, minted_enrollments, refused_over_an_overwrite)
        path = filed.get(entry.response_id, entry.path)
        outcomes.append(
            ForwardOutcome(
                response_id=entry.response_id,
                questionnaire=result.questionnaire or entry.questionnaire or None,
                target_kind=result.target_kind,
                kind=kind,
                notes=result.notes,
                refusals=result.refusals,
                import_outcome=imported,
                completeness=completeness.get(entry.response_id),
                overwritten_values=overwritten.get(entry.response_id, ()),
                overwrite_refused=refused_over_an_overwrite,
                spool_path=_relative_path(path, project_root),
                submitted_by=entry.submitted_by,
            )
        )
    return tuple(outcomes)


def _minted_enrollment_uids(conversion: ConversionReport) -> frozenset[str]:
    """Every enrollment UID this run's registrations mint, which is what their stage events name.

    The UIDs are the client's own - a registration response carries the enrollment it creates in its
    `D2TrackerEnrollment` extension - so they are known before DHIS2 answers anything. Both
    registration shapes mint one: the person the run creates carries theirs inside them, and the
    person the instance already holds is enrolled by a payload that is the enrollment itself.
    """
    nested = (
        enrollment for tracked_entity in conversion.tracked_entities for enrollment in tracked_entity.enrollments or []
    )
    return frozenset(
        enrollment.enrollment for enrollment in (*nested, *conversion.enrollments) if enrollment.enrollment
    )


def _outcome_kind(
    result: ConversionResult,
    imported: ForwardImportOutcome | None,
    minted_enrollments: frozenset[str],
    overwrite_refused: bool,
) -> ForwardOutcomeKind:
    """Which of the five states one receipt ended in.

    A translated receipt with no import answer is one the drain stopped short of, not one the
    translator refused: the two are different facts about different failures, and calling the first
    the second would report a healthy receipt as unreadable and hide that the run ended early. A
    receipt the run would not overwrite with is the same state as a translator refusal - it stayed
    in the queue and DHIS2 was never asked - so it is graded the same, and the outcome says which
    refusal it met.
    """
    if result.is_refused or overwrite_refused:
        return ForwardOutcomeKind.REFUSED
    if imported is None:
        return ForwardOutcomeKind.NOT_POSTED
    if not imported.is_rejected:
        return ForwardOutcomeKind.ACCEPTED
    if _is_unverifiable(result, imported, minted_enrollments):
        return ForwardOutcomeKind.UNVERIFIABLE
    return ForwardOutcomeKind.REJECTED


def _is_unverifiable(
    result: ConversionResult,
    imported: ForwardImportOutcome,
    minted_enrollments: frozenset[str],
) -> bool:
    """Whether a rejection is only DHIS2 saying the enrollment this event names does not exist yet.

    Three things have to hold together. The payload is a tracker event; every row DHIS2 named against
    it is one of the pair it answers an absent enrollment with (BUGS.md 68); and the enrollment the
    event names is one a registration of the same run mints. An event naming an enrollment nobody in
    the run creates fails the last test and stays a rejection, which is the orphan the run must state.
    """
    event = result.payload_of(TrackerEvent)
    if event is None or event.enrollment not in minted_enrollments:
        return False
    error_codes = {issue.error_code for issue in imported.issues}
    return bool(error_codes) and all(code in _ABSENT_ENROLLMENT_ERROR_CODES for code in error_codes)


def _relative_path(path: Path, project_root: Path) -> str:
    """Name one spool file relative to the project when it lives inside it, so the report stays portable."""
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


class SpoolStateCounts(BaseModel):
    """How many receipts sit in each state, plus how many files are in quarantine beside them."""

    model_config = ConfigDict(frozen=True)

    received: int = 0
    forwarded: int = 0
    rejected: int = 0
    withdrawn: int = 0
    """Receipts that landed and were later retracted from DHIS2 by `d2w fhir withdraw`."""

    malformed: int = 0
    """Files in `malformed/`, which are not receipts - they are bytes that would not read as one."""

    refused_in_queue: int = 0
    """Of the received receipts, how many the last committing drain refused and left in the queue."""

    @property
    def total(self) -> int:
        """How many receipts the spool holds, which counts the four states and not the holding pen."""
        return self.received + self.forwarded + self.rejected + self.withdrawn


class SpoolReceiptRow(BaseModel):
    """One receipt as the spool listing states it: where it sits, what it answers, and why it is there."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    state: SpoolState
    questionnaire: str
    form_kind: str
    received_at: str
    submitted_by: str | None = None
    """The DHIS2 username the facade validated the submission under, or None when it validated none."""

    reason: str | None = None
    """Why DHIS2 refused it, or why the translator would not convert it, off the report beside the file."""


class SpoolStateReport(BaseModel):
    """One project's capture spool as `d2w fhir spool` states it, read off the directory alone."""

    model_config = ConfigDict(frozen=True)

    project_root: Path
    counts: SpoolStateCounts
    receipts: tuple[SpoolReceiptRow, ...] = ()
    quarantined: tuple[QuarantinedFile, ...] = ()

    @property
    def counts_line(self) -> str:
        """The whole spool in one line, which is what a summary hint wants."""
        line = (
            f"{self.counts.received:,} received, {self.counts.forwarded:,} forwarded, {self.counts.rejected:,} rejected"
        )
        if self.counts.refused_in_queue:
            line = f"{line} ({self.counts.refused_in_queue:,} of the received refused by a drain)"
        if self.counts.withdrawn:
            line = f"{line}, {self.counts.withdrawn:,} withdrawn"
        return f"{line}, {self.counts.malformed:,} malformed" if self.counts.malformed else line


class RequeuedReceipt(BaseModel):
    """One receipt moved back into the queue, and where its file now sits."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    spool_path: str
    """Where the receipt sits now, relative to the project root."""


class RequeueReport(BaseModel):
    """What one `d2w fhir requeue` moved, in the order the ids were given."""

    model_config = ConfigDict(frozen=True)

    project_root: Path
    requeued: tuple[RequeuedReceipt, ...] = ()

    @property
    def counts_line(self) -> str:
        """What the run amounted to, which is the one line a summary states."""
        return f"{len(self.requeued):,} receipt(s) moved back to received/"


def read_spool_state(project: FhirProject) -> SpoolStateReport:
    """State what one project's capture spool holds, from the directory alone.

    NO DHIS2 CONNECTION AND NO PROFILE. Every fact in the report is on disk: which directory a
    receipt is in is its state, the sidecar beside a drained one says what DHIS2 answered, and the
    holding pen says what would not read as a receipt at all. An operator asking what is queued has
    to be able to ask it while the instance is down, which is exactly when they will.

    A file that does not read as a receipt is moved to `malformed/` by the read that met it and
    counted there, so the listing states it rather than failing over it.

    Rows read oldest first, which is how a queue reads: the receipt that has been waiting longest is
    at the top.
    """
    contents = read_spooled_receipts(spool_layout(project))
    rows = tuple(
        SpoolReceiptRow(
            response_id=receipt.response_id,
            state=receipt.state,
            questionnaire=receipt.questionnaire,
            form_kind=receipt.form_kind,
            received_at=receipt.received_at,
            submitted_by=receipt.submitted_by,
            reason=_receipt_reason(receipt),
        )
        for receipt in sorted(contents.receipts, key=lambda receipt: (receipt.received_at, receipt.response_id))
    )
    counts = SpoolStateCounts(
        received=len(contents.in_state(SpoolState.RECEIVED)),
        forwarded=len(contents.in_state(SpoolState.FORWARDED)),
        rejected=len(contents.in_state(SpoolState.REJECTED)),
        withdrawn=len(contents.in_state(SpoolState.WITHDRAWN)),
        malformed=len(contents.quarantined),
        refused_in_queue=sum(1 for receipt in contents.in_state(SpoolState.RECEIVED) if receipt.refusal is not None),
    )
    return SpoolStateReport(
        project_root=project.project_root,
        counts=counts,
        receipts=rows,
        quarantined=contents.quarantined,
    )


def requeue_rejected_responses(
    project: FhirProject, response_ids: Sequence[str] = (), *, all_rejected: bool = False
) -> RequeueReport:
    """Move rejected receipts back into `received/`, so the next drain posts them again.

    The one reverse move the spool has, and it is an operator's decision rather than the forwarder's:
    a rejection is DHIS2 stating that this payload is wrong, so it stays where it is until a person
    who has changed the instance, the guide, or their mind says otherwise.

    An id that is not in `rejected/` is refused by name rather than skipped, and refused before
    anything moves: a run that had already requeued three of five receipts before naming the fourth
    as unknown would leave the operator to work out which three.
    """
    layout = spool_layout(project)
    contents = read_spooled_receipts(layout)
    rejected = {receipt.response_id for receipt in contents.in_state(SpoolState.REJECTED)}
    wanted = sorted(rejected) if all_rejected else list(response_ids)
    unknown = [response_id for response_id in wanted if response_id not in rejected]
    if unknown:
        named = ", ".join(f"`{response_id}`" for response_id in unknown)
        raise SpoolReadError(
            f"{named} is not in {layout.directory_for(SpoolState.REJECTED)}; "
            "`d2w fhir spool --details` lists what is there"
        )
    moved = [
        RequeuedReceipt(
            response_id=response_id,
            spool_path=_relative_path(move_to_received(layout, response_id), project.project_root),
        )
        for response_id in wanted
    ]
    return RequeueReport(project_root=project.project_root, requeued=tuple(moved))


def _receipt_reason(receipt: SpooledReceipt) -> str | None:
    """What the sidecar beside one receipt says, as the one line a listing row shows.

    A drained receipt reads its import report. A queued receipt reads the refusal record a
    committing drain left beside it, when one has - a receipt no drain has touched has nothing on
    disk to read, and the row states no reason rather than inventing one. A withdrawn receipt reads
    the record of the delete, which is the one state whose sidecar is not an import report.
    """
    if receipt.state is SpoolState.RECEIVED:
        if receipt.refusal is None:
            return None
        drains = pluralize(receipt.refusal.attempt_count, "drain")
        return f"{receipt.refusal.line} (refused by {drains}, last at {receipt.refusal.refused_at})"
    path = receipt.path.with_name(f"{receipt.response_id}{IMPORT_REPORT_SUFFIX}")
    if not path.is_file():
        return None
    model = WithdrawalRecord if receipt.state is SpoolState.WITHDRAWN else ForwardImportRecord
    try:
        record = model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None
    if isinstance(record, WithdrawalRecord):
        return record.line
    if record.issues:
        return record.issues[0].line
    return record.message


#: What `/api/tracker` is asked to do when a withdrawal retracts an event this project forwarded.
#: `DELETE` needs nothing of the object but its UID - the payload is the identity alone - and the
#: run is synchronous for the same reason a forward's is: the answer is the point.
_TRACKER_DELETE_PARAMS = {"importStrategy": "DELETE", "async": "false"}

#: The form kinds whose receipt lands as the single `/api/tracker` event a withdrawal retracts. An
#: aggregate receipt lands a set of cells and has to be read before it is deleted, because deleting
#: an aggregate tuple that was never written materialises a tombstone that blocks the parent data
#: element for ever (BUGS.md 87); a registration lands a person and an enrollment whose deletion
#: cascades into events other receipts named. Both are designed and neither is built - see
#: `docs/fhir/design/data-lifecycle.md`.
_WITHDRAWABLE_FORM_KINDS = frozenset({"event", "tracker-event"})

#: What the sidecar of a withdrawn receipt says in the words a person reading `withdrawn/` cold
#: needs, which are not the words "deleted". DHIS2 soft-deletes: the row stays, carrying its value,
#: and it is gone from every ordinary read.
_WITHDRAWAL_MESSAGE = (
    "Withdrawn. This DHIS2 instance keeps a hidden copy of the event; it no longer appears in reports. "
    "The UID is burned, so this receipt can never be forwarded again."
)


class WithdrawalNotEnabledError(LookupError):
    """Raised when a withdrawal is asked for and this project's `[forward] withdrawals` says off."""


class WithdrawalUnsupportedError(LookupError):
    """Raised when the named receipt landed something other than the one event a withdrawal retracts."""


class WithdrawalKind(StrEnum):
    """What became of one receipt a withdrawal named."""

    #: DHIS2 deleted the event, and the receipt now sits in `withdrawn/`.
    RETRACTED = "retracted"

    #: A dry run: DHIS2 validated the delete, wrote nothing, and the receipt is untouched in `forwarded/`.
    WOULD_RETRACT = "would-retract"

    #: DHIS2 refused the delete. The receipt stays in `forwarded/`, because what it says is still true.
    REFUSED = "refused"


class WithdrawalRecord(ForwardImportOutcome):
    """The sidecar beside a withdrawn receipt: what DHIS2 answered when it was asked to take the event back.

    A document of its own rather than a second import report, because it answers a different
    question. `forwarded/<id>.report.json` says what DHIS2 did with the payload when it took it and
    stays where it is; this one says what it did when it was asked to let go of it.
    """

    event_uid: str
    """The DHIS2 event this withdrawal named, derived from the receipt's own logical id."""

    withdrawn_at: str
    """The instant the withdrawal was posted, as a FHIR `instant` (UTC)."""

    received_at: str | None = None
    """When the receipt this withdrawal retracts was captured."""

    note: str = _WITHDRAWAL_MESSAGE
    """What remains in the instance, in the words a person reading this file cold needs them in."""

    @property
    def line(self) -> str:
        """The record as the one line a listing row shows: the fact, and the object it is about."""
        return f"withdrawn at {self.withdrawn_at}; event {self.event_uid} no longer appears in reports"


class WithdrawnReceipt(BaseModel):
    """One receipt a withdrawal run named, and what DHIS2 answered about the event it landed."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    kind: WithdrawalKind
    event_uid: str
    questionnaire: str
    form_kind: str
    received_at: str
    outcome: ForwardImportOutcome
    """DHIS2's own answer to the delete, projected out of the `/api/tracker` report shape."""

    spool_path: str | None = None
    """Where the receipt sits now, relative to the project root; None when nothing moved it."""

    @property
    def line(self) -> str:
        """The one line a listing row shows about this receipt: the reason, or what the delete counted.

        The counts are the delete's own two - a withdrawal never creates or updates anything, so the
        forward's `created / updated / ignored` would be three zeroes for every row that worked.
        """
        if self.outcome.issues:
            return self.outcome.issues[0].line
        return f"{self.outcome.deleted} deleted, {self.outcome.ignored} ignored"


class WithdrawReport(BaseModel):
    """What one `d2w fhir withdraw` retracted, in the order the ids were given."""

    model_config = ConfigDict(frozen=True)

    project_root: Path
    dry_run: bool
    withdrawal_posture: WithdrawalPosture
    receipts: tuple[WithdrawnReceipt, ...] = ()

    @property
    def retracted(self) -> tuple[WithdrawnReceipt, ...]:
        """Every receipt DHIS2 took the delete for, which on a dry run is none - it validated instead."""
        return tuple(receipt for receipt in self.receipts if receipt.kind is WithdrawalKind.RETRACTED)

    @property
    def refused(self) -> tuple[WithdrawnReceipt, ...]:
        """Every receipt DHIS2 would not delete, each still in `forwarded/` with its import report."""
        return tuple(receipt for receipt in self.receipts if receipt.kind is WithdrawalKind.REFUSED)

    @property
    def counts_line(self) -> str:
        """What the run amounted to, which is the one line a summary states."""
        verb = "would be withdrawn" if self.dry_run else "withdrawn"
        taken = len(self.receipts) - len(self.refused)
        line = f"{taken:,} receipt(s) {verb}"
        return f"{line}, {len(self.refused):,} refused by DHIS2" if self.refused else line


async def withdraw_responses(
    profile: Profile,
    project: FhirProject,
    response_ids: Sequence[str],
    *,
    import_responses: bool = False,
    withdrawals: WithdrawalPosture | None = None,
    client: Dhis2Client | None = None,
) -> WithdrawReport:
    """Retract from DHIS2 the events named forwarded receipts landed, and file each receipt as withdrawn.

    THE RECEIPT IS NEVER REWRITTEN AND NEVER MUTATED. A withdrawal is a state the receipt moves into,
    exactly as forwarding is: the file is renamed from `forwarded/` to `withdrawn/` and a sidecar
    lands beside it holding what DHIS2 answered the delete. The import report that recorded what the
    receipt landed stays behind in `forwarded/`, because it is still true of that import.

    THE IDENTITY IS RECOMPUTED, NOT LOOKED UP. An event's DHIS2 UID is derived from the receipt's own
    logical id, so the object to delete is `receipt_event_uid(<the receipt's id>)` and the run needs
    no guide, no metadata read, and no translation to know it - which is what makes a withdrawal
    answerable about a project whose IG was never compiled.

    WITHDRAWAL IS TERMINAL. DHIS2 burns the UID of a tracker object it deletes and refuses it under
    every import strategy afterwards (`E1082`), so the withdrawn receipt can never be forwarded
    again and no correction can ever be modelled as delete-then-recreate. What remains in the
    instance is a soft-deleted row carrying its values, invisible to every ordinary read - which is
    what the sidecar says, rather than the bare word "deleted" this toolkit cannot stand behind.

    `[forward] withdrawals` gates the whole command and defaults to `"off"`: a project that publishes
    forms and forwards them is not thereby a project that reaches back into what DHIS2 already holds.
    `withdrawals=WithdrawalPosture.RETRACT` overrides the table for one run, in the same order every
    other dial resolves - the caller's word, then the file, then the default.

    A DRY RUN IS THE DEFAULT, exactly as it is for a drain. The delete goes to the real endpoint
    under `importMode=VALIDATE`, so DHIS2's own rules answer whether it would take it - which for a
    terminal act is the one rehearsal worth having - and nothing is written and no receipt moves.

    Only a receipt in `forwarded/` can be withdrawn, and only one that landed a single event: a
    queued receipt never reached DHIS2, a rejected one never landed, and the aggregate and
    registration legs each need a guard this one does not. Each of those is refused by name, and
    refused before anything is posted, so a run of five never leaves an operator working out which
    two it reached.
    """
    posture = withdrawals if withdrawals is not None else project.config.forward.withdrawals
    if posture is not WithdrawalPosture.RETRACT:
        raise WithdrawalNotEnabledError(
            f"this project does not withdraw what it forwarded: `[forward] withdrawals` is `{posture.value}`. "
            f'Set `withdrawals = "{WithdrawalPosture.RETRACT.value}"` in fhir.toml, or pass '
            f"`--withdrawals {WithdrawalPosture.RETRACT.value}` for one run. Withdrawal is terminal - DHIS2 "
            "burns the UID it deletes and the receipt can never be forwarded again."
        )
    layout = spool_layout(project)
    with drain_lock(layout):
        wanted = [read_receipt(layout, SpoolState.FORWARDED, response_id) for response_id in response_ids]
        _refuse_unwithdrawable(wanted)
        receipts: list[WithdrawnReceipt] = []
        async with _instance_connection(profile, client) as client:
            for spooled in wanted:
                receipts.append(await _withdraw_one(client, spooled, project, dry_run=not import_responses))
    return WithdrawReport(
        project_root=project.project_root,
        dry_run=not import_responses,
        withdrawal_posture=posture,
        receipts=tuple(receipts),
    )


def _refuse_unwithdrawable(spooled: Sequence[SpooledResponse]) -> None:
    """Refuse the whole run when any named receipt landed something other than one event.

    Named before anything is posted, and named with the kind it is, because "this one is aggregate"
    is what the operator has to act on - not a partial run they then have to reconstruct.
    """
    other = [entry for entry in spooled if entry.form_kind not in _WITHDRAWABLE_FORM_KINDS]
    if not other:
        return
    named = ", ".join(f"`{entry.response_id}` ({entry.form_kind or 'no form kind'})" for entry in other)
    raise WithdrawalUnsupportedError(
        f"{named}: a withdrawal retracts the one `/api/tracker` event a receipt landed, and these landed "
        "something else. `d2w data aggregate delete` and `d2w data tracker delete` are the raw escape "
        "hatches outside the FHIR path; the design that brings the other kinds inside it is in "
        "docs/fhir/design/data-lifecycle.md."
    )


async def _withdraw_one(
    client: Dhis2Client, spooled: SpooledResponse, project: FhirProject, *, dry_run: bool
) -> WithdrawnReceipt:
    """Post one event's delete, then file the receipt under `withdrawn/` when DHIS2 took it."""
    event_uid = receipt_event_uid(spooled.response.id or spooled.response_id)
    params = {**_TRACKER_DELETE_PARAMS, **(_TRACKER_DRY_RUN_PARAMS if dry_run else {})}
    body: dict[str, Any] = {_TRACKER_EVENTS_KEY: [{"event": event_uid}]}
    outcome = _tracker_import_outcome(await _post_body(client, _TRACKER_PATH, body, params))
    if outcome.is_rejected:
        kind = WithdrawalKind.REFUSED
    else:
        kind = WithdrawalKind.WOULD_RETRACT if dry_run else WithdrawalKind.RETRACTED
    spool_path: str | None = None
    if kind is WithdrawalKind.RETRACTED:
        record = WithdrawalRecord(
            **outcome.model_dump(),
            event_uid=event_uid,
            withdrawn_at=_utc_instant(),
            received_at=spooled.received_at or None,
        )
        moved = move_to_withdrawn(spooled, record)
        spool_path = _relative_path(moved, project.project_root)
    return WithdrawnReceipt(
        response_id=spooled.response_id,
        kind=kind,
        event_uid=event_uid,
        questionnaire=spooled.questionnaire,
        form_kind=spooled.form_kind,
        received_at=spooled.received_at,
        outcome=outcome,
        spool_path=spool_path,
    )
