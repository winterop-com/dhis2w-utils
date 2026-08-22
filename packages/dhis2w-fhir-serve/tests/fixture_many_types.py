"""The same fixture project with six tracked entity types on it, two of them the same FHIR resource.

WHY THIS EXISTS. A DHIS2 instance may declare fifty tracked entity types, and
`[generate.tracked_entity_types]` is one line per type - so the arrangement this tree is built to
hold is the ordinary one, not the exotic one: several types, several resources, and more types than
resources. `fixture_project` publishes two types over two resources, which proves the register is
not a `Patient` surface but cannot prove what happens when two types land on ONE resource.

WHAT IT ADDS, on top of `build_capture_project`, and what each addition is for:

| Tracked entity type | Published as | Why |
| --- | --- | --- |
| `TetPerson01` Person | `Patient` | the fixture's own, unchanged |
| `TetSample01` Specimen batch | `Specimen` | the fixture's own, unchanged |
| `TetFridge01` Cold-chain fridge | `Device` | one half of the shared resource |
| `TetVehicl01` Delivery vehicle | `Device` | the other half - `GET /Device` is both |
| `TetHerd0001` Livestock herd | `Group` | a third resource, so the union is not the only story |
| `TetWaterP01` Water point | `Location` | a fourth, and one an organisation unit also uses |

**The two `Device` types are the point.** One FHIR resource type is one register surface over the
union of its tracked entity types: `GET /Device` searches, lists, and counts fridges and vehicles
together, every resource states which type it is as a `meta.tag`, and `_tag` asks the union about
one of its halves. Nothing about that is a special case in the serving code - `RegisterSurface`
groups the published map's rows by resource - and this tree is what holds it to that.

The four new types share one unique attribute, `TeaAssetTg1`. A shared key is what makes an
identifier search over `/Device` a real question: the value names one asset, and which of the two
types holds it is the instance's business rather than the caller's.

Built by layering rather than by copying: `build_capture_project` writes the tree, and this rewrites
the three tracked-entity-type terminology artifacts and adds four registration forms beside the two
that are already there. A second whole fixture would be the same bytes going stale separately.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from fixture_project import (
    CAPTURE_CANONICAL,
    ENTITY_LEVEL_EXTENSION,
    FORM_TYPE_URL,
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    RESOURCE_TYPE_CODE_SYSTEM,
    RESOURCE_TYPE_VALUE_SET,
    SPECIMEN_RESOURCE_TYPE,
    SPECIMEN_TRACKED_ENTITY_TYPE_NAME,
    SPECIMEN_TRACKED_ENTITY_TYPE_UID,
    TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
    TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM_BODY,
    TRACKED_ENTITY_TYPE_CODE_SYSTEM,
    TRACKED_ENTITY_TYPE_CODE_SYSTEM_BODY,
    TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM,
    TRACKED_ENTITY_TYPE_RESOURCE_MAP,
    TRACKED_ENTITY_TYPE_VALUE_SET,
    build_capture_project,
    write_resource,
)
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from pathlib import Path

    from dhis2w_fhir.config import FhirProject

#: The attribute every added type collects: one unique asset tag, so an identifier search over a
#: shared resource is answered by whichever of its types holds the value.
ASSET_TAG_ATTRIBUTE = "TeaAssetTg1"
ASSET_TAG_ATTRIBUTE_DISPLAY = "Asset tag"
ASSET_TAG_IDENTIFIER_SYSTEM = f"http://dhis2.org/fhir/tracked-entity-attribute/{ASSET_TAG_ATTRIBUTE}"


class FixtureTrackedEntityType(BaseModel):
    """One tracked entity type this tree publishes: what DHIS2 calls it, and what FHIR serves it as."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    resource_type: str

    def questionnaire_url(self) -> str:
        """The canonical of the registration form this type publishes."""
        return f"{CAPTURE_CANONICAL}/Questionnaire/{self.uid}"


#: The two types `build_capture_project` already publishes, restated so one table is the whole map.
PERSON_TYPE = FixtureTrackedEntityType(uid=REGISTRATION_TRACKED_ENTITY_TYPE_UID, name="Person", resource_type="Patient")
SPECIMEN_TYPE = FixtureTrackedEntityType(
    uid=SPECIMEN_TRACKED_ENTITY_TYPE_UID,
    name=SPECIMEN_TRACKED_ENTITY_TYPE_NAME,
    resource_type=SPECIMEN_RESOURCE_TYPE,
)

#: The pair that share `Device`, which is what this fixture exists for.
FRIDGE_TYPE = FixtureTrackedEntityType(uid="TetFridge01", name="Cold-chain fridge", resource_type="Device")
VEHICLE_TYPE = FixtureTrackedEntityType(uid="TetVehicl01", name="Delivery vehicle", resource_type="Device")

#: Two more resources beside them, so the shared one is one arrangement among several rather than
#: the only thing this tree can say.
HERD_TYPE = FixtureTrackedEntityType(uid="TetHerd0001", name="Livestock herd", resource_type="Group")
WATER_POINT_TYPE = FixtureTrackedEntityType(uid="TetWaterP01", name="Water point", resource_type="Location")

#: Every type this tree publishes, in the order the register pages through them.
#:
#: That order is the order the compiled forms are read in, and nothing about it is chosen here: the
#: tracker program's registration form is read first and registers the person type, and the six
#: type-level forms follow by their file names, which are their UIDs. It is stated as a tuple so a
#: test asserting the order of a listing walk is asserting one written-down fact rather than
#: re-deriving the loader's.
MANY_TRACKED_ENTITY_TYPES: tuple[FixtureTrackedEntityType, ...] = (
    PERSON_TYPE,
    FRIDGE_TYPE,
    HERD_TYPE,
    SPECIMEN_TYPE,
    VEHICLE_TYPE,
    WATER_POINT_TYPE,
)

#: The types added on top of the two the capture fixture already writes forms for.
ADDED_TRACKED_ENTITY_TYPES: tuple[FixtureTrackedEntityType, ...] = (
    FRIDGE_TYPE,
    VEHICLE_TYPE,
    HERD_TYPE,
    WATER_POINT_TYPE,
)

#: Every FHIR resource type the register serves this tree over, in the order the types register.
#:
#: Five resources from six types: `Device` appears once, where the fridge first put it, and the
#: vehicle joins the register already standing there rather than opening a second one.
MANY_REGISTER_RESOURCE_TYPES: tuple[str, ...] = ("Patient", "Device", "Group", "Specimen", "Location")


def registration_questionnaire(published: FixtureTrackedEntityType) -> dict[str, Any]:
    """The person-only registration form of one type, as the emitter writes it for a non-person type.

    One entity-level question and no program: a form generated from the type itself asks the
    attributes the type itself collects, and there is no enrollment for an answer to land on. The
    `subjectType` is the resource the map takes the type onto, which is the fact `$generate` reads to
    type the subject of what it mints.
    """
    return {
        "resourceType": "Questionnaire",
        "id": published.uid,
        "url": published.questionnaire_url(),
        "title": published.name,
        "description": (
            f"DHIS2 tracked entity type {published.name} ({published.uid}) as a registration form: "
            "the tracked entity attributes the type itself collects."
        ),
        "extension": [{"url": FORM_TYPE_URL, "valueCode": "tracked-entity"}],
        "identifier": [{"system": TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM, "value": published.uid}],
        "name": f"D2TET_{published.uid}",
        "status": "draft",
        "experimental": True,
        "subjectType": [published.resource_type],
        "code": [{"system": f"{CAPTURE_CANONICAL}/CodeSystem/d2-form-type-cs", "code": "tracked-entity"}],
        "item": [
            {
                "linkId": ASSET_TAG_ATTRIBUTE,
                "code": [
                    {
                        "system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
                        "code": ASSET_TAG_ATTRIBUTE,
                        "display": ASSET_TAG_ATTRIBUTE_DISPLAY,
                    }
                ],
                "text": ASSET_TAG_ATTRIBUTE_DISPLAY,
                "type": "string",
                "required": True,
                "extension": [{"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": True}],
            }
        ],
    }


def tracked_entity_type_code_system() -> dict[str, Any]:
    """`D2TET_CS` over all six types - the vocabulary the map's source is drawn from."""
    body = copy.deepcopy(TRACKED_ENTITY_TYPE_CODE_SYSTEM_BODY)
    body["concept"] = [{"code": published.uid, "display": published.name} for published in MANY_TRACKED_ENTITY_TYPES]
    body["count"] = len(MANY_TRACKED_ENTITY_TYPES)
    return body


def tracked_entity_type_resource_map() -> dict[str, Any]:
    """`D2TET_CM` over all six types - the contract a running facade reads its resources off.

    Every row is explicit, the `Patient` one included. A map whose defaults were implied would leave
    a reader unable to tell an unmapped type from a type deliberately published as a person, and it
    is the map rather than `fhir.toml` that a served resource is decided by.
    """
    return {
        "resourceType": "ConceptMap",
        "id": TRACKED_ENTITY_TYPE_RESOURCE_MAP.rsplit("/", 1)[-1],
        "url": TRACKED_ENTITY_TYPE_RESOURCE_MAP,
        "name": "D2TET_CM",
        "title": "DHIS2 tracked entity types as FHIR resource types",
        "status": "draft",
        "sourceCanonical": TRACKED_ENTITY_TYPE_VALUE_SET,
        "targetCanonical": RESOURCE_TYPE_VALUE_SET,
        "group": [
            {
                "source": TRACKED_ENTITY_TYPE_CODE_SYSTEM,
                "target": RESOURCE_TYPE_CODE_SYSTEM,
                "element": [
                    {
                        "code": published.uid,
                        "display": published.name,
                        "target": [{"code": published.resource_type, "equivalence": "equal"}],
                    }
                    for published in MANY_TRACKED_ENTITY_TYPES
                ],
            }
        ],
    }


def tracked_entity_attribute_code_system() -> dict[str, Any]:
    """`D2TEA_CS` with the shared asset tag beside the attributes the capture fixture publishes."""
    body = copy.deepcopy(TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM_BODY)
    body["concept"] = [
        *body["concept"],
        {
            "code": ASSET_TAG_ATTRIBUTE,
            "display": ASSET_TAG_ATTRIBUTE_DISPLAY,
            "property": [
                {"code": "dhis2-code", "valueString": "TEA_ASSET_TAG"},
                {"code": "value-type", "valueCode": "TEXT"},
                {"code": "unique", "valueBoolean": True},
                {"code": "searchable", "valueBoolean": True},
            ],
        },
    ]
    body["count"] = len(body["concept"])
    return body


def build_many_types_project(destination: Path) -> FhirProject:
    """Write the capture tree and republish its tracked-entity-type contract over all six types."""
    project = build_capture_project(destination)
    compiled = destination / "ig" / "fsh-generated" / "resources"
    for published in ADDED_TRACKED_ENTITY_TYPES:
        write_resource(compiled / f"Questionnaire-{published.uid}.json", registration_questionnaire(published))
    terminology = destination / "ig" / "input" / "resources" / "terminology"
    for body in (
        tracked_entity_type_code_system(),
        tracked_entity_type_resource_map(),
        tracked_entity_attribute_code_system(),
    ):
        write_resource(terminology / f"{body['resourceType']}-{body['id']}.json", body)
    return project
