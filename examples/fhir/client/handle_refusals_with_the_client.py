"""Read a refusal with `FacadeClient` - `FacadeError`, its status, and the issues the facade stated.

`read_capture_refusal.py` next door meets the same refusals over plain httpx and digs the issues out
of the parsed body. This is the typed path: anything that is not an answer raises `FacadeError`, and
the error carries the `OperationOutcome` the facade refused with. There is no status code to compare
against a constant and no body to reach into.

Three properties are the whole surface:

- **`status_code`** says which fault line was crossed. A 404 is an address this facade does not
  serve. A 422 is a document that read fine and is wrong about the DHIS2 world.
- **`issues`** is one `OperationOutcomeIssue` per thing wrong, typed - `severity`, `code`,
  `expression` locating it in the document, and `diagnostics` saying it in words. A phase collects
  everything it finds before answering, so a capture screen renders a whole round of corrections.
- **`diagnostics`** joins those words into one line, for the log entry that has to say why in one.

**A connection that never reached the facade is not this.** httpx's own `TransportError` passes
through untouched, because a server that did not answer stated no outcome to carry.

Usage:
    uv run python examples/fhir/client/handle_refusals_with_the_client.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import os
import sys

from _fixture import aggregate_form_id, served_facade
from _runner import run_example
from dhis2w_fhir import FacadeClient, FacadeError

#: Makes the generated draft byte-reproducible, so the only thing wrong with it is what is spoiled here.
SEED = 20260

#: A resource id no guide publishes, so the read has no address to serve.
ABSENT_FORM_ID = "no-such-form"

#: A form canonical this project does not publish, which is what the spoiled submission claims to answer.
ABSENT_CANONICAL = "http://example.org/fhir/no-such-guide/Questionnaire/NotPublished"


async def main() -> None:
    """Read a resource nobody holds, submit a response answering a form nobody publishes, and read both refusals."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()

    async with FacadeClient(base_url) as facade:
        print(f"{facade.base_url}")

        # AN ADDRESS THIS FACADE DOES NOT SERVE. A read of a resource the store does not hold is a
        # 404 with an OperationOutcome, not an empty answer pretending the question was asked.
        print(f"\nread Questionnaire/{ABSENT_FORM_ID}")
        try:
            await facade.read("Questionnaire", ABSENT_FORM_ID)
        except FacadeError as refusal:
            report(refusal)
        else:
            print("  answered - this facade publishes a form under that id after all")

        # A DOCUMENT THAT READ FINE AND IS WRONG. The draft is a perfectly good QuestionnaireResponse
        # filled against the form's own rules; the one thing spoiled is the form it claims to answer.
        # Nothing about that is visible until the canonical is resolved, which is why it is not a 400.
        draft = await facade.generate(aggregate_form_id(), seed=SEED)
        spoiled = draft.model_copy(update={"questionnaire": ABSENT_CANONICAL})
        print(f"\nsubmit a response answering {ABSENT_CANONICAL}")
        try:
            await facade.submit_response(spoiled)
        except FacadeError as refusal:
            report(refusal)
        else:
            print("  accepted - this facade publishes that form after all")

        # The same client, the same three properties, on both. That is the point: a caller writes one
        # `except FacadeError` and renders every refusal the facade ever makes the same way.
        print("\nBoth read the same way - one `except FacadeError`, one loop over `issues`.")


def report(refusal: FacadeError) -> None:
    """One refusal printed the way a capture screen renders it: the status, then each issue, then one line."""
    print(f"  refused with {refusal.status_code}")
    for issue in refusal.issues:
        location = (issue.expression or ["the request"])[0]
        print(f"    [{issue.severity}] {issue.code} at {location}")
        print(f"      {issue.diagnostics}")
    print(f"    in one line: {refusal.diagnostics}")


if __name__ == "__main__":
    run_example(main)
