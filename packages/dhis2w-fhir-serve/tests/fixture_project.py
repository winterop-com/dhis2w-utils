"""The IG project the serve tests and the browser e2e both run against, written to a directory.

The resources are the dhis2w-fhir goldens - one Questionnaire per form kind plus the terminology
they bind, and the ConceptMap the emitter writes beside one of the option sets - so a test that
accepts them is a test that the facade accepts the documented contract.

Beside them sits an organisation-unit registry: nine Locations over four levels, carrying every
geometry state a real selection produces, plus the assignment List that restricts one form to two
of them. The goldens publish no registry, and a browser that folds `partOf` into a tree, decodes a
boundary, and joins an assignment needs one to fold, decode, and join.

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
"""

#: The compiled Questionnaires the capture project serves - one per form kind, plus the tracker
#: stage carrying a required question and a numeric bound.
CAPTURE_QUESTIONNAIRE_FILES = (
    "Questionnaire-BfMAe6Itzgt.json",
    "Questionnaire-EVTsupVis01.json",
    "Questionnaire-ZzYYXq4fJie.json",
    "Questionnaire-PsAncVisit1.json",
)

#: The data-dictionary terminology every generated form draws its question codes from.
CAPTURE_SUPPORT_FILES = (
    "CodeSystem-d2-de-cs.json",
    "CodeSystem-d2-coc-cs.json",
    "ValueSet-d2-de-vs.json",
    "ValueSet-d2-coc-vs.json",
)

AGGREGATE_RESPONSE_FILE = "QuestionnaireResponse-BfMAe6Itzgt-example-1.json"
EVENT_RESPONSE_FILE = "QuestionnaireResponse-EVTsupVis01-example-1.json"
TRACKER_RESPONSE_FILE = "QuestionnaireResponse-ZzYYXq4fJie-example-1.json"

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
    """Publishes a boundary attachment whose payload is not GeoJSON, which a reader must skip rather than crash on."""


def _square(west: float, south: float, east: float, north: float) -> list[list[list[float]]]:
    """One closed rectangular ring, as a Polygon's coordinate list."""
    return [[[west, south], [east, south], [east, north], [west, north], [west, south]]]


#: The fixture's organisation-unit hierarchy - four levels, nine units, every geometry state.
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
    if unit.malformed_boundary:
        payload = b"this attachment is not GeoJSON"
        extensions.append(
            {
                "url": BOUNDARY_EXTENSION,
                "valueAttachment": {
                    "contentType": BOUNDARY_CONTENT_TYPE,
                    "data": base64.b64encode(payload).decode("ascii"),
                    "title": f"{unit.name} ({unit.uid})",
                    "size": len(payload),
                },
            }
        )
    elif unit.boundary is not None:
        feature = {
            "type": "Feature",
            "geometry": unit.boundary,
            "properties": {"dhis2Id": unit.uid, "level": unit.level, "name": unit.name},
        }
        payload = json.dumps(feature, separators=(",", ":")).encode("utf-8")
        extensions.append(
            {
                "url": BOUNDARY_EXTENSION,
                "valueAttachment": {
                    "contentType": BOUNDARY_CONTENT_TYPE,
                    "data": base64.b64encode(payload).decode("ascii"),
                    "title": f"{unit.name} ({unit.uid})",
                    "size": len(payload),
                },
            }
        )
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


def build_assignment_list() -> dict[str, Any]:
    """The assignment artifact restricting the scoped form, in the shape the generate target writes it."""
    return {
        "resourceType": "List",
        "id": SCOPED_ASSIGNMENT_LIST_ID,
        "status": "current",
        "mode": "snapshot",
        "title": "Outbreak response - assigned organisation units",
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

    registry = destination / "ig" / "input" / "resources" / "registry"
    for unit in ORG_UNITS:
        write_resource(registry / f"Location-{unit.uid}.json", build_location(unit))
    write_resource(registry / f"List-{SCOPED_ASSIGNMENT_LIST_ID}.json", build_assignment_list())

    terminology = destination / "ig" / "input" / "resources" / "terminology"
    built = [*option_terminology(golden(TRACKER_RESPONSE_FILE)), SYMPTOM_CODE_SYSTEM_BODY, SYMPTOM_VALUE_SET_BODY]
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
