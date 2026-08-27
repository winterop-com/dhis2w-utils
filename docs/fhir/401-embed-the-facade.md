# Embed the facade

**Who this is for:** the developer who wants the FHIR facade inside their own
process - as a library, with no server to run, no port to bind, and no UI.

**Before you start:** a project you can serve
([Serve the guide](201-serve.md)) and the `[serve]` extra installed
(`uv sync --all-extras`, or `pip install 'dhis2w-cli[serve]'`).

**You will be able to:**

- build the facade with `create_app` and drive it over an ASGI transport
- take a capture with no server and read the receipt it wrote to disk
- drain that spool from the same process, through a connection you own
- fill and read the materialized projection - the local storage layer - from Python
- mount the facade's routers inside your own FastAPI application, behind your
  own authentication

**The runnable version of this page** is the five files this page quotes:
[`embed_the_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/embed_the_facade.py),
[`capture_headless.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/capture_headless.py),
[`forward_headless.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/forward_headless.py),
[`projection_local_store.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/projection_local_store.py),
and
[`embed_in_fastapi.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/embed_in_fastapi.py).
Every console block below is their output.

## The third posture

[Build your own facade](401-build-your-own-facade.md) sets out two: run
`d2w fhir serve`, or write your own route over `translate_response`. There is a
third between them, and for a lot of integrations it is the right one - **take
this facade as a library**. `d2w fhir serve` is one caller of `create_app`, not
the way in: the factory takes settings and answers a FastAPI application, and an
ASGI transport speaks to that application directly.

Nothing is on the network. The answers are the ones a served facade returns,
because they are produced by the same routers over the same store.

## The pattern

Three lines carry it:

```python
from dhis2w_fhir_serve import ServeSettings, create_app

application = create_app(ServeSettings(project_dir=project_root, live=True))

async with application.router.lifespan_context(application):
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://embedded") as client:
        capability = (await client.get("/metadata")).raise_for_status().json()
```

1. `create_app` builds the application and loads nothing.
2. `lifespan_context` runs the startup an ASGI server would have run: the
   project is read, the store is built, the spool is opened, and `/metadata` is
   rendered once.
3. `ASGITransport` calls the application in this event loop. The `base_url` names
   no host and reaches none - it is the authority in front of every path.

```console
$ uv run python examples/fhir/client/embed_the_facade.py
d2w fhir serve 1.8.0.dev0 - loaded, not listening
  serves: QuestionnaireResponse, Questionnaire, CodeSystem, ValueSet, Location, Organization, List, ConceptMap, Patient
7 Questionnaire(s) published
  ZzYYXq4fJie      Child Programme - Baby Postnatal
  A03MvHHogjR      Child Programme - Birth
  BfMAe6Itzgt      Child Health
  IpHINAT79UW      Child Programme
  TuL8IOPzpHh      EPI Stock
facade closed - no port was ever bound
```

`live=True` builds the store off the DHIS2 instance the project's profile names,
which is what a project that has never run SUSHI has to do. `live=False` serves
the compiled guide on disk and needs no instance at all.

**`ServeSettings.resolve` is the other constructor**, and it is the one
`d2w fhir serve` uses: it reads `fhir.toml`, resolves the profile, and refuses
the run for the five postures it cannot honour before anything is built.
Constructing `ServeSettings` directly - as above - states the settings outright
and skips those refusals, which is the right trade for a process that decides
its own configuration. See [Serving](301-serving.md) for what the table holds.

## Capture with no server

The capture surface is a route like any other, so an embedded facade receives
submissions by being handed one:

```console
$ uv run python examples/fhir/client/capture_headless.py
$generate on BfMAe6Itzgt: a completed draft with 2 item(s)
POST -> 201, receipt 65feb2ba5fd84c3784525312197b72f2 answering http://example.org/fhir/example-demo/Questionnaire/BfMAe6Itzgt
spool: .../.serve/responses
  14 not yet sent to DHIS2, 2 accepted by DHIS2, 0 refused by DHIS2, 0 unreadable
  this run wrote 65feb2ba5fd84c3784525312197b72f2: aggregate capture, received, at 2026-08-22T10:31:27Z
```

The receipt outlives the application, because a capture is a file: the spool is
a directory of JSON envelopes, and which directory a receipt is in is its state.
`d2w fhir spool` reads the same tree, and so does `service.read_spool_state`.

**The posture is `auth = "none"`, and for an embedded facade that is the honest
one.** An authentication posture answers "which callers on the network may
submit"; over an ASGI transport there is no network and no caller but the
program holding the application, so the process boundary is the trust boundary.
A posture is what you state when you put the same application on a socket -
which the last section does.

## Drain from the same process

`forward_responses` is what `d2w fhir forward` calls, and an embedder calls it
with two things the command line cannot give it:

- **A connection it owns.** A drain given `client=` reads and posts through that
  connection and leaves it open, so a process that already holds a DHIS2 client
  spends no new one on the drain.
- **Dials as arguments.** Each of the six is `None` for "the caller stated
  nothing", which falls to `fhir.toml` and then to the key's own default. A
  service that decides these in its own configuration states them here.

```console
$ uv run python examples/fhir/client/forward_headless.py
instance: http://localhost:8080 (profile local_basic)
dry run, lenient coded answers
  14 spooled, 14 translated, 0 refused, 14 posted (validate only), 10 accepted, 4 rejected
  accepted      0ba507bf613548b2b2c2a204ea976e54   data-value-set
  rejected      cf148d711b1d4e9bb6ce85d904e6588d   tracker-event
  rejected x4 [E1079] Event: `...` Program: `...` is different from Program defined in Enrollment `...`.
```

A dry run is the default and it is a real run: every payload goes to the real
endpoint under that endpoint's own validate-only mode, so DHIS2's rules decide
each answer while nothing is written and no receipt moves. See
[Forward captures into DHIS2](201-forward.md) for the states and the postures.

## The local storage layer

A [materialized projection](design/projection.md) is a durable copy of the
mapped scope of an instance, held as the FHIR resources this project's map
publishes. `run_sync` fills it - it is what `d2w fhir sync` calls - and
`ProjectionStore` is the protocol every read goes through:

```console
$ uv run python examples/fhir/client/projection_local_store.py
projection: .../.serve/projection.sqlite
sync (incremental): created 0, updated 1, removed 0 over 2 page(s)
read as far as: tracked entities 2026-08-22 00:06:48.152000, enrollments 2026-08-22 00:06:47.986000
answers are as of: 2026-08-22 00:06:47.986000
518 Patient(s) held; this page carries 3
  A9wHDpwJSpk http://dhis2.org/fhir/id/tracked-entity|A9wHDpwJSpk (3 attribute value(s))
identifier A9wHDpwJSpk: 1 match(es)
membership of A9wHDpwJSpk: held
membership of nobodyAtAll: not held
```

**DHIS2 stays the record.** The projection is derived, a sync is the only thing
that writes it, it is rebuildable from zero as a routine operation, and every
answer out of it states the instant it is as of - the earlier of the two
collection watermarks, because a projection is as current as its least current
half. A row that disagrees with the instance is a defect of the sync, and the
fix is another sync rather than an edit.

**A projection never authorizes.** It decides who is on the page; the record a
caller receives is read back from DHIS2 under that caller's own credentials, so
the instance decides every disclosure exactly as it does without one.

## Mount it in your own FastAPI application

The other seam, for a service that already IS a FastAPI application. Three
functions are the whole contract:

```python
from dhis2w_fhir_serve import attach_serve_runtime, open_serve_runtime, register_routes


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    async with open_serve_runtime(settings) as runtime:
        attach_serve_runtime(application, runtime)
        yield


application = FastAPI(lifespan=lifespan)
register_error_handlers(application)
# ... this service's own routes ...
register_routes(
    application,
    auth=settings.auth,
    auth_scope=settings.auth_scope,
    authentication=require_example_key,
)
```

- **`open_serve_runtime`** loads what one facade holds - the project, the store,
  the spool, the register, and the connections a live run reads through - as a
  value, without building an application. Its lifetime is the caller's.
- **`attach_serve_runtime`** puts that runtime where every route handler reads it
  from. It is the whole of what an application mounting these routers promises.
- **`register_routes`** mounts them. `authentication` is the dependency the
  guarded routers carry, and an application that already knows who its callers
  are passes its own. Which routers it lands on is `ServeRouters.guarded` - a
  value the program can read for itself. FHIR lands at the base URL, and the
  facade's own API - the receipts, the settings, the caller, the evaluator, the
  vocabularies, the register listings - lands at `/facade` as an application of
  its own, contract included, at `/facade/openapi.json`. An application that
  wants those controls somewhere else builds them with `build_facade_api` and
  mounts that under a prefix of its own choosing; one that wants FHIR and
  nothing operational mounts `ServeRouters` without them.

**Mount your own routes first.** The facade's read routes are catch-alls -
`/{resource_type}` claims any one-segment path - and `register_routes` puts them
last so every fixed path ahead of them wins. A route added after that call is a
route the catch-all already claimed.

```console
$ uv run python examples/fhir/client/embed_in_fastapi.py
guarded routers: 16 of 17
GET /status -> the embedding application
GET /metadata -> 200 (no key sent)
GET /Questionnaire -> 401 this service needs its own key
GET /Questionnaire with the key -> 200, 7 form(s)
GET /facade/spool with the key -> 200
GET /facade/openapi.json -> 10 operations, served under /facade (no key sent)

FHIR only: GET /metadata -> 200, GET /Questionnaire -> 200
FHIR only: GET /facade/spool -> 404 (nothing operational mounted)

Controls at /controls: GET /controls/spool -> 200
Controls at /controls: the contract names 10 operations under /controls
```

`auth_scope = "all"` guards everything but `/metadata`, which stays open because
a client has to be able to read the posture it is expected to meet. The 401 is
this application's own refusal, answered as an `OperationOutcome`: the facade's
error handlers are registered on the app, so a FHIR client reads a FHIR refusal
whoever raised it. `/facade/openapi.json` answers without the key under that same
scope, for `/metadata`'s reason: a contract nobody may read is a contract nobody
can meet.

The last two blocks are the same program mounting the groups by hand rather than
through `register_routes` - once with the FHIR surface alone, where no
operational address exists to refuse, and once with the controls under a prefix
this service chose. The contract moves with them: it names the same ten
operations under whichever base they were mounted at.

Next: [Build your own facade](401-build-your-own-facade.md) for the case where
you want the translation and none of the rest of this. The
[`dhis2w_fhir_serve` API reference](api-dhis2w-fhir-serve.md) documents every
symbol named on this page.
