"""The IG project the serve tests and the browser e2e both run against, written to a directory.

The resources are the dhis2w-fhir goldens - one Questionnaire per form kind plus the terminology
they bind, and the ConceptMap the emitter writes beside one of the option sets - so a test that
accepts them is a test that the facade accepts the documented contract.

Three forms are written here rather than harvested. The first is the registration form of the tracker
program whose stage form the goldens already publish: it gives the fixture a whole tracker surface -
register a person against `PrAncCare01`, mint the identifier pair, then answer `PsAncVisit1` with the
same pair - which is what the capture, `$generate`, and e2e paths all need to exercise the
registration contract end to end. The second is the person-only form of the tracked entity type that
program registers into, which is the same surface with the enrollment taken out of it: a person put
in the instance and enrolled in nothing. The third registers a tracked entity type that is not a
person at all, and the `D2TET_CM` beside them takes it onto `Specimen` - so the register this project
serves is two FHIR resources rather than one, which is what makes the generalized read surface and
the typed capture screens real rather than hypothetical.

Beside them sits an organisation-unit registry: ten Locations over four levels, carrying every
geometry state a real selection produces, the curated profile exemplar a generated IG publishes
beside them - a second Location claiming the root unit's uid, which a consumer has to deduplicate -
and the assignment List that restricts one form to two of them. The goldens publish no registry,
and a browser that folds `partOf` into a tree, decodes a boundary, and joins an assignment needs
one to fold, decode, and join.

This lives outside `conftest.py` because two callers need it and only one of them is pytest. The
Playwright suite boots a real `d2w fhir serve --ui` and needs the same tree on disk first, which it
gets by running this module:

    uv run python packages/dhis2w-fhir-serve/tests/fixture_project.py <destination>

Building it rather than committing it keeps one copy of the goldens in the workspace. A committed
second copy would be the same bytes going stale the first time the emitter changes.
"""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from typing import Annotated, Any

import typer
from dhis2w_fhir import build_option_set_concept_map_artifacts
from dhis2w_fhir.config import FhirProject, load_fhir_config
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir_serve.spool import SPOOL_RELATIVE_PATH
from pydantic import BaseModel, ConfigDict

#: Where the dhis2w-fhir goldens live, relative to this file.
GOLDEN_DIRECTORY = Path(__file__).resolve().parents[2] / "dhis2w-fhir" / "tests" / "data" / "r4"

#: The canonical and identifier base the goldens were compiled under.
CAPTURE_CANONICAL = "http://localhost:8080/fhir"
CAPTURE_IDENTIFIER_BASE = "http://dhis2.org/fhir"

CAPTURE_FHIR_TOML = f"""
[ig]
id = "dhis2.fhir.capture"
canonical = "{CAPTURE_CANONICAL}"
name = "Dhis2FhirCapture"
title = "DHIS2 FHIR Capture IG"
publisher = "Example Organisation"

[generate]
identifier_system_base = "{CAPTURE_IDENTIFIER_BASE}"

[generate.organisation_units]
root = ""
max_level = 0

[serve]
# No basemap layers, so the map's layer control offers None alone. The browser suite asserts
# that the organisation-units page issues no failing request, and a run that reached
# tile.openstreetmap.org would be asserting on somebody else's uptime - and would make a test
# suite that is meant to be offline talk to the internet. The layers-on path is covered by the
# vitest cases over the style fork and by the e2e spec that states its own layers over
# `/uiconfig`, whose tiles are fulfilled in the browser and never fetched.
basemaps = []
"""

#: The compiled Questionnaires the capture project serves - one per form kind, plus the tracker
#: stage carrying a required question and a numeric bound, and the aggregate form whose data set
#: rides a non-default category combo and therefore declares a vocabulary of attribute option
#: combos its responses must name one of.
CAPTURE_QUESTIONNAIRE_FILES = (
    "Questionnaire-BfMAe6Itzgt.json",
    "Questionnaire-EVTsupVis01.json",
    "Questionnaire-ZzYYXq4fJie.json",
    "Questionnaire-PsAncVisit1.json",
    "Questionnaire-TuL8IOPzpHh.json",
)

#: The data-dictionary terminology every generated form draws its question codes from, plus the
#: attribute-option-combo pair the non-default-combo form binds - without which a capture client
#: has a form declaring a vocabulary and no way to expand it.
#:
#: The category pairs ride with them because both combo vocabularies decompose their concepts into
#: those categories: a reader who follows a combo's category property lands on the CodeSystem named
#: here, so a project serving the combos without the categories would publish links to nothing.
CAPTURE_SUPPORT_FILES = (
    "CodeSystem-d2-de-cs.json",
    "CodeSystem-d2-coc-cs.json",
    "ValueSet-d2-de-vs.json",
    "ValueSet-d2-coc-vs.json",
    "CodeSystem-d2-aoc-idcDPkDtepR-cs.json",
    "ValueSet-d2-aoc-idcDPkDtepR-vs.json",
    "CodeSystem-d2-cat-yY2bQYqNt0o-cs.json",
    "ValueSet-d2-cat-yY2bQYqNt0o-vs.json",
    "CodeSystem-d2-cat-fMZEcRHuamy-cs.json",
    "ValueSet-d2-cat-fMZEcRHuamy-vs.json",
    "CodeSystem-d2-cat-YNZyaJHiHYq-cs.json",
    "ValueSet-d2-cat-YNZyaJHiHYq-vs.json",
    "CodeSystem-d2-cat-Qzh0MSUx4RM-cs.json",
    "ValueSet-d2-cat-Qzh0MSUx4RM-vs.json",
)

#: The category the attribute option combos of the non-default-combo form decompose over, and the
#: concept property they name it under - what the browser follows from a combo row to its parts.
PROJECT_CATEGORY_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-cat-yY2bQYqNt0o-cs"
PROJECT_CATEGORY_PROPERTY = "category-yY2bQYqNt0o"

AGGREGATE_RESPONSE_FILE = "QuestionnaireResponse-BfMAe6Itzgt-example-1.json"
EVENT_RESPONSE_FILE = "QuestionnaireResponse-EVTsupVis01-example-1.json"
TRACKER_RESPONSE_FILE = "QuestionnaireResponse-ZzYYXq4fJie-example-1.json"

#: The golden submission of the non-default-combo data set - the one that names the attribute
#: option combo its values are filed under, coded from the vocabulary its form declares.
ATTRIBUTE_COMBO_RESPONSE_FILE = "QuestionnaireResponse-TuL8IOPzpHh-example-1.json"

#: The vocabulary that form declares, and the CodeSystem behind it a response codes its combo from.
ATTRIBUTE_COMBO_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-aoc-idcDPkDtepR-vs"
ATTRIBUTE_COMBO_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-aoc-idcDPkDtepR-cs"

#: The concept property an id-mode CodeSystem carries the DHIS2 option code on.
OPTION_CODE_PROPERTY_URI = f"{CAPTURE_IDENTIFIER_BASE}/property/dhis2-code"

#: The extensions a numeric question carries its inclusive bounds on.
MINIMUM_VALUE_URL = "http://hl7.org/fhir/StructureDefinition/minValue"
MAXIMUM_VALUE_URL = "http://hl7.org/fhir/StructureDefinition/maxValue"

FORM_TYPE_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-form-type"

TEMPORAL_QUESTIONNAIRE_UID = "PrTemporal1"
TEMPORAL_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{TEMPORAL_QUESTIONNAIRE_UID}"
SYMPTOM_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-os-OsSymptom01-cs"
SYMPTOM_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-os-OsSymptom01-vs"
UNPUBLISHED_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-os-Unpublished-vs"

#: An event form covering the value types the dhis2w-fhir goldens happen not to ask for - the three
#: temporal primitives, a URL, a repeating multi-select, a decimal with both bounds, and a question
#: bound to terminology this project never published. Written in the shape the emitter writes.
TEMPORAL_QUESTIONNAIRE_BODY: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": TEMPORAL_QUESTIONNAIRE_UID,
    "url": TEMPORAL_QUESTIONNAIRE,
    "title": "Temporal capture",
    "description": "DHIS2 event program Temporal capture (PrTemporal1) as a data capture form.",
    "extension": [{"url": FORM_TYPE_URL, "valueCode": "event"}],
    "identifier": [{"system": f"{CAPTURE_IDENTIFIER_BASE}/id/program", "value": TEMPORAL_QUESTIONNAIRE_UID}],
    "name": f"D2PR_{TEMPORAL_QUESTIONNAIRE_UID}",
    "status": "draft",
    "experimental": True,
    "subjectType": ["Location"],
    "item": [
        {"linkId": "DeVisitDate1", "text": "Visit date", "type": "date"},
        {"linkId": "DeVisitTime1", "text": "Visit time", "type": "time"},
        {"linkId": "DeVisitStamp", "text": "Visit stamp", "type": "dateTime"},
        {"linkId": "DeVisitLink1", "text": "Visit link", "type": "url"},
        # A DHIS2 ORGANISATION_UNIT data element, which the emitter answers as `reference`.
        {"linkId": "DeVisitUnit1", "text": "Visited unit", "type": "reference"},
        {
            "linkId": "DeSymptoms01",
            "text": "Symptoms",
            "type": "choice",
            "repeats": True,
            "answerValueSet": SYMPTOM_VALUE_SET,
        },
        {
            "linkId": "DeCoverage01",
            "text": "Coverage",
            "type": "decimal",
            "extension": [
                {"url": MINIMUM_VALUE_URL, "valueDecimal": 0},
                {"url": MAXIMUM_VALUE_URL, "valueDecimal": 100},
            ],
        },
        {
            "linkId": "DeOpenBind01",
            "text": "Bound to terminology this project never published",
            "type": "choice",
            "answerValueSet": UNPUBLISHED_VALUE_SET,
        },
    ],
}

#: The option set the temporal form's multi-select is answered from, in id mode like every other pair.
SYMPTOM_CODE_SYSTEM_BODY: dict[str, Any] = {
    "resourceType": "CodeSystem",
    "id": SYMPTOM_CODE_SYSTEM.rsplit("/", 1)[-1],
    "url": SYMPTOM_CODE_SYSTEM,
    "status": "draft",
    "content": "complete",
    "caseSensitive": True,
    "valueSet": SYMPTOM_VALUE_SET,
    "property": [{"code": "dhis2-code", "uri": OPTION_CODE_PROPERTY_URI, "type": "string"}],
    "concept": [
        {"code": "OpFever0001", "display": "Fever", "property": [{"code": "dhis2-code", "valueString": "FEVER"}]},
        {"code": "OpCough0001", "display": "Cough", "property": [{"code": "dhis2-code", "valueString": "COUGH"}]},
    ],
    "count": 2,
}

#: The option set the symptom terminology was generated from, as the ConceptMap emitter reads it.
#:
#: The concepts of `SYMPTOM_CODE_SYSTEM_BODY` are this set's option UIDs and the `dhis2-code`
#: property values are its option codes, so the map the emitter writes from it lands on exactly
#: the concepts the hand-written CodeSystem holds. Building the map rather than hand-writing it
#: keeps `$translate` in the browser answering off what `d2w fhir generate` really emits.
SYMPTOM_OPTION_SET = OptionSetIn(
    uid="OsSymptom01",
    name="Symptoms",
    options=[
        OptionIn(uid="OpFever0001", code="FEVER", name="Fever", sort_order=1),
        OptionIn(uid="OpCough0001", code="COUGH", name="Cough", sort_order=2),
    ],
)

#: The map that option set emits, and the two DHIS2 systems it maps a symptom concept onto.
SYMPTOM_CONCEPT_MAP = f"{CAPTURE_CANONICAL}/ConceptMap/d2-os-OsSymptom01-cm"
OPTION_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/option"
OPTION_CODE_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/option-code"

SYMPTOM_VALUE_SET_BODY: dict[str, Any] = {
    "resourceType": "ValueSet",
    "id": SYMPTOM_VALUE_SET.rsplit("/", 1)[-1],
    "url": SYMPTOM_VALUE_SET,
    "status": "draft",
    "compose": {"include": [{"system": SYMPTOM_CODE_SYSTEM}]},
}

#: The urls the organisation-unit registry is published under, as `d2w fhir generate` derives them.
ORG_UNIT_IDENTIFIER_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/org-unit"
ORG_UNIT_CODE_IDENTIFIER_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/org-unit-code"
ORG_UNIT_LEVEL_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-organisation-unit-level"
ORG_UNIT_LEVEL_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-ou-level-cs"
ORG_UNIT_ASSIGNMENT_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-organisation-unit-assignment"
BOUNDARY_EXTENSION = "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"
BOUNDARY_CONTENT_TYPE = "application/geo+json"


class OrgUnitFixture(BaseModel):
    """One organisation unit of the fixture registry, in the terms the Location emitter reads.

    A hand-written miniature of what `d2w fhir generate` writes for a real selection: a hierarchy
    deep enough to fold, every geometry state the emitter can produce (boundary and point, boundary
    only, point only, neither), and one unit whose `partOf` names a unit the project never
    published - which is what a consumer folding the hierarchy has to survive.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str
    level: int
    parent_uid: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    boundary: dict[str, Any] | None = None
    malformed_boundary: bool = False
    """Publishes a geometry attachment whose payload is not GeoJSON, which a reader must skip rather than crash on."""

    point_attachment: tuple[float, float] | None = None
    """Publishes a Point geometry attachment - what DHIS2 stores for a facility - as (longitude, latitude).

    The extension is named for boundaries and R4 documents it as one, but DHIS2 keeps a district's
    polygon and a facility's pin in the same `geometry` field, so most of a real registry's
    attachments are Points. A reader treating the attachment as polygon-or-failure reports every
    facility as broken, which is what this state exists to catch.
    """


def _square(west: float, south: float, east: float, north: float) -> list[list[list[float]]]:
    """One closed rectangular ring, as a Polygon's coordinate list."""
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


#: The fixture's organisation-unit hierarchy - four levels, ten units, every geometry state.
#:
#: The UIDs and names are the DHIS2 demo database's, because the capture goldens report against
#: them: `Location/ImspTQPwCqd` is the unit the golden aggregate response names as its subject.
#: The boundaries are hand-drawn rectangles rather than the real polygons - a browser proving it
#: renders a MultiPolygon needs a MultiPolygon, not four hundred kilobytes of one.
ORG_UNITS: tuple[OrgUnitFixture, ...] = (
    OrgUnitFixture(
        uid="ImspTQPwCqd",
        name="Sierra Leone",
        code="OU_SL",
        level=1,
        boundary={"type": "MultiPolygon", "coordinates": [_square(-13.3, 6.9, -10.3, 10.0)]},
    ),
    OrgUnitFixture(
        uid="O6uvpzGd5pu",
        name="Bo",
        code="OU_BO",
        level=2,
        parent_uid="ImspTQPwCqd",
        latitude=7.96,
        longitude=-11.74,
        boundary={"type": "Polygon", "coordinates": _square(-12.2, 7.5, -11.2, 8.4)},
    ),
    OrgUnitFixture(
        uid="fdc6uOvgoji",
        name="Bombali",
        code="OU_BOMBALI",
        level=2,
        parent_uid="ImspTQPwCqd",
        boundary={"type": "Polygon", "coordinates": _square(-12.6, 8.8, -11.7, 9.6)},
    ),
    OrgUnitFixture(
        uid="YuQRtpLP10I",
        name="Badjia",
        code="OU_BADJIA",
        level=3,
        parent_uid="O6uvpzGd5pu",
        latitude=7.92,
        longitude=-11.75,
        boundary={"type": "Polygon", "coordinates": _square(-11.9, 7.8, -11.6, 8.1)},
    ),
    OrgUnitFixture(
        uid="lc3eMKXaEfw",
        name="Bargbe",
        code="OU_BARGBE",
        level=3,
        parent_uid="O6uvpzGd5pu",
        latitude=7.72,
        longitude=-11.62,
        # Both renderings of one place, and deliberately not at the same coordinates: a reader has
        # to state which one wins, and the drawn dot is the proof of which it picked.
        point_attachment=(-11.5, 7.6),
    ),
    OrgUnitFixture(
        uid="vWbkYPRmKyS",
        name="Baoma",
        code="OU_BAOMA",
        level=3,
        parent_uid="O6uvpzGd5pu",
        latitude=8.12,
        longitude=-11.55,
        malformed_boundary=True,
    ),
    OrgUnitFixture(
        uid="MgFYJDBqSSs",
        name="Yoni CHP",
        code="OU_YONI",
        level=4,
        parent_uid="fdc6uOvgoji",
        point_attachment=(-12.1, 9.2),
    ),
    OrgUnitFixture(
        uid="EJoI3HuIUEV",
        name="Kagbere CHC",
        code="OU_KAGBERE",
        level=4,
        parent_uid="fdc6uOvgoji",
    ),
    OrgUnitFixture(
        uid="DiszpKrYNg8",
        name="Ngelehun CHC",
        code="OU_NGELEHUN",
        level=4,
        parent_uid="YuQRtpLP10I",
        latitude=7.87,
        longitude=-11.7,
    ),
    OrgUnitFixture(
        uid="Rp268JB6Ne4",
        name="Adonkia CHP",
        code="OU_ADONKIA",
        level=4,
        parent_uid="Unpublished01",
    ),
)

#: The event form whose organisation-unit assignment restricts it to two of the eight units.
SCOPED_QUESTIONNAIRE_UID = "PrScoped001"
SCOPED_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{SCOPED_QUESTIONNAIRE_UID}"
SCOPED_ASSIGNMENT_LIST_ID = f"d2-pr-{SCOPED_QUESTIONNAIRE_UID}-org-units"

#: The units that form may be captured against - one district and one facility, on different branches.
SCOPED_ASSIGNMENT_UNITS = ("O6uvpzGd5pu", "DiszpKrYNg8")

#: The tracker program whose stage form `PsAncVisit1` the goldens already publish. Its registration
#: form is written here so the fixture carries one whole tracker surface: a client registers a
#: person against `PrAncCare01`, mints the pair, and answers `PsAncVisit1` with the same UIDs.
REGISTRATION_PROGRAM_UID = "PrAncCare01"
REGISTRATION_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{REGISTRATION_PROGRAM_UID}"
REGISTRATION_TRACKED_ENTITY_TYPE_UID = "TetPerson01"

#: The assignment that program is scoped to - the same two units the scoped event form uses, so a
#: registration outside them is the one case the assignment dial grades for the tracker kinds.
REGISTRATION_ASSIGNMENT_LIST_ID = f"d2-pr-{REGISTRATION_PROGRAM_UID}-org-units"

#: The tracked entity attributes that form asks: a unique business identifier DHIS2 alone can check
#: for uniqueness, a date, one bound to a published option set, and one the program asks that its
#: tracked entity type does not collect - the last is what makes both DHIS2 import levels visible.
REGISTRATION_UNIQUE_ATTRIBUTE = "TeaNationId"
REGISTRATION_DATE_ATTRIBUTE = "TeaBirthDat"
REGISTRATION_CODED_ATTRIBUTE = "TeaSex00001"
REGISTRATION_PROGRAM_ONLY_ATTRIBUTE = "TeaHousehld"

#: The attribute the second tracked entity type collects: a unique laboratory reference.
SPECIMEN_UNIQUE_ATTRIBUTE = "TeaLabRef01"

#: The extension a registration question states its DHIS2 import level on.
ENTITY_LEVEL_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-entity-level"

#: The vocabulary that coded attribute binds - written here in the emitter's own id-mode shape.
SEX_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-os-OsSex000001-cs"
SEX_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-os-OsSex000001-vs"

#: The support pair the registration form's item codes are drawn from, as `D2TEA_CS` publishes it.
TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-tea-cs"
TRACKED_ENTITY_ATTRIBUTE_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-tea-vs"

#: The extensions and identifier systems a registration response carries beyond the tracker pair.
ENROLLED_AT_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-enrolled-at"
INCIDENT_AT_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-incident-at"

#: The extension a registration form declares whether its program collects an incident date on. The
#: fixture program collects none and says so, which is the false half of the fact a generated form
#: always publishes - the true half is written by the test that needs it.
COLLECTS_INCIDENT_DATE_EXTENSION = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-collects-incident-date"
TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity-type"

REGISTRATION_QUESTIONNAIRE_BODY: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": REGISTRATION_PROGRAM_UID,
    "url": REGISTRATION_QUESTIONNAIRE,
    "title": "Antenatal care",
    "description": (
        f"DHIS2 tracker program Antenatal care ({REGISTRATION_PROGRAM_UID}) as a registration form: "
        "the tracked entity attributes captured when a person is enrolled in the program."
    ),
    "extension": [
        {"url": FORM_TYPE_URL, "valueCode": "tracker"},
        {"url": COLLECTS_INCIDENT_DATE_EXTENSION, "valueBoolean": False},
        {
            "url": ORG_UNIT_ASSIGNMENT_EXTENSION,
            "valueReference": {"reference": f"List/{REGISTRATION_ASSIGNMENT_LIST_ID}"},
        },
    ],
    "identifier": [
        {"system": f"{CAPTURE_IDENTIFIER_BASE}/id/program", "value": REGISTRATION_PROGRAM_UID},
        {"system": f"{CAPTURE_IDENTIFIER_BASE}/id/program-code", "value": "PR_ANC"},
        {"system": TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM, "value": REGISTRATION_TRACKED_ENTITY_TYPE_UID},
    ],
    "name": f"D2PR_{REGISTRATION_PROGRAM_UID}",
    "status": "draft",
    "experimental": True,
    "subjectType": ["Patient"],
    "code": [{"system": f"{CAPTURE_CANONICAL}/CodeSystem/d2-form-type-cs", "code": "tracker"}],
    "item": [
        {
            "linkId": REGISTRATION_UNIQUE_ATTRIBUTE,
            "code": [
                {
                    "system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
                    "code": REGISTRATION_UNIQUE_ATTRIBUTE,
                    "display": "National identifier",
                }
            ],
            "text": "National id",
            "type": "string",
            "required": True,
            "extension": [{"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": True}],
        },
        {
            "linkId": REGISTRATION_DATE_ATTRIBUTE,
            "code": [
                {
                    "system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
                    "code": REGISTRATION_DATE_ATTRIBUTE,
                    "display": "Date of birth",
                }
            ],
            "text": "Date of birth",
            "type": "date",
            "extension": [{"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": True}],
        },
        {
            "linkId": REGISTRATION_CODED_ATTRIBUTE,
            "code": [
                {"system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM, "code": REGISTRATION_CODED_ATTRIBUTE, "display": "Sex"}
            ],
            "text": "Sex",
            "type": "choice",
            "answerValueSet": SEX_VALUE_SET,
            "extension": [{"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": True}],
        },
        {
            "linkId": REGISTRATION_PROGRAM_ONLY_ATTRIBUTE,
            "code": [
                {
                    "system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
                    "code": REGISTRATION_PROGRAM_ONLY_ATTRIBUTE,
                    "display": "Household size",
                }
            ],
            "text": "Household size",
            "type": "integer",
            "extension": [
                {"url": "http://hl7.org/fhir/StructureDefinition/minValue", "valueInteger": 1},
                {"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": False},
            ],
        },
    ],
}

#: The option set the registration form's coded attribute is answered from, in id mode like the rest.
SEX_CODE_SYSTEM_BODY: dict[str, Any] = {
    "resourceType": "CodeSystem",
    "id": SEX_CODE_SYSTEM.rsplit("/", 1)[-1],
    "url": SEX_CODE_SYSTEM,
    "status": "draft",
    "content": "complete",
    "caseSensitive": True,
    "valueSet": SEX_VALUE_SET,
    "property": [{"code": "dhis2-code", "uri": OPTION_CODE_PROPERTY_URI, "type": "string"}],
    "concept": [
        {"code": "OpFemale001", "display": "Female", "property": [{"code": "dhis2-code", "valueString": "F"}]},
        {"code": "OpMale00001", "display": "Male", "property": [{"code": "dhis2-code", "valueString": "M"}]},
    ],
    "count": 2,
}

SEX_VALUE_SET_BODY: dict[str, Any] = {
    "resourceType": "ValueSet",
    "id": SEX_VALUE_SET.rsplit("/", 1)[-1],
    "url": SEX_VALUE_SET,
    "status": "draft",
    "compose": {"include": [{"system": SEX_CODE_SYSTEM}]},
}

#: The data-dictionary pair over the attributes the registration forms ask, as `D2TEA_CS` publishes
#: it: the DHIS2 code, the value type, whether DHIS2 declares the attribute unique, and whether it
#: declares it searchable. The household attribute carries no `dhis2-code` on purpose - DHIS2 does
#: not require a code on a tracked entity attribute, and a consumer of this system has to render that
#: absence honestly rather than invent one.
#:
#: Date of birth is the searchable-but-not-unique case, which is the one the widened search default
#: exists for: DHIS2 lets a clerk look somebody up by it, nothing enforces that two people differ in
#: it, and a facade keying on uniqueness alone would refuse the lookup the instance permits.
TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM_BODY: dict[str, Any] = {
    "resourceType": "CodeSystem",
    "id": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM.rsplit("/", 1)[-1],
    "url": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
    "name": "D2TEA_CS",
    "title": "DHIS2 tracked entity attributes",
    "status": "draft",
    "content": "complete",
    "caseSensitive": True,
    "valueSet": TRACKED_ENTITY_ATTRIBUTE_VALUE_SET,
    "property": [
        {"code": "dhis2-code", "uri": f"{CAPTURE_IDENTIFIER_BASE}/property/dhis2-code", "type": "string"},
        {"code": "value-type", "uri": f"{CAPTURE_IDENTIFIER_BASE}/property/value-type", "type": "code"},
        {"code": "unique", "uri": f"{CAPTURE_IDENTIFIER_BASE}/property/unique", "type": "boolean"},
        {"code": "searchable", "uri": f"{CAPTURE_IDENTIFIER_BASE}/property/searchable", "type": "boolean"},
    ],
    "concept": [
        {
            "code": REGISTRATION_DATE_ATTRIBUTE,
            "display": "Date of birth",
            "property": [
                {"code": "dhis2-code", "valueString": "TEA_BIRTH_DATE"},
                {"code": "value-type", "valueCode": "DATE"},
                {"code": "unique", "valueBoolean": False},
                {"code": "searchable", "valueBoolean": True},
            ],
        },
        {
            "code": REGISTRATION_PROGRAM_ONLY_ATTRIBUTE,
            "display": "Household size",
            "property": [
                {"code": "value-type", "valueCode": "INTEGER_POSITIVE"},
                {"code": "unique", "valueBoolean": False},
                {"code": "searchable", "valueBoolean": False},
            ],
        },
        {
            "code": REGISTRATION_UNIQUE_ATTRIBUTE,
            "display": "National identifier",
            "property": [
                {"code": "dhis2-code", "valueString": "TEA_NATIONAL_ID"},
                {"code": "value-type", "valueCode": "TEXT"},
                {"code": "unique", "valueBoolean": True},
                {"code": "searchable", "valueBoolean": True},
            ],
        },
        {
            "code": REGISTRATION_CODED_ATTRIBUTE,
            "display": "Sex",
            "property": [
                {"code": "dhis2-code", "valueString": "TEA_SEX"},
                {"code": "value-type", "valueCode": "TEXT"},
                {"code": "unique", "valueBoolean": False},
                {"code": "searchable", "valueBoolean": False},
            ],
        },
        {
            "code": SPECIMEN_UNIQUE_ATTRIBUTE,
            "display": "Laboratory reference",
            "property": [
                {"code": "dhis2-code", "valueString": "TEA_LAB_REF"},
                {"code": "value-type", "valueCode": "TEXT"},
                {"code": "unique", "valueBoolean": True},
                {"code": "searchable", "valueBoolean": True},
            ],
        },
    ],
    "count": 5,
}

TRACKED_ENTITY_ATTRIBUTE_VALUE_SET_BODY: dict[str, Any] = {
    "resourceType": "ValueSet",
    "id": TRACKED_ENTITY_ATTRIBUTE_VALUE_SET.rsplit("/", 1)[-1],
    "url": TRACKED_ENTITY_ATTRIBUTE_VALUE_SET,
    "name": "D2TEA_VS",
    "title": "DHIS2 tracked entity attributes",
    "status": "draft",
    "compose": {"include": [{"system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM}]},
}

#: The second tracked entity type this project registers, and the one that is not a person. It is
#: what makes the fixture's register more than a Patient surface: `D2TET_CM` takes it onto Specimen,
#: so the facade serves `GET /Specimen` over it with the same machinery `GET /Patient` runs on, and
#: the capture UI has a second typed section to name.
SPECIMEN_TRACKED_ENTITY_TYPE_UID = "TetSample01"
SPECIMEN_TRACKED_ENTITY_TYPE_NAME = "Specimen batch"
SPECIMEN_RESOURCE_TYPE = "Specimen"
SPECIMEN_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{SPECIMEN_TRACKED_ENTITY_TYPE_UID}"

#: The tracked-entity-type vocabulary and the map onto FHIR resource types, as
#: `dhis2w_fhir.resources.questionnaires.documents` emits the pair for a run publishing two types.
TRACKED_ENTITY_TYPE_CODE_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-tet-cs"
TRACKED_ENTITY_TYPE_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-tet-vs"
TRACKED_ENTITY_TYPE_RESOURCE_MAP = f"{CAPTURE_CANONICAL}/ConceptMap/d2-tet-cm"
RESOURCE_TYPE_CODE_SYSTEM = "http://hl7.org/fhir/resource-types"
RESOURCE_TYPE_VALUE_SET = "http://hl7.org/fhir/ValueSet/resource-types"

TRACKED_ENTITY_TYPE_CODE_SYSTEM_BODY: dict[str, Any] = {
    "resourceType": "CodeSystem",
    "id": TRACKED_ENTITY_TYPE_CODE_SYSTEM.rsplit("/", 1)[-1],
    "url": TRACKED_ENTITY_TYPE_CODE_SYSTEM,
    "name": "D2TET_CS",
    "title": "DHIS2 tracked entity types",
    "status": "draft",
    "content": "complete",
    "caseSensitive": True,
    "valueSet": TRACKED_ENTITY_TYPE_VALUE_SET,
    "concept": [
        {"code": REGISTRATION_TRACKED_ENTITY_TYPE_UID, "display": "Person"},
        {"code": SPECIMEN_TRACKED_ENTITY_TYPE_UID, "display": SPECIMEN_TRACKED_ENTITY_TYPE_NAME},
    ],
    "count": 2,
}

TRACKED_ENTITY_TYPE_VALUE_SET_BODY: dict[str, Any] = {
    "resourceType": "ValueSet",
    "id": TRACKED_ENTITY_TYPE_VALUE_SET.rsplit("/", 1)[-1],
    "url": TRACKED_ENTITY_TYPE_VALUE_SET,
    "name": "D2TET_VS",
    "title": "DHIS2 tracked entity types",
    "status": "draft",
    "compose": {"include": [{"system": TRACKED_ENTITY_TYPE_CODE_SYSTEM}]},
}

#: The published contract the register reads at startup: every type this project registers, and the
#: FHIR resource its registrations are served as. Both rows are explicit - the Patient row included,
#: because a map whose defaults were implied would leave a reader unable to tell an unmapped type
#: from a type deliberately published as a person.
TRACKED_ENTITY_TYPE_RESOURCE_MAP_BODY: dict[str, Any] = {
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
                    "code": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
                    "display": "Person",
                    "target": [{"code": "Patient", "equivalence": "equal"}],
                },
                {
                    "code": SPECIMEN_TRACKED_ENTITY_TYPE_UID,
                    "display": SPECIMEN_TRACKED_ENTITY_TYPE_NAME,
                    "target": [{"code": SPECIMEN_RESOURCE_TYPE, "equivalence": "equal"}],
                },
            ],
        }
    ],
}

#: The person-only registration form of the specimen type - the same shape as the Person form, over
#: a type the map takes onto something other than `Patient`, and declaring that resource as its
#: `subjectType` the way the emitter resolves it.
SPECIMEN_QUESTIONNAIRE_BODY: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": SPECIMEN_TRACKED_ENTITY_TYPE_UID,
    "url": SPECIMEN_QUESTIONNAIRE,
    "title": SPECIMEN_TRACKED_ENTITY_TYPE_NAME,
    "description": (
        f"DHIS2 tracked entity type {SPECIMEN_TRACKED_ENTITY_TYPE_NAME} ({SPECIMEN_TRACKED_ENTITY_TYPE_UID}) as a "
        "registration form: the tracked entity attributes the type itself collects."
    ),
    "extension": [{"url": FORM_TYPE_URL, "valueCode": "tracked-entity"}],
    "identifier": [
        {"system": TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM, "value": SPECIMEN_TRACKED_ENTITY_TYPE_UID},
    ],
    "name": f"D2TET_{SPECIMEN_TRACKED_ENTITY_TYPE_UID}",
    "status": "draft",
    "experimental": True,
    "subjectType": [SPECIMEN_RESOURCE_TYPE],
    "code": [{"system": f"{CAPTURE_CANONICAL}/CodeSystem/d2-form-type-cs", "code": "tracked-entity"}],
    "item": [
        {
            "linkId": SPECIMEN_UNIQUE_ATTRIBUTE,
            "code": [
                {
                    "system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
                    "code": SPECIMEN_UNIQUE_ATTRIBUTE,
                    "display": "Laboratory reference",
                }
            ],
            "text": "Laboratory reference",
            "type": "string",
            "required": True,
            "extension": [{"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": True}],
        }
    ],
}

#: The person-only registration form of the same tracked entity type the tracker program registers
#: into. It is generated from the *type* rather than from a program, so it asks the attributes the
#: type itself collects - every one of them entity-level, because there is no enrollment for an
#: answer to land on - names no program at all, and publishes no organisation-unit assignment:
#: DHIS2 hangs one on a data set and on a programme, never on a type.
#:
#: The fixture publishes one so the browser has a whole person-only surface to shelve, open, fill,
#: and submit. It shares `TetPerson01` with the registration form on purpose: a project registering
#: people into one type through two doors is the ordinary arrangement, and it is what makes the
#: patient index's tracked-entity-type set a set rather than a list of one per form.
PERSON_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{REGISTRATION_TRACKED_ENTITY_TYPE_UID}"
TRACKED_ENTITY_TYPE_CODE_IDENTIFIER_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity-type-code"

PERSON_QUESTIONNAIRE_BODY: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    "url": PERSON_QUESTIONNAIRE,
    "title": "Person",
    "description": (
        f"DHIS2 tracked entity type Person ({REGISTRATION_TRACKED_ENTITY_TYPE_UID}) as a registration form: "
        "the tracked entity attributes the type itself collects, captured when a person is registered "
        "without being enrolled in any program."
    ),
    "extension": [{"url": FORM_TYPE_URL, "valueCode": "tracked-entity"}],
    "identifier": [
        {"system": TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM, "value": REGISTRATION_TRACKED_ENTITY_TYPE_UID},
        {"system": TRACKED_ENTITY_TYPE_CODE_IDENTIFIER_SYSTEM, "value": "TET_PERSON"},
    ],
    "name": f"D2TET_{REGISTRATION_TRACKED_ENTITY_TYPE_UID}",
    "status": "draft",
    "experimental": True,
    "subjectType": ["Patient"],
    "code": [{"system": f"{CAPTURE_CANONICAL}/CodeSystem/d2-form-type-cs", "code": "tracked-entity"}],
    "item": [
        {
            "linkId": REGISTRATION_UNIQUE_ATTRIBUTE,
            "code": [
                {
                    "system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
                    "code": REGISTRATION_UNIQUE_ATTRIBUTE,
                    "display": "National identifier",
                }
            ],
            "text": "National id",
            "type": "string",
            "required": True,
            "extension": [{"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": True}],
        },
        {
            "linkId": REGISTRATION_DATE_ATTRIBUTE,
            "code": [
                {
                    "system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM,
                    "code": REGISTRATION_DATE_ATTRIBUTE,
                    "display": "Date of birth",
                }
            ],
            "text": "Date of birth",
            "type": "date",
            "extension": [{"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": True}],
        },
        {
            "linkId": REGISTRATION_CODED_ATTRIBUTE,
            "code": [
                {"system": TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM, "code": REGISTRATION_CODED_ATTRIBUTE, "display": "Sex"}
            ],
            "text": "Sex",
            "type": "choice",
            "answerValueSet": SEX_VALUE_SET,
            "extension": [{"url": ENTITY_LEVEL_EXTENSION, "valueBoolean": True}],
        },
    ],
}

SCOPED_QUESTIONNAIRE_BODY: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": SCOPED_QUESTIONNAIRE_UID,
    "url": SCOPED_QUESTIONNAIRE,
    "title": "Outbreak response",
    "description": "DHIS2 event program Outbreak response (PrScoped001) as a data capture form.",
    "extension": [
        {"url": FORM_TYPE_URL, "valueCode": "event"},
        {
            "url": ORG_UNIT_ASSIGNMENT_EXTENSION,
            "valueReference": {"reference": f"List/{SCOPED_ASSIGNMENT_LIST_ID}"},
        },
    ],
    "identifier": [{"system": f"{CAPTURE_IDENTIFIER_BASE}/id/program", "value": SCOPED_QUESTIONNAIRE_UID}],
    "name": f"D2PR_{SCOPED_QUESTIONNAIRE_UID}",
    "status": "draft",
    "experimental": True,
    "subjectType": ["Location"],
    "item": [{"linkId": "DeCaseCount01", "text": "Cases investigated", "type": "integer"}],
}

app = typer.Typer(add_completion=False, help="Write the capture fixture project used by the browser e2e suite.")


def build_location(unit: OrgUnitFixture) -> dict[str, Any]:
    """One Location, in the shape `dhis2w_fhir.resources.organisation_units.location` emits it."""
    extensions: list[dict[str, Any]] = []
    geometry = unit.boundary
    if unit.point_attachment is not None:
        geometry = {"type": "Point", "coordinates": [unit.point_attachment[0], unit.point_attachment[1]]}
    if unit.malformed_boundary:
        extensions.append(_geometry_attachment(unit, b"this attachment is not GeoJSON"))
    elif geometry is not None:
        feature = {
            "type": "Feature",
            "geometry": geometry,
            "properties": {"dhis2Id": unit.uid, "level": unit.level, "name": unit.name},
        }
        extensions.append(_geometry_attachment(unit, json.dumps(feature, separators=(",", ":")).encode("utf-8")))
    extensions.append(
        {
            "url": ORG_UNIT_LEVEL_EXTENSION,
            "valueCoding": {
                "system": ORG_UNIT_LEVEL_CODE_SYSTEM,
                "code": f"level-{unit.level}",
                "display": f"Level {unit.level}",
            },
        }
    )
    body: dict[str, Any] = {
        "resourceType": "Location",
        "id": unit.uid,
        "description": f"DHIS2 organisation unit {unit.name} ({unit.uid}), level {unit.level} - physical location.",
        "identifier": [
            {"system": ORG_UNIT_IDENTIFIER_SYSTEM, "value": unit.uid},
            {"system": ORG_UNIT_CODE_IDENTIFIER_SYSTEM, "value": unit.code},
        ],
        "name": unit.name,
        "status": "active",
        "extension": extensions,
    }
    if unit.latitude is not None and unit.longitude is not None:
        body["position"] = {"longitude": unit.longitude, "latitude": unit.latitude}
    if unit.parent_uid is not None:
        body["partOf"] = {"reference": f"Location/{unit.parent_uid}"}
    return body


def _geometry_attachment(unit: OrgUnitFixture, payload: bytes) -> dict[str, Any]:
    """The `location-boundary-geojson` extension carrying one payload, in the emitter's own shape."""
    return {
        "url": BOUNDARY_EXTENSION,
        "valueAttachment": {
            "contentType": BOUNDARY_CONTENT_TYPE,
            "data": base64.b64encode(payload).decode("ascii"),
            "title": f"{unit.name} ({unit.uid})",
            "size": len(payload),
        },
    }


def build_registry_exemplar() -> dict[str, Any]:
    """The curated `Usage: #example` Location the IG publishes beside the registry profiles.

    A real generated project ships this: the registry itself is pre-built JSON that SUSHI never
    compiles, so `registry-examples.fsh` builds one worked example per registry profile out of the
    selection's own root unit. It therefore carries that unit's real uid on the real org-unit
    identifier system, under an id derived from the profile rather than from the unit, and with no
    `partOf` - which is exactly the shape that folds into a hierarchy as a second, parentless copy
    of the root. The fixture publishes one so the browser has to deduplicate it rather than showing
    Sierra Leone twice.
    """
    root = ORG_UNITS[0]
    return {
        "resourceType": "Location",
        "id": "d2-location-example",
        "meta": {"profile": [f"{CAPTURE_CANONICAL}/StructureDefinition/d2-location"]},
        "identifier": [
            {"system": ORG_UNIT_IDENTIFIER_SYSTEM, "value": root.uid},
            {"system": ORG_UNIT_CODE_IDENTIFIER_SYSTEM, "value": root.code},
        ],
        "status": "active",
        "name": root.name,
        "extension": [
            {
                "url": ORG_UNIT_LEVEL_EXTENSION,
                "valueCoding": {
                    "system": ORG_UNIT_LEVEL_CODE_SYSTEM,
                    "code": f"level-{root.level}",
                    "display": f"Level {root.level}",
                },
            }
        ],
        "managingOrganization": {"reference": "Organization/d2-organization-example"},
    }


def build_assignment_list(list_id: str, title: str) -> dict[str, Any]:
    """One assignment artifact restricting a form, in the shape the generate target writes it."""
    return {
        "resourceType": "List",
        "id": list_id,
        "status": "current",
        "mode": "snapshot",
        "title": title,
        "entry": [{"item": {"reference": f"Location/{uid}"}} for uid in SCOPED_ASSIGNMENT_UNITS],
    }


def golden(filename: str) -> dict[str, Any]:
    """One dhis2w-fhir golden resource, parsed."""
    parsed: dict[str, Any] = json.loads((GOLDEN_DIRECTORY / filename).read_text(encoding="utf-8"))
    return parsed


def write_resource(path: Path, resource: dict[str, Any]) -> None:
    """Write one resource file, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resource, indent=2) + "\n", encoding="utf-8")


def build_capture_project(destination: Path) -> FhirProject:
    """Write the whole fixture tree into `destination` and answer with the project over it.

    The spool is deliberately not seeded. What the e2e proves is the loop - generate, post, read the
    receipt back - and a pre-seeded receipt would let that pass without the POST ever having worked.
    """
    destination.mkdir(parents=True, exist_ok=True)
    config_path = destination / "fhir.toml"
    config_path.write_text(CAPTURE_FHIR_TOML, encoding="utf-8")

    compiled = destination / "ig" / "fsh-generated" / "resources"
    for filename in (*CAPTURE_QUESTIONNAIRE_FILES, *CAPTURE_SUPPORT_FILES):
        write_resource(compiled / filename, golden(filename))
    write_resource(compiled / f"Questionnaire-{TEMPORAL_QUESTIONNAIRE_UID}.json", TEMPORAL_QUESTIONNAIRE_BODY)
    write_resource(compiled / f"Questionnaire-{SCOPED_QUESTIONNAIRE_UID}.json", SCOPED_QUESTIONNAIRE_BODY)
    write_resource(compiled / f"Questionnaire-{REGISTRATION_PROGRAM_UID}.json", REGISTRATION_QUESTIONNAIRE_BODY)
    write_resource(compiled / f"Questionnaire-{REGISTRATION_TRACKED_ENTITY_TYPE_UID}.json", PERSON_QUESTIONNAIRE_BODY)
    write_resource(compiled / f"Questionnaire-{SPECIMEN_TRACKED_ENTITY_TYPE_UID}.json", SPECIMEN_QUESTIONNAIRE_BODY)

    registry = destination / "ig" / "input" / "resources" / "registry"
    for unit in ORG_UNITS:
        write_resource(registry / f"Location-{unit.uid}.json", build_location(unit))
    write_resource(registry / "Location-d2-location-example.json", build_registry_exemplar())
    write_resource(
        registry / f"List-{SCOPED_ASSIGNMENT_LIST_ID}.json",
        build_assignment_list(SCOPED_ASSIGNMENT_LIST_ID, "Outbreak response - assigned organisation units"),
    )
    write_resource(
        registry / f"List-{REGISTRATION_ASSIGNMENT_LIST_ID}.json",
        build_assignment_list(REGISTRATION_ASSIGNMENT_LIST_ID, "Antenatal care - assigned organisation units"),
    )

    terminology = destination / "ig" / "input" / "resources" / "terminology"
    built = [
        *option_terminology(golden(TRACKER_RESPONSE_FILE)),
        SYMPTOM_CODE_SYSTEM_BODY,
        SYMPTOM_VALUE_SET_BODY,
        SEX_CODE_SYSTEM_BODY,
        SEX_VALUE_SET_BODY,
        TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM_BODY,
        TRACKED_ENTITY_ATTRIBUTE_VALUE_SET_BODY,
        TRACKED_ENTITY_TYPE_CODE_SYSTEM_BODY,
        TRACKED_ENTITY_TYPE_VALUE_SET_BODY,
        TRACKED_ENTITY_TYPE_RESOURCE_MAP_BODY,
    ]
    for resource in built:
        write_resource(terminology / f"{resource['resourceType']}-{resource['id']}.json", resource)

    project = FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())
    for artifact in build_option_set_concept_map_artifacts(
        [SYMPTOM_OPTION_SET],
        project.config.generate,
        project.config.ig.canonical,
        ig_status=project.config.ig.status,
    ):
        path = project.resources_directory / artifact.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")
    return project


def option_terminology(response: dict[str, Any]) -> list[dict[str, Any]]:
    """The CodeSystem / ValueSet pair behind every option set the tracker response answers from.

    The goldens publish the questionnaires and the responses but not the option-set terminology
    they bind, so the pairs are built here in the shape the emitter writes: concept codes are
    DHIS2 option UIDs, and the option code rides along as the `dhis2-code` property.
    """
    resources: list[dict[str, Any]] = []
    for system, concepts in sorted(_codings_by_system(response).items()):
        code_system_id = system.rsplit("/", 1)[-1]
        value_set_id = f"{code_system_id.removesuffix('-cs')}-vs"
        value_set_url = f"{CAPTURE_CANONICAL}/ValueSet/{value_set_id}"
        resources.append(
            {
                "resourceType": "CodeSystem",
                "id": code_system_id,
                "url": system,
                "status": "draft",
                "content": "complete",
                "caseSensitive": True,
                "valueSet": value_set_url,
                "property": [
                    {
                        "code": "dhis2-code",
                        "uri": OPTION_CODE_PROPERTY_URI,
                        "description": "DHIS2 option code.",
                        "type": "string",
                    }
                ],
                "concept": [
                    {
                        "code": code,
                        "display": display,
                        "property": [{"code": "dhis2-code", "valueString": _option_code(display)}],
                    }
                    for code, display in sorted(concepts.items())
                ],
                "count": len(concepts),
            }
        )
        resources.append(
            {
                "resourceType": "ValueSet",
                "id": value_set_id,
                "url": value_set_url,
                "status": "draft",
                "compose": {"include": [{"system": system}]},
            }
        )
    return resources


@app.command()
def write(
    destination: Annotated[Path, typer.Argument(help="Directory to write the fixture project into.")],
) -> None:
    """Write the fixture project into a fresh spool, and print the directory it landed in.

    The spool is emptied first. The browser suite asserts that a receipt it just posted appears in
    the listing, and leftovers from the previous run would let that pass without this run's POST
    ever having worked.
    """
    shutil.rmtree(destination / SPOOL_RELATIVE_PATH, ignore_errors=True)
    project = build_capture_project(destination)
    typer.echo(str(project.project_root))


def _codings_by_system(response: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Every coded answer of one response golden, as `code -> display` per code system."""
    found: dict[str, dict[str, str]] = {}

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            for answer in item.get("answer", []):
                coding = answer.get("valueCoding")
                if coding is not None:
                    found.setdefault(coding["system"], {})[coding["code"]] = coding.get("display", "")
            walk(item.get("item", []))

    walk(response.get("item", []))
    return found


def _option_code(display: str) -> str:
    """A stable DHIS2-style option code for a synthesised concept, derived from its display."""
    return "".join(character if character.isalnum() else "_" for character in display).upper().strip("_")


if __name__ == "__main__":
    app()
