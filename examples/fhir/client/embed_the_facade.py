"""Build the facade in your own process and drive it without a socket - the proof that it is a library.

`d2w fhir serve` is one caller of `create_app`, not the way in. The factory takes `ServeSettings`
and answers a FastAPI application; an ASGI transport speaks to that application directly, so a
program that wants the FHIR surface gets it as function calls over a loaded store. No port is bound,
no process is started, nothing is on the network, and the answers are byte-for-byte the ones a
served facade returns - the same routers, the same store, the same CapabilityStatement.

Three lines carry the whole pattern:

1. `create_app(ServeSettings(...))` - the application, with nothing loaded yet.
2. `app.router.lifespan_context(app)` - the startup the ASGI server would have run: the project is
   read, the store is built, the spool is opened, `/metadata` is rendered once.
3. `httpx.ASGITransport(app=app)` - a client that calls the application in this event loop.

The store is built `live=True`, off the DHIS2 instance, because the shared example project has
never run SUSHI: a compiled `ig/fsh-generated/resources` is the other store and this project holds
none. An embedder serving a compiled guide passes `live=False` and needs no instance at all.

Usage:
    uv run python examples/fhir/client/embed_the_facade.py [PROJECT_DIRECTORY]

With no argument it embeds the shared example project (see `_fixture.py`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from _fixture import example_project
from _runner import run_example
from dhis2w_fhir_serve import ServeSettings, create_app

FHIR_JSON = "application/fhir+json"

EMBEDDED_BASE_URL = "http://embedded"
"""The authority an ASGI transport puts in front of every path - it names no host and reaches none."""


async def main() -> None:
    """Load one facade in this process and read its conformance and its published forms."""
    directory = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else example_project()

    # The store is built live, so this reads the instance the project's profile names. Nothing else
    # here is a network call: every request below is a function call into the application object.
    application = create_app(ServeSettings(project_dir=directory, live=True))
    print(f"project: {directory}")

    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport, base_url=EMBEDDED_BASE_URL, headers={"Accept": FHIR_JSON}, timeout=60.0
        ) as client:
            capability = (await client.get("/metadata")).raise_for_status().json()
            software = capability["software"]
            print(f"{software['name']} {software.get('version', '?')} - loaded, not listening")
            print(f"  serves: {', '.join(entry['type'] for entry in capability['rest'][0].get('resource', []))}")

            bundle = (await client.get("/Questionnaire", params={"_count": 5})).raise_for_status().json()
            print(f"{bundle.get('total', 0)} Questionnaire(s) published")
            for entry in bundle.get("entry", []):
                resource = entry["resource"]
                print(f"  {resource['id']:16} {resource.get('title', '-')}")

    # The lifespan has unwound: the store is released and the live client the facade held is closed.
    print("facade closed - no port was ever bound")


if __name__ == "__main__":
    run_example(main)
