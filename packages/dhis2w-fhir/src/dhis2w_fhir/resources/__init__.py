"""FSH emitters, one component subpackage per DHIS2 resource domain."""

from __future__ import annotations

from dhis2w_fhir.resources.option_sets import build_option_set_artifacts, max_slug_length
from dhis2w_fhir.resources.organisation_units import (
    build_organisation_unit_instances,
    build_organisation_unit_level_terminology,
    build_organisation_unit_profiles,
    build_organisation_unit_terminology,
)

__all__ = [
    "build_option_set_artifacts",
    "build_organisation_unit_instances",
    "build_organisation_unit_level_terminology",
    "build_organisation_unit_profiles",
    "build_organisation_unit_terminology",
    "max_slug_length",
]
