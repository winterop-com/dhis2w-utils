"""Service layer for the `fhir` plugin - project scaffolding and FSH generation (CLI + MCP share it)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile, resolve
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir import (
    FhirProject,
    FhirValidationReport,
    FshArtifact,
    GenerateAllReport,
    GenerateConfig,
    GenerateReport,
    InitOptions,
    NoFhirProjectError,
    OptionInput,
    OptionSetInput,
    OrgUnitInput,
    ScaffoldReport,
    build_code_validation,
    build_option_set_artifacts,
    build_org_unit_instances,
    build_org_unit_level_terminology,
    build_org_unit_profiles,
    build_org_unit_terminology,
    build_scaffold_files,
    clean_generated_files,
    load_project,
    write_artifacts,
)

if TYPE_CHECKING:
    from dhis2w_client.generated.v42.schemas import OptionSet, OrganisationUnit

_STREAM_PAGE_SIZE = 500
_ORG_UNIT_FIELDS = "id,code,name,shortName,level,path,parent[id],geometry,contactPerson,email,phoneNumber"


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


async def validate_codes(profile: Profile, config: GenerateConfig) -> FhirValidationReport:
    """Check the instance's option-set codes and names for FHIR-safety without writing anything."""
    async with open_client(profile) as client:
        models = await client.resources.option_sets.list(
            fields="id,code,name,options[id,code,name,sortOrder]",
            order=["name:asc"],
            paging=False,
        )
    return build_code_validation([_option_set_input(model) for model in models], config)


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


async def generate_option_sets(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate one CodeSystem/ValueSet FSH file per configured option set into `terminology/`."""
    config = project.config.generate
    async with open_client(profile) as client:
        models = await client.resources.option_sets.list(
            fields="id,code,name,options[id,code,name,sortOrder]",
            order=["name:asc"],
            paging=False,
        )
    inputs = [_option_set_input(model) for model in models]
    notes: list[str] = []
    inputs = _apply_option_set_selection(inputs, project, notes)
    build = build_option_set_artifacts(inputs, config)
    deleted = clean_generated_files(project.fsh_directory / "terminology")
    written = write_artifacts(project.fsh_directory, build.artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_directory="terminology",
        deleted_files=deleted,
        written_files=written,
        option_set_count=len(inputs),
        notes=[*notes, *build.notes],
    )


async def generate_org_units(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate Organization/Location instances (and optional terminology) into `organization/`."""
    selection = project.config.generate.org_units
    filters: list[str] = []
    if selection.root is not None:
        filters.append(f"path:like:{selection.root}")
    if selection.max_level is not None:
        filters.append(f"level:le:{selection.max_level}")
    notes: list[str] = []
    org_units: list[OrgUnitInput] = []
    non_point_geometries = 0
    async with open_client(profile) as client:
        page = 1
        while True:
            models = await client.resources.organisation_units.list(
                fields=_ORG_UNIT_FIELDS,
                filters=filters or None,
                order=["path:asc"],
                page=page,
                page_size=_STREAM_PAGE_SIZE,
                paging=True,
            )
            for model in models:
                mapped = _org_unit_input(model, notes)
                if mapped is None:
                    continue
                if mapped.latitude is None and model.geometry is not None:
                    non_point_geometries += 1
                org_units.append(mapped)
            if len(models) < _STREAM_PAGE_SIZE:
                break
            page += 1
    if non_point_geometries:
        notes.append(f"{non_point_geometries} organisation units have non-Point geometry; no Location emitted")
    generate_config = project.config.generate
    artifacts: list[FshArtifact] = [build_org_unit_profiles(generate_config)]
    if org_units:
        artifacts.append(build_org_unit_level_terminology([org_unit.level for org_unit in org_units], generate_config))
        instances = build_org_unit_instances(org_units, generate_config)
        artifacts.extend(instances.artifacts)
        notes.extend(instances.notes)
        if selection.terminology:
            artifacts.append(build_org_unit_terminology(org_units, generate_config))
    else:
        notes.append("no organisation units matched the configured selection")
    deleted = clean_generated_files(project.fsh_directory / "organization")
    written = write_artifacts(project.fsh_directory, artifacts)
    return GenerateReport(
        project_root=project.project_root,
        target_directory="organization",
        deleted_files=deleted,
        written_files=written,
        org_unit_count=len(org_units),
        location_count=sum(1 for org_unit in org_units if org_unit.latitude is not None),
        notes=notes,
    )


async def generate_all(profile: Profile, project: FhirProject) -> GenerateAllReport:
    """Generate option-set terminology and organisation-unit instances in one run."""
    option_sets = await generate_option_sets(profile, project)
    org_units = await generate_org_units(profile, project)
    return GenerateAllReport(option_sets=option_sets, org_units=org_units)


def _apply_option_set_selection(
    inputs: list[OptionSetInput], project: FhirProject, notes: list[str]
) -> list[OptionSetInput]:
    """Filter option sets by the configured include lists, noting entries that matched nothing."""
    selection = project.config.generate.option_sets
    if not selection.include_names and not selection.include_ids:
        return inputs
    wanted_names = set(selection.include_names)
    wanted_ids = set(selection.include_ids)
    selected = [item for item in inputs if item.name in wanted_names or item.uid in wanted_ids]
    for name in sorted(wanted_names - {item.name for item in selected}):
        notes.append(f"include_names entry {name!r} matched no option set")
    for uid in sorted(wanted_ids - {item.uid for item in selected}):
        notes.append(f"include_ids entry {uid!r} matched no option set")
    return selected


def _option_set_input(model: OptionSet) -> OptionSetInput:
    """Map a generated OptionSet (with inline option dicts) into the emission input model."""
    options = [
        OptionInput(
            uid=str(raw["id"]),
            code=raw.get("code"),
            name=str(raw.get("name") or raw["id"]),
            sort_order=raw.get("sortOrder"),
        )
        for raw in model.options or []
        if isinstance(raw, dict) and raw.get("id")
    ]
    uid = model.id or ""
    return OptionSetInput(uid=uid, code=model.code, name=model.name or uid, options=options)


def _org_unit_input(model: OrganisationUnit, notes: list[str]) -> OrgUnitInput | None:
    """Map a generated OrganisationUnit into the emission input model; None when it lacks a UID."""
    uid = model.id
    if not uid:
        return None
    latitude: float | None = None
    longitude: float | None = None
    geometry = model.geometry
    if isinstance(geometry, dict) and geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates")
        if isinstance(coordinates, list) and len(coordinates) == 2:
            # GeoJSON order is [longitude, latitude].
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
        else:
            notes.append(f"org unit {uid}: Point geometry has malformed coordinates; Location skipped")
    path = model.path or f"/{uid}"
    level = model.level if model.level is not None else len([part for part in path.split("/") if part])
    return OrgUnitInput(
        uid=uid,
        name=model.name or uid,
        short_name=model.shortName,
        code=model.code,
        level=level,
        path=path,
        parent_uid=model.parent.id if model.parent is not None else None,
        latitude=latitude,
        longitude=longitude,
        contact_person=model.contactPerson,
        email=model.email,
        phone_number=model.phoneNumber,
    )
