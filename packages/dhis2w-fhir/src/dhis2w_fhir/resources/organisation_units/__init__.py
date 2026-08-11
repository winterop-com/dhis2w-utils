"""Emission for DHIS2 organisation units: FSH profiles and terminology, plus the pre-built JSON registry.

Point geometry lands in `Location.position`; Polygon/MultiPolygon geometry
contributes its area-weighted centroid; every other geometry type is embedded
without a position. Every unit with usable geometry carries the full GeoJSON
Feature through the standard `location-boundary-geojson` extension. An
optional toggle emits the whole selection as a CodeSystem/ValueSet with
`level`, `parent`, and `dhis2-code` concept properties.

Both terminology pairs have a JSON twin in `documents.py` beside their FSH
emitter, rendering the prose and the property declarations `schemas.py` states
once, so a server running without a compiled guide serves the level vocabulary
every published Location codes its level from.
"""

from __future__ import annotations

from dhis2w_fhir.resources.organisation_units.documents import (
    OrganisationUnitTerminologyBuild,
    build_organisation_unit_level_terminology_documents,
    build_organisation_unit_terminology_documents,
)
from dhis2w_fhir.resources.organisation_units.location import BOUNDARY_CONTENT_TYPE, build_location
from dhis2w_fhir.resources.organisation_units.naming import (
    OrganisationUnitInstanceUrls,
    OrganisationUnitNaming,
)
from dhis2w_fhir.resources.organisation_units.organization import (
    ORGANISATION_UNIT_STEM_SURFACE,
    REGISTRY_DIRECTORY,
    build_organisation_unit_instances,
    build_organisation_unit_profiles,
    build_registry_examples,
    organisation_unit_stem_subjects,
    plan_organisation_unit_stems,
)
from dhis2w_fhir.resources.organisation_units.terminology import (
    build_organisation_unit_level_terminology,
    build_organisation_unit_terminology,
)

__all__ = [
    "BOUNDARY_CONTENT_TYPE",
    "ORGANISATION_UNIT_STEM_SURFACE",
    "REGISTRY_DIRECTORY",
    "OrganisationUnitInstanceUrls",
    "OrganisationUnitNaming",
    "OrganisationUnitTerminologyBuild",
    "build_location",
    "build_organisation_unit_instances",
    "build_organisation_unit_level_terminology",
    "build_organisation_unit_level_terminology_documents",
    "build_organisation_unit_profiles",
    "build_organisation_unit_terminology",
    "build_organisation_unit_terminology_documents",
    "build_registry_examples",
    "organisation_unit_stem_subjects",
    "plan_organisation_unit_stems",
]
