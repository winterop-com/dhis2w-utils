"""Service layer for the `fhir` plugin - project scaffolding and FSH generation (CLI + MCP share it)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile, resolve
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.config import FhirProject, GenerateConfig, NoFhirProjectError, load_project
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
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.scaffold.schemas import InitOptions, ScaffoldReport
from dhis2w_fhir.validation import build_code_validation
from dhis2w_fhir.validation.schemas import FhirValidationReport, MetadataCollectionIn, MetadataItemIn
from dhis2w_fhir.writer import FshArtifact, sync_artifacts

if TYPE_CHECKING:
    from dhis2w_client.generated.v42.schemas import OptionSet, OrganisationUnit

_STREAM_PAGE_SIZE = 500
_ORGANISATION_UNIT_FIELDS = "id,code,name,shortName,level,path,parent[id],geometry,contactPerson,email,phoneNumber"


class GenerateReport(BaseModel):
    """Outcome of one `d2w fhir generate` target."""

    project_root: Path
    target_directory: str
    deleted_files: list[str] = Field(default_factory=list)
    written_files: list[str] = Field(default_factory=list)
    unchanged_count: int = 0
    option_set_count: int = 0
    organisation_unit_count: int = 0
    position_count: int = 0
    boundary_count: int = 0
    notes: list[str] = Field(default_factory=list)


class GenerateAllReport(BaseModel):
    """Outcome of `d2w fhir generate all`."""

    option_sets: GenerateReport
    organisation_units: GenerateReport


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


async def validate_codes(profile: Profile, config: GenerateConfig) -> FhirValidationReport:
    """Check the whole instance's codes (sweep) plus the option sets in depth, without writing anything."""
    async with open_client(profile) as client:
        raw = await client.get_raw("/api/metadata", params={"fields": "id,name,code"})
        models = await client.resources.option_sets.list(
            fields="id,code,name,options[id,code,name,sortOrder]",
            order=["name:asc"],
            paging=False,
        )
    option_sets = [_option_set_input(model) for model in models]
    return build_code_validation(option_sets, _sweep_collections(raw), config)


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


async def generate_organisation_units(profile: Profile, project: FhirProject) -> GenerateReport:
    """Generate Organization/Location instances (and optional terminology) into `organization/`."""
    selection = project.config.generate.organisation_units
    filters: list[str] = []
    if selection.root is not None:
        filters.append(f"path:like:{selection.root}")
    if selection.max_level is not None:
        filters.append(f"level:le:{selection.max_level}")
    notes: list[str] = []
    organisation_units: list[OrganisationUnitIn] = []
    polygon_units: list[str] = []
    malformed_units: list[str] = []
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
                mapped = _organisation_unit_input(model, polygon_units, malformed_units)
                if mapped is not None:
                    organisation_units.append(mapped)
            if len(models) < _STREAM_PAGE_SIZE:
                break
            page += 1
    if polygon_units:
        notes.append(
            aggregate_note(
                f"{len(polygon_units)} organisation units have Polygon geometry; Location.position uses the "
                "boundary centroid",
                polygon_units,
            )
        )
    if malformed_units:
        notes.append(
            aggregate_note(
                f"{len(malformed_units)} organisation units have malformed geometry; skipped", malformed_units
            )
        )
    generate_config = project.config.generate
    artifacts: list[FshArtifact] = [build_organisation_unit_profiles(generate_config)]
    if organisation_units:
        artifacts.append(
            build_organisation_unit_level_terminology(
                [organisation_unit.level for organisation_unit in organisation_units], generate_config
            )
        )
        instances = build_organisation_unit_instances(organisation_units, generate_config)
        artifacts.extend(instances.artifacts)
        notes.extend(instances.notes)
        if selection.terminology:
            artifacts.append(build_organisation_unit_terminology(organisation_units, generate_config))
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
    """Generate option-set terminology and organisation-unit instances in one run."""
    option_sets = await generate_option_sets(profile, project)
    organisation_units = await generate_organisation_units(profile, project)
    return GenerateAllReport(option_sets=option_sets, organisation_units=organisation_units)


def _apply_option_set_selection(inputs: list[OptionSetIn], project: FhirProject, notes: list[str]) -> list[OptionSetIn]:
    """Filter option sets by the configured UID include list, noting entries that matched nothing."""
    selection = project.config.generate.option_sets
    if not selection.include_ids:
        return inputs
    wanted_ids = set(selection.include_ids)
    selected = [item for item in inputs if item.uid in wanted_ids]
    for uid in sorted(wanted_ids - {item.uid for item in selected}):
        notes.append(f"include_ids entry {uid!r} matched no option set")
    return selected


def _option_set_input(model: OptionSet) -> OptionSetIn:
    """Map a generated OptionSet (with inline option dicts) into the emitter projection."""
    options = [
        OptionIn(
            uid=str(raw["id"]),
            code=raw.get("code"),
            name=str(raw.get("name") or raw["id"]),
            sort_order=raw.get("sortOrder"),
        )
        for raw in model.options or []
        if isinstance(raw, dict) and raw.get("id")
    ]
    uid = model.id or ""
    return OptionSetIn(uid=uid, code=model.code, name=model.name or uid, options=options)


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


def _organisation_unit_input(
    model: OrganisationUnit,
    polygon_units: list[str],
    malformed_units: list[str],
) -> OrganisationUnitIn | None:
    """Map a generated OrganisationUnit into the emitter projection; None when it lacks a UID."""
    uid = model.id
    if not uid:
        return None
    label = f"{model.name or uid} ({uid})"
    position: GeoPoint | None = None
    boundary_geojson: str | None = None
    geometry = model.geometry
    if isinstance(geometry, dict):
        geometry_type = str(geometry.get("type"))
        positions: list[GeoPoint] = []
        coordinates = geometry.get("coordinates")
        _walk_positions(coordinates, positions)
        if not positions:
            malformed_units.append(label)
        elif geometry_type == "Point":
            position = positions[0]
        elif geometry_type in {"Polygon", "MultiPolygon"}:
            polygon_units.append(label)
            position = _polygon_centroid(geometry_type, coordinates, positions)
        else:
            malformed_units.append(label)
        if position is not None:
            boundary_geojson = json.dumps(geometry, separators=(",", ":"), sort_keys=True)
    latitude = position.latitude if position is not None else None
    longitude = position.longitude if position is not None else None
    path = model.path or f"/{uid}"
    level = model.level if model.level is not None else len([part for part in path.split("/") if part])
    return OrganisationUnitIn(
        uid=uid,
        name=model.name or uid,
        short_name=model.shortName,
        code=model.code,
        level=level,
        path=path,
        parent_uid=model.parent.id if model.parent is not None else None,
        latitude=latitude,
        longitude=longitude,
        boundary_geojson=boundary_geojson,
        contact_person=model.contactPerson,
        email=model.email,
        phone_number=model.phoneNumber,
    )
