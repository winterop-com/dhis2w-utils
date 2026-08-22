"""Fill this project's local storage layer from Python, then read the register back out of it - no server, no CLI.

DHIS2 STAYS THE RECORD. A projection is a derived copy of the mapped scope of an instance, held as
the FHIR resources this project's map publishes, filled by a sync and written by nothing else. It is
rebuildable from zero as a routine operation, every row is stamped with the instant it was read at,
and every answer served out of it states that instant. A row that disagrees with DHIS2 is a defect
of the sync, and the fix is another sync rather than an edit.

This is the storage layer an embedded facade sits on, taken on its own: `run_sync` is what
`d2w fhir sync` calls, and `ProjectionStore` is the protocol every read goes through. Four reads
here, in the order a caller meets them:

1. **The watermark** - how far each polled tracker collection has been read, and the one instant the
   whole projection is as of, which is the earlier of the two.
2. **A page** - `search` over a resource type, which is what a register listing is answered from.
3. **An identifier search** - the same `search`, naming the value a register lookup starts from.
4. **Membership** - `read` of one resource by type and id, which is the question "does this
   projection hold that person" answered without asking the instance.

WHAT A PROJECTION NEVER DOES IS AUTHORIZE. The rows say who is on the page; a record a caller
actually receives is read back from DHIS2 under that caller's own credentials, so the instance
decides every disclosure exactly as it does without a projection.

The `[serve.projection]` table is stated here in code rather than read from `fhir.toml`, because
this file is about the library: an embedder that holds its own configuration builds the same model
from it. A project serving the same projection writes `store = "sqlite"` under `[serve.projection]`
and `d2w fhir serve` opens it at startup.

Usage:
    uv run python examples/fhir/client/projection_local_store.py [PROJECT_DIRECTORY]

With no argument it fills the shared example project's projection (see `_fixture.py`). The first run
reads the whole mapped register; every run after it reads what moved, which on an unchanged instance
is one request.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from _fixture import example_project
from _runner import run_example
from dhis2w_fhir import load_project, service
from dhis2w_fhir.config import ProjectionBackend, ProjectionConfig
from dhis2w_fhir_serve import (
    ProjectionQuery,
    RegisterSurface,
    ServeSettings,
    TrackedEntityIndex,
    build_store,
    open_live_client,
    open_projection_store,
    projection_path,
    run_sync,
)

PAGE_SIZE = 3
"""How many projected resources this example pages, so the printout is a sample rather than a dump."""


async def main() -> None:
    """Sync one project's projection, then answer three questions out of it without touching DHIS2."""
    directory = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else example_project()
    project = load_project(directory)
    generation = service.resolve_generation_profile(project)

    # `store = "sqlite"` is the whole of what turns the projection on, and `path` is one file under
    # the project root. Deleting that file is supported: the next sync fills it from zero.
    configured = ProjectionConfig(store=ProjectionBackend.SQLITE)
    settings = ServeSettings(
        project_dir=project.project_root,
        live=True,
        tracked_entities=project.config.serve.tracked_entities,
        projection=configured,
        dhis2_base_url=generation.profile.base_url,
    )
    print(f"project: {project.project_root}")
    print(f"projection: {projection_path(configured, project_root=project.project_root)}")

    async with open_live_client(project, settings) as client:
        # The register surface is resolved off the served store, which is the same map a live facade
        # answers a register read through - so a synced answer and a live one are the same bytes.
        served = await build_store(settings, project, client)
        surface = RegisterSurface.resolve(TrackedEntityIndex.from_store(project, served), settings.tracked_entities)
        async with open_projection_store(configured, project_root=project.project_root) as projection:
            if projection is None:
                print('this project holds no projection: state `store = "sqlite"` to hold one')
                return
            report = await run_sync(
                client,
                surface=surface,
                store=projection,
                project_root=project.project_root,
                store_path=projection_path(configured, project_root=project.project_root),
                overlap=timedelta(seconds=configured.overlap_seconds),
            )
            print(f"sync ({report.mode}): {report.counts_line()}")

            # 1. The watermark. The two collections are polled independently, and the instant an
            #    answer states is the earlier of the two - a projection is as current as its least
            #    current half.
            watermarks = await projection.watermarks()
            print(
                f"read as far as: tracked entities {watermarks.tracked_entities}, enrollments {watermarks.enrollments}"
            )
            print(f"answers are as of: {(await projection.cursor()).updated_at}")

            # 2. A page. This is what a register listing is answered from - one indexed query over
            #    the local file rather than one tracker query per type.
            resource_type = surface.register_resource_types()[0]
            page = await projection.search(ProjectionQuery(resource_type=resource_type, count=PAGE_SIZE))
            print(f"{page.total} {resource_type}(s) held; this page carries {len(page.resources)}")
            for resource in page.resources:
                print(f"  {resource.resource_id} {_identifier_line(resource.body)}")

            if not page.resources:
                print("nothing projected yet: the instance holds no tracked entity of a published type")
                return

            # 3. One identifier search - the lookup a register read starts from, answered without a
            #    request to the instance. The system names which key the value is; naming none asks
            #    under every key the projection holds.
            wanted = page.resources[0]
            found = await projection.search(
                ProjectionQuery(resource_type=resource_type, identifiers=(wanted.resource_id,))
            )
            print(f"identifier {wanted.resource_id}: {len(found.resources)} match(es)")

            # 4. Membership. One resource by type and id - "does this projection hold that person",
            #    answered off disk. What the caller may then SEE is DHIS2's answer, read back live
            #    under the caller's own credentials.
            held = await projection.read(resource_type, wanted.resource_id)
            print(f"membership of {wanted.resource_id}: {'held' if held is not None else 'not held'}")
            missing = await projection.read(resource_type, "nobodyAtAll")
            print(f"membership of nobodyAtAll: {'held' if missing is not None else 'not held'}")


def _identifier_line(body: dict[str, Any]) -> str:
    """What one projected resource is keyed by, read off the FHIR document the sync stored verbatim.

    A projected person carries identifiers and the DHIS2 attribute values the map publishes, and no
    `name`: what a record says about somebody is read from the instance under the credentials of
    whoever asked, so the projection holds the keys that decide who is on the page.
    """
    identifiers = body.get("identifier") or []
    keys = ", ".join(f"{identifier.get('system', '')}|{identifier.get('value', '')}" for identifier in identifiers)
    attributes = sum(1 for extension in body.get("extension") or [] if extension.get("extension"))
    return f"{keys} ({attributes} attribute value(s))"


if __name__ == "__main__":
    run_example(main)
