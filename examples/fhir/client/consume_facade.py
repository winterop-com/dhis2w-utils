"""Drive a running `d2w fhir serve` facade over plain HTTP - discover, fill, submit, read the receipt.

This is the integration developer's path and it needs no DHIS2 and no dhis2w package:
just httpx and a served project. The facade answers `application/fhir+json` and nothing
else, so every read below is FHIR and every code path a real client walks is walked here:

1. `/metadata` - the CapabilityStatement, which is the facade's only contract.
2. `Questionnaire?_count=...` - the published forms, as a searchset Bundle.
3. `Questionnaire/{id}/$generate` - a filled draft answering that form's own rules.
4. `POST /QuestionnaireResponse` - the draft submitted back as a capture.
5. `QuestionnaireResponse/{id}` - the receipt, which is the submission as it arrived.
6. `/spool` - the verdict shape: what is queued, forwarded, rejected, malformed.

`$generate` and the POST are deliberately paired: the invariant the operation exists for
is that its own output is immediately postable, so a client can prove a form is answerable
before writing a line of form-filling code.

Usage:
    d2w fhir serve --port 8123          # in the project directory, in another shell
    uv run python examples/fhir/client/consume_facade.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on
the example project and stops it at exit - which is what lets this run unattended. That
import is the only line here that needs this repository; everything below it is httpx
against a URL, which is the whole point.
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx
from _fixture import served_facade

FHIR_JSON = "application/fhir+json"
CREATED = 201
"""What an accepted capture answers; anything else carries an OperationOutcome saying why not."""


async def main() -> None:
    """Walk the whole read-and-capture loop against one served project."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    async with httpx.AsyncClient(base_url=base_url, headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        capability = (await client.get("/metadata")).raise_for_status().json()
        served = [entry.get("type") for entry in capability["rest"][0].get("resource", [])]
        print(f"{capability['software']['name']} {capability['software'].get('version', '?')} at {base_url}")
        print(f"  serves: {', '.join(served)}")

        # A searchset Bundle. `total` is the whole set; `entry` is this page of it.
        bundle = (await client.get("/Questionnaire", params={"_count": 5})).raise_for_status().json()
        print(f"{bundle.get('total', 0)} Questionnaire(s) published; first page holds {len(bundle.get('entry', []))}")
        if not bundle.get("entry"):
            print("nothing published - generate and compile the project first")
            return
        for entry in bundle["entry"]:
            print(f"  {entry['resource']['id']:16} {entry['resource'].get('title', '-')}")

        form_id = bundle["entry"][0]["resource"]["id"]

        # $generate fills the form against its own rules - value types, bounds, repeats, and real
        # concepts of the CodeSystems its questions bind. `seed` makes it byte-reproducible.
        draft = (
            (await client.get(f"/Questionnaire/{form_id}/$generate", params={"seed": 4242})).raise_for_status().json()
        )
        print(f"$generate on {form_id}: {len(draft.get('item', []))} top-level item(s), status {draft['status']}")

        # The invariant: what $generate produced is postable at the same server, unchanged.
        submitted = await client.post(
            "/QuestionnaireResponse", json=draft, headers={"Content-Type": FHIR_JSON, "Accept": FHIR_JSON}
        )
        print(f"POST /QuestionnaireResponse -> {submitted.status_code} {submitted.headers.get('location', '')}")
        if submitted.status_code != CREATED:
            print(f"  refused: {submitted.text[:300]}")
            return

        # An accepted capture answers an OperationOutcome, and the `Location` header is where the
        # receipt is served from - so the id comes off the header, not out of the body. The receipt
        # is the submission as it arrived, never a live view of DHIS2 data: nothing has been written
        # to any instance yet, and `d2w fhir forward` is what does that.
        response_id = submitted.headers["location"].rsplit("/", 1)[-1]
        receipt = (await client.get(f"/QuestionnaireResponse/{response_id}")).raise_for_status().json()
        print(f"receipt {receipt['id']}: answers {receipt['questionnaire']}, authored {receipt.get('authored', '-')}")

        # /spool is the one non-FHIR endpoint a client reads: the queue's own verdict, counted by
        # the state each receipt's file is in. It lives on a lowercase segment so it can never
        # shadow a FHIR resource type.
        spool = (await client.get("/spool", headers={"Accept": "application/json"})).raise_for_status().json()
        counts = spool["counts"]
        print(
            f"spool: {spool['total']} total - {counts['received']} not yet sent to DHIS2, "
            f"{counts['forwarded']} accepted by DHIS2, {counts['rejected']} refused by DHIS2, "
            f"{counts['malformed']} unreadable"
        )


if __name__ == "__main__":
    asyncio.run(main())
