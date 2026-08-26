"""A chart review of one person in the DHIS2 register, written as CQL - the `registered` context.

`context.kind = "registered"` names one tracked entity by its DHIS2 UID, and the facade reads it out
of the instance and projects it exactly the way `GET /Patient/{uid}` does. Nothing is posted and
nothing is stored: the person is in DHIS2, the question is in the request, and the answer comes back
over HTTP. A facade serving a compiled guide with no instance behind it refuses this context by
name - it is `--live` only.

What a register record actually carries is worth saying plainly, because it decides how the library
reads. DHIS2 states a person as a tracked entity type plus a bag of tracked entity attribute values,
so the projection carries the UID as an `identifier`, the type as a `meta.tag`, and every attribute
as a `d2-tracked-entity-attribute-value` extension holding an `attributeId` and a `value`. There is
no `Patient.name` and no `Patient.birthDate` unless a project nominates one under `[ips.identity]` -
`examples/fhir/client/identity_nominations.py` is that feature.

So the library here does what a chart review does: it asks who this record is, what kind of record
it is, and what was written down about them. One CQL function does the reaching-into-an-extension
work once, and one define per attribute reads like a line of a chart. The attribute UIDs are not
typed into this file - they are read off the guide's own `CodeSystem`, so the library is written from
the vocabulary the server publishes rather than from a list somebody kept in their head.

Usage:
    d2w fhir serve --live --port 8123   # in the project directory, in another shell
    uv run python examples/fhir/client/evaluate_registered_person.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
from _fixture import served_facade
from _runner import run_example

#: The register the guide publishes people under. The type is named rather than assumed: a project
#: tracking something other than people publishes its register under whatever its map states.
PERSON_RESOURCE_TYPE = "Patient"

#: The guide's own vocabularies: one concept per tracked entity type, one per tracked entity
#: attribute. Both are published by `d2w fhir generate` off the instance's metadata.
TRACKED_ENTITY_TYPE_CODE_SYSTEM = "d2-tet-cs"
TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM = "d2-tea-cs"

#: How many of the register's people to look at before choosing one to review.
#:
#: A record with nothing written on it is a true answer and a dull chart, so the person with the
#: most attributes recorded on this page is the one reviewed.
REGISTER_PAGE = 20

#: The extension every tracked entity attribute value rides under, relative to the guide's canonical.
ATTRIBUTE_VALUE_EXTENSION = "StructureDefinition/d2-tracked-entity-attribute-value"

#: The two defines that are the library's plumbing rather than a line of the chart.
#:
#: They answer, and a caller reading every row would see them - a library states its working out
#: loud, and a define is a define. They are held back here so the chart reads as a chart.
HELPER_DEFINITIONS = ("Attribute Value Extension", "Attribute Values")


async def main() -> None:
    """Read the guide's vocabulary, pick a person, write a library from both, and review the record."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        print(f"evaluating against {base_url}")

        canonical = await guide_canonical(client)
        types = await concepts(client, TRACKED_ENTITY_TYPE_CODE_SYSTEM)
        attributes = await concepts(client, TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM)
        print()
        print(f"the guide publishes {len(types)} tracked entity type(s) and {len(attributes)} attribute(s):")
        for code, display in attributes.items():
            print(f"  {code}  {display}")

        person = await someone(client)
        print()
        print(f"reviewing {PERSON_RESOURCE_TYPE}/{person} - a tracked entity UID, read live out of DHIS2")

        library = chart_review_library(canonical, types, attributes)
        answered = await evaluate(client, library, person)
        print()
        declared = len(answered["definitions"])
        print(
            f"the library declares {declared} define(s) - {len(HELPER_DEFINITIONS)} of them plumbing, the rest chart:"
        )
        for row in answered["results"]:
            if row["name"] in HELPER_DEFINITIONS:
                continue
            print(f"  {row['name']:26} {said(row)}")
        for diagnostic in answered["diagnostics"]:
            print(f"  {diagnostic['kind']} error: {diagnostic['message'].splitlines()[0]}")

        # The type code the record carries is a DHIS2 UID, and a UID is not a chart line. The facade's
        # own terminology service turns it into the concept the guide published under it - which is
        # the coded check a reader actually wants: is this code one this guide knows, and what is it?
        type_code = one(answered, "Register Type")
        if type_code is not None:
            checked = await client.get(
                "/terminology/validate-code",
                params={"system": f"{canonical}/CodeSystem/{TRACKED_ENTITY_TYPE_CODE_SYSTEM}", "code": type_code},
            )
            verdict = checked.raise_for_status().json()
            known = "known to this guide" if verdict["result"] else "not a code this guide publishes"
            print()
            print(f"  the record's type code {type_code} is {known}: {verdict['display'] or verdict['message']}")


def chart_review_library(canonical: str, types: dict[str, str], attributes: dict[str, str]) -> str:
    """The CQL a chart review is, written from the vocabulary the server publishes.

    One function does the extension-walking once; one define per attribute reads a line of the chart.
    Every define uses the query form rather than `First(...)` - a register record is one resource, so
    a collection of one is the honest answer and a scalar would be a claim the data does not make.
    """
    person_type = next(iter(types), "")
    lines = [
        "library RegisterChartReview version '1.0'",
        "using FHIR version '4.0.1'",
        "",
        f"define \"Attribute Value Extension\": '{canonical}/{ATTRIBUTE_VALUE_EXTENSION}'",
        "",
        "// Every attribute value the record carries, unwrapped from the extension it rides in.",
        'define "Attribute Values": flatten ([Patient] P return P.extension)',
        "",
        "// What was written down for one named attribute, or nothing where nobody wrote anything.",
        'define function "Recorded"(attributeId String):',
        '  flatten (("Attribute Values") E',
        '    where E.url = "Attribute Value Extension"',
        "      and exists ((E.extension) A where A.url = 'attributeId' and A.valueString = attributeId)",
        "    return ((E.extension) V where V.url = 'value' return V.valueString))",
        "",
        "// Who this record is, and what kind of record it is.",
        'define "Tracked Entity UID": flatten ([Patient] P return (P.identifier) I return I.value)',
        'define "Register Type": flatten ([Patient] P return (P.meta.tag) T return T.code)',
        'define "Attributes Recorded": [Patient] P return Count(P.extension)',
        f'define "Is A Person Record": exists (flatten ([Patient] P return (P.meta.tag) T '
        f"where T.code = '{person_type}'))",
        "",
        "// One line of the chart per attribute the guide publishes.",
    ]
    lines.extend(f'define "{display}": "Recorded"(\'{code}\')' for code, display in attributes.items())
    return "\n".join(lines)


async def guide_canonical(client: httpx.AsyncClient) -> str:
    """The canonical every url of this guide is built from, read off one of its own resources."""
    listed = (await client.get("/CodeSystem", params={"_count": 1})).raise_for_status().json()
    url = str(listed["entry"][0]["resource"]["url"])
    return url.rsplit("/CodeSystem/", 1)[0]


async def concepts(client: httpx.AsyncClient, code_system_id: str) -> dict[str, str]:
    """Every concept one of the guide's CodeSystems publishes, as code to display."""
    read = (await client.get(f"/CodeSystem/{code_system_id}")).raise_for_status().json()
    return {concept["code"]: concept.get("display", concept["code"]) for concept in read.get("concept", [])}


async def someone(client: httpx.AsyncClient) -> str:
    """The tracked entity UID of the person on the register's first page with the most written down."""
    page = (await client.get(f"/{PERSON_RESOURCE_TYPE}", params={"_count": REGISTER_PAGE})).raise_for_status().json()
    people = [entry["resource"] for entry in page.get("entry", [])]
    if not people:
        message = "this facade's register holds nobody - seed the instance, or point the example at one that does"
        raise SystemExit(message)
    richest = max(people, key=lambda person: len(person.get("extension", [])))
    return str(richest["id"])


async def evaluate(client: httpx.AsyncClient, library: str, tracked_entity_uid: str) -> dict[str, Any]:
    """One CQL library over one tracked entity the DHIS2 instance holds."""
    answered = await client.post(
        "/evaluate",
        json={
            "language": "cql",
            "source": library,
            "context": {
                "kind": "registered",
                "resource_type": PERSON_RESOURCE_TYPE,
                "tracked_entity_uid": tracked_entity_uid,
            },
        },
    )
    if answered.status_code != 200:
        for issue in answered.json().get("issue", []):
            print(f"  refused: {issue['diagnostics']}")
        answered.raise_for_status()
    body: dict[str, Any] = answered.json()
    return body


def said(row: dict[str, Any]) -> str:
    """One define's answer as a chart line: what it says, or that nobody wrote anything down."""
    if row["refusal"] is not None:
        return f"refused - {row['refusal']}"
    values = row["values"]
    if not values:
        return "(nothing recorded)"
    if len(values) == 1:
        return str(values[0])
    return ", ".join(str(value) for value in values)


def one(answered: dict[str, Any], name: str) -> str | None:
    """The single value one named define answered, or None where it answered nothing."""
    for row in answered["results"]:
        if row["name"] == name and row["values"]:
            return str(row["values"][0])
    return None


if __name__ == "__main__":
    run_example(main)
