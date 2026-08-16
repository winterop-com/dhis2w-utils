"""Capture against a facade from a stack that has never heard of DHIS2 tooling - httpx and a JSON body.

Nothing that reads the form, builds the document, or posts it imports anything of this project's.
That is the point: a facade is an ordinary HTTP endpoint taking an ordinary JSON document, and the
document below is short enough to rewrite in Kotlin, C#, Go, or a shell script in an afternoon.
Every DHIS2 concept a submission carries is annotated where it sits.

The one exception is finding a server to talk to. Name `D2W_FHIR_EXAMPLE_FACADE` and this file
imports nothing at all; leave it unset and it asks the fixture beside it for the address of the one
that runs with these examples. That is a question about where a server is, not about how to use it.

The two reads a client cannot skip, and why:

- **the guide's canonical** - every URL in the body hangs off it, and it is stated by the form
  itself (`Questionnaire.url`). Read it once from any served form, then hard-code it;
- **the form's link ids** - a `linkId` is the DHIS2 UID of what is being answered, and a client that
  invents one is refused. A data element on its own is `<dataElementUid>`; one cell of a
  disaggregated data set is `<dataElementUid>.<categoryOptionComboUid>`.

Everything else in the body is literal, and every value in it is one a person could type.

Usage:
    d2w fhir serve --port 8123           # in the project directory, in another shell
    D2W_FHIR_EXAMPLE_FACADE=http://127.0.0.1:8123 uv run python examples/fhir/client/send_without_the_library.py
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

FHIR_JSON = "application/fhir+json"
OK = 200
CREATED = 201

DATA_SET = "BfMAe6Itzgt"
"""The DHIS2 data set being reported. A form is served under the UID of the object it came from."""

ORGANISATION_UNIT = "y77LiPqLMoq"
"""The DHIS2 organisation unit the report is for. Published as a Location, named as `Location/<uid>`.

It has to be a unit the data set is actually assigned to: the facade accepts a capture reported
anywhere the guide publishes, but DHIS2 refuses one outside the assignment with E1029 when the
receipt is forwarded, and the facade says so in a warning on the 201."""


def capture_body(guide: str, form_url: str, link_id: str) -> dict[str, Any]:
    """One month of one data set, at one organisation unit, as the JSON a facade receives."""
    return {
        "resourceType": "QuestionnaireResponse",
        # WHICH FORM. The full canonical of the form being answered - not the bare UID.
        "questionnaire": form_url,
        # THE COMPLETENESS CLAIM. A data set report is filed as reported, so this has to be
        # "completed": the facade refuses a half-finished one rather than keep a receipt for a
        # report nobody made. Keep drafts on your own side and post once, on the submit.
        "status": "completed",
        # WHERE. The DHIS2 organisation unit, as a reference to its published Location.
        "subject": {"reference": f"Location/{ORGANISATION_UNIT}"},
        "extension": [
            # WHICH KIND OF DHIS2 OBJECT this answers. "aggregate" is a data set report.
            {"url": f"{guide}/StructureDefinition/d2-form-type", "valueCode": "aggregate"},
            # WHEN. The DHIS2 reporting period, in DHIS2's own ISO spelling, with the frequency
            # beside it. The form states the frequency it expects, so a client never guesses.
            {
                "url": f"{guide}/StructureDefinition/d2-period",
                "extension": [
                    {"url": "iso", "valueString": "202601"},
                    {"url": "type", "valueCode": "Monthly"},
                ],
            },
        ],
        # THE VALUES. One entry per answered question; linkId is the DHIS2 UID being answered, and
        # the value element is typed after the data element's DHIS2 value type - valueInteger for an
        # integer, valueDecimal for a number, valueString for text, valueCoding for an option set.
        "item": [{"linkId": link_id, "answer": [{"valueInteger": 42}]}],
    }


def first_question(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The first item of a form that takes an answer, walking through the groups that only nest others."""
    for item in items:
        if item.get("type") not in ("group", "display"):
            return item
        nested = first_question(item.get("item", []))
        if nested is not None:
            return nested
    return None


def facade_base_url() -> str:
    """The facade to post to: the one an operator names, or the one the fixture stands up.

    This is the only line of this file that knows the fixture exists, and it is about finding a
    server rather than about talking to one - everything below is plain HTTP against an address,
    which is the point of the file. Name `D2W_FHIR_EXAMPLE_FACADE` and nothing here imports
    anything at all.
    """
    named = os.environ.get("D2W_FHIR_EXAMPLE_FACADE", "").strip()
    if named:
        return named.rstrip("/")
    from _fixture import served_facade

    started: str = served_facade()
    return started.rstrip("/")


async def main() -> None:
    """Read the form, post one filled copy of it, and print what the facade answered."""
    base_url = facade_base_url()
    async with httpx.AsyncClient(base_url=base_url, headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        form = await client.get(f"/Questionnaire/{DATA_SET}")
        if form.status_code != OK:
            print(f"the facade at {base_url} serves no form `{DATA_SET}` - set DATA_SET to one it does")
            return
        published = form.json()
        form_url = published["url"]
        guide = form_url.rsplit("/Questionnaire/", 1)[0]
        question = first_question(published.get("item", []))
        if question is None:
            print(f"`{DATA_SET}` asks nothing, so there is nothing to report")
            return
        print(f"guide: {guide}")
        print(f"answering {question['linkId']} ({question.get('text', '-')})")

        body = capture_body(guide, form_url, question["linkId"])
        print(json.dumps(body, indent=2))

        sent = await client.post(
            "/QuestionnaireResponse",
            content=json.dumps(body),
            headers={"Content-Type": FHIR_JSON},
        )
        print(f"\nPOST /QuestionnaireResponse -> {sent.status_code}")
        for issue in sent.json().get("issue", []):
            print(f"  [{issue['severity']}] {issue.get('diagnostics')}")
        if sent.status_code == CREATED:
            # The receipt lives at the Location header. The body is an OperationOutcome, so the id
            # is not in it - and the submission is held at the facade, not yet sent to DHIS2.
            print(f"  receipt: {sent.headers['location']}")


if __name__ == "__main__":
    asyncio.run(main())
