"""Attribute fixtures that make the FHIR `D2AttributeValue` extension testable end to end.

The FHIR plugin emits every DHIS2 attribute value as a `D2AttributeValue` extension on
five resource types: Organization, Location, CodeSystem, ValueSet and Questionnaire.
The Sierra Leone play bundle carries attribute values on organisation units and event
programs only, so the option-set path (CodeSystem / ValueSet) and the data-set path
(Questionnaire) have no live coverage at all — they rest on unit fixtures written from
reading the emitter. This module puts real attribute values on a real option set and a
real data set so a generate run against this stack is evidence rather than assumption.

The `attributeCode` sub-extension is `0..1`: the emitter writes it when the instance
coded the attribute and omits the sub-extension entirely when it did not. A fixture
where every attribute carries a code never exercises the omission, and one where none
do never exercises the presence — so the three attributes here are deliberately split:

1. `AtrFhirOpS1` — targets `optionSet`, HAS a code, `unique = false`.
   Exercises `attributeCode` PRESENT on CodeSystem + ValueSet.
2. `AtrFhirDsQ1` — targets `dataSet`, NO code, `unique = false`.
   Exercises `attributeCode` ABSENT on Questionnaire.
3. `AtrFhirOrU1` — targets `organisationUnit`, HAS a code, `unique = true`.
   Exercises `attributeCode` PRESENT on Organization + Location, and the `unique`
   flag, which the play bundle's attributes never set.

All three are `valueType = TEXT`, which is what the extension's `valueString` carries
whatever DHIS2's declared value type happens to be.

Targets are objects the rest of the seed already created:

- Option set `OsVaccType1` (VACCINE_TYPE, from `workspace_fixtures`).
- Data set `BfMAe6Itzgt` (Child Health, from the play metadata import).
- Organisation unit `ImspTQPwCqd` (Sierra Leone root — level 1, so it survives a
  `d2w fhir init --max-level` cap of 1 or higher).

Idempotent twice over: the attribute definitions land through `/api/metadata` with
fixed UIDs under `CREATE_AND_UPDATE`, and the values go through the client's
`attribute_values.set_value` read-merge-write, which replaces any prior entry for the
same attribute UID instead of appending a second one. Re-running leaves the attribute
count and every `attributeValues` list exactly where it was.

Called from `seed_play` after the deferred DataSet import, because the data set it
attaches a value to only exists once that pass has run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dhis2w_client.generated.v42.enums import ValueType
from dhis2w_client.generated.v42.oas import Sharing
from dhis2w_client.generated.v42.schemas import Attribute
from dhis2w_client.v42.sharing import ACCESS_READ_WRITE_DATA

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client

# Fixed UIDs — hand-chosen so the FHIR fixtures can pin them, and distinct from
# `AtrSNOMED01` (the option-level attribute `workspace_fixtures` seeds).
ATTRIBUTE_OPTION_SET_UID = "AtrFhirOpS1"
ATTRIBUTE_DATA_SET_UID = "AtrFhirDsQ1"
ATTRIBUTE_ORGANISATION_UNIT_UID = "AtrFhirOrU1"

# Codes. The data-set attribute deliberately has none.
ATTRIBUTE_OPTION_SET_CODE = "FHIR_CODE_SYSTEM_URI"
ATTRIBUTE_ORGANISATION_UNIT_CODE = "FHIR_FACILITY_REGISTRY_ID"

# Targets the surrounding seed already created.
TARGET_OPTION_SET_UID = "OsVaccType1"
TARGET_DATA_SET_UID = "BfMAe6Itzgt"
TARGET_ORGANISATION_UNIT_UID = "ImspTQPwCqd"

# Values attached to those targets.
OPTION_SET_ATTRIBUTE_VALUE = "http://snomed.info/sct"
DATA_SET_ATTRIBUTE_VALUE = "Paper register 12A, revision 2025-03"
ORGANISATION_UNIT_ATTRIBUTE_VALUE = "SL-NATIONAL-0001"

_SHARING = Sharing(public=ACCESS_READ_WRITE_DATA, external=False, users={}, userGroups={})


def option_set_attribute() -> Attribute:
    """Typed `Attribute` — coded, applies to OptionSet, not unique."""
    return Attribute(
        id=ATTRIBUTE_OPTION_SET_UID,
        name="FHIR code system URI",
        shortName="FHIR CS URI",
        code=ATTRIBUTE_OPTION_SET_CODE,
        description="Terminology system URI the generated CodeSystem / ValueSet pair maps onto.",
        valueType=ValueType.TEXT,
        optionSetAttribute=True,
        unique=False,
        mandatory=False,
        sharing=_SHARING,
    )


def data_set_attribute() -> Attribute:
    """Typed `Attribute` — uncoded, applies to DataSet, not unique."""
    return Attribute(
        id=ATTRIBUTE_DATA_SET_UID,
        name="FHIR questionnaire source form",
        shortName="FHIR Q source",
        description="Paper form the data set was digitised from. Deliberately uncoded.",
        valueType=ValueType.TEXT,
        dataSetAttribute=True,
        unique=False,
        mandatory=False,
        sharing=_SHARING,
    )


def organisation_unit_attribute() -> Attribute:
    """Typed `Attribute` — coded, applies to OrganisationUnit, unique."""
    return Attribute(
        id=ATTRIBUTE_ORGANISATION_UNIT_UID,
        name="FHIR facility registry id",
        shortName="FHIR facility id",
        code=ATTRIBUTE_ORGANISATION_UNIT_CODE,
        description="National facility-registry identifier carried onto Organization and Location.",
        valueType=ValueType.TEXT,
        organisationUnitAttribute=True,
        unique=True,
        mandatory=False,
        sharing=_SHARING,
    )


def all_attributes() -> list[Attribute]:
    """Every attribute this fixture defines, in the order it posts them."""
    return [option_set_attribute(), data_set_attribute(), organisation_unit_attribute()]


async def seed_fhir_attributes(client: Dhis2Client) -> int:
    """Post the three attribute definitions and attach one value to each of their targets.

    Definitions go through `/api/metadata` with `CREATE_AND_UPDATE` on fixed UIDs, so a
    re-run updates in place. Values go through the read-merge-write accessor, which
    replaces the entry for the same attribute UID rather than appending. Returns the
    count of attribute values attached so `seed_play` can report progress.
    """
    metadata_bundle: dict[str, list[dict[str, Any]]] = {
        "attributes": [
            attribute.model_dump(by_alias=True, exclude_none=True, mode="json") for attribute in all_attributes()
        ],
    }
    await client.post_raw(
        "/api/metadata",
        body=metadata_bundle,
        params={"importStrategy": "CREATE_AND_UPDATE", "atomicMode": "OBJECT"},
    )
    await client.attribute_values.set_value(
        "optionSets", TARGET_OPTION_SET_UID, ATTRIBUTE_OPTION_SET_UID, OPTION_SET_ATTRIBUTE_VALUE
    )
    await client.attribute_values.set_value(
        "dataSets", TARGET_DATA_SET_UID, ATTRIBUTE_DATA_SET_UID, DATA_SET_ATTRIBUTE_VALUE
    )
    await client.attribute_values.set_value(
        "organisationUnits",
        TARGET_ORGANISATION_UNIT_UID,
        ATTRIBUTE_ORGANISATION_UNIT_UID,
        ORGANISATION_UNIT_ATTRIBUTE_VALUE,
    )
    return 3
