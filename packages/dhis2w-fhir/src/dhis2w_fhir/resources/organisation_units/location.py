"""Location emission for organisation units: position, the boundary attachment, and the hierarchy links."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from dhis2w_fhir.foundation.attribute_values import attribute_value_extensions
from dhis2w_fhir.i18n import name_translations, translated_element
from dhis2w_fhir.names import code_or_uid, flatten_whitespace, page_string
from dhis2w_fhir.r4 import (
    BOUNDARY_EXTENSION_URL,
    Attachment,
    Extension,
    Identifier,
    Location,
    LocationPosition,
    Meta,
    Reference,
)

if TYPE_CHECKING:
    from dhis2w_fhir.attributes import AttributeCodeIndex
    from dhis2w_fhir.resources.organisation_units.naming import OrganisationUnitInstanceUrls
    from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn

#: The media type the GeoJSON Feature travels under inside the boundary attachment.
BOUNDARY_CONTENT_TYPE = "application/geo+json"


def build_location(
    organisation_unit: OrganisationUnitIn,
    urls: OrganisationUnitInstanceUrls,
    selected_uids: set[str],
    locales: list[str],
    attribute_codes: AttributeCodeIndex,
    extension_url: str,
) -> Location:
    """Build the Location of one organisation unit - always emitted; position/boundary attach with geometry."""
    uid = organisation_unit.uid
    position: LocationPosition | None = None
    if organisation_unit.latitude is not None and organisation_unit.longitude is not None:
        position = LocationPosition(longitude=organisation_unit.longitude, latitude=organisation_unit.latitude)
    parent_uid = organisation_unit.parent_uid if organisation_unit.parent_uid in selected_uids else None
    description = (
        f"DHIS2 organisation unit {organisation_unit.name} ({uid}), "
        f"level {organisation_unit.level} - physical location."
    )
    return Location(
        id=uid,
        meta=Meta(profile=[urls.location_profile]),
        identifier=[
            Identifier(system=urls.identifier_system, value=uid),
            Identifier(system=urls.code_identifier_system, value=code_or_uid(organisation_unit.code, uid)),
        ],
        name=flatten_whitespace(organisation_unit.name),
        name_element=translated_element(name_translations(organisation_unit.translations, locales)),
        description=page_string(description),
        status="inactive" if organisation_unit.closed else "active",
        position=position,
        extension=_extensions(organisation_unit, attribute_codes, extension_url) or None,
        managingOrganization=Reference(reference=f"Organization/{uid}"),
        partOf=Reference(reference=f"Location/{parent_uid}") if parent_uid is not None else None,
    )


def _extensions(
    organisation_unit: OrganisationUnitIn, attribute_codes: AttributeCodeIndex, extension_url: str
) -> list[Extension]:
    """A Location's extensions in emission order: the GeoJSON boundary, then one per DHIS2 attribute value.

    The order is a contract rather than an accident. A regenerate of an unchanged unit has to
    produce a byte-identical file for `sync_artifacts` to report it unchanged, so the boundary
    always leads and the attribute values always follow it in the order DHIS2 returned them.
    """
    return [
        *_boundary_extensions(organisation_unit),
        *attribute_value_extensions(organisation_unit.attribute_values, attribute_codes, extension_url),
    ]


def _boundary_extensions(organisation_unit: OrganisationUnitIn) -> list[Extension]:
    """The `location-boundary-geojson` extension carrying the unit's GeoJSON Feature, empty without geometry."""
    if organisation_unit.boundary_geojson is None:
        return []
    payload = organisation_unit.boundary_geojson.encode("utf-8")
    return [
        Extension(
            url=BOUNDARY_EXTENSION_URL,
            valueAttachment=Attachment(
                contentType=BOUNDARY_CONTENT_TYPE,
                data=base64.b64encode(payload).decode("ascii"),
                title=flatten_whitespace(f"{organisation_unit.name} ({organisation_unit.uid})"),
                size=len(payload),
            ),
        )
    ]
