"""Service layer for the `fhir` plugin - project scaffolding and FSH generation (CLI + MCP share it)."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile, resolve
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
from dhis2w_fhir.config import FhirProject, GenerateConfig, NoFhirProjectError, load_project
from dhis2w_fhir.foundation import build_foundation_artifacts
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.names import code_or_uid
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.period import parse_period, recent_periods
from dhis2w_fhir.r4 import QuestionnaireResponse
from dhis2w_fhir.resources.categories import CATEGORY_DIRECTORY, build_category_artifacts
from dhis2w_fhir.resources.categories.schemas import CategoryIn
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
)
from dhis2w_fhir.resources.option_sets import (
    CONCEPT_MAP_DIRECTORY,
    TERMINOLOGY_DIRECTORY,
    build_option_set_artifacts,
    build_option_set_concept_map_artifacts,
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
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    FormKind,
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
)
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.scaffold.schemas import InitOptions, ScaffoldReport
from dhis2w_fhir.validation import build_aborting_code, build_code_validation
from dhis2w_fhir.validation.schemas import (
    FhirValidationReport,
    MetadataCollectionIn,
    MetadataItemIn,
    ValidationScope,
)
from dhis2w_fhir.writer import FshArtifact, JsonArtifact, clean_generated_files, sync_artifacts, sync_json_artifacts

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client
    from dhis2w_client.generated.v42.schemas import (
        Attribute,
        Category,
        DataSet,
        OptionSet,
        OrganisationUnit,
        Program,
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
_QUESTIONNAIRE_DATA_ELEMENT_FIELDS = (
    "dataElement[id,name,formName,valueType,domainType,optionSet[id],"
    "categoryCombo[id,name,isDefault,categoryOptionCombos[id,name,code]]]"
)
_DATA_SET_FIELDS = (
    "id,name,code,description,periodType,sections[id,name,dataElements[id]],"
    f"{_ATTRIBUTE_VALUE_FIELDS},"
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
_PROGRAM_FIELDS = (
    f"id,name,code,description,programType,{_ATTRIBUTE_VALUE_FIELDS},programStages[{_PROGRAM_STAGE_FIELDS}]"
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

#: The envelope keys the tracker events endpoint has answered under.
_EVENT_ENVELOPE_KEYS = ("instances", "events")

#: Where the synthetic load set is written, relative to the project root. It is not IG input: the
#: files are a corpus to POST at a running `d2w fhir serve`, so they sit beside `ig/` rather than
#: inside it, and the target owns the directory outright.
_LOAD_DIRECTORY = "load"

#: How many synthetic responses each questionnaire target contributes to a load set by default -
#: enough that a seven-form instance yields a corpus worth measuring a POST loop against.
DEFAULT_LOAD_SET_PER_TARGET = 25


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
    organisation_unit_count: int = 0
    position_count: int = 0
    boundary_count: int = 0
    example_count: int = 0
    page_count: int = 0
    intro_count: int = 0
    notes: list[str] = Field(default_factory=list)


class LoadSetReport(BaseModel):
    """Outcome of one load-set run: the synthetic QuestionnaireResponse corpus written to disk."""

    project_root: Path
    target_directory: str
    written_files: list[str] = Field(default_factory=list)
    unchanged_count: int = 0
    deleted_files: list[str] = Field(default_factory=list)
    response_count: int = 0
    questionnaire_count: int = 0
    notes: list[str] = Field(default_factory=list)


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

#: The id-only program projection scope resolution reads: the routing type, the stages, and each
#: stage's data-element references with the option set every element binds.
_SCOPE_PROGRAM_FIELDS = "id,programType,programStages[id,programStageDataElements[dataElement[id,optionSet[id]]]]"


class _ScopeBindings(BaseModel):
    """The data elements the selected containers carry, and the option sets those elements bind."""

    data_element_uids: set[str] = Field(default_factory=set)
    option_set_uids: set[str] = Field(default_factory=set)

    def collect(self, reference: dict[str, object]) -> None:
        """Record one wire data-element reference: its UID plus the option set it binds, when it binds one."""
        uid = _optional_text(reference.get("id"))
        if uid is None:
            return
        self.data_element_uids.add(uid)
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


async def resolve_validation_scope(client: Dhis2Client, config: GenerateConfig) -> ValidationScope:
    """Resolve the UID sets the configured selection emits, from a handful of id-only reads.

    The same selection semantics `generate` applies - an empty table selects everything of its
    kind, the option sets add the closure the selected forms bind (through the
    `_selected_option_set_uids` helper both paths share), the organisation units go through the
    shared `_organisation_unit_selection_filters` - read in projections that carry ids alone, so
    scoping a national instance costs five small requests rather than a second metadata sweep.

    A data element is in scope when a selected data set or a selected program's stage carries it;
    an event program contributes its single stage's elements (the stage itself is not a surface -
    only a tracker stage emits its own Questionnaire). A program named under the selection table
    its type does not belong to contributes nothing here: that misconfiguration is generate's
    refusal to raise, not validate's.
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
    category_models: list[Category] = await client.resources.categories.list(
        fields="id",
        filters=[_uid_filter(category_ids)] if category_ids else None,
        paging=False,
    )
    return ValidationScope(
        option_sets=option_sets,
        categories=frozenset(model.id for model in category_models if model.id),
        organisation_units=await _fetch_published_organisation_unit_uids(client, config),
        data_sets=frozenset(data_sets),
        programs=frozenset(programs),
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
    artifacts = build_foundation_artifacts(project.config.generate, ig_status=project.config.ig.status)
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
    notes: list[str] = []
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
    notes: list[str],
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
    concept_map_sync = sync_json_artifacts(project.resources_directory, CONCEPT_MAP_DIRECTORY, concept_maps)
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
    notes: list[str] = []
    progress.step(_FETCH_LABEL, "fetching categories")
    async with open_client(profile) as client:
        models = await client.resources.categories.list(
            fields=_CATEGORY_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        attribute_codes = await resolve_attribute_code_index(client)
    inputs = _selected_categories([_category_input(model) for model in models], config, notes)
    progress.complete(f"{len(inputs):,} categor{'y' if len(inputs) == 1 else 'ies'}")
    return _emit_categories(project, categories=inputs, attribute_codes=attribute_codes, notes=notes, progress=progress)


def _emit_categories(
    project: FhirProject,
    *,
    categories: list[CategoryIn],
    attribute_codes: AttributeCodeIndex,
    notes: list[str],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the category documents off an already-selected category list and sync them into the project."""
    progress.step("categories", f"writing ig/input/resources/{CATEGORY_DIRECTORY}")
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
    sync = sync_json_artifacts(project.resources_directory, CATEGORY_DIRECTORY, build.artifacts)
    report = GenerateReport(
        project_root=project.project_root,
        target_base="ig/input",
        target_directory=f"resources/{CATEGORY_DIRECTORY}",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        category_count=len(categories),
        notes=[*notes, *build.notes],
    )
    progress.complete(_target_counts(report))
    return report


def _selected_categories(inputs: list[CategoryIn], config: GenerateConfig, notes: list[str]) -> list[CategoryIn]:
    """Filter categories by the configured UIDs, noting entries that matched nothing.

    An absent or empty `[generate.categories] include_ids` selects every category the instance
    holds, matching the option-set selection. A category is not pulled in by a closure the way
    an option set is: nothing generated today binds a category, so the list stands on its own.
    """
    selection = config.categories
    if not selection.include_ids:
        return inputs
    configured_ids = set(selection.include_ids)
    selected = [item for item in inputs if item.uid in configured_ids]
    selected_ids = {item.uid for item in selected}
    for uid in sorted(configured_ids - selected_ids):
        notes.append(f"include_ids entry {uid!r} matched no category")
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


async def generate_questionnaires(
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateReport:
    """Generate one Questionnaire FSH file per selected data set, event program, and tracker program stage."""
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[str] = []
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets")
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources)
        attribute_codes = await resolve_attribute_code_index(client)
    progress.complete(f"{len(sources):,} questionnaire target(s)")
    return _emit_questionnaires(
        project,
        sources=sources,
        option_set_plan=option_set_plan,
        attribute_codes=attribute_codes,
        notes=notes,
        progress=progress,
    )


def _emit_questionnaires(
    project: FhirProject,
    *,
    sources: list[QuestionnaireSourceIn],
    option_set_plan: OptionSetIdentityPlan,
    attribute_codes: AttributeCodeIndex,
    notes: list[str],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the Questionnaire FSH off already-fetched sources and sync each of its four directories."""
    progress.step("questionnaires", f"writing ig/input/fsh/{{{','.join(QUESTIONNAIRE_DIRECTORIES)}}}")
    _refuse_build_aborting_codes([_coded_source(source) for source in sources])
    build = build_questionnaire_artifacts(
        sources,
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
        option_set_plan=option_set_plan,
        attribute_codes=attribute_codes,
    )
    syncs = [
        sync_artifacts(project.fsh_directory, directory, _artifacts_under(build.artifacts, directory))
        for directory in QUESTIONNAIRE_DIRECTORIES
    ]
    report = GenerateReport(
        project_root=project.project_root,
        target_directory=", ".join(QUESTIONNAIRE_DIRECTORIES),
        deleted_files=[name for sync in syncs for name in sync.deleted],
        written_files=[path for sync in syncs for path in sync.written],
        unchanged_count=sum(len(sync.unchanged) for sync in syncs),
        questionnaire_count=len(sources),
        notes=[*notes, *build.notes],
    )
    progress.complete(_target_counts(report))
    return report


async def generate_examples(
    profile: Profile, project: FhirProject, *, reporter: ProgressReporter | None = None
) -> GenerateReport:
    """Generate one `Usage: #example` QuestionnaireResponse per configured example into `examples/`."""
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[str] = []
    if config.examples.per_target <= 0:
        return await _emit_examples(
            None,
            project,
            sources=[],
            option_sets=[],
            option_set_plan=option_set_identities([], config),
            published_organisation_unit_uids=frozenset(),
            notes=notes,
            progress=progress,
        )
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets and the option sets they bind")
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        option_sets = await _fetch_example_option_sets(client, sources)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources)
        published_uids = await _fetch_published_organisation_unit_uids(client, config)
        progress.complete(f"{len(sources):,} questionnaire target(s), {len(option_sets):,} bound option set(s)")
        return await _emit_examples(
            client,
            project,
            sources=sources,
            option_sets=option_sets,
            option_set_plan=option_set_plan,
            published_organisation_unit_uids=published_uids,
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
    notes: list[str],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Read the example responses off the instance and sync one QuestionnaireResponse per example.

    The one emitter that still reads the instance during its own step: an instance-sourced
    example is a walk over `/api/dataValueSets` and `/api/tracker/events` per target, which no
    shared metadata fetch can stand in for. `client` is None only when `[generate.examples]`
    asks for no examples at all, where nothing is read and the target sweeps its directory.

    `published_organisation_unit_uids` is the registry's own selection, so an `ORGANISATION_UNIT`
    answer naming a unit the guide publishes no Location for is left unanswered rather than
    pointed at a resource no consumer can resolve.
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
    """
    config = project.config.generate
    progress = _StepAnnouncer(reporter, GENERATE_TARGET_STEPS)
    notes: list[str] = []
    progress.step(_FETCH_LABEL, "fetching the questionnaire targets and the option sets they bind")
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        option_sets = await _fetch_example_option_sets(client, sources)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources)
        root_uid = await _root_organisation_unit_uid(client)
    progress.complete(f"{len(sources):,} questionnaire target(s)")
    progress.step("load set", f"writing {_LOAD_DIRECTORY}")
    documents: list[QuestionnaireResponse] = []
    if root_uid is None:
        notes.append("the instance has no level-1 organisation unit; no load set emitted")
    else:
        synthetic = build_synthetic_responses(sources, option_sets, per_target, root_uid, datetime.now(tz=UTC).date())
        notes.extend(synthetic.notes)
        build = build_example_documents(
            sources,
            synthetic.responses,
            option_sets,
            config,
            project.config.ig.canonical,
            option_set_plan=option_set_plan,
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
        questionnaire_count=len(sources),
        notes=notes,
    )
    progress.complete(f"{len(report.written_files):,} written, {report.unchanged_count:,} unchanged")
    return report


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
    notes: list[str],
    progress: _StepAnnouncer,
) -> list[ExampleResponseIn]:
    """Collect the example responses from whichever source the project configured."""
    today = datetime.now(tz=UTC).date()
    root_uid = await _root_organisation_unit_uid(client)
    if root_uid is None:
        notes.append("the instance has no level-1 organisation unit; no examples emitted")
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
    notes: list[str],
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
        else:
            found = await _fetch_event_responses(client, source, per_target)
        if not found:
            empty_targets.append(f"{source.name} ({source.uid})")
        responses.extend(found)
    if empty_targets:
        notes.append(
            aggregate_note(
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
    """Turn one grouped data value key into the example projection, resolving its period's dates."""
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
    "tracker-event": "programStages",
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
    even on a national hierarchy, which is what lets the solo examples target apply the same
    out-of-selection guard `generate full` applies without repeating the registry's full walk.
    """
    models: list[OrganisationUnit] = await client.resources.organisation_units.list(
        fields="id",
        filters=_organisation_unit_selection_filters(config) or None,
        paging=False,
    )
    return frozenset(model.id for model in models if model.id)


def _registry_scale_notes(organisation_unit_count: int) -> list[str]:
    """Warn while generating when the registry is large enough to dominate the publisher's rendering pass."""
    instance_count = organisation_unit_count * _INSTANCES_PER_ORGANISATION_UNIT
    if instance_count < _REGISTRY_RENDER_COST_INSTANCES:
        return []
    return [
        f"{organisation_unit_count} organisation units emit {instance_count} instances. They ship as "
        "pre-built JSON so SUSHI never compiles them, but the IG publisher renders a page per resource, "
        "so they set the wall clock of `make build`. Narrow the registry with "
        "`[generate.organisation_units]` max_level or root if the build is longer than you want."
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
        notes=tally.to_notes(),
        progress=progress,
    )


def _emit_organisation_units(
    project: FhirProject,
    *,
    organisation_units: list[OrganisationUnitIn],
    attribute_codes: AttributeCodeIndex,
    notes: list[str],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the organisation-unit profiles, terminology, and registry off an already-paged hierarchy."""
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
            organisation_units, generate_config, project.config.ig.canonical, attribute_codes=attribute_codes
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
        notes.append("no organisation units matched the configured selection")
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
    notes: list[str] = []
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
        notes=notes,
        progress=progress,
    )


def _emit_pages(
    project: FhirProject,
    *,
    sources: list[QuestionnaireSourceIn],
    option_sets: list[OptionSetIn],
    organisation_units: list[OrganisationUnitIn],
    notes: list[str],
    progress: _StepAnnouncer,
) -> GenerateReport:
    """Build the narrative pages off what the other targets were built from - no second read of the instance.

    The forms are the ones the questionnaire target really writes: a form skipped for a `linkId`
    collision gets no catalog row and no intro, because the page would link an artifact the guide
    does not hold.
    """
    progress.step("pages", f"writing ig/{PAGES_BASE_SUBDIRECTORY}/{PAGES_DIRECTORY}")
    pages = PagesIn(forms=_published_sources(sources), option_sets=option_sets, organisation_units=organisation_units)
    build = build_page_artifacts(pages, project.config.generate, project.config.ig.canonical)
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
            notes=list(inputs.source_notes),
            progress=progress,
        )
        organisation_units = _emit_organisation_units(
            project,
            organisation_units=inputs.organisation_units,
            attribute_codes=inputs.attribute_codes,
            notes=list(inputs.geometry_notes),
            progress=progress,
        )
        pages = _emit_pages(
            project,
            sources=inputs.sources,
            option_sets=inputs.option_sets,
            organisation_units=inputs.organisation_units,
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
    notes: list[str] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    option_set_notes: list[str] = Field(default_factory=list)
    category_notes: list[str] = Field(default_factory=list)
    geometry_notes: list[str] = Field(default_factory=list)


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
    source_notes: list[str] = []
    option_set_notes: list[str] = []
    category_notes: list[str] = []
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
    category_models = await client.resources.categories.list(
        fields=_CATEGORY_FIELDS,
        order=["name:asc"],
        paging=False,
    )
    categories = _selected_categories([_category_input(model) for model in category_models], config, category_notes)
    organisation_units = await _fetch_organisation_units(client, config, tally, today, steps)
    steps.tick("reading the attribute-code join")
    attribute_codes = await resolve_attribute_code_index(client)
    geometry_notes = tally.to_notes()
    return LiveIgInputs(
        sources=sources,
        option_sets=option_sets,
        option_set_plan=option_set_plan,
        categories=categories,
        organisation_units=organisation_units,
        attribute_codes=attribute_codes,
        notes=[*source_notes, *option_set_notes, *category_notes, *geometry_notes],
        source_notes=source_notes,
        option_set_notes=option_set_notes,
        category_notes=category_notes,
        geometry_notes=geometry_notes,
    )


def _selected_option_sets(
    inputs: list[OptionSetIn], sources: list[QuestionnaireSourceIn], config: GenerateConfig, notes: list[str]
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
        notes.append(f"include_ids entry {uid!r} matched no option set")
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


def _option_set_closure(sources: list[QuestionnaireSourceIn], config: GenerateConfig, notes: list[str]) -> set[str]:
    """Collect the option sets the selected forms bind their data elements to, noting the additions."""
    closure = _bound_option_set_uids(sources)
    added = sorted(closure - set(config.option_sets.include_ids))
    if added:
        notes.append(
            aggregate_note(
                f"{len(added)} option sets added by the data set / event program closure",
                added,
            )
        )
    return closure


async def _fetch_questionnaire_sources(
    client: Dhis2Client, config: GenerateConfig, notes: list[str]
) -> list[QuestionnaireSourceIn]:
    """Fetch the selected data sets, event programs, and tracker program stages as the Questionnaire projection.

    An absent or empty `include_ids` selects everything the instance holds of that table's kind,
    matching the terminology targets. Data sets come first, then the programs.
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
    return sources


async def _fetch_program_sources(
    client: Dhis2Client, config: GenerateConfig, notes: list[str]
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


def _swept_program_sources(models: list[Program], notes: list[str]) -> list[QuestionnaireSourceIn]:
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
            aggregate_note(
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
    configured_ids: list[str], found_ids: set[str | None], table: str, label: str, notes: list[str]
) -> None:
    """Note the configured UIDs the instance answered nothing for, rather than dropping them silently."""
    missing = [uid for uid in configured_ids if uid not in found_ids]
    if missing:
        notes.append(
            aggregate_note(f"{len(missing)} [generate.{table}] include_ids entries matched no {label}", missing)
        )


def _data_set_source(model: DataSet, notes: list[str]) -> QuestionnaireSourceIn:
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
        notes=notes,
    )


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


def _event_program_source(model: Program, notes: list[str]) -> QuestionnaireSourceIn:
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


def _tracker_program_sources(model: Program, notes: list[str]) -> list[QuestionnaireSourceIn]:
    """Map a program with registration onto one Questionnaire source per stage, in the program's stage order.

    A tracker program is a sequence of visits rather than a single form, so each stage is its own
    data-capture form and carries the program as the context its name, its grouping identifier,
    and its file path are built from.
    """
    uid = model.id or ""
    name = model.name or uid
    program_type = _program_type(model)
    if program_type != _TRACKER_PROGRAM_TYPE:
        raise UnsupportedProgramError(
            f"program {name!r} ({uid}) has programType {program_type}; a WITHOUT_REGISTRATION program is "
            "selected under [generate.event_programs]"
        )
    program = ProgramContextIn(uid=uid, name=name)
    sources: list[QuestionnaireSourceIn] = []
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
    "tracker-event": "tracker program stage",
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
    notes: list[str],
    period_type: str | None = None,
    program: ProgramContextIn | None = None,
) -> QuestionnaireSourceIn:
    """Split one form's data elements into its sections plus whatever the sections leave out."""
    sections = _questionnaire_sections(raw_sections, items)
    sectioned_ids = {item.uid for section in sections for item in section.items}
    flat_items = [item for item in items if item.uid not in sectioned_ids]
    if sections and flat_items:
        notes.append(
            aggregate_note(
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
        is_default=bool(raw.get("isDefault")),
        option_combos=_option_combo_inputs(raw.get("categoryOptionCombos")),
    )


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
    """
    if not isinstance(raw_attribute_values, list):
        return []
    attribute_values: list[AttributeValueIn] = []
    for raw in raw_attribute_values:
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

    def to_notes(self) -> list[str]:
        """Roll the tally up into one aggregate note per noteworthy geometry outcome."""
        notes: list[str] = []
        if self.other_geometry_units:
            type_names = ", ".join(sorted(self.other_geometry_types))
            notes.append(
                aggregate_note(
                    f"{len(self.other_geometry_units)} organisation units have {type_names} geometry; embedded "
                    "without position",
                    self.other_geometry_units,
                )
            )
        if self.malformed_units:
            notes.append(
                aggregate_note(
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
