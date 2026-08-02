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
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.resources.organisation_units import (
    build_organisation_unit_instances,
    build_organisation_unit_level_terminology,
    build_organisation_unit_profiles,
    build_organisation_unit_terminology,
)
from dhis2w_fhir.resources.organisation_units.schemas import GeoPoint, OrganisationUnitIn
from dhis2w_fhir.resources.questionnaires import build_questionnaire_artifacts
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
from dhis2w_fhir.writer import FshArtifact, sync_artifacts

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client
    from dhis2w_client.generated.v42.schemas import DataSet, OptionSet, OrganisationUnit, Program

_STREAM_PAGE_SIZE = 500
_TRANSLATION_FIELDS = "translations[locale,property,value]"
_OPTION_SET_FIELDS = f"id,code,name,{_TRANSLATION_FIELDS},options[id,code,name,sortOrder,{_TRANSLATION_FIELDS}]"
_ORGANISATION_UNIT_FIELDS = (
    "id,code,name,shortName,level,path,parent[id],geometry,contactPerson,email,phoneNumber,openingDate,closedDate,"
    f"{_TRANSLATION_FIELDS}"
)
_QUESTIONNAIRE_DATA_ELEMENT_FIELDS = (
    "dataElement[id,name,formName,valueType,optionSet[id],"
    "categoryCombo[id,name,isDefault,categoryOptionCombos[id,name,code]]]"
)
_DATA_SET_FIELDS = (
    f"id,name,code,sections[id,name,dataElements[id]],dataSetElements[{_QUESTIONNAIRE_DATA_ELEMENT_FIELDS}]"
)
_EVENT_PROGRAM_FIELDS = (
    "id,name,code,programType,programStages[id,name,programStageSections[id,name,dataElements[id]],"
    f"programStageDataElements[compulsory,{_QUESTIONNAIRE_DATA_ELEMENT_FIELDS}]]"
)

#: The only DHIS2 program type the questionnaire target maps today.
_EVENT_PROGRAM_TYPE = "WITHOUT_REGISTRATION"


class GenerateReport(BaseModel):
    """Outcome of one `d2w fhir generate` target."""

    project_root: Path
    target_directory: str
    deleted_files: list[str] = Field(default_factory=list)
    written_files: list[str] = Field(default_factory=list)
    unchanged_count: int = 0
    option_set_count: int = 0
    questionnaire_count: int = 0
    organisation_unit_count: int = 0
    position_count: int = 0
    boundary_count: int = 0
    notes: list[str] = Field(default_factory=list)


class GenerateAllReport(BaseModel):
    """Outcome of `d2w fhir generate all`."""

    foundation: GenerateReport
    option_sets: GenerateReport
    questionnaires: GenerateReport
    organisation_units: GenerateReport


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
    artifacts = build_foundation_artifacts(project.config.generate, experimental=project.config.ig.experimental)
    sync = sync_artifacts(project.fsh_directory, "foundation", artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_directory="foundation",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
    )


async def generate_option_sets(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate one CodeSystem/ValueSet FSH file per configured option set into `terminology/`."""
    config = project.config.generate
    notes: list[str] = []
    async with open_client(profile) as client:
        models = await client.resources.option_sets.list(
            fields=_OPTION_SET_FIELDS,
            order=["name:asc"],
            paging=False,
        )
        closure = await _option_set_closure(client, config, notes)
    inputs = [_option_set_input(model) for model in models]
    inputs = _apply_option_set_selection(inputs, config, closure, notes)
    build = build_option_set_artifacts(inputs, config, experimental=project.config.ig.experimental)
    sync = sync_artifacts(project.fsh_directory, "terminology", build.artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_directory="terminology",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        option_set_count=len(inputs),
        notes=[*notes, *build.notes],
    )


async def generate_questionnaires(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate one Questionnaire FSH file per configured data set / event program into `questionnaires/`."""
    config = project.config.generate
    notes: list[str] = []
    sources: list[QuestionnaireSourceIn] = []
    if config.data_sets.include_ids or config.event_programs.include_ids:
        async with open_client(profile) as client:
            sources = await _fetch_questionnaire_sources(client, config, notes)
    build = build_questionnaire_artifacts(
        sources, config, project.config.ig.canonical, experimental=project.config.ig.experimental
    )
    sync = sync_artifacts(project.fsh_directory, "questionnaires", build.artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_directory="questionnaires",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        questionnaire_count=len(sources),
        notes=[*notes, *build.notes],
    )


async def generate_organisation_units(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate Organization/Location instances (and optional terminology) into `organization/`."""
    selection = project.config.generate.organisation_units
    filters: list[str] = []
    if selection.root is not None:
        filters.append(f"path:like:{selection.root}")
    if selection.max_level is not None:
        filters.append(f"level:le:{selection.max_level}")
    organisation_units: list[OrganisationUnitIn] = []
    tally = GeometryTally()
    today = datetime.now(tz=UTC).date()
    async with open_client(profile) as client:
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
    notes: list[str] = tally.to_notes()
    generate_config = project.config.generate
    experimental = project.config.ig.experimental
    artifacts: list[FshArtifact] = [build_organisation_unit_profiles(generate_config, experimental=experimental)]
    if organisation_units:
        artifacts.append(
            build_organisation_unit_level_terminology(
                [organisation_unit.level for organisation_unit in organisation_units],
                generate_config,
                experimental=experimental,
            )
        )
        instances = build_organisation_unit_instances(organisation_units, generate_config)
        artifacts.extend(instances.artifacts)
        notes.extend(instances.notes)
        if selection.terminology:
            artifacts.append(
                build_organisation_unit_terminology(organisation_units, generate_config, experimental=experimental)
            )
    else:
        notes.append("no organisation units matched the configured selection")
    sync = sync_artifacts(project.fsh_directory, "organization", artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_directory="organization",
        deleted_files=sync.deleted,
        written_files=sync.written,
        unchanged_count=len(sync.unchanged),
        organisation_unit_count=len(organisation_units),
        position_count=sum(1 for organisation_unit in organisation_units if organisation_unit.latitude is not None),
        boundary_count=sum(
            1 for organisation_unit in organisation_units if organisation_unit.boundary_geojson is not None
        ),
        notes=notes,
    )


async def generate_all(profile: Profile, project: FhirProject) -> GenerateAllReport:
    """Generate the foundation, option-set terminology, questionnaires, and organisation-unit instances in one run."""
    foundation = await generate_foundation(project)
    option_sets = await generate_option_sets(profile, project)
    questionnaires = await generate_questionnaires(profile, project)
    organisation_units = await generate_organisation_units(profile, project)
    return GenerateAllReport(
        foundation=foundation,
        option_sets=option_sets,
        questionnaires=questionnaires,
        organisation_units=organisation_units,
    )


def _apply_option_set_selection(
    inputs: list[OptionSetIn], config: GenerateConfig, closure: set[str], notes: list[str]
) -> list[OptionSetIn]:
    """Filter option sets by the configured UIDs plus the target closure, noting entries that matched nothing."""
    selection = config.option_sets
    if not selection.include_ids:
        return inputs
    configured_ids = set(selection.include_ids)
    wanted_ids = configured_ids | closure
    selected = [item for item in inputs if item.uid in wanted_ids]
    selected_ids = {item.uid for item in selected}
    for uid in sorted(configured_ids - selected_ids):
        notes.append(f"include_ids entry {uid!r} matched no option set")
    return selected


async def _option_set_closure(client: Dhis2Client, config: GenerateConfig, notes: list[str]) -> set[str]:
    """Collect the option sets the configured data sets and event programs bind their data elements to.

    An empty `[generate.option_sets] include_ids` already means every option set, so the
    closure is a no-op there and the targets are not fetched a second time.
    """
    if not config.option_sets.include_ids:
        return set()
    if not (config.data_sets.include_ids or config.event_programs.include_ids):
        return set()
    sources = await _fetch_questionnaire_sources(client, config, [])
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
    """Fetch every configured data set and event program as the Questionnaire projection."""
    sources: list[QuestionnaireSourceIn] = []
    data_set_ids = config.data_sets.include_ids
    if data_set_ids:
        data_sets = await client.resources.data_sets.list(
            fields=_DATA_SET_FIELDS,
            filters=[_uid_filter(data_set_ids)],
            order=["name:asc"],
            paging=False,
        )
        sources.extend(_data_set_source(model, notes) for model in data_sets)
        _note_unmatched(data_set_ids, {model.id for model in data_sets}, "data_sets", "data set", notes)
    event_program_ids = config.event_programs.include_ids
    if event_program_ids:
        programs = await client.resources.programs.list(
            fields=_EVENT_PROGRAM_FIELDS,
            filters=[_uid_filter(event_program_ids)],
            order=["name:asc"],
            paging=False,
        )
        sources.extend(_event_program_source(model, notes) for model in programs)
        _note_unmatched(event_program_ids, {model.id for model in programs}, "event_programs", "event program", notes)
    return sources


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
    """Map a generated DataSet into the Questionnaire projection, joining sections to their data elements."""
    uid = model.id or ""
    items: list[QuestionnaireItemIn] = []
    for element in model.dataSetElements or []:
        reference = element.dataElement
        if reference is None or not reference.id:
            continue
        items.append(_questionnaire_item(reference.model_dump(), compulsory=False))
    return _questionnaire_source(
        uid=uid,
        name=model.name or uid,
        code=model.code,
        kind="aggregate",
        items=items,
        raw_sections=model.sections,
        notes=notes,
    )


def _event_program_source(model: Program, notes: list[str]) -> QuestionnaireSourceIn:
    """Map a generated Program into the Questionnaire projection, refusing every shape but a single-stage event."""
    uid = model.id or ""
    name = model.name or uid
    program_type = str(model.programType) if model.programType is not None else "unknown"
    if program_type != _EVENT_PROGRAM_TYPE:
        raise UnsupportedProgramError(
            f"program {name!r} ({uid}) has programType {program_type}; tracker programs are not implemented yet"
        )
    stages = [stage for stage in model.programStages or [] if isinstance(stage, dict)]
    if len(stages) > 1:
        raise UnsupportedProgramError(
            f"event program {name!r} ({uid}) has {len(stages)} program stages; "
            "only single-stage event programs are implemented"
        )
    items: list[QuestionnaireItemIn] = []
    raw_sections: object = None
    if stages:
        stage = stages[0]
        for entry in stage.get("programStageDataElements") or []:
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
        kind="event",
        items=items,
        raw_sections=raw_sections,
        notes=notes,
    )


def _questionnaire_source(
    uid: str,
    name: str,
    code: str | None,
    kind: FormKind,
    items: list[QuestionnaireItemIn],
    raw_sections: object,
    notes: list[str],
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
    return QuestionnaireSourceIn(uid=uid, name=name, code=code, kind=kind, sections=sections, flat_items=flat_items)


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
    raw_combos = raw.get("categoryOptionCombos")
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
    return CategoryComboIn(
        uid=uid,
        name=_optional_text(raw.get("name")) or uid,
        is_default=bool(raw.get("isDefault")),
        option_combos=option_combos,
    )


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
