"""Location instance rendering for organisation units: position, boundary extension, and partOf."""

from __future__ import annotations

import base64

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import code_or_uid, quote
from dhis2w_fhir.resources.organisation_units.naming import OrganisationUnitNaming
from dhis2w_fhir.resources.organisation_units.schemas import GeoPoint, OrganisationUnitIn

#: The standard R4 extension carrying a Location's boundary as a GeoJSON attachment.
BOUNDARY_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"


class LocationInstance(BaseModel):
    """Everything the FSH template needs for one Location instance, every conditional already resolved."""

    model_config = ConfigDict(frozen=True)

    uid: str
    profile: str
    title_literal: str
    description_literal: str
    name_literal: str
    identifier_code_literal: str
    closed: bool = False
    position: GeoPoint | None = None
    boundary_data: str | None = None
    boundary_title_literal: str | None = None
    boundary_size: int | None = None
    parent_uid: str | None = None


def build_location_instance(
    organisation_unit: OrganisationUnitIn, names: OrganisationUnitNaming, selected_uids: set[str]
) -> LocationInstance:
    """Build the Location view - always emitted; position/boundary attach when geometry exists."""
    position: GeoPoint | None = None
    if organisation_unit.latitude is not None and organisation_unit.longitude is not None:
        position = GeoPoint(longitude=organisation_unit.longitude, latitude=organisation_unit.latitude)
    boundary_data: str | None = None
    boundary_title_literal: str | None = None
    boundary_size: int | None = None
    if organisation_unit.boundary_geojson is not None:
        payload = organisation_unit.boundary_geojson.encode("utf-8")
        boundary_data = base64.b64encode(payload).decode("ascii")
        boundary_title_literal = quote(f"{organisation_unit.name} ({organisation_unit.uid})")
        boundary_size = len(payload)
    parent_uid = organisation_unit.parent_uid if organisation_unit.parent_uid in selected_uids else None
    description = (
        f"DHIS2 organisation unit {organisation_unit.name} ({organisation_unit.uid}), "
        f"level {organisation_unit.level} - physical location."
    )
    return LocationInstance(
        uid=organisation_unit.uid,
        profile=names.location_profile,
        title_literal=quote(f"Location - {organisation_unit.name}"),
        description_literal=quote(description),
        name_literal=quote(organisation_unit.name),
        identifier_code_literal=quote(code_or_uid(organisation_unit.code, organisation_unit.uid)),
        closed=organisation_unit.closed,
        position=position,
        boundary_data=boundary_data,
        boundary_title_literal=boundary_title_literal,
        boundary_size=boundary_size,
        parent_uid=parent_uid,
    )
