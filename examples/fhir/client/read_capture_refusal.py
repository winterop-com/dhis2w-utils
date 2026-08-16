"""A facade refusing three submissions, and the answer that says why in each case.

Every refusal is one HTTP response carrying an OperationOutcome, and every issue inside it locates
itself: `code` says what kind of problem it is, `expression` says where in the document it sits, and
`diagnostics` says it in words. A phase collects everything it finds before answering, so a client
fixes a whole class of problem per round trip instead of one fault at a time.

**The status is the fault line, and it is worth reading before anything else.**

- **400** means the bytes are not a submission this endpoint can read at all. The document is
  malformed, or it is some other kind of FHIR resource, or it carries a key the resource does not
  have. Nothing has been checked against any form yet, because there is nothing to check.
- **422** means the document was read fine and is wrong about the DHIS2 world. The form was found,
  and the submission disagrees with what that form asks - an answer typed differently from the data
  element it answers, a question the form does not ask, a report claiming a period it cannot.
- **415** is earlier still: the `Content-Type` says the body is not JSON, so it is refused unread.

A 400 is a bug in the sending code. A 422 is a bug in what was filled in. They are fixed by
different people, which is why the facade is careful to say which it met.

Usage:
    d2w fhir serve --port 8123           # in the project directory, in another shell
    uv run python examples/fhir/client/read_capture_refusal.py
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from _fixture import aggregate_form_id, served_facade

FHIR_JSON = "application/fhir+json"


async def refused(client: httpx.AsyncClient, what: str, body: str, *, content_type: str = FHIR_JSON) -> None:
    """Post one submission that will not be accepted, and print the answer in full."""
    answer = await client.post("/QuestionnaireResponse", content=body, headers={"Content-Type": content_type})
    print(f"\n{what} -> HTTP {answer.status_code}")
    for issue in answer.json().get("issue", []):
        location = (issue.get("expression") or ["the request"])[0]
        print(f"  [{issue['code']}] at {location}")
        print(f"    {issue['diagnostics']}")


def first_answered(items: list[dict[str, Any]]) -> str:
    """The link id of the first question the draft answered, walking through the groups above it."""
    for item in items:
        if item.get("answer"):
            return str(item["linkId"])
        nested = first_answered(item.get("item", []))
        if nested:
            return nested
    return ""


async def main() -> None:
    """Meet a malformed submission, one the models will not read, and one that is merely wrong."""
    async with httpx.AsyncClient(base_url=served_facade(), headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        # A valid submission to spoil. Whatever is wrong below is wrong on purpose and only there.
        draft: dict[str, Any] = (
            (await client.get(f"/Questionnaire/{aggregate_form_id()}/$generate", params={"seed": 11}))
            .raise_for_status()
            .json()
        )

        # MALFORMED, in the plainest way: not a capture at all. A facade will not guess what an
        # Observation was meant to be, and refuses before it looks at any form.
        await refused(
            client,
            "a body that is some other kind of FHIR resource",
            json.dumps({"resourceType": "Observation", "status": "final"}),
        )

        # STILL MALFORMED, and this is the one that catches real clients: an unknown key anywhere in
        # the document is refused rather than dropped. A misspelled element that travelled silently
        # would be a value nobody notices missing until an audit months later.
        misspelled = dict(draft)
        misspelled["reporter"] = "clinic tablet 7"
        await refused(client, "a body carrying a key the resource does not have", json.dumps(misspelled))

        # WELL FORMED AND WRONG. This is a perfectly good QuestionnaireResponse; it is wrong about
        # the form it claims to answer. Two faults, both in the same phase, so both come back at
        # once: a value typed differently from the data element it answers, and a question this form
        # does not ask. Neither is visible until the form is resolved, which is why this is a 422.
        answered = draft.get("item") or []
        wrong: dict[str, Any] = dict(draft)
        wrong["item"] = [
            {"linkId": first_answered(answered), "answer": [{"valueString": "about forty"}]},
            {"linkId": "notAQuestionOfThisForm", "answer": [{"valueInteger": 1}]},
        ]
        await refused(client, "answers that break the form's own rules", json.dumps(wrong))

        # EARLIEST OF ALL: the declaration says the body is not JSON, so it is never read.
        await refused(
            client,
            "a body declared as something this endpoint does not parse",
            "<QuestionnaireResponse/>",
            content_type="application/fhir+xml",
        )


if __name__ == "__main__":
    asyncio.run(main())
