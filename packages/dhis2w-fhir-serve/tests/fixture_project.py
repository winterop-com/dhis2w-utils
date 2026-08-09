"""The IG project the serve tests and the browser e2e both run against, written to a directory.

The resources are the dhis2w-fhir goldens - one Questionnaire per form kind plus the terminology
they bind - so a test that accepts them is a test that the facade accepts the documented contract.

This lives outside `conftest.py` because two callers need it and only one of them is pytest. The
Playwright suite boots a real `d2w fhir serve --ui` and needs the same tree on disk first, which it
gets by running this module:

    uv run python packages/dhis2w-fhir-serve/tests/fixture_project.py <destination>

Building it rather than committing it keeps one copy of the goldens in the workspace. A committed
second copy would be the same bytes going stale the first time the emitter changes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated, Any

import typer
from dhis2w_fhir.config import FhirProject, load_fhir_config
from dhis2w_fhir_serve.spool import SPOOL_RELATIVE_PATH

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

SYMPTOM_VALUE_SET_BODY: dict[str, Any] = {
    "resourceType": "ValueSet",
    "id": SYMPTOM_VALUE_SET.rsplit("/", 1)[-1],
    "url": SYMPTOM_VALUE_SET,
    "status": "draft",
    "compose": {"include": [{"system": SYMPTOM_CODE_SYSTEM}]},
}

app = typer.Typer(add_completion=False, help="Write the capture fixture project used by the browser e2e suite.")


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

    terminology = destination / "ig" / "input" / "resources" / "terminology"
    built = [*option_terminology(golden(TRACKER_RESPONSE_FILE)), SYMPTOM_CODE_SYSTEM_BODY, SYMPTOM_VALUE_SET_BODY]
    for resource in built:
        write_resource(terminology / f"{resource['resourceType']}-{resource['id']}.json", resource)

    return FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())


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
