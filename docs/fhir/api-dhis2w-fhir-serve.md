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
and renames receipt files between the spool's four lifecycle directories while the server is up,
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
- Run one FHIRPath expression, CQL library, or ELM library over a resource and read what the parser
  and the evaluator said about it (`evaluate_source`, `EvaluationLanguage`, `EvaluationOutcome`,
  `EvaluationResult`, `EvaluationDiagnostic`, `json_safe`, `syntax_diagnostic`).
- Read an evaluation's `Parameters` input, and say an evaluation's answer as the `Parameters` a FHIR
  client reads (`evaluation_ask`, `evaluation_parameters`, `EVALUATE_OPERATION_PATH`).
- Ask what a code means in the vocabularies one project publishes, with no server running
  (`load_terminology`, `TerminologyState`, `LookedUpCode`, `ValidatedCode`, `ConceptProperty`).
- Answer a CDS Hooks invocation with cards built from a CQL library (`CdsService`, `CdsDiscovery`,
  `CdsHookRequest`, `CdsHookResponse`, `CdsCard`, `CqlLibraryHookContext`).
- Page through the receipts a facade holds the way `GET /spool` pages through them (`page_of`,
  `SpoolCursor`, `SpoolPage`, `requested_page_size`, `requested_cursor`).
- Load a project's served resources without an HTTP server (`load_compiled_store`, `ResourceStore`,
  `SearchQuery`, `IdentifierToken`).
- Read or write the receipt spool a running facade keeps, in any of its four lifecycle states
  (`ResponseSpool`, `StoredReceipt`, `StoredResponseEnvelope`, `ResponseLifecycle`,
  `RECEIVED_RESPONSES_RELATIVE_PATH`, `WITHDRAWN_RESPONSES_RELATIVE_PATH`).
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
- Read a register's value filter, or narrow a search of your own by one (`AttributeFilter`,
  `requested_attribute_filters`, `ATTRIBUTE_FILTER_PARAMETER`, `ATTRIBUTE_FILTER_OPERATOR`).
- Put something other than the DHIS2 instance behind a register search, or hold a copy of an
  instance as FHIR resources (`NameSearchIndex`, `NameQuery`, `NameMatch`, `NameMatches`,
  `Dhis2NameSearchIndex`, `build_name_search_index`, `ProjectionStore`, `ProjectedResource`,
  `ProjectionBatch`, `ProjectionCursor`).

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
   as long as the context manager is entered. Under `auth = "dhis2"` it holds a second connection
   beside it - `ServeRuntime.caller_client`, pointed at the same instance and carrying no credential -
   which is the pool a register read forwards each caller's own `Authorization` over; see
   [credential pass-through](#credential-pass-through). `attach_serve_runtime` puts all three things
   the handlers read onto the application, and nothing serves a request before it has been called.
3. **The routers.** `serve_routers` states the mount requirements as data: the FHIR routers carry
   `Depends(require_json_is_acceptable)`, the facade routers do not, the read catch-alls mount after
   every fixed path your application serves - `/{resource_type}` claims any one-segment path, so your
   own `/health` mounts first or it is gone - and every router gets the HEAD sweep, or a liveness
   probe asking `HEAD /metadata` reads a live facade as down. `ServeRouters.guarded` is the fourth
   requirement, and the one an application usually answers itself: see
   [bring your own authentication](#bring-your-own-authentication).
4. **The error handlers.** Without `register_error_handlers`, every typed refusal the facade raises -
   `RegisterDisabledError`, `NotServedError`, `CaptureDisabledError` - is a 500 with no
   `OperationOutcome` in it.

### Pick what you mount

`serve_routers` answers every router this facade has, and an embedding application rarely wants all
of them. The two collections it answers - `fhir` and `facade` - are what you narrow, and the route
modules are where each router is imported from:

```python
from dhis2w_fhir_serve.metadata import router as metadata_router
from dhis2w_fhir_serve.routes.capture import refusal_router as capture_refusal_router
from dhis2w_fhir_serve.routes.capture import router as capture_router
from dhis2w_fhir_serve.routes.cds import router as cds_router
from dhis2w_fhir_serve.routes.enrollments import router as enrollments_router
from dhis2w_fhir_serve.routes.evaluate import router as evaluate_router
from dhis2w_fhir_serve.routes.spool import router as spool_router
from dhis2w_fhir_serve.routes.terminology import router as terminology_router
```

Five named picks, each a pair of tuples in place of `routers.fhir` and `routers.facade` in the loop
above. Every one of them still mounts `serve_routers().read` last, still wants the HEAD sweep, and
still needs `register_error_handlers` - those three are not part of the choice.

**Capture only.** Receive submissions, and publish the forms they answer.

```python
fhir = (metadata_router, capture_router)
facade = (spool_router,)
```

**Capture and register.** The same, plus who the submissions are about. The register itself claims no
router - `GET /Patient` is the read catch-all dispatching to it - so what this pick adds beyond the
one above is the enrollment listing a stage form picks from. Live runs only.

```python
fhir = (metadata_router, capture_router)
facade = (spool_router, enrollments_router)
```

**Read-only guide server.** Publish the guide and receive nothing. The refusal router claims
`POST /QuestionnaireResponse` so the address answers 405 naming `[serve] capture = false`, rather
than falling through to a 405 that says nothing.

```python
fhir = (metadata_router, capture_refusal_router)
facade = ()
```

**Evaluate playground.** The guide, and the three surfaces that run over it: FHIRPath, CQL, and ELM
evaluation, this guide's own vocabularies, and CDS Hooks.

```python
fhir = (metadata_router,)
facade = (evaluate_router, terminology_router, cds_router)
```

**The full facade.** Every line above, in one call.

```python
routers = serve_routers(capture=settings.capture)
```

#### Bring your own authentication

`serve_routers` answers a fourth value beside the three collections: `guarded`, the routers the
authentication check belongs on for the posture and scope it was called with. It is a subset of the
routers already in `fhir`, `facade`, and `read`, compared by identity through `routers.is_guarded`,
so a router is mounted once and the guard is one more dependency on that mount.

`d2w fhir serve` mounts `dhis2w_fhir_serve.auth.require_authenticated` over it. An application that
already knows who its callers are mounts its own dependency instead - the set is the same set, and
nothing else about the facade changes:

```python
from dhis2w_fhir_serve import ServeRouters, serve_routers
from fastapi import Depends, Request


async def whoever_this_application_says(request: Request) -> None: ...  # raise your own 401 here


routers = serve_routers(capture=settings.capture, auth=settings.auth, auth_scope=settings.auth_scope)
for router in routers.fhir:
    guard = [Depends(whoever_this_application_says)] if routers.is_guarded(router) else []
    application.include_router(router, dependencies=[*guard, Depends(require_json_is_acceptable)])
```

A dependency mounted this way that wants its captures attributed writes a
`dhis2w_fhir_serve.auth.RequestIdentity` onto `request.state` under
`dhis2w_fhir_serve.auth.REQUEST_IDENTITY_ATTRIBUTE`; the capture route reads it there and stamps the
username onto the receipt. An identity written with `posture=ServeAuth.DHIS2` also puts the register
reads on the pass-through path, where the request's own `Authorization` header is what reaches DHIS2 -
so write that posture only for an identity whose credential DHIS2 itself would accept. `register_routes` takes the same seam as its `authentication` argument for
an application that wants the facade's own mounting and its own check.

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

### Authentication

Who the facade serves: the four postures `[serve] auth` picks between, the scope `[serve] auth_scope`
covers, the startup refusals a posture this run could not honour meets before the socket opens, and
the one dependency the guarded routers carry.

The `dhis2` posture's 401 challenges with `xBasic`, not `Basic` - a browser that meets `Basic` on a
request a page made opens its own credential dialog and never hands the response back, leaving the
capture UI's Submit pending instead of rendering the refusal. The scheme callers **send** is
untouched, and the header reads the same for every caller rather than shifting by `Accept` or user
agent. `BROWSER_SAFE_BASIC_SCHEME` is the constant.

::: dhis2w_fhir_serve.auth

### Who the caller is (`GET /whoami`)

The one address whose whole answer is who this server just decided the caller is. It carries the
authentication check in **every** scope - `write` guards one route and `all` guards all but
`/metadata`, and this one is guarded under both - so a client can get a verdict on a credential
without doing anything with it. Wrong credentials get the same 401, the same OperationOutcome, and
the same `WWW-Authenticate` challenge every other refusal on this facade gets.

It names a caller only where `[serve] auth` names a posture. Under `auth = "none"` the address
answers its own 404 - "this server authenticates nobody, so it names nobody: `/whoami` answers a
caller only where `[serve] auth` states a posture" - rather than falling through to the read
catch-all, which would call `whoami` a resource type nobody asked for.

```console
$ curl -su clerk:the-right-password http://127.0.0.1:8095/whoami
{"posture":"dhis2","username":"clerk","name":"clerk"}

$ curl -su clerk:wrong -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8095/whoami
401
```

`username` is the DHIS2 username under `dhis2`, the claim `[serve.jwt] username_claim` names under
`jwt` - the same value a receipt is stamped with - and null under `token`, which names a deployment
rather than a person. `name` is what to call the caller in a sentence: the username where there is
one, and a stated constant where there is not.

The capture UI's sign-in panel is the first caller: it asks here with what was typed before it holds
on to anything, so a wrong password is refused at the prompt rather than at the first submission.
The path is fixed rather than discovered, because the UI is served same-origin by the very process
that answers it.

::: dhis2w_fhir_serve.routes.whoami

### The external issuer

Under `[serve] auth = "jwt"`, callers arrive with a token an OpenID Connect issuer this facade does
not run has minted. The issuer's discovery document and its JWKS are read once while the server
starts - an issuer this machine cannot reach refuses the run - and every token is then verified in
memory against those public keys: signature over the asymmetric algorithms only, `iss`, `exp`, `nbf`,
and `aud` where one is configured. The keys are held for as long as their own `Cache-Control` asks,
never below a floor, and an unknown `kid` forces one refetch so a key rotation is not an outage.

::: dhis2w_fhir_serve.oidc

### Credential pass-through

Under `[serve] auth = "dhis2"` on a live run - and under `"jwt"` with `[serve.jwt] forward_bearer` on
- a register read carries the **caller's** own `Authorization` header to the instance, opaque and
unparsed, so DHIS2 applies its sharing, organisation unit scopes, ownership, and access levels to the
person who actually asked. The reads share one pooled connection held on the runtime for the life of
the process, and that pool carries no credential of its own - `CallerCredentialReader` is the
per-request pairing of it with one caller's header, and nothing on the path is cached. The startup
store build, `/uiconfig`, and the forward drain are not on it: none of them acts on behalf of a
request. Under `jwt` with `forward_bearer` off there is no caller channel at all, and the register
answers 501 rather than falling back to the facade's own profile.

::: dhis2w_fhir_serve.passthrough

### Resource store

The compiled IG merged with the predefined resource tree, indexed by `(resourceType, id)` and by
canonical url. Resources are held as the bytes they were written as, so what a client reads back is
what the project publishes.

::: dhis2w_fhir_serve.store

### Response spool

Every received QuestionnaireResponse, written atomically to `.serve/responses/received/` and read
back from whichever of `received/`, `forwarded/`, `rejected/`, and `withdrawn/` it has since been
moved to - the first three by `d2w fhir forward`, the fourth by `d2w fhir withdraw`. The directory
is the index and is re-read on every call, because those commands rename files while the server
runs. A stored response is a receipt - the submission as it arrived, never a live view of DHIS2
data.

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
otherwise defines - each module docstring states why. The filtering module is the register's value
filter, `d2-attribute={attributeUid}|{value}`: which attributes each register answers it on, how the
two backends run it, and why it answers equality and nothing else.

::: dhis2w_fhir_serve.register.index

::: dhis2w_fhir_serve.register.surface

::: dhis2w_fhir_serve.register.wire

::: dhis2w_fhir_serve.register.projection

::: dhis2w_fhir_serve.register.listing

::: dhis2w_fhir_serve.register.filtering

::: dhis2w_fhir_serve.routes.register

### The projection seams

**Reach for these when you are putting something other than the DHIS2 instance behind a register
search, or holding a copy of an instance as FHIR resources.** `NameSearchIndex` is what every
register search runs through: it answers with tracked entity identifiers and scores and never with
records, so the record behind a match is read back live, under the caller's own credentials, and
DHIS2 authorizes each disclosure exactly as it does today. `ProjectionStore` is the durable document
backend beside it, written by a sync and by nothing else. The design is
[the materialized projection](design/projection.md), sections 7 and 9.

Two backends of each ship. `Dhis2NameSearchIndex` is the instance itself, which is what
`[serve.search] backend = "dhis2"` selects and what a server that states no `[serve.search]` runs; it
improves nothing over the search a live run has always run, and proving the seam is its whole job.
`SqliteProjectionStore` and `SqliteNameSearchIndex` are the other half - one file under the project,
selected together by `[serve.projection] store = "sqlite"` and `[serve.search] backend =
"projection"`.

::: dhis2w_fhir_serve.projection.base

::: dhis2w_fhir_serve.projection.dhis2_names

::: dhis2w_fhir_serve.projection.factory

### The materialized projection

**Reach for these when you are filling a projection, reading one, or serving an answer out of one.**
`SqliteProjectionStore` is the reference implementation of `ProjectionStore` and the Embedded
posture's whole backend: SQLAlchemy over aiosqlite, one file, no service. `run_sync` is what fills
it - the initial materialization, the incremental `updatedAfter` poll with `includeDeleted=true` as a
constant, and the full rebuild - and `SyncReport` is what it answers with. `SqliteNameSearchIndex` is
the search over its keys, and `projection.serving` is how an answer served from it states the instant
it is as of.

**What none of them does is decide who may read what.** A projection-served answer names candidates;
the record behind each one is read from the instance under the caller's own credentials, so DHIS2
authorizes every disclosure per match per caller. That is R9's recommended posture (iii), and each
module docstring says where its half of it sits.

::: dhis2w_fhir_serve.projection.schema

::: dhis2w_fhir_serve.projection.sqlite_store

::: dhis2w_fhir_serve.projection.sqlite_names

::: dhis2w_fhir_serve.projection.sync

::: dhis2w_fhir_serve.projection.serving

### Enrollment listing

`GET /tracked-entities/{uid}/enrollments` - which programs one tracked entity is enrolled in, as the
picker's typed JSON feed rather than as a FHIR resource, because whether a DHIS2 enrollment is an
`EpisodeOfCare` or a `CarePlan` is a decision this project has deliberately not taken yet.

::: dhis2w_fhir_serve.routes.enrollments

### The record

`GET /tracked-entities/{uid}/events` - one tracked entity's own events, each served as the
`QuestionnaireResponse` its program stage's published form describes, and `GET
/tracked-entities/{uid}/events/{eventUid}` for one of them. Where the register answers who somebody
is, this answers what has happened to them: one entity-scoped read of the instance per request, under
the credentials of whoever asked. The wire module holds the read and the order it puts the record in,
and the projection turns one recorded event into the document the capture contract already states for
it - so the shape a client reads back is the shape a client would post.

::: dhis2w_fhir_serve.history.wire

::: dhis2w_fhir_serve.history.projection

::: dhis2w_fhir_serve.routes.history

### The patient summary

`GET /{type}/{id}/$summary` and `GET /{type}/$summary?identifier=` - the IPS's own two
addresses, answered on the register resources R4 gives a person and refused by name on the rest.
A summary reads nothing new: the subject is the resource the register already serves, and the
doses come off the very record projection above, read through the immunisation mapping
`[ips.sections.immunizations]` states. `dhis2w_fhir.summary` assembles the document; these two
modules are what finds the doses and what answers the request, with the document's caveat riding
the response as well as `Composition.text`.

::: dhis2w_fhir_serve.summary

::: dhis2w_fhir_serve.routes.summary

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

### Evaluating an expression

`POST /evaluate` - one FHIRPath expression, CQL library, or ELM library run over one resource this
facade serves, answering typed results and real diagnostics: a parse failure at the line and column
the parser stopped on, a per-define refusal in the define's own row. The engine layer is a pure
function over FHIR-shaped JSON, so a caller with a loaded store evaluates the same expression with no
server running. The sandbox is closed by construction - no library path is ever passed to the engine
and ELM is parsed to a dict before the engine sees it, so an expression reaches the supplied context
and nothing else.

::: dhis2w_fhir_serve.evaluation

::: dhis2w_fhir_serve.routes.evaluate

### The evaluation as a Parameters resource

`POST /$evaluate` - the same evaluation, answered as the `Parameters` resource a FHIR client expects
from an operation: one parameter per define named by the define, `value[x]` for a single primitive,
`resource` where a define answered a resource, one `part` per value where it answered several, an
`OperationOutcome` part where it refused, and an `outcome` parameter carrying the line and column a
parser stopped on. Both directions are pure functions - `evaluation_ask` reads a `Parameters` input
into the request it asks for, `evaluation_parameters` says one `EvaluationOutcome` in FHIR's own
terms - so a caller assembling or reading an operation body needs no server running.

::: dhis2w_fhir_serve.routes.evaluate_operation

### This guide's vocabularies

`GET /terminology/validate-code` and `GET /terminology/lookup` - is this code in that published value
set, and what is this code called. It answers about the CodeSystems and ValueSets **this project
publishes** and is not a general terminology server: a SNOMED CT or LOINC code is answered "this
server publishes no code system under that url". Membership goes to the engine's in-memory
terminology service, so the composition rules are the engine's; the code systems are indexed here,
because that service takes none through its public surface.

::: dhis2w_fhir_serve.terminology

::: dhis2w_fhir_serve.routes.terminology

### CDS Hooks

`GET /cds-services` and `POST /cds-services/{id}` - the discovery document and one service, which
evaluates a caller-supplied CQL library (or a Library this guide publishes) over the resources the
hook prefetched and answers one card per define that resolves to true or to a message. There is no
feedback endpoint, no suggestions, and no second service; each would mean an EHR state this facade
does not hold.

::: dhis2w_fhir_serve.routes.cds

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
