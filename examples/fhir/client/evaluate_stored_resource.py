"""Ask a served guide about one of its own resources - FHIRPath one-liners over a `stored` context.

`context.kind = "stored"` names a resource by type and id, the way a read names one, and the
expression runs over exactly what `GET /Questionnaire/{id}` would have answered. Nothing is posted:
the document is already on the server, so the request carries the question and nothing else.

That turns the facade into something you can interrogate. A DHIS2 data set becomes a `Questionnaire`
whose sections are groups, whose data elements are groups inside those, and whose category
combination cells are the answerable items at the bottom - and one line of FHIRPath counts each
storey without downloading the form or writing a parser for it.

The last call names a resource the guide does not hold. That is the one thing on this page that is
not a 200: a stored context is a promise the server can keep or refuse, and a refusal is an
`OperationOutcome` with a 4xx, not an empty answer pretending the question was asked.

Usage:
    d2w fhir serve --port 8123          # in the project directory, in another shell
    uv run python examples/fhir/client/evaluate_stored_resource.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
from _fixture import aggregate_form_id, served_facade
from _runner import run_example

#: The questions asked of the stored form, each with the reason it is worth asking.
#:
#: Read top to bottom they are one form's anatomy: what it is called, what its sections are, how
#: many data elements sit under them, and how many answerable cells those data elements open up.
QUESTIONS: tuple[tuple[str, str], ...] = (
    ("Questionnaire.title", "the DHIS2 data set's own name, carried through unchanged"),
    ("Questionnaire.subjectType", "who a response is about - a Location, because a data set reports at a place"),
    ("Questionnaire.item.text", "the sections, which are the data set's own section names"),
    ("Questionnaire.item.item.count()", "the data elements inside those sections"),
    ("Questionnaire.item.item.item.count()", "the answerable cells - one per category combination of each element"),
    ("Questionnaire.item.item.item.type.distinct()", "every answer type the form asks for, listed once each"),
    ("Questionnaire.item.item.item.where(type = 'integer').count()", "how many of those cells take a whole number"),
)

#: One expression whose answer is a link id, which is where the DHIS2 identity of a cell lives.
LINK_ID_EXPRESSION = "Questionnaire.item.item.item.linkId"

#: How many link ids to print. There are over a hundred and they all have the same shape.
LINK_ID_SAMPLE = 3

#: A resource id no guide publishes, so the stored context has nothing to resolve.
ABSENT_RESOURCE_ID = "no-such-form"


async def main() -> None:
    """Ask one stored Questionnaire seven questions, sample its link ids, then name a resource nobody holds."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    form_id = aggregate_form_id()
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        print(f"evaluating against {base_url}")
        print(f"stored context: Questionnaire/{form_id}, read off the server rather than posted")
        print()

        for expression, why in QUESTIONS:
            answered = await evaluate(client, expression, form_id)
            print(f"  {expression}")
            print(f"    {said(answered)}")
            print(f"    {why}")

        # A link id is not a FHIR invention: it is `{dataElement}.{categoryOptionCombo}`, which is
        # exactly the pair DHIS2 needs to store one number. A capture posts answers keyed by these.
        answered = await evaluate(client, LINK_ID_EXPRESSION, form_id)
        values = answered["results"][0]["values"] if answered["results"] else []
        print()
        print(f"  {LINK_ID_EXPRESSION}")
        print(f"    {len(values)} link id(s), the first {LINK_ID_SAMPLE}: {values[:LINK_ID_SAMPLE]}")
        print("    each is {dataElement}.{categoryOptionCombo} - the DHIS2 identity a capture is keyed by")

        # A stored context this server cannot resolve. Not an empty answer: the question was never
        # asked, and the facade says so with the type and the id it was given.
        print()
        refused = await client.post(
            "/evaluate",
            json={
                "language": "fhirpath",
                "source": "Questionnaire.title",
                "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": ABSENT_RESOURCE_ID},
            },
        )
        print(f"  naming Questionnaire/{ABSENT_RESOURCE_ID}: HTTP {refused.status_code}")
        for issue in refused.json().get("issue", []):
            print(f"    {issue['code']}: {issue['diagnostics']}")


async def evaluate(client: httpx.AsyncClient, expression: str, resource_id: str) -> dict[str, Any]:
    """One FHIRPath expression over one resource the served guide already holds."""
    answered = await client.post(
        "/evaluate",
        json={
            "language": "fhirpath",
            "source": expression,
            "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": resource_id},
        },
    )
    answered.raise_for_status()
    body: dict[str, Any] = answered.json()
    return body


def said(answered: dict[str, Any]) -> str:
    """One outcome as a line to read: the collection it answered, or the diagnostic that stopped it."""
    for diagnostic in answered["diagnostics"]:
        return f"{diagnostic['kind']} error: {diagnostic['message'].splitlines()[0]}"
    values = answered["results"][0]["values"] if answered["results"] else []
    if not values:
        return "matched nothing - the document does not say"
    if len(values) == 1:
        return f"{values[0]!r}"
    return f"{values}"


if __name__ == "__main__":
    run_example(main)
