"""Take a capture with no server and no browser: post a response into an embedded facade, read the file it wrote.

The capture half of the headless story. `embed_the_facade.py` shows the application answering reads;
this one hands it a `QuestionnaireResponse` and follows what the submission becomes: a `201`, a
receipt served back at its own address, and a JSON file in the project's spool that
`d2w fhir forward` will drain later. Nothing here binds a port, opens a browser, or shells out to
the CLI.

THE POSTURE IS `auth = "none"`, and for an embedded facade that is the honest one. An authentication
posture answers "which callers on the network may submit"; over an ASGI transport there is no
network and no caller but this program, so the process boundary is the trust boundary and a
credential check here would be this code proving its identity to itself. An embedder that later
serves the same application over HTTP states the posture then - `embed_in_fastapi.py` mounts the
same routers with the caller's own check over them.

The response posted is what `Questionnaire/{id}/$generate` answers, which is a draft filled against
the form's own rules - value types, bounds, repeats, real concepts from the CodeSystems its
questions bind. A `seed` makes it reproducible. An embedder filling forms from its own data posts
its own document instead; `build_aggregate_response.py` builds one field by field.

Usage:
    uv run python examples/fhir/client/capture_headless.py [PROJECT_DIRECTORY]

With no argument it captures into the shared example project (see `_fixture.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from _fixture import aggregate_form_id, example_project
from _runner import run_example
from dhis2w_fhir import load_project, service
from dhis2w_fhir_serve import ServeSettings, create_app

FHIR_JSON = "application/fhir+json"
CREATED = 201

EMBEDDED_BASE_URL = "http://embedded"
"""The authority an ASGI transport puts in front of every path - it names no host and reaches none."""

GENERATE_SEED = 20260822
"""What makes `$generate` reproducible, so two runs of this file answer the same form the same way."""


async def main() -> None:
    """Post one generated response into an embedded facade and show the receipt it wrote to disk."""
    directory = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else example_project()
    form_id = aggregate_form_id()

    application = create_app(ServeSettings(project_dir=directory, live=True))
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport, base_url=EMBEDDED_BASE_URL, headers={"Accept": FHIR_JSON}, timeout=60.0
        ) as client:
            draft = (
                (await client.get(f"/Questionnaire/{form_id}/$generate", params={"seed": GENERATE_SEED}))
                .raise_for_status()
                .json()
            )
            print(f"$generate on {form_id}: a {draft['status']} draft with {len(draft.get('item', []))} item(s)")

            submitted = await client.post(
                "/QuestionnaireResponse", json=draft, headers={"Content-Type": FHIR_JSON, "Accept": FHIR_JSON}
            )
            if submitted.status_code != CREATED:
                # A refusal is an OperationOutcome saying which answer the form would not take.
                print(f"refused with {submitted.status_code}: {submitted.text[:300]}")
                return

            # The receipt's address is the `Location` header, never a field of the body: the body is
            # the OperationOutcome stating what was stored and what was warned about.
            response_id = submitted.headers["location"].rsplit("/", 1)[-1]
            receipt = (await client.get(f"/QuestionnaireResponse/{response_id}")).raise_for_status().json()
            print(f"POST -> 201, receipt {receipt['id']} answering {receipt['questionnaire']}")

    # The application is closed and the receipt is still there, because a capture is a file. This is
    # the same directory `d2w fhir forward` drains and the same one `forward_headless.py` reads.
    project = load_project(directory)
    state = service.read_spool_state(project)
    counts = state.counts
    print(f"spool: {service.spool_layout(project).root}")
    print(
        f"  {counts.received} not yet sent to DHIS2, {counts.forwarded} accepted by DHIS2, "
        f"{counts.rejected} refused by DHIS2, {counts.malformed} unreadable"
    )
    for row in state.receipts:
        if row.response_id == response_id:
            print(f"  this run wrote {row.response_id}: {row.form_kind} capture, {row.state}, at {row.received_at}")


if __name__ == "__main__":
    run_example(main)
