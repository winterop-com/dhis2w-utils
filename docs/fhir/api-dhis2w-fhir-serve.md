# FHIR facade server (`dhis2w_fhir_serve`)

`dhis2w_fhir_serve` is the package behind [`d2w fhir serve`](201-serve.md):
a FastAPI application that serves one generated IG as a FHIR endpoint and receives
QuestionnaireResponse captures against it. It is its own workspace member because it needs FastAPI
and uvicorn, and `dhis2w-fhir` - which generates a file tree - needs neither; `pip install
'dhis2w-cli[serve]'` (or `uv add dhis2w-fhir-serve`) is what puts the command on the CLI.

Everything a running facade serves is loaded once at startup and held on `app.state.context`, so a
request is index lookups and nothing else. The store is either the compiled IG on disk or - under
`--live` - the same read set built off a DHIS2 instance through one client opened during startup.
That client stays open for the life of the process, because `GET /Patient` and the enrollment
listing answer from the instance per request; no read of the store ever touches DHIS2 again.

The receipt spool is the one exception, and deliberately so: it is a path rather than a loaded
index, and every read of it re-reads the directory. `d2w fhir forward` runs as a separate process
and renames receipt files between the spool's three lifecycle directories while the server is up,
so anything cached would be stale within seconds of a drain.

## When to reach for it

- Embed the facade in another ASGI process (`create_app`, `ServeSettings`), or mount its routers
  beside your own routes over a runtime you opened yourself (`ServeSettings.resolve`,
  `open_serve_runtime`, `attach_serve_runtime`, `serve_routers`, `register_error_handlers`) - see
  [Embed the facade](#embed-the-facade).
- Get the settings `d2w fhir serve` gets for the same project and the same flags, precedence rules
  included (`ServeSettings.resolve`, `ServeInvocation`).
- Load a project's store, spool, and register surface without an HTTP server at all
  (`open_serve_runtime`, `ServeRuntime`, `ServeContext`).
- Build the served read set off a live DHIS2 instance, over a client you hold open
  (`open_live_client`, `build_live_store`, `build_store`).
- Translate a concept through the ConceptMaps a project publishes, with no server running
  (`find_translations`, `TranslateRequest`, `TranslationMatch`).
- Page through the receipts a facade holds the way `GET /spool` pages through them (`page_of`,
  `SpoolCursor`, `SpoolPage`, `requested_page_size`, `requested_cursor`).
- Load a project's served resources without an HTTP server (`load_compiled_store`, `ResourceStore`,
  `SearchQuery`, `IdentifierToken`).
- Read or write the receipt spool a running facade keeps, in any of its three lifecycle states
  (`ResponseSpool`, `StoredReceipt`, `StoredResponseEnvelope`, `ResponseLifecycle`,
  `RECEIVED_RESPONSES_RELATIVE_PATH`).
- Validate a QuestionnaireResponse against a served IG outside the endpoint
  (`validate_response`, `build_capture_index`, `CaptureNaming`, `CodingResolverSet`).
- Generate a synthetic response against a served form (`generate_response`, `draw_seed`,
  `resolve_period_type`, `MAXIMUM_SEED`).
- Render the FHIR error and outcome bodies the facade answers with (`outcome`, `rejection_outcome`,
  `success_outcome`, `build_server_capability`).
- Read what a guide states about the tracked entities an instance holds, or search a DHIS2 instance
  for one, without an HTTP server (`TrackedEntityIndex`, `PublishedAttribute`,
  `PublishedTrackedEntityType`, `RegisterSurface`, `ServedRegister`, `registered_entity_for`,
  `search_tracked_entities`, `fetch_tracked_entity`, `TrackedEntityEnrollment`,
  `TrackedEntityEnrollments`).

## Worked example - load a store and read one resource

```python
from dhis2w_fhir import load_project
from dhis2w_fhir_serve import SearchQuery, load_compiled_store

project = load_project()
store = load_compiled_store(project)

store.summary().counts_by_type
# {'CodeSystem': 42, 'Location': 1332, 'Organization': 1332, 'Questionnaire': 9, 'ValueSet': 42}

entry = store.by_type_and_id("Questionnaire", "BfMAe6Itzgt")
entry.body["title"]
# 'Child Health'

store.search("Questionnaire", SearchQuery(urls=("http://example.org/fhir/demo/Questionnaire/BfMAe6Itzgt",)))
# (StoreEntry(resource_type='Questionnaire', resource_id='BfMAe6Itzgt', ...),)
```

## Embed the facade

`create_app` builds the whole server, and an application that already runs FastAPI wants the FHIR
surface inside the process it has. That is four steps, and each one is a name:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dhis2w_fhir import load_project
from dhis2w_fhir_serve import (
    ServeSettings,
    accept_head_wherever_get_is_served,
    attach_serve_runtime,
    open_serve_runtime,
    register_error_handlers,
    require_json_is_acceptable,
    serve_routers,
)
from fastapi import Depends, FastAPI

settings = ServeSettings.resolve(load_project()).settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with open_serve_runtime(settings) as runtime:
        attach_serve_runtime(app, runtime)
        yield


application = FastAPI(lifespan=lifespan)
register_error_handlers(application)

routers = serve_routers(capture=settings.capture)
for router in routers.in_mount_order():
    accept_head_wherever_get_is_served(router)
for router in routers.fhir:
    application.include_router(router, dependencies=[Depends(require_json_is_acceptable)])
for router in routers.facade:
    application.include_router(router)
application.include_router(routers.read, dependencies=[Depends(require_json_is_acceptable)])
```

What each step is for:

1. **The settings.** `ServeSettings.resolve` applies the flag-over-`[serve]` precedence, resolves the
   DHIS2 profile, and refuses a project that has never been built. Constructing `ServeSettings`
   directly is supported too, and a facade built that way differs from `d2w fhir serve` on purpose
   rather than by accident.
2. **The runtime.** `open_serve_runtime` loads the project, the store, the spool, the register
   surface, and the CapabilityStatement, and holds the DHIS2 client a live run reads through open for
   as long as the context manager is entered. `attach_serve_runtime` puts the two things every
   handler reads onto the application, and nothing serves a request before it has been called.
3. **The routers.** `serve_routers` states the mount requirements as data: the FHIR routers carry
   `Depends(require_json_is_acceptable)`, the facade routers do not, the read catch-alls mount after
   every fixed path your application serves - `/{resource_type}` claims any one-segment path, so your
   own `/health` mounts first or it is gone - and every router gets the HEAD sweep, or a liveness
   probe asking `HEAD /metadata` reads a live facade as down.
4. **The error handlers.** Without `register_error_handlers`, every typed refusal the facade raises -
   `RegisterDisabledError`, `NotServedError`, `CaptureDisabledError` - is a 500 with no
   `OperationOutcome` in it.

Two things stay outside this contract. The capture UI is not a router and is reached by running
`create_app` with `settings.ui`; see [the UI boundary](design/library.md#35-the-ui-boundary-and-what-it-means-for-the-package-layout).
And a facade served under a path is **mounted** rather than included under a prefix: every `fullUrl`,
`self`, and paging link is built from `request.base_url`, which carries an ASGI mount's path and not
an `include_router` prefix.

A worked example of all of this is coming to the facade ladder in
[Build your own facade](401-build-your-own-facade.md), as the level above `complex_facade.py`: an
application that mounts these routers rather than reimplementing them.

## Reference

### Settings

What one running facade is built from: the project it serves, whether the store is built live,
which DHIS2 profile that build reads with, and how strictly a received code is checked - and how one
invocation resolves all of that from a project's `[serve]` table and the dials it was given.

::: dhis2w_fhir_serve.settings

### The runtime

What one loaded facade holds - the project, its store, its spool, its register surface, the
statement it answers `/metadata` with, and the DHIS2 client a live run reads through - as a value a
caller can open without starting a server. The lifespan is its first caller.

::: dhis2w_fhir_serve.runtime

### Application

The app factory and the lifespan that opens the runtime and attaches it.

::: dhis2w_fhir_serve.app

### The routers

Every router the facade mounts, with what mounting it requires stated as data: which carry the
`Accept` negotiation, which answer plain JSON about the facade rather than FHIR resources out of it,
which claim every path of their shape and therefore mount last, and where the runtime state the
handlers read is written and read back.

::: dhis2w_fhir_serve.routes

::: dhis2w_fhir_serve.routes.context

::: dhis2w_fhir_serve.routes.negotiation

### Resource store

The compiled IG merged with the predefined resource tree, indexed by `(resourceType, id)` and by
canonical url. Resources are held as the bytes they were written as, so what a client reads back is
what the project publishes.

::: dhis2w_fhir_serve.store

### Response spool

Every received QuestionnaireResponse, written atomically to `.serve/responses/received/` and read
back from whichever of `received/`, `forwarded/`, and `rejected/` `d2w fhir forward` has since
moved it to. The directory is the index and is re-read on every call, because the forwarder renames
files while the server runs. A stored response is a receipt - the submission as it arrived, never a
live view of DHIS2 data.

::: dhis2w_fhir_serve.spool

### Spool listing

`GET /spool` - the receipt envelopes with their lifecycle state, and the DHIS2 import report behind
a rejection. Typed JSON rather than FHIR, because a receipt envelope has no FHIR analogue; the
module docstring states the reasoning in full.

::: dhis2w_fhir_serve.routes.spool

### Capture

Receiving a QuestionnaireResponse: the naming the capture contract is written in, the questionnaire
index an answer is checked against, the terminology resolver behind a coded answer, the phase
machine that runs the whole thing, and the OperationOutcome vocabulary every answer is spoken in.

::: dhis2w_fhir_serve.capture.naming

::: dhis2w_fhir_serve.capture.index

::: dhis2w_fhir_serve.capture.resolve

::: dhis2w_fhir_serve.capture.validate

::: dhis2w_fhir_serve.capture.outcome

### The register

`GET /{resourceType}` and `GET /{resourceType}/{id}`, answered from the DHIS2 instance rather than
from the store, and only by a process started with `--live`. Which resource types those are is the
published `D2TET_CM`'s to say - one per FHIR resource the map takes a registered tracked entity type
onto - so a project tracking people alone serves `Patient` and one that also registers samples serves
`Specimen` beside it. The index reads what the guide publishes about the instance's subjects, the
surface narrows that by `[serve.tracked_entities]`, the wire module holds the empirical
`/api/tracker/trackedEntities` contract the search obeys, and the projection turns one tracked entity
into the resource its type is registered as, carrying identity and no claim the target resource
otherwise defines - each module docstring states why.

::: dhis2w_fhir_serve.register.index

::: dhis2w_fhir_serve.register.surface

::: dhis2w_fhir_serve.register.wire

::: dhis2w_fhir_serve.register.projection

::: dhis2w_fhir_serve.register.listing

::: dhis2w_fhir_serve.routes.register

### Enrollment listing

`GET /tracked-entities/{uid}/enrollments` - which programs one tracked entity is enrolled in, as the
picker's typed JSON feed rather than as a FHIR resource, because whether a DHIS2 enrollment is an
`EpisodeOfCare` or a `CarePlan` is a decision this project has deliberately not taken yet.

::: dhis2w_fhir_serve.routes.enrollments

### Read and search routes

`GET /{type}/{id}` and `GET /{type}`, answered from the store for every definitional resource and
from the spool for QuestionnaireResponse.

::: dhis2w_fhir_serve.routes.read

### Capture route

`POST /QuestionnaireResponse` - the one write the facade accepts.

::: dhis2w_fhir_serve.routes.capture

### Generating a response

`GET|POST /Questionnaire/{id}/$generate` and the synthesizer behind it: one served form filled in
from the very capture index a submission is validated against, so the generated response posts back
at the same server for a 201.

::: dhis2w_fhir_serve.routes.generate

::: dhis2w_fhir_serve.synthesize

### Terminology translation

`GET /ConceptMap/$translate` - the DHIS2 identifiers the published ConceptMaps state for one
concept. The matching itself is a pure function over the maps a store holds, so a caller with a
loaded store answers the same question with no server running.

::: dhis2w_fhir_serve.routes.translate

### Conformance

`GET /metadata`, and the `kind #instance` CapabilityStatement it answers with.

::: dhis2w_fhir_serve.metadata

::: dhis2w_fhir_serve.capability

### Live store

The store built off a DHIS2 instance instead of a compiled IG, over the same JSON builders the
generate targets write to disk.

::: dhis2w_fhir_serve.live

### Errors

Every failed interaction, and the OperationOutcome it answers with.

::: dhis2w_fhir_serve.errors

### Request logging

One log line per interaction, and the plain configuration the server process runs under.

::: dhis2w_fhir_serve.log

### Package surface

The names below re-export from `dhis2w_fhir_serve` itself.

::: dhis2w_fhir_serve
    options:
      members: false
