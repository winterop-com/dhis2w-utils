"""Send one submission to a running facade and read the receipt it is handed back.

What a 201 means here is narrower than it looks, and the whole example is about that line:
the facade understood the submission, checked it against the published form, and wrote it to
disk durably. **Nothing has reached DHIS2.** No data value exists, no event exists, no data set
is registered complete. `d2w fhir forward` is what drains the queue into an instance, and until
it runs the receipt is a promise the facade made about bytes it is holding, nothing more.

Two shapes of the answer surprise a first-time sender, and both are R4 doing what R4 says:

- **The body is not the resource.** A `create` answers an OperationOutcome saying what happened,
  so the receipt's id is not in the body at all - it is the last segment of the `Location` header,
  which is where the receipt is served from.
- **The receipt is the submission, not a view of DHIS2.** Reading it back gives the bytes that
  were sent, which is why it is worth keeping: it is the evidence of what a reporter reported.

Usage:
    d2w fhir serve --port 8123           # in the project directory, in another shell
    uv run python examples/fhir/client/send_response.py
"""

from __future__ import annotations

import asyncio

import httpx
from _fixture import aggregate_form_id, served_facade

FHIR_JSON = "application/fhir+json"
CREATED = 201
"""What an accepted submission answers. Anything else carries an OperationOutcome saying why not."""


async def main() -> None:
    """Post one filled form, then read back everything the facade said about it."""
    base_url = served_facade()
    async with httpx.AsyncClient(base_url=base_url, headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        # $generate fills the form against its own rules, so the submission below is the server's
        # own idea of a valid one. A real client fills it from what a reporter typed.
        form_id = aggregate_form_id()
        draft = (
            (await client.get(f"/Questionnaire/{form_id}/$generate", params={"seed": 20260})).raise_for_status().json()
        )

        sent = await client.post("/QuestionnaireResponse", json=draft, headers={"Content-Type": FHIR_JSON})
        print(f"POST /QuestionnaireResponse -> {sent.status_code}")
        if sent.status_code != CREATED:
            for issue in sent.json().get("issue", []):
                print(f"  refused [{issue.get('code')}] {issue.get('diagnostics')}")
            return

        # The information issue states, in the server's own words, what was and was not done.
        for issue in sent.json().get("issue", []):
            print(f"  [{issue['severity']}] {issue.get('diagnostics')}")

        # The id comes off the header because the body is an OperationOutcome. A client that goes
        # looking for it in the body finds nothing, on every capture the facade ever accepts.
        location = sent.headers["location"]
        receipt_id = location.rsplit("/", 1)[-1]
        print(f"  Location: {location}")
        print(f"  receipt id: {receipt_id}")

        # The receipt is the submission as it arrived, held for the forwarder. It is not a report
        # of anything DHIS2 holds - at this point the instance has never heard of it.
        receipt = (await client.get(f"/QuestionnaireResponse/{receipt_id}")).raise_for_status().json()
        print(f"  answers {receipt['questionnaire']}")
        print(f"  status {receipt['status']}, {len(receipt.get('item', []))} top-level item(s)")
        print(f"  identical to what was sent: {receipt.get('item') == draft.get('item')}")

        # Not yet sent to DHIS2 is a state of its own, and it is the one this receipt is in.
        counts = (
            (await client.get("/facade/spool", headers={"Accept": "application/json"}))
            .raise_for_status()
            .json()["counts"]
        )
        print(f"  the queue now holds {counts['received']} submission(s) not yet sent to DHIS2")
        print("  run `d2w fhir forward --import` in the project directory to send them")


if __name__ == "__main__":
    asyncio.run(main())
