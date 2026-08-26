"""Submit one filled form with `FacadeClient` - the typed path, where `send_response.py` is the raw one.

`send_response.py` next door does exactly this over plain httpx, and it is worth reading first: it
shows what the wire actually carries. This file is what an integrator writes instead once they are
in Python and want the contract handed to them rather than reconstructed. Four calls, no request
built by hand, no header spelled twice, and no status code compared against a constant.

What the client is doing that a raw caller has to remember:

- **The id is not in the body.** A `create` answers an `OperationOutcome`, so the identity of an
  accepted submission is the last segment of the `Location` header. `CaptureReceipt` carries the id,
  the url, the server's own note, and any warnings the answer stated - so nothing here goes looking
  in the body for an id that was never there.
- **A refusal is an exception with the reasons attached.** Anything that is not an answer raises
  `FacadeError` carrying the `OperationOutcome` the facade refused with, one issue per thing wrong.
  There is no status code to check.
- **A 201 is not a DHIS2 write.** The facade understood the submission, checked it against the
  published form, and wrote it to disk durably. Nothing has reached DHIS2 yet; `d2w fhir forward`
  is what drains the queue into an instance.

Usage:
    uv run python examples/fhir/client/send_with_the_client.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended. A guarded facade
takes a credential: `FacadeClient(base_url, auth=BearerToken(token=...))`, or `UsernamePassword`
/ `PersonalAccessToken` under the posture that checks credentials against DHIS2.
"""

from __future__ import annotations

import os
import sys

from _fixture import aggregate_form_id, served_facade
from _runner import run_example
from dhis2w_fhir import FacadeClient, FacadeError

#: Makes the generated draft byte-reproducible, so two runs submit the same answers.
SEED = 20260


async def main() -> None:
    """Fill one published form, submit it, and read the receipt back - four calls and no request built by hand."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()

    async with FacadeClient(base_url) as facade:
        capability = await facade.capability()
        software = capability.software
        print(f"{software.name if software else 'a facade'} at {facade.base_url}")

        # $generate fills the form against its own rules - value types, bounds, repeats, and real
        # concepts of the CodeSystems its questions bind. A real client fills it from what a
        # reporter typed; the invariant is that either one is postable at this same server.
        form_id = aggregate_form_id()
        draft = await facade.generate(form_id, seed=SEED)
        print(f"$generate on {form_id}: {len(draft.item or [])} top-level item(s), status {draft.status}")

        try:
            receipt = await facade.submit_response(draft)
        except FacadeError as refusal:
            # Every issue the facade named, in the order it named them - this is what a capture
            # screen renders beside the fields the reporter has to fix.
            print(f"refused with {refusal.status_code}")
            for issue in refusal.issues:
                print(f"  [{issue.severity}] {issue.code}: {issue.diagnostics}")
            return

        print(f"accepted: receipt {receipt.response_id}")
        print(f"  served from {receipt.location}")
        print(f"  the facade says: {receipt.note}")
        if receipt.warnings:
            for warning in receipt.warnings:
                print(f"  [{warning.severity}] {warning.code}: {warning.diagnostics}")
        else:
            print("  no warnings - the facade had nothing to note beyond storing it")

        # The receipt is the submission as it arrived, held for the forwarder. It is not a report of
        # anything DHIS2 holds: at this point the instance has never heard of it.
        stored = await facade.read_response(receipt.response_id)
        print(f"read back {stored.id}: answers {stored.questionnaire}, status {stored.status}")
        print(f"  identical to what was sent: {stored.item == draft.item}")
        print("Not yet sent to DHIS2 - run `d2w fhir forward --import` in the project directory to send it.")


if __name__ == "__main__":
    run_example(main)
