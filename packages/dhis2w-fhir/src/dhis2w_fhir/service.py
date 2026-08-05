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

from dhis2w_fhir.config import FhirProject, GenerateConfig, NoFhirProjectError, load_project
from dhis2w_fhir.foundation import build_foundation_artifacts
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.period import parse_period, recent_periods
from dhis2w_fhir.resources.examples import (
    COMPLETED_STATUS,
    EXAMPLES_DIRECTORY,
    build_example_artifacts,
    build_synthetic_responses,
    response_status_code,
)
from dhis2w_fhir.resources.examples.schemas import (
    ExampleAnswerIn,
    ExampleResponseIn,
    ExampleSelection,
)
from dhis2w_fhir.resources.option_sets import (
    TERMINOLOGY_DIRECTORY,
    build_option_set_artifacts,
    option_set_identities,
)
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIdentityPlan, OptionSetIn
from dhis2w_fhir.resources.organisation_units import (
    REGISTRY_DIRECTORY,
    build_organisation_unit_instances,
    build_organisation_unit_level_terminology,
    build_organisation_unit_profiles,
    build_organisation_unit_terminology,
)
from dhis2w_fhir.resources.organisation_units.schemas import GeoPoint, OrganisationUnitIn
from dhis2w_fhir.resources.pages import (
    INTRO_SUFFIX,
    PAGES_BASE_SUBDIRECTORY,
    PAGES_DIRECTORY,
    build_page_artifacts,
)
from dhis2w_fhir.resources.pages.schemas import PagesIn
from dhis2w_fhir.resources.questionnaires import QUESTIONNAIRE_DIRECTORIES, build_questionnaire_artifacts
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    FormKind,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
)
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.scaffold.schemas import InitOptions, ScaffoldReport
from dhis2w_fhir.validation import build_code_validation
from dhis2w_fhir.validation.schemas import FhirValidationReport, MetadataCollectionIn, MetadataItemIn
from dhis2w_fhir.writer import FshArtifact, JsonArtifact, sync_artifacts, sync_json_artifacts

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client
    from dhis2w_client.generated.v42.schemas import DataSet, OptionSet, OrganisationUnit, Program

_STREAM_PAGE_SIZE = 500
_TRANSLATION_FIELDS = "translations[locale,property,value]"
_OPTION_SET_FIELDS = (
    f"id,code,name,description,{_TRANSLATION_FIELDS},options[id,code,name,sortOrder,{_TRANSLATION_FIELDS}]"
)

#: The option-set projection the identity plan is assigned from - a slug needs the UID and the name alone.
_OPTION_SET_IDENTITY_FIELDS = "id,name"
_ORGANISATION_UNIT_FIELDS = (
    "id,code,name,shortName,description,level,path,parent[id],geometry,contactPerson,email,phoneNumber,openingDate,"
    f"closedDate,{_TRANSLATION_FIELDS}"
)
_QUESTIONNAIRE_DATA_ELEMENT_FIELDS = (
    "dataElement[id,name,formName,valueType,domainType,optionSet[id],"
    "categoryCombo[id,name,isDefault,categoryOptionCombos[id,name,code]]]"
)
_DATA_SET_FIELDS = (
    "id,name,code,description,periodType,sections[id,name,dataElements[id]],"
    "compulsoryDataElementOperands[dataElement[id],categoryOptionCombo[id]],"
    f"dataSetElements[{_QUESTIONNAIRE_DATA_ELEMENT_FIELDS}]"
)
_EVENT_PROGRAM_FIELDS = (
    "id,name,code,description,programType,programStages[id,name,programStageSections[id,name,dataElements[id]],"
    f"programStageDataElements[compulsory,{_QUESTIONNAIRE_DATA_ELEMENT_FIELDS}]]"
)

#: The only DHIS2 program type the questionnaire target maps today.
_EVENT_PROGRAM_TYPE = "WITHOUT_REGISTRATION"

#: The tracker-event projection one example response is built from.
_EXAMPLE_EVENT_FIELDS = "event,orgUnit,occurredAt,status,dataValues[dataElement,value]"

#: How many candidate periods the data-value discovery tries before giving a data set up.
_EXAMPLE_PERIOD_ATTEMPTS = 6

#: The envelope keys the tracker events endpoint has answered under.
_EVENT_ENVELOPE_KEYS = ("instances", "events")


class GenerateReport(BaseModel):
    """Outcome of one `d2w fhir generate` target."""

    project_root: Path
    target_directory: str
    target_base: str = "ig/input/fsh"
    deleted_files: list[str] = Field(default_factory=list)
    written_files: list[str] = Field(default_factory=list)
    unchanged_count: int = 0
    option_set_count: int = 0
    questionnaire_count: int = 0
    organisation_unit_count: int = 0
    position_count: int = 0
    boundary_count: int = 0
    example_count: int = 0
    page_count: int = 0
    intro_count: int = 0
    notes: list[str] = Field(default_factory=list)


class GenerateAllReport(BaseModel):
    """Outcome of `d2w fhir generate all`."""

    foundation: GenerateReport
    option_sets: GenerateReport
    questionnaires: GenerateReport
    examples: GenerateReport
    organisation_units: GenerateReport
    pages: GenerateReport


class UnsupportedProgramError(ValueError):
    """Raised when a configured event program is a shape the questionnaire target does not map."""


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
    profile: Profile, config: GenerateConfig, code_source: str | None = None
) -> FhirValidationReport:
    """Check the whole instance's codes (sweep) plus the option sets in depth, without writing anything."""
    effective_source = resolve_code_source(config, code_source)
    async with open_client(profile) as client:
        raw = await client.get_raw("/api/metadata", params={"fields": "id,name,code", "defaults": "EXCLUDE"})
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
    option_sets = [_option_set_input(model) for model in models]
    return build_code_validation(option_sets, _sweep_collections(raw), config, effective_source)


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


async def generate_foundation(project: FhirProject) -> GenerateReport:
    """Generate the instance-independent `foundation/` artifacts: DHIS2 identifier aliases and D2Period."""
    artifacts = build_foundation_artifacts(project.config.generate, ig_status=project.config.ig.status)
    sync = sync_artifacts(project.fsh_directory, "foundation", artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_directory="foundation",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
    )


async def generate_option_sets(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate one pre-built CodeSystem and ValueSet document per configured option set into `terminology/`."""
    config = project.config.generate
    notes: list[str] = []
    async with open_client(profile) as client:
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        sources = await _closure_sources(client, config)
    inputs = _selected_option_sets([_option_set_input(model) for model in models], sources, config, notes)
    build = build_option_set_artifacts(inputs, config, project.config.ig.canonical, ig_status=project.config.ig.status)
    sync = sync_json_artifacts(project.resources_directory, TERMINOLOGY_DIRECTORY, build.artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_base="ig/input",
        target_directory=f"resources/{TERMINOLOGY_DIRECTORY}",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        option_set_count=len(inputs),
        notes=[*notes, *build.notes],
    )


async def generate_questionnaires(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate one Questionnaire FSH file per selected data set / event program, split across three directories."""
    config = project.config.generate
    notes: list[str] = []
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        option_set_plan = await _fetch_option_set_identity_plan(client, config, sources)
    build = build_questionnaire_artifacts(
        sources,
        config,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
        option_set_plan=option_set_plan,
    )
    syncs = [
        sync_artifacts(project.fsh_directory, directory, _artifacts_under(build.artifacts, directory))
        for directory in QUESTIONNAIRE_DIRECTORIES
    ]
    return GenerateReport(
        project_root=project.project_root,
        target_directory=", ".join(QUESTIONNAIRE_DIRECTORIES),
        deleted_files=[name for sync in syncs for name in sync.deleted],
        written_files=[path for sync in syncs for path in sync.written],
        unchanged_count=sum(len(sync.unchanged) for sync in syncs),
        questionnaire_count=len(sources),
        notes=[*notes, *build.notes],
    )


async def generate_examples(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate one `Usage: #example` QuestionnaireResponse per configured example into `examples/`."""
    config = project.config.generate
    selection = config.examples
    notes: list[str] = []
    artifacts: list[FshArtifact] = []
    example_count = 0
    if selection.per_target > 0:
        async with open_client(profile) as client:
            sources = await _fetch_questionnaire_sources(client, config, notes)
            option_sets = await _fetch_example_option_sets(client, sources)
            option_set_plan = await _fetch_option_set_identity_plan(client, config, sources)
            responses = await _example_responses(client, sources, option_sets, selection, notes)
        build = build_example_artifacts(
            sources,
            responses,
            option_sets,
            config,
            project.config.ig.canonical,
            option_set_plan=option_set_plan,
        )
        artifacts = build.artifacts
        notes.extend(build.notes)
        example_count = len(build.artifacts)
    sync = sync_artifacts(project.fsh_directory, EXAMPLES_DIRECTORY, artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_directory=EXAMPLES_DIRECTORY,
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        example_count=example_count,
        notes=notes,
    )


async def _example_responses(
    client: Dhis2Client,
    sources: list[QuestionnaireSourceIn],
    option_sets: list[OptionSetIn],
    selection: ExampleSelection,
    notes: list[str],
) -> list[ExampleResponseIn]:
    """Collect the example responses from whichever source the project configured."""
    today = datetime.now(tz=UTC).date()
    root_uid = await _root_organisation_unit_uid(client)
    if root_uid is None:
        notes.append("the instance has no level-1 organisation unit; no examples emitted")
        return []
    if selection.source == "instance":
        return await _fetch_instance_responses(client, sources, selection.per_target, root_uid, notes)
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
) -> list[ExampleResponseIn]:
    """Read example responses off the instance: data value sets for data sets, events for programs."""
    today = datetime.now(tz=UTC).date()
    responses: list[ExampleResponseIn] = []
    empty_targets: list[str] = []
    for source in sorted(sources, key=lambda item: (item.name, item.uid)):
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
    """Read the most recent events of one event program as example responses."""
    raw = await client.get_raw(
        "/api/tracker/events",
        params={
            "program": source.uid,
            "pageSize": per_target,
            "order": "occurredAt:desc",
            "fields": _EXAMPLE_EVENT_FIELDS,
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
                kind="event",
                organisation_unit_uid=organisation_unit_uid,
                status_code=response_status_code(_optional_text(entry.get("status"))),
                authored=_optional_text(entry.get("occurredAt")),
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


def _artifacts_under(artifacts: list[FshArtifact], directory: str) -> list[FshArtifact]:
    """The artifacts one sync directory owns - each directory is swept against its own files alone."""
    return [artifact for artifact in artifacts if artifact.relative_path.startswith(f"{directory}/")]


async def _fetch_organisation_units(
    client: Dhis2Client, config: GenerateConfig, tally: GeometryTally, today: date
) -> list[OrganisationUnitIn]:
    """Page the configured slice of the DHIS2 hierarchy into the emitter projection, ordered by path."""
    selection = config.organisation_units
    filters: list[str] = []
    if selection.root is not None:
        filters.append(f"path:like:{selection.root}")
    if selection.max_level is not None:
        filters.append(f"level:le:{selection.max_level}")
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
        page += 1
    return organisation_units


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


async def generate_organisation_units(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate the profiles and terminology into `organization/`, and the instance registry into `registry/`."""
    selection = project.config.generate.organisation_units
    tally = GeometryTally()
    today = datetime.now(tz=UTC).date()
    async with open_client(profile) as client:
        organisation_units = await _fetch_organisation_units(client, project.config.generate, tally, today)
    notes: list[str] = tally.to_notes()
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
        instances = build_organisation_unit_instances(organisation_units, generate_config, project.config.ig.canonical)
        registry = instances.artifacts
        notes.extend(instances.notes)
        if selection.terminology:
            artifacts.append(
                build_organisation_unit_terminology(organisation_units, generate_config, ig_status=ig_status)
            )
    else:
        notes.append("no organisation units matched the configured selection")
    notes.extend(_registry_scale_notes(len(organisation_units)))
    sync = sync_artifacts(project.fsh_directory, "organization", artifacts)
    registry_sync = sync_json_artifacts(project.resources_directory, REGISTRY_DIRECTORY, registry)
    return GenerateReport(
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


async def generate_pages(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate the narrative site pages and the per-artifact intros into `ig/input/pagecontent/`."""
    config = project.config.generate
    notes: list[str] = []
    tally = GeometryTally()
    today = datetime.now(tz=UTC).date()
    async with open_client(profile) as client:
        sources = await _fetch_questionnaire_sources(client, config, notes)
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        organisation_units = await _fetch_organisation_units(client, config, tally, today)
    pages = PagesIn(
        forms=sources,
        option_sets=_selected_option_sets([_option_set_input(model) for model in models], sources, config, notes),
        organisation_units=organisation_units,
    )
    build = build_page_artifacts(pages, config, project.config.ig.canonical)
    sync = sync_artifacts(project.ig_directory / PAGES_BASE_SUBDIRECTORY, PAGES_DIRECTORY, build.artifacts)
    intro_count = sum(1 for artifact in build.artifacts if artifact.relative_path.endswith(INTRO_SUFFIX))
    return GenerateReport(
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


async def generate_all(profile: Profile, project: FhirProject) -> GenerateAllReport:
    """Generate the foundation, terminology, questionnaires, examples, org-unit instances, and the pages."""
    foundation = await generate_foundation(project)
    option_sets = await generate_option_sets(profile, project)
    questionnaires = await generate_questionnaires(profile, project)
    examples = await generate_examples(profile, project)
    organisation_units = await generate_organisation_units(profile, project)
    pages = await generate_pages(profile, project)
    return GenerateAllReport(
        foundation=foundation,
        option_sets=option_sets,
        questionnaires=questionnaires,
        examples=examples,
        organisation_units=organisation_units,
        pages=pages,
    )


def _selected_option_sets(
    inputs: list[OptionSetIn], sources: list[QuestionnaireSourceIn], config: GenerateConfig, notes: list[str]
) -> list[OptionSetIn]:
    """Filter option sets by the configured UIDs plus the target closure, noting entries that matched nothing."""
    selection = config.option_sets
    if not selection.include_ids:
        return inputs
    configured_ids = set(selection.include_ids)
    wanted_ids = configured_ids | _option_set_closure(sources, config, notes)
    selected = [item for item in inputs if item.uid in wanted_ids]
    selected_ids = {item.uid for item in selected}
    for uid in sorted(configured_ids - selected_ids):
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


async def _closure_sources(client: Dhis2Client, config: GenerateConfig) -> list[QuestionnaireSourceIn]:
    """Fetch the questionnaire targets the option-set closure reads, or nothing when the closure is a no-op.

    An empty `[generate.option_sets] include_ids` already means every option set, so the
    closure is a no-op there and the targets are not fetched a second time.
    """
    if not config.option_sets.include_ids:
        return []
    return await _fetch_questionnaire_sources(client, config, [])


def _option_set_closure(sources: list[QuestionnaireSourceIn], config: GenerateConfig, notes: list[str]) -> set[str]:
    """Collect the option sets the selected data sets and event programs bind their data elements to."""
    closure = {
        item.option_set_uid for source in sources for item in _source_items(source) if item.option_set_uid is not None
    }
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
    """Fetch the selected data sets and event programs as the Questionnaire projection.

    An absent or empty `include_ids` selects everything the instance holds, matching the
    terminology targets. The whole-instance sweep auto-selects the single-stage event
    programs and notes the shapes it skips; an explicit list refuses them by name instead.
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
    event_program_ids = config.event_programs.include_ids
    programs = await client.resources.programs.list(
        fields=_EVENT_PROGRAM_FIELDS,
        filters=[_uid_filter(event_program_ids)] if event_program_ids else None,
        order=["name:asc"],
        paging=False,
    )
    if event_program_ids:
        sources.extend(_event_program_source(model, notes) for model in programs)
        _note_unmatched(event_program_ids, {model.id for model in programs}, "event_programs", "event program", notes)
    else:
        sources.extend(_event_program_source(model, notes) for model in _single_stage_event_programs(programs, notes))
    return sources


def _single_stage_event_programs(models: list[Program], notes: list[str]) -> list[Program]:
    """Keep the single-stage event programs of a whole-instance sweep, noting the shapes it skips."""
    supported: list[Program] = []
    tracker: list[str] = []
    multi_stage: list[str] = []
    for model in models:
        label = f"{model.name or model.id or ''} ({model.id or ''})"
        if _program_type(model) != _EVENT_PROGRAM_TYPE:
            tracker.append(label)
        elif len(_program_stages(model)) > 1:
            multi_stage.append(label)
        else:
            supported.append(model)
    if tracker:
        notes.append(
            aggregate_note(f"{len(tracker)} tracker programs skipped (tracker generation not implemented)", tracker)
        )
    if multi_stage:
        notes.append(
            aggregate_note(
                f"{len(multi_stage)} multi-stage event programs skipped "
                "(only single-stage event programs are implemented)",
                multi_stage,
            )
        )
    return supported


def _program_type(model: Program) -> str:
    """The program's live `programType`, or `unknown` when the instance sent none."""
    return str(model.programType) if model.programType is not None else "unknown"


def _program_stages(model: Program) -> list[dict[str, object]]:
    """The program's stages as the wire sends them."""
    return [stage for stage in model.programStages or [] if isinstance(stage, dict)]


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
    """Map a generated Program into the Questionnaire projection, refusing every shape but a single-stage event."""
    uid = model.id or ""
    name = model.name or uid
    program_type = _program_type(model)
    if program_type != _EVENT_PROGRAM_TYPE:
        raise UnsupportedProgramError(
            f"program {name!r} ({uid}) has programType {program_type}; tracker programs are not implemented yet"
        )
    stages = _program_stages(model)
    if len(stages) > 1:
        raise UnsupportedProgramError(
            f"event program {name!r} ({uid}) has {len(stages)} program stages; "
            "only single-stage event programs are implemented"
        )
    items: list[QuestionnaireItemIn] = []
    raw_sections: object = None
    if stages:
        stage = stages[0]
        raw_elements = stage.get("programStageDataElements")
        for entry in raw_elements if isinstance(raw_elements, list) else []:
            if not isinstance(entry, dict):
                continue
            reference = entry.get("dataElement")
            if not isinstance(reference, dict) or not reference.get("id"):
                continue
            items.append(_questionnaire_item(reference, compulsory=bool(entry.get("compulsory"))))
        raw_sections = stage.get("programStageSections")
    return _questionnaire_source(
        uid=uid,
        name=name,
        code=model.code,
        description=model.description,
        kind="event",
        items=items,
        raw_sections=raw_sections,
        notes=notes,
    )


def _questionnaire_source(
    uid: str,
    name: str,
    code: str | None,
    description: str | None,
    kind: FormKind,
    items: list[QuestionnaireItemIn],
    raw_sections: object,
    notes: list[str],
    period_type: str | None = None,
) -> QuestionnaireSourceIn:
    """Split one form's data elements into its sections plus whatever the sections leave out."""
    sections = _questionnaire_sections(raw_sections, items)
    sectioned_ids = {item.uid for section in sections for item in section.items}
    flat_items = [item for item in items if item.uid not in sectioned_ids]
    if sections and flat_items:
        label = "data set" if kind == "aggregate" else "event program"
        notes.append(
            aggregate_note(
                f"{label} {name!r} ({uid}) has {len(flat_items)} data elements outside its sections; "
                "emitted after the sectioned ones",
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
        sections=sections,
        flat_items=flat_items,
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
    )
