"""Service layer for the `fhir` plugin - project scaffolding and FSH generation (CLI + MCP share it)."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from dhis2w_client.errors import Dhis2ApiError

# The v41 generated OAS tree carries no import-summary, import-conflict, or import-count module, so
# the import-report shapes come from v42 on every major - they are the wire shape all three answer with.
from dhis2w_client.generated.v42.oas import ImportConflict, ImportSummary, TrackerImportError, TrackerImportReport
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile, resolve
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
from dhis2w_fhir.config import FhirProject, GenerateConfig, NoFhirProjectError, load_project
from dhis2w_fhir.conversion.artifacts import (
    BoundQuestionUids,
    bound_question_uids,
    build_project_context,
    load_compiled_artifacts,
)
from dhis2w_fhir.conversion.schemas import (
    FORWARD_TARGET_ORDER,
    CodedAnswerMode,
    ConversionNaming,
    ConversionNote,
    ConversionRefusal,
    ConversionReport,
    ConversionResult,
    ConversionTargetKind,
)
from dhis2w_fhir.conversion.translator import translate_responses
from dhis2w_fhir.foundation import build_foundation_artifacts
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.names import StemResolution, StemSubject, code_or_uid
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, aggregate_generate_note, generate_note
from dhis2w_fhir.period import parse_period, recent_periods
from dhis2w_fhir.r4 import QuestionnaireResponse
from dhis2w_fhir.resources.attribute_combos import (
    ATTRIBUTE_COMBO_DIRECTORY,
    attribute_combo_concept_map_file_prefix,
    build_attribute_combo_artifacts,
    build_attribute_combo_concept_map_artifacts,
)
from dhis2w_fhir.resources.categories import (
    CATEGORY_DIRECTORY,
    build_category_artifacts,
    build_category_concept_map_artifacts,
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
from dhis2w_fhir.resources.option_sets import (
    CONCEPT_MAP_DIRECTORY,
    TERMINOLOGY_DIRECTORY,
    build_option_set_artifacts,
    build_option_set_concept_map_artifacts,
    option_set_concept_map_file_prefix,
    option_set_identities,
)
from dhis2w_fhir.resources.option_sets.schemas import (
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
from dhis2w_fhir.resources.organisation_units.schemas import GeoPoint, OrganisationUnitIn
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
from dhis2w_fhir.resources.questionnaires.schemas import (
    FORM_KIND_PROFILES,
    CategoryComboIn,
    CategoryOptionComboIn,
    FormKind,
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
    QuestionnaireStemPlan,
    plan_questionnaire_stems,
)
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.scaffold.schemas import InitOptions, ScaffoldReport
from dhis2w_fhir.spool import SpooledResponse, move_to_forwarded, move_to_rejected, read_received_responses
from dhis2w_fhir.validation import build_aborting_code, build_code_validation
from dhis2w_fhir.validation.schemas import (
    FhirValidationReport,
    MetadataCollectionIn,
    MetadataItemIn,
    ValidationScope,
)
from dhis2w_fhir.writer import FshArtifact, JsonArtifact, clean_generated_files, sync_artifacts, sync_json_artifacts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dhis2w_client import Dhis2Client
    from dhis2w_client.generated.v42.schemas import (
        Attribute,
        Category,
        DataElement,
        DataSet,
        OptionSet,
        OrganisationUnit,
        Program,
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
#: What a category combo has to state for its option combos to publish their own composition: the
#: ordered categories the combo splits over, and the category options each option combo is met from.
#: The UIDs alone - every name and every concept code the decomposition emits is joined from the
#: category projection the same run reads, so a combo says which options it is and nothing more.
_CATEGORY_COMBO_DECOMPOSITION_FIELDS = "categories[id],categoryOptionCombos[id,name,code,categoryOptions[id]]"

#: The data-element projection every form kind's questions are built from. `code` rides it for the
#: data dictionary, which publishes the DHIS2 code of the object a question is asked from the way
#: the attribute dictionary publishes an attribute's - a data element DHIS2 left uncoded publishes
#: no code rather than its UID under a `dhis2-code` label.
_QUESTIONNAIRE_DATA_ELEMENT_FIELDS = (
    "dataElement[id,code,name,formName,valueType,domainType,optionSet[id],"
    f"categoryCombo[id,name,isDefault,{_CATEGORY_COMBO_DECOMPOSITION_FIELDS}]]"
)
#: The data set's own category combo - the attribute combo whose option combos are the third key
#: of every value it holds. It rides the very projection the disaggregation combos ride, so the
#: attribute-option-combo vocabulary is read on the metadata sweep the forms already cost rather
#: than on a request of its own.
_ATTRIBUTE_COMBO_FIELDS = f"categoryCombo[id,code,name,isDefault,{_CATEGORY_COMBO_DECOMPOSITION_FIELDS}]"

_DATA_SET_FIELDS = (
    "id,name,code,description,periodType,sections[id,name,dataElements[id]],"
    f"{_ATTRIBUTE_VALUE_FIELDS},{_ATTRIBUTE_COMBO_FIELDS},"
    "compulsoryDataElementOperands[dataElement[id],categoryOptionCombo[id]],"
    f"dataSetElements[{_QUESTIONNAIRE_DATA_ELEMENT_FIELDS}]"
)

#: The stage projection both program kinds read: an event program takes its single stage's questions,
#: a tracker program takes one Questionnaire per stage, so a stage carries its own identity, its own
#: attribute values, and the sort orders DHIS2 holds the stages and their questions in.
_PROGRAM_STAGE_FIELDS = (
    f"id,name,code,description,sortOrder,{_ATTRIBUTE_VALUE_FIELDS},"
    "programStageSections[id,name,dataElements[id]],"
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
_PROGRAM_ATTRIBUTE_FIELDS = (
    "trackedEntityType[id,trackedEntityTypeAttributes[trackedEntityAttribute[id]]],displayIncidentDate,"
    "programTrackedEntityAttributes[mandatory,searchable,sortOrder,"
    "trackedEntityAttribute[id,name,code,formName,valueType,unique,optionSet[id]]]"
)

#: The tracked entity type projection a person-only registration form is built from: the type's own
#: identity, and the attributes it collects itself through the join that carries their order,
#: whether the type requires them, and whether DHIS2 will find a person by them.
_TRACKED_ENTITY_TYPE_FIELDS = (
    f"id,name,code,description,{_ATTRIBUTE_VALUE_FIELDS},"
    "trackedEntityTypeAttributes[mandatory,searchable,sortOrder,"
    "trackedEntityAttribute[id,name,code,formName,valueType,unique,optionSet[id]]]"
)
_PROGRAM_FIELDS = (
    f"id,name,code,description,programType,{_ATTRIBUTE_VALUE_FIELDS},{_PROGRAM_ATTRIBUTE_FIELDS},"
    f"programStages[{_PROGRAM_STAGE_FIELDS}]"
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


def _refuse_build_aborting_codes(objects: list[_CodedObject]) -> None:
    """Refuse the run before a single file is written when an emitted code aborts the publisher's build."""
    for coded in objects:
        if not build_aborting_code(coded.emitted_code):
            continue
        raise BuildAbortingCodeError(
            f"{coded.resource_type} {coded.name!r} ({coded.uid}) has code {coded.emitted_code!r}, which carries "
            "'<'. A DHIS2 code becomes an identifier value, which the IG publisher writes into a table cell "
            "unescaped and then strict-parses, so `make build` aborts with \"Unable to Parse HTML - node 'td' "
            'has unexpected content" in its last pass, once every resource has already been rendered. '
            "Change the code in DHIS2, then run `d2w fhir validate` for the full report."
        )


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
    """One-line outcome of one generate target: what it wrote, left alone, removed, and noted."""
    parts = [f"{len(report.written_files)} written", f"{report.unchanged_count} unchanged"]
    if report.deleted_files:
        parts.append(f"{len(report.deleted_files)} deleted")
    if report.notes:
        parts.append(f"{len(report.notes)} note{'' if len(report.notes) == 1 else 's'}")
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

#: Registry instances past which the IG publisher's rendering pass dominates the build. The registry
#: itself never reaches SUSHI - it ships as pre-built JSON - but the publisher still renders a page
#: per resource, so the wall clock of `make build` tracks this count.
_REGISTRY_RENDER_COST_INSTANCES = 10_000

#: Read timeout for the validate sweep's single `/api/metadata` request. The client's 30 s default
#: is sized for an ordinary API read; a whole-instance metadata read is a different shape of request
#: and needs its own ceiling. Measured on a national instance: 13 MB over 58 s, so the default fails
#: it every time and `d2w fhir validate` cannot run at all against exactly the instances whose size
#: makes its findings worth having.
_SWEEP_TIMEOUT_SECONDS = 600.0


def _sweep_collections(raw: dict[str, object]) -> list[MetadataCollectionIn]:
    """Wrap the raw `/api/metadata?fields=id,name,code` body into typed sweep sources."""
    collections: list[MetadataCollectionIn] = []
    for resource, value in raw.items():
        if resource in _SWEEP_EXCLUDED_COLLECTIONS or not isinstance(value, list):
            continue
        items = [
            MetadataItemIn(uid=str(entry["id"]), name=entry.get("name"), code=entry.get("code"))
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


async def validate_codes(
    profile: Profile,
    config: GenerateConfig,
    code_source: str | None = None,
    *,
    reporter: ProgressReporter | None = None,
) -> FhirValidationReport:
    """Check the whole instance's codes (sweep) plus the option sets in depth, without writing anything.

    The run first resolves the configured selection into a `ValidationScope`, so every finding's
    severity means build impact on this project's IG rather than instance-wide alarm.
    """
    effective_source = resolve_code_source(config, code_source)
    progress = _StepAnnouncer(reporter, VALIDATE_CODES_STEPS)
    progress.step("connecting")
    async with open_client(profile, timeout=_SWEEP_TIMEOUT_SECONDS) as client:
        progress.complete(profile.base_url)
        progress.step("selection", "resolving the configured selection")
        scope = await resolve_validation_scope(client, config)
        progress.complete(_scope_summary(scope))
        progress.step("instance sweep", "sweeping instance metadata (can take a minute on a large instance)")
        raw = await client.get_raw("/api/metadata", params={"fields": "id,name,code", "defaults": "EXCLUDE"})
        collections = _sweep_collections(raw)
        object_count = sum(len(collection.items) for collection in collections)
        progress.complete(f"{len(collections):,} collections, {object_count:,} objects")
        progress.step("option sets", "reading option sets")
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        progress.complete(f"{len(models):,} read")
    progress.step("findings", "building report")
    option_sets = [_option_set_input(model) for model in models]
    report = build_code_validation(option_sets, collections, config, effective_source, scope=scope)
    progress.complete(f"{len(report.findings):,} finding(s)")
    return report


#: The id-only data-set projection scope resolution reads: membership alone, no form detail.
_SCOPE_DATA_SET_FIELDS = "id,dataSetElements[dataElement[id,optionSet[id]]]"

#: The id-only program projection scope resolution reads: the routing type, the stages with each
#: stage's data-element references, and the tracked entity attributes a tracker program's
#: registration form asks - every one of them carrying the option set it binds, because the
#: option-set closure is the union of what the whole capture surface binds.
_SCOPE_PROGRAM_FIELDS = (
    "id,programType,programStages[id,programStageDataElements[dataElement[id,optionSet[id]]]],"
    "programTrackedEntityAttributes[trackedEntityAttribute[id,optionSet[id]]]"
)


class _ScopeBindings(BaseModel):
    """The data elements the selected containers carry, and the option sets they and the attributes bind."""

    data_element_uids: set[str] = Field(default_factory=set)
    option_set_uids: set[str] = Field(default_factory=set)

    def collect(self, reference: dict[str, object]) -> None:
        """Record one wire data-element reference: its UID plus the option set it binds, when it binds one."""
        uid = _optional_text(reference.get("id"))
        if uid is None:
            return
        self.data_element_uids.add(uid)
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
    """Mine one tracker program's registration attributes into the scope bindings' option-set closure."""
    raw_attributes = program.programTrackedEntityAttributes
    for entry in raw_attributes if isinstance(raw_attributes, list) else []:
        if not isinstance(entry, dict):
            continue
        reference = _tracked_entity_attribute_reference(entry)
        if reference is not None:
            bindings.collect_option_set(reference)


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
    attributes contribute their option sets to the closure without joining the data-element
    surface: a registration form asks them as questions, so the sets they bind are published, but
    an attribute is not a data element and `dataElements` is what that surface answers for. A
    program named under the selection table its type does not belong to contributes nothing here:
    that misconfiguration is generate's refusal to raise, not validate's.
    """
    bindings = _ScopeBindings()
    data_set_ids = config.data_sets.include_ids
    data_set_models: list[DataSet] = await client.resources.data_sets.list(
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
    event_ids = config.event_programs.include_ids
    tracker_ids = config.tracker_programs.include_ids
    program_models: list[Program] = await client.resources.programs.list(
        fields=_SCOPE_PROGRAM_FIELDS,
        filters=[_uid_filter([*event_ids, *tracker_ids])] if event_ids and tracker_ids else None,
        paging=False,
    )
    programs: set[str] = set()
    tracker_programs: set[str] = set()
    program_stages: set[str] = set()
    for program in program_models:
        uid = program.id or ""
        if not uid:
            continue
        program_type = _program_type(program)
        stages = _program_stages(program)
        as_event = uid in event_ids if event_ids else program_type == _EVENT_PROGRAM_TYPE
        as_tracker = uid in tracker_ids if tracker_ids else program_type == _TRACKER_PROGRAM_TYPE
        if as_event and program_type == _EVENT_PROGRAM_TYPE:
            programs.add(uid)
            for stage in stages[:1]:
                _collect_stage_elements(stage, bindings)
        if as_tracker and program_type == _TRACKER_PROGRAM_TYPE:
            programs.add(uid)
            tracker_programs.add(uid)
            _collect_registration_attributes(program, bindings)
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
    # built-in default placeholder, which `_category_selected` keeps off the build path.
    category_models: list[Category] = await client.resources.categories.list(
        fields="id,name",
        filters=[_uid_filter(category_ids)] if category_ids else None,
        paging=False,
    )
    return ValidationScope(
        option_sets=option_sets,
        categories=frozenset(
            model.id
            for model in category_models
            if model.id and _category_selected(model.id, model.name or "", config.categories)
        ),
        organisation_units=await _fetch_published_organisation_unit_uids(client, config),
        data_sets=frozenset(data_sets),
        programs=frozenset(programs),
        tracker_programs=frozenset(tracker_programs),
        program_stages=frozenset(program_stages),
        data_elements=frozenset(bindings.data_element_uids),
    )


def _scope_summary(scope: ValidationScope) -> str:
    """One line of in-scope set sizes - the durable outcome of the resolving-selection step."""
    return (
        f"{len(scope.data_sets):,} data sets, {len(scope.programs):,} programs, "
        f"{len(scope.program_stages):,} stages, {len(scope.data_elements):,} data elements, "
        f"{len(scope.option_sets):,} option sets, {len(scope.categories):,} categories, "
        f"{len(scope.organisation_units):,} organisation units"
    )


async def init_project(directory: Path, options: InitOptions, *, force: bool = False) -> ScaffoldReport:
    """Scaffold a SUSHI IG project into `directory`, skipping files that already exist unless `force`."""
    report = ScaffoldReport(directory=directory.resolve())
    for scaffold_file in build_scaffold_files(options):
        destination = directory / scaffold_file.relative_path
        if destination.exists() and not force:
            report.skipped_files.append(scaffold_file.relative_path)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(scaffold_file.content, encoding="utf-8")
        report.created_files.append(scaffold_file.relative_path)
    return report


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
    )
    progress.complete(_target_counts(report))
    return report


async def generate_option_sets(
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateReport:
    """Generate a CodeSystem/ValueSet pair per option set into `terminology/`, plus its ConceptMap."""
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[GenerateNote] = []
    progress.step(_FETCH_LABEL, "fetching option sets")
    async with open_client(profile) as client:
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        sources = await _closure_sources(client, config)
        attribute_codes = await resolve_attribute_code_index(client)
    inputs = _selected_option_sets([_option_set_input(model) for model in models], sources, config, notes)
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
    _refuse_build_aborting_codes(
        [
            _CodedObject(resource_type="optionSets", uid=option_set.uid, name=option_set.name, code=option_set.code)
            for option_set in option_sets
        ]
    )
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
    sync = sync_json_artifacts(project.resources_directory, TERMINOLOGY_DIRECTORY, build.artifacts)
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
        notes=[*notes, *build.notes],
    )
    progress.complete(_target_counts(report))
    return report


async def generate_categories(
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateReport:
    """Generate one pre-built CodeSystem and ValueSet document per configured category into `categories/`."""
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[GenerateNote] = []
    progress.step(_FETCH_LABEL, "fetching categories")
    async with open_client(profile) as client:
        inputs = await _fetch_categories(client, config, notes)
        attribute_codes = await resolve_attribute_code_index(client)
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
    _refuse_build_aborting_codes(
        [
            _CodedObject(resource_type="categories", uid=category.uid, name=category.name, code=category.code)
            for category in categories
        ]
    )
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
    sync = sync_json_artifacts(project.resources_directory, CATEGORY_DIRECTORY, build.artifacts)
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
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateReport:
    """Generate one Questionnaire FSH file per selected data set, event program, and tracker program stage."""
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[GenerateNote] = []
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets")
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources)
        attribute_codes = await resolve_attribute_code_index(client)
        # The categories the run publishes, read in this target's own fetch phase: the combo
        # vocabularies decompose every option combo into them, so the concept codes and the
        # CodeSystem canonicals a coding names come from the very selection the category target
        # emits rather than from a shape guessed off the combo.
        categories = await _fetch_categories(client, config, notes)
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
    CodeSystem.
    """
    generate = project.config.generate
    canonical = project.config.ig.canonical
    ig_status = project.config.ig.status
    progress.step(
        "questionnaires",
        f"writing ig/input/fsh/{{{','.join(QUESTIONNAIRE_DIRECTORIES)}}} and "
        f"ig/input/resources/{{{ASSIGNMENT_DIRECTORY},{ATTRIBUTE_COMBO_DIRECTORY}}}",
    )
    _refuse_build_aborting_codes([_coded_source(source) for source in sources])
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
        sync_json_artifacts(project.resources_directory, ATTRIBUTE_COMBO_DIRECTORY, attribute_combo_build.artifacts),
        sync_json_artifacts(
            project.resources_directory,
            CONCEPT_MAP_DIRECTORY,
            concept_maps,
            owned_prefix=attribute_combo_concept_map_file_prefix(generate),
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
        assignment_count=len(assignment_build.artifacts),
        attribute_combo_count=len(attribute_combo_build.artifacts),
        notes=[
            *notes,
            *build.notes,
            *assignment_build.notes,
            *attribute_combo_build.notes,
            *decomposition.notes,
        ],
    )
    progress.complete(_target_counts(report))
    return report


async def generate_examples(
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateReport:
    """Generate one `Usage: #example` QuestionnaireResponse per configured example into `examples/`."""
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
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
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        option_sets = await _fetch_example_option_sets(client, sources)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources)
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
        notes=notes,
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
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources)
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
    report = LoadSetReport(
        project_root=project.project_root,
        target_directory=_LOAD_DIRECTORY,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        deleted_files=sync.deleted,
        response_count=len(documents),
        questionnaire_count=len(covered_sources),
        notes=notes,
    )
    progress.complete(f"{len(report.written_files):,} written, {report.unchanged_count:,} unchanged")
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
        groups = _data_value_groups(raw, source.uid, iso)
        if groups:
            return groups[:per_target]
    return []


class _DataValueGroup(BaseModel):
    """One `(orgUnit, period, attributeOptionCombo)` key of a data value set and the values under it."""

    organisation_unit_uid: str
    period_iso: str
    attribute_option_combo_uid: str
    answers: list[ExampleAnswerIn] = Field(default_factory=list)


def _data_value_groups(raw: dict[str, object], data_set_uid: str, fallback_iso: str) -> list[ExampleResponseIn]:
    """Group a data value set by its reporting key, richest group first, then by organisation unit."""
    values = raw.get("dataValues")
    grouped: dict[str, _DataValueGroup] = {}
    for entry in values if isinstance(values, list) else []:
        if not isinstance(entry, dict):
            continue
        data_element_uid = _optional_text(entry.get("dataElement"))
        value = entry.get("value")
        if data_element_uid is None or not isinstance(value, str):
            continue
        organisation_unit_uid = _optional_text(entry.get("orgUnit")) or ""
        period_iso = _optional_text(entry.get("period")) or fallback_iso
        attribute_option_combo_uid = _optional_text(entry.get("attributeOptionCombo")) or ""
        key = f"{organisation_unit_uid}.{period_iso}.{attribute_option_combo_uid}"
        group = grouped.setdefault(
            key,
            _DataValueGroup(
                organisation_unit_uid=organisation_unit_uid,
                period_iso=period_iso,
                attribute_option_combo_uid=attribute_option_combo_uid,
            ),
        )
        group.answers.append(
            ExampleAnswerIn(
                data_element_uid=data_element_uid,
                category_option_combo_uid=_optional_text(entry.get("categoryOptionCombo")),
                value=value,
            )
        )
    ordered = sorted(grouped.values(), key=lambda group: (-len(group.answers), group.organisation_unit_uid))
    return [_data_value_response(group, data_set_uid) for group in ordered if group.organisation_unit_uid]


def _data_value_response(group: _DataValueGroup, data_set_uid: str) -> ExampleResponseIn:
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
        attribute_option_combo_uid=group.attribute_option_combo_uid or None,
        answers=group.answers,
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
        code=source.code,
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
            "pre-built JSON so SUSHI never compiles them, but the IG publisher renders a page per resource, "
            "so they set the wall clock of `make build`. Narrow the registry with "
            "`[generate.organisation_units]` max_level or root if the build is longer than you want.",
        )
    ]


async def generate_organisation_units(
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateReport:
    """Generate the profiles and terminology into `organization/`, and the instance registry into `registry/`."""
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    tally = GeometryTally()
    today = datetime.now(tz=UTC).date()
    progress.step(_FETCH_LABEL, "fetching organisation units")
    async with open_client(profile) as client:
        organisation_units = await _fetch_organisation_units(client, project.config.generate, tally, today, progress)
        attribute_codes = await resolve_attribute_code_index(client)
    progress.complete(f"{len(organisation_units):,} organisation unit(s)")
    return _emit_organisation_units(
        project,
        organisation_units=organisation_units,
        attribute_codes=attribute_codes,
        stems=plan_organisation_unit_stems(
            organisation_unit_stem_subjects(organisation_units), project.config.generate.naming.source
        ),
        notes=tally.to_notes(),
        progress=progress,
    )


def _emit_organisation_units(
    project: FhirProject,
    *,
    organisation_units: list[OrganisationUnitIn],
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
    _refuse_build_aborting_codes(
        [
            _CodedObject(
                resource_type="organisationUnits",
                uid=organisation_unit.uid,
                name=organisation_unit.name,
                code=organisation_unit.code,
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
                ig_status=ig_status,
            )
        )
        instances = build_organisation_unit_instances(
            organisation_units,
            generate_config,
            project.config.ig.canonical,
            attribute_codes=attribute_codes,
            stems=stems,
        )
        registry = instances.artifacts
        notes.extend(instances.notes)
        examples = build_registry_examples(organisation_units, generate_config, ig_status=ig_status)
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
    report = GenerateReport(
        project_root=project.project_root,
        target_base="ig/input",
        target_directory=f"fsh/organization, resources/{REGISTRY_DIRECTORY}",
        deleted_files=[*sync.deleted, *registry_sync.deleted],
        written_files=[*sync.written, *registry_sync.written],
        unchanged_count=len(sync.unchanged) + len(registry_sync.unchanged),
        organisation_unit_count=len(organisation_units),
        position_count=sum(1 for organisation_unit in organisation_units if organisation_unit.latitude is not None),
        boundary_count=sum(
            1 for organisation_unit in organisation_units if organisation_unit.boundary_geojson is not None
        ),
        notes=notes,
    )
    progress.complete(_target_counts(report))
    return report


async def generate_pages(
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateReport:
    """Generate the narrative site pages and the per-artifact intros into `ig/input/pagecontent/`."""
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[GenerateNote] = []
    tally = GeometryTally()
    today = datetime.now(tz=UTC).date()
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets, option sets, and organisation units")
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        organisation_units = await _fetch_organisation_units(client, config, tally, today, progress)
    option_sets = _selected_option_sets([_option_set_input(model) for model in models], sources, config, notes)
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
        intro_count=intro_count,
        notes=[*notes, *build.notes],
    )
    progress.complete(_target_counts(report))
    return report


async def generate_full(
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateFullReport:
    """Generate every target off one connected client and one pass over the instance's metadata.

    The whole IG in a single run. The instance is read once - the questionnaire targets, every
    option set, the categories, the organisation-unit slice, and the run's attribute-code join -
    and each target then builds and syncs off that one result, so nothing is fetched a second
    time the way seven separate commands would fetch it. The foundation runs first because it
    reads nothing at all, and the pages run last because they narrate what the other targets
    wrote. Each target keeps the notes it alone owns, so its report reads exactly as the solo
    command's does.
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_FULL_STEPS)
    progress.step(_FETCH_LABEL, "fetching instance metadata")
    async with open_client(profile) as client:
        inputs = await fetch_live_ig_inputs(client, config, progress=progress)
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
    client: Dhis2Client, config: GenerateConfig, *, progress: _StepAnnouncer | None = None
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
    """
    steps = progress if progress is not None else _StepAnnouncer()
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
    option_set_plan = _option_set_identity_plan(fetched_option_sets, config, sources)
    steps.tick("reading categories")
    categories = await _fetch_categories(client, config, category_notes)
    organisation_units = await _fetch_organisation_units(client, config, tally, today, steps)
    steps.tick("reading the attribute-code join")
    attribute_codes = await resolve_attribute_code_index(client)
    steps.tick("reading the organisation-unit assignments")
    assignments = await fetch_assignment_index(client, sources)
    geometry_notes = tally.to_notes()
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
    client: Dhis2Client, config: GenerateConfig, sources: list[QuestionnaireSourceIn]
) -> OptionSetIdentityPlan:
    """Assign the option-set identities for one generate run, off the very selection the terminology target emits.

    A slug is assigned against its peers - truncation and collision suffixes both depend on the
    whole list - so every target that names an option set has to plan over the identical
    selection. The projection is narrower than the terminology target's because a slug is
    decided by the UID and the name alone. The selection notes belong to the terminology
    target's report, so they are not raised a second time here.
    """
    models = await client.resources.option_sets.list(
        fields=_OPTION_SET_IDENTITY_FIELDS,
        order=["name:asc"],
        paging=False,
    )
    inputs = [OptionSetIn(uid=model.id or "", name=model.name or model.id or "") for model in models]
    return option_set_identities(_selected_option_sets(inputs, sources, config, []), config)


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
    matching the terminology targets. Data sets come first, then the programs, then the tracked
    entity types - whose default is not the whole instance but the types the selected tracker
    programs track, so a project selecting one program publishes a person-only form for the kind
    of person that program registers rather than for every kind the instance knows.
    """
    sources: list[QuestionnaireSourceIn] = []
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
    a run selecting no tracker programs and naming no types costs no request at all.
    """
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
    """
    event_ids = config.event_programs.include_ids
    tracker_ids = config.tracker_programs.include_ids
    if not event_ids and not tracker_ids:
        return _swept_program_sources(await _list_programs(client, None), notes)
    sources: list[QuestionnaireSourceIn] = []
    if event_ids:
        selected = await _list_programs(client, event_ids)
        sources.extend(_event_program_source(model, notes) for model in selected)
        _note_unmatched(event_ids, {model.id for model in selected}, "event_programs", "event program", notes)
    else:
        swept = await _list_programs(client, None)
        sources.extend(
            _event_program_source(model, notes) for model in swept if _program_type(model) == _EVENT_PROGRAM_TYPE
        )
    if tracker_ids:
        selected = await _list_programs(client, tracker_ids)
        for model in selected:
            sources.extend(_tracker_program_sources(model, notes))
        _note_unmatched(tracker_ids, {model.id for model in selected}, "tracker_programs", "tracker program", notes)
    else:
        swept = await _list_programs(client, None)
        for model in swept:
            if _program_type(model) == _TRACKER_PROGRAM_TYPE:
                sources.extend(_tracker_program_sources(model, notes))
    return sources


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
    """
    uid = model.id or ""
    compulsory = _compulsory_operands(model)
    items: list[QuestionnaireItemIn] = []
    for element in model.dataSetElements or []:
        reference = element.dataElement
        if reference is None or not reference.id:
            continue
        items.append(_marked_required(_questionnaire_item(reference.model_dump(), compulsory=False), compulsory))
    items.sort(key=lambda item: (item.name, item.uid))
    return _questionnaire_source(
        uid=uid,
        name=model.name or uid,
        code=model.code,
        description=model.description,
        kind="aggregate",
        period_type=str(model.periodType) if model.periodType is not None else None,
        items=items,
        raw_sections=model.sections,
        attribute_values=_attribute_value_inputs(model.attributeValues),
        attribute_combo=_category_combo_input(_attribute_combo_wire(model)),
        notes=notes,
    )


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
    if stages:
        stage = stages[0]
        items = _stage_items(stage)
        raw_sections = stage.get("programStageSections")
    return _questionnaire_source(
        uid=uid,
        name=name,
        code=model.code,
        description=model.description,
        kind="event",
        items=items,
        raw_sections=raw_sections,
        attribute_values=_attribute_value_inputs(model.attributeValues),
        notes=notes,
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
        uid=uid, name=name, code=model.code, tracked_entity_type_uid=_tracked_entity_type_uid(model)
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
                kind="tracker-event",
                items=_stage_items(stage),
                raw_sections=stage.get("programStageSections"),
                attribute_values=_attribute_value_inputs(stage.get("attributeValues")),
                notes=notes,
                program=program,
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
        kind="tracker",
        items=_registration_items(model),
        raw_sections=None,
        attribute_values=_attribute_value_inputs(model.attributeValues),
        notes=notes,
        displays_incident_date=bool(model.displayIncidentDate),
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
            entity_level=True,
        )
        for entry in entries
        if (reference := _tracked_entity_attribute_reference(entry)) is not None
    ]


def _tracked_entity_type_uid(model: Program) -> str | None:
    """The DHIS2 tracked entity type a program enrols a person as, or None when the instance sent none."""
    reference = model.trackedEntityType
    return _optional_text(reference.id) if reference is not None else None


def _tracked_entity_type_attribute_uids(model: Program) -> frozenset[str] | None:
    """The attributes a program's tracked entity type collects itself, or None when the instance sent none.

    DHIS2 asks its registration questions at two levels: a `trackedEntityTypeAttribute` is
    collected for the entity whichever program enrols it, while an attribute only
    `programTrackedEntityAttributes` names is the program's own. An empty set is a type that
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
    for entry in raw_attributes:
        if not isinstance(entry, dict):
            continue
        attribute = _tracked_entity_attribute_reference(entry)
        uid = _optional_text(attribute.get("id")) if attribute is not None else None
        if uid is not None:
            uids.add(uid)
    return frozenset(uids)


def _registration_items(model: Program) -> list[QuestionnaireItemIn]:
    """One tracker program's registration questions, ordered by DHIS2 sort order then attribute name and UID.

    `programTrackedEntityAttributes` is the join between the program and its attributes, and it
    holds exactly what a stage's `programStageDataElements` join holds: whether the question is
    mandatory on this program, and where it sits in the form. So the two read the same way, and
    an attribute is projected onto the very question shape a data element is.

    The tracked entity type's own join decides one thing the program's join cannot: whether the
    answer is imported onto the tracked entity or onto the enrollment.
    """
    raw_attributes = model.programTrackedEntityAttributes
    entries = [
        entry
        for entry in (raw_attributes if isinstance(raw_attributes, list) else [])
        if isinstance(entry, dict) and _tracked_entity_attribute_reference(entry) is not None
    ]
    entries.sort(key=_registration_item_sort_key)
    entity_level_uids = _tracked_entity_type_attribute_uids(model)
    return [
        _tracked_entity_attribute_item(
            reference,
            mandatory=bool(entry.get("mandatory")),
            searchable=bool(entry.get("searchable")),
            entity_level=None
            if entity_level_uids is None
            else _optional_text(reference.get("id")) in entity_level_uids,
        )
        for entry in entries
        if (reference := _tracked_entity_attribute_reference(entry)) is not None
    ]


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
    raw: dict[str, object], *, mandatory: bool, searchable: bool, entity_level: bool | None
) -> QuestionnaireItemIn:
    """Map one wire tracked entity attribute into the question projection both emitters consume.

    `mandatory`, `searchable`, and `entity_level` come off the join rather than off the attribute,
    because all three are facts about this form asking this attribute rather than about the
    attribute itself.
    """
    uid = _optional_text(raw.get("id")) or ""
    option_set = raw.get("optionSet")
    option_set_uid = _optional_text(option_set.get("id")) if isinstance(option_set, dict) else None
    return QuestionnaireItemIn(
        uid=uid,
        name=_optional_text(raw.get("name")) or uid,
        code=_optional_text(raw.get("code")),
        form_name=_optional_text(raw.get("formName")),
        value_type=_optional_text(raw.get("valueType")) or "",
        option_set_uid=option_set_uid,
        compulsory=mandatory,
        unique=bool(raw.get("unique")),
        searchable=searchable,
        entity_level=entity_level,
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
    period_type: str | None = None,
    program: ProgramContextIn | None = None,
    attribute_combo: CategoryComboIn | None = None,
    displays_incident_date: bool = False,
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
        kind=kind,
        period_type=period_type,
        program=program,
        attribute_combo=attribute_combo,
        displays_incident_date=displays_incident_date,
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
                items=[items_by_uid[member_id] for member_id in member_ids if member_id in items_by_uid],
            )
        )
    return sections


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
        value_type=_optional_text(raw.get("valueType")) or "",
        domain_type=_optional_text(raw.get("domainType")) or "",
        option_set_uid=option_set_uid,
        compulsory=compulsory,
        category_combo=_category_combo_input(raw.get("categoryCombo")),
    )


def _category_combo_input(raw: object) -> CategoryComboIn | None:
    """Map one wire category combo, option combos included; None when the data element carries none."""
    if not isinstance(raw, dict):
        return None
    uid = _optional_text(raw.get("id"))
    if uid is None:
        return None
    return CategoryComboIn(
        uid=uid,
        name=_optional_text(raw.get("name")) or uid,
        code=_optional_text(raw.get("code")),
        is_default=bool(raw.get("isDefault")),
        category_uids=_reference_uid_list(raw.get("categories")),
        option_combos=_option_combo_inputs(raw.get("categoryOptionCombos")),
    )


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
    serialises it in a different order on every request (BUGS.md #64). This is the single
    point every consumer reads its order from - the questionnaire's option-combo child items,
    the example responses answering them, and the `D2COC_CS` support concepts - so a
    regenerate of an unchanged form produces an unchanged file, and the examples, fetched by
    a separate request, answer the questionnaire's items in the questionnaire's own order,
    which the FHIR validator requires.
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
#: translate, post, file what each response became.
FORWARD_STEPS = 6

#: The `/api/dataValueSets` endpoint one aggregate response is imported through.
_DATA_VALUE_SETS_PATH = "/api/dataValueSets"

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

#: The two codes DHIS2 answers a tracker event whose enrollment it cannot find with: `E1313` for the
#: enrollment nobody has, and the `E1079` program mismatch it asserts against that same absent
#: enrollment (BUGS.md 68). A rejection carrying only these is the whole shape a dry run cannot check.
_ABSENT_ENROLLMENT_ERROR_CODES = frozenset({"E1079", "E1313"})

#: What a dry run says about a stage event whose enrollment only a registration of the same run creates.
_UNVERIFIABLE_IN_DRY_RUN_REASON = (
    "The enrollment this event answers into is created by a registration validated in the same run. A dry "
    "run writes nothing to the instance, so there is no enrollment for DHIS2 to check the event against. "
    "An import posts registrations first, and the event is checked against the enrollment one created."
)


class ForwardOutcomeKind(StrEnum):
    """What became of one spooled response in a forward run."""

    #: The translator would not read the response whole, so it never reached DHIS2 and stays in the spool.
    REFUSED = "refused"

    #: DHIS2 took the payload - imported it, or validated it on a dry run.
    ACCEPTED = "accepted"

    #: DHIS2 was given the payload and refused it; the import report says why.
    REJECTED = "rejected"

    #: A dry run could not check the payload, because what it answers into is created by the same run.
    UNVERIFIABLE = "unverifiable"


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

    @property
    def is_rejected(self) -> bool:
        """Whether DHIS2 refused the payload: an error status, or any row it named against the payload."""
        return self.status == _ERROR_IMPORT_STATUS or bool(self.issues)

    @property
    def counts_line(self) -> str:
        """What the import did, as the one cell a per-response table shows when there is no reason to show."""
        return f"{self.created} created, {self.updated} updated, {self.ignored} ignored"


class ForwardRejectionRecord(ForwardImportOutcome):
    """The sidecar beside a rejected receipt: DHIS2's own answer, plus which payload was posted.

    The target kind is what tells an operator reading `rejected/<id>.report.json` cold which of the
    tracker shapes DHIS2 turned down - a person and their enrollment, or the enrollment alone for a
    person the instance already held - without opening the receipt beside it and reading its
    extensions back.
    """

    target_kind: ConversionTargetKind | None = None


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
    spool_path: str
    """Where the receipt sits now, relative to the project root - unmoved on a dry run and on a refusal."""


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
    spooled: int = 0
    outcomes: tuple[ForwardOutcome, ...] = ()
    unreadable_artifacts: tuple[str, ...] = ()
    """Every published non-form document the R4 models could not read, and so translated against nothing."""

    @property
    def refused(self) -> tuple[ForwardOutcome, ...]:
        """Every response the translator would not read whole, which is every response that stayed put."""
        return tuple(outcome for outcome in self.outcomes if outcome.kind == ForwardOutcomeKind.REFUSED)

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
    def translated_count(self) -> int:
        """How many responses produced a payload."""
        return self.spooled - len(self.refused)

    @property
    def posted_count(self) -> int:
        """How many payloads were posted to DHIS2."""
        return len(self.accepted) + len(self.rejected) + len(self.unverifiable)

    @property
    def counts_line(self) -> str:
        """The whole run in one line, which is what a progress reporter and a summary hint both want."""
        return (
            f"{self.spooled:,} spooled, {self.translated_count:,} translated, {len(self.refused):,} refused, "
            f"{self.posted_count:,} posted, {len(self.accepted):,} accepted, {len(self.rejected):,} rejected, "
            f"{len(self.unverifiable):,} unverifiable in a dry run"
        )

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
                reason = _generalised_reason(issue.reason)
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


async def forward_responses(
    profile: Profile,
    project: FhirProject,
    *,
    import_responses: bool = False,
    coded_answer_mode: CodedAnswerMode | None = None,
    reporter: ProgressReporter | None = None,
) -> ForwardReport:
    """Drain a project's capture spool into DHIS2: translate every receipt, post it, and file what it became.

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

    `coded_answer_mode` defaults to what `[serve] strict_codes` says, so a project that captures
    strictly forwards strictly without stating it twice.
    """
    mode = coded_answer_mode if coded_answer_mode is not None else _configured_coded_answer_mode(project)
    progress = _StepAnnouncer(reporter, FORWARD_STEPS)
    progress.step("spool", "reading the capture spool")
    spooled = read_received_responses(project.project_root)
    progress.complete(f"{len(spooled):,} pending response(s)")

    progress.step("compiled IG", "reading the published guide")
    artifacts = load_compiled_artifacts(project)
    unreadable = f", {len(artifacts.unreadable_resources):,} unreadable" if artifacts.unreadable_resources else ""
    progress.complete(
        f"{artifacts.resource_count:,} resource(s), {len(artifacts.questionnaires):,} form(s){unreadable}"
    )

    naming = ConversionNaming.from_config(project.config.generate, project.config.ig.canonical)
    bound = bound_question_uids(artifacts, naming)
    dry_run = not import_responses
    async with open_client(profile) as client:
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

        progress.step("post", _post_caption(0, len(conversion.translated), dry_run=dry_run))
        imports = await _post_translations(client, spooled, conversion, dry_run=dry_run, progress=progress)
        progress.complete(f"{len(imports):,} payload(s) posted{' (validate only)' if dry_run else ''}")

    progress.step("spool", "filing what each response became")
    minted_enrollments = _minted_enrollment_uids(conversion) if dry_run else frozenset[str]()
    outcomes = _file_outcomes(
        spooled,
        conversion,
        imports,
        project.project_root,
        moving=import_responses,
        minted_enrollments=minted_enrollments,
    )
    report = ForwardReport(
        project_root=project.project_root,
        dry_run=dry_run,
        coded_answer_mode=mode,
        spooled=len(spooled),
        outcomes=outcomes,
        unreadable_artifacts=artifacts.unreadable_resources,
    )
    progress.complete(report.counts_line)
    return report


def _configured_coded_answer_mode(project: FhirProject) -> CodedAnswerMode:
    """The coded-answer dial a project forwards under, which is the one it captures under."""
    return CodedAnswerMode.STRICT if project.config.serve.strict_codes else CodedAnswerMode.LENIENT


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


async def _post_translations(
    client: Dhis2Client,
    spooled: Sequence[SpooledResponse],
    conversion: ConversionReport,
    *,
    dry_run: bool,
    progress: _StepAnnouncer,
) -> dict[str, ForwardImportOutcome]:
    """Post every translated payload, one response at a time, keyed by the receipt it came from.

    One payload per POST is what makes the outcome attributable: DHIS2 answers a bundle with one
    report for the bundle, and a spool whose receipts move individually needs one answer each.

    The order is `FORWARD_TARGET_ORDER` and then the spool's, which is what makes one drain
    internally consistent: a person-only capture creates the person a registration captured seconds
    later enrols, a registration creates the enrollment a stage event captured seconds later answers
    against, and DHIS2 refuses an event naming an enrollment it cannot find with `E1313`. Posting
    by kind is the whole of the coordination - there is no dependency graph, and a registration
    DHIS2 rejects still leaves its stage events to fail `E1313`, which the next drain retries once
    the cause is fixed.
    """
    translated = sorted(
        ((entry, result) for entry, result in zip(spooled, conversion.results, strict=True) if not result.is_refused),
        key=lambda pair: _post_order(pair[1]),
    )
    imports: dict[str, ForwardImportOutcome] = {}
    for posted, (entry, result) in enumerate(translated, start=1):
        imports[entry.response_id] = await _post_result(client, result, dry_run=dry_run)
        if posted % _POST_TICK_INTERVAL == 0 or posted == len(translated):
            progress.tick(_post_caption(posted, len(translated), dry_run=dry_run))
    return imports


def _post_order(result: ConversionResult) -> int:
    """Where one translated payload sits in the posting order its target kind gives it."""
    if result.target_kind is None or result.target_kind not in FORWARD_TARGET_ORDER:
        return len(FORWARD_TARGET_ORDER)
    return FORWARD_TARGET_ORDER.index(result.target_kind)


async def _post_result(client: Dhis2Client, result: ConversionResult, *, dry_run: bool) -> ForwardImportOutcome:
    """Post one translated payload to the endpoint its target kind names, and project DHIS2's answer."""
    if result.data_value_set is not None:
        params = dict(_DATA_VALUE_SETS_DRY_RUN_PARAMS) if dry_run else {}
        body = result.data_value_set.model_dump(by_alias=True, exclude_none=True, mode="json")
        return _aggregate_import_outcome(await _post_body(client, _DATA_VALUE_SETS_PATH, body, params))
    params = {**_TRACKER_PARAMS, **(_TRACKER_DRY_RUN_PARAMS if dry_run else {})}
    if result.tracked_entity is not None:
        registration = result.tracked_entity.model_dump(by_alias=True, exclude_none=True, mode="json")
        body = {_TRACKER_TRACKED_ENTITIES_KEY: [registration]}
        return _tracker_import_outcome(await _post_body(client, _TRACKER_PATH, body, params))
    if result.enrollment is not None:
        enrolment = result.enrollment.model_dump(by_alias=True, exclude_none=True, mode="json")
        body = {_TRACKER_ENROLLMENTS_KEY: [enrolment]}
        return _tracker_import_outcome(await _post_body(client, _TRACKER_PATH, body, params))
    if result.event is None:
        raise ValueError(
            "a translated result carries no data value set, no tracked entity, no enrollment, and no event"
        )
    body = {_TRACKER_EVENTS_KEY: [result.event.model_dump(by_alias=True, exclude_none=True, mode="json")]}
    return _tracker_import_outcome(await _post_body(client, _TRACKER_PATH, body, params))


async def _post_body(
    client: Dhis2Client,
    path: str,
    body: dict[str, Any],
    params: dict[str, str],
) -> dict[str, Any]:
    """POST one payload and answer with DHIS2's own JSON body, whether it accepted the payload or refused it.

    A refused import is `409 Conflict` carrying the endpoint's report, so a rejection is an outcome to
    record rather than an error to raise. The body is passed on **raw** rather than parsed here, because
    the two endpoints do not agree on whether the report is wrapped: `/api/dataValueSets` answers a
    `WebMessage` whose `response` is the `ImportSummary`, and `/api/tracker` answers the
    `TrackerImportReport` bare, with no envelope around it at all - so the one shape that can carry both
    is the body itself, and each family unwraps its own. Anything the error carries no JSON object for -
    an authentication failure, an unreachable instance - is about the run and not about one response,
    and is raised.
    """
    try:
        return await client.post_raw(path, body, params=params)
    except Dhis2ApiError as error:
        if isinstance(error.body, dict):
            return error.body
        raise


def _aggregate_import_outcome(body: dict[str, Any]) -> ForwardImportOutcome:
    """Project an `/api/dataValueSets` answer: the import counts, and every conflict it named."""
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
    )


def _tracker_import_outcome(body: dict[str, Any]) -> ForwardImportOutcome:
    """Project an `/api/tracker` answer: the stats, and every validation error it reported."""
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
    )


def _envelope(body: dict[str, Any]) -> dict[str, Any]:
    """The `WebMessage` fields of an answer, which are the body's own when no envelope wrapped the report."""
    return body


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


def _generalised_reason(reason: str) -> str:
    """One DHIS2 message with its quoted identifiers generalised away, so one rule reads as one cause."""
    return _QUOTED_IDENTIFIER.sub("`...`", reason)


def _rejection_cause_key(error_code: str | None, generalised_reason: str) -> tuple[str | None, str]:
    """What a rejection rolls up under: the error code alone, or the generalised message when there is no code.

    An error code names a DHIS2 rule identically on every major, while the wording around it drifts, so
    a coded row carries no message in its key and a codeless one has nothing else to be named by.
    """
    return (error_code, "") if error_code else (None, generalised_reason)


def _file_outcomes(
    spooled: Sequence[SpooledResponse],
    conversion: ConversionReport,
    imports: dict[str, ForwardImportOutcome],
    project_root: Path,
    *,
    moving: bool,
    minted_enrollments: frozenset[str],
) -> tuple[ForwardOutcome, ...]:
    """Pair every receipt with what DHIS2 said about it, moving the file when the run really imported.

    `minted_enrollments` is empty on an import run, which is what keeps the unverifiable reading a
    dry-run reading: an import creates the enrollments it posts, so nothing it rejects goes unchecked.
    """
    outcomes: list[ForwardOutcome] = []
    for entry, result in zip(spooled, conversion.results, strict=True):
        imported = imports.get(entry.response_id)
        kind = _outcome_kind(result, imported, minted_enrollments)
        path = _filed_path(entry, kind, imported, result.target_kind, moving=moving)
        outcomes.append(
            ForwardOutcome(
                response_id=entry.response_id,
                questionnaire=result.questionnaire or entry.questionnaire or None,
                target_kind=result.target_kind,
                kind=kind,
                notes=result.notes,
                refusals=result.refusals,
                import_outcome=imported,
                spool_path=_relative_path(path, project_root),
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
) -> ForwardOutcomeKind:
    """Which of the four states one receipt ended in."""
    if result.is_refused or imported is None:
        return ForwardOutcomeKind.REFUSED
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
    if result.event is None or result.event.enrollment not in minted_enrollments:
        return False
    error_codes = {issue.error_code for issue in imported.issues}
    return bool(error_codes) and all(code in _ABSENT_ENROLLMENT_ERROR_CODES for code in error_codes)


def _filed_path(
    entry: SpooledResponse,
    kind: ForwardOutcomeKind,
    imported: ForwardImportOutcome | None,
    target_kind: ConversionTargetKind | None,
    *,
    moving: bool,
) -> Path:
    """Move the receipt into the state it ended in, and answer with where it now sits.

    A dry run moves nothing at all, so a run that validated the whole spool leaves the queue exactly
    as it found it and can be run again as the import. `unverifiable` is a dry-run reading and so is
    named here for the same reason: what a run could not check stays where the next run finds it.

    A rejection takes its report along, and the report names the payload kind DHIS2 turned down as
    well as what DHIS2 said about it.
    """
    if not moving or kind in (ForwardOutcomeKind.REFUSED, ForwardOutcomeKind.UNVERIFIABLE):
        return entry.path
    if kind == ForwardOutcomeKind.ACCEPTED:
        return move_to_forwarded(entry)
    if imported is None:
        return entry.path
    record = ForwardRejectionRecord(**dict(imported), target_kind=target_kind)
    return move_to_rejected(entry, record)


def _relative_path(path: Path, project_root: Path) -> str:
    """Name one spool file relative to the project when it lives inside it, so the report stays portable."""
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()
