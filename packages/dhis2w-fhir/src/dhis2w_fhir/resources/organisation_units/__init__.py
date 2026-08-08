"""Emission for DHIS2 organisation units: FSH profiles and terminology, plus the pre-built JSON registry.

Point geometry lands in `Location.position`; Polygon/MultiPolygon geometry
contributes its area-weighted centroid; every other geometry type is embedded
without a position. Every unit with usable geometry carries the full GeoJSON
Feature through the standard `location-boundary-geojson` extension. An
optional toggle emits the whole selection as a CodeSystem/ValueSet with
`level`, `parent`, and `dhis2-code` concept properties.
"""

from __future__ import annotations

from dhis2w_fhir.resources.organisation_units.location import BOUNDARY_CONTENT_TYPE, build_location
from dhis2w_fhir.resources.organisation_units.naming import (
    OrganisationUnitInstanceUrls,
    OrganisationUnitNaming,
)
from dhis2w_fhir.resources.organisation_units.organization import (
    REGISTRY_DIRECTORY,
    build_organisation_unit_instances,
    build_organisation_unit_profiles,
    build_registry_examples,
)
from dhis2w_fhir.resources.organisation_units.terminology import (
    build_organisation_unit_level_terminology,
    build_organisation_unit_terminology,
)

__all__ = [
    "BOUNDARY_CONTENT_TYPE",
    "REGISTRY_DIRECTORY",
    "OrganisationUnitInstanceUrls",
    "OrganisationUnitNaming",
    "build_location",
    "build_organisation_unit_instances",
    "build_organisation_unit_level_terminology",
    "build_organisation_unit_profiles",
    "build_organisation_unit_terminology",
    "build_registry_examples",
]
