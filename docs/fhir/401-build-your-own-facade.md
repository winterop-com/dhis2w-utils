# Build your own facade

**Who this is for:** the developer who already has a FastAPI application and
wants it to receive FHIR captures - fluent in Python, DHIS2 knowledge optional.

**Before you start:** a project whose guide you can build a translation context
from ([Set up an IG project](201-set-up-a-project.md)) and what a valid
submission is ([The capture contract](401-capture-contract.md)).

**You will be able to:**

- build a `ConversionContext` and translate a `QuestionnaireResponse` with it
- post each translated payload to the DHIS2 endpoint its shape names
- answer a refusal with the categories, elements, and reasons the translator gave
- decide which of four facade shapes your integration actually needs
- see the point at which writing more of one costs more than running
  `d2w fhir serve`

## Two postures

`d2w fhir serve` is the complete facade. It publishes the guide, states its own
capabilities at `/metadata`, answers the register off the live instance, stores
every submission as a receipt, and hands that spool to `d2w fhir forward`, which
drains it into DHIS2 and files each receipt under what DHIS2 said. Nothing in
that chain is optional to it: the durability *is* the product.

Most integrations do not want a second server. They have an application, it
already has authentication, logging, and a queue for work that failed, and what
they need from this toolchain is the one piece they cannot write themselves -
the translation from a captured `QuestionnaireResponse` into the DHIS2 import
payload it means. That is `translate_response`, and everything around it is
about fifty lines of FastAPI.

The two are not exclusive. A deployment often serves the guide from
`d2w fhir serve` for discovery and reads, and receives its own traffic on its own
route, both built from the same published artifacts.

## The ladder

Between those two postures there is a ladder, and each rung buys back exactly
one guarantee the rung below traded away. Four runnable files walk it:

| Rung | What it adds | What it still gives up |
| --- | --- | --- |
| [minimal](#rung-one-minimal) | one route: translate, post, answer with DHIS2's verdict | everything else - nothing is written down, and a client per request |
| [basic](#rung-two-basic) | one client for the process, settings at startup, `/health`, a log line per verdict | durability: an unreachable instance is still a failed request |
| [complex](#rung-three-complex) | a durable spool, `201` before DHIS2 is asked, a background drain, receipts readable by id | tracker routing, the coded-answer dial, overwrite naming, any published surface |
| [advanced](#rung-four-advanced) | tracker routing, the strict/lenient dial, overwrite naming, a small `/metadata` | the register, the guide, capture screens, requeue, a drain that is its own process |

Read the last column downwards. Each rung's remaining gap is the next rung's
subject, and the last rung's gap is the served facade itself - which is the
whole argument of [When to stop building](#when-to-stop-building).

The rungs are cumulative in guarantees, not in code: each file is standalone and
runs on its own, so a rung can be read cold without the three below it.

## Rung one: minimal

[`examples/fhir/client/minimal_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/minimal_facade.py) -
one file, one route, and a `__main__` that drives it in-process. This section
walks it in the order the code reads.

### Build the context once

A `ConversionContext` carries everything the translator reads besides the
response: the served forms, the option terminology, the published `Location`
table it resolves organisation units through, and the naming a project's
extensions are written in.

```python
from dhis2w_fhir import build_project_context, load_project, service

project = load_project(project_root)
artifacts = await service.fetch_live_artifacts(client, project)
context = build_project_context(project, artifacts)
```

It is a `BaseModel` and it is frozen, so build it at start-up, keep it for the
process, and rebuild it when the instance's metadata moves. `fetch_live_artifacts`
reads the instance; `load_compiled_artifacts` reads a SUSHI-compiled guide off
disk instead, and both produce the same thing.

### Receive the response

```python
@app.post("/QuestionnaireResponse")
async def capture(response: QuestionnaireResponse) -> JSONResponse:
```

`dhis2w_fhir.r4.QuestionnaireResponse` is a pydantic model, so FastAPI parses and
validates the body before the function runs. Every R4 model here is closed: an
unknown key, or a `value[x]` the element does not have, is FastAPI's own 422 and
never reaches the translator.

### Translate, and answer a refusal

```python
result = translate_response(response, context)
if result.is_refused:
    refusals = [refusal.model_dump(mode="json", exclude_none=True) for refusal in result.refusals]
    return JSONResponse(status_code=422, content={"refusals": refusals})
```

A refusal is about the response alone - the instance is never asked about it.
Each `ConversionRefusal` carries a `category` a caller can route on, a `reason`
written for a person, and the `link_id` or `element` it stumbled on:

```json
{
  "refusals": [
    {
      "category": "unknown-form",
      "reason": "`http://example.org/fhir/Questionnaire/NotAServedForm` is no form this context carries",
      "element": "QuestionnaireResponse.questionnaire"
    }
  ]
}
```

`translate_response` is a pure function of the response and the context, so this
half of the route is testable without a DHIS2 instance anywhere near it.

### Post the payload to the endpoint its shape names

`ConversionResult.payload` is whichever document the translation produced, and
the typed field that carried it says where it goes:

| The result carries | Endpoint | Body |
| --- | --- | --- |
| `data_value_set` | `/api/dataValueSets` | the envelope itself |
| `tracked_entity` | `/api/tracker` | `{"trackedEntities": [payload]}` |
| `enrollment` | `/api/tracker` | `{"enrollments": [payload]}` |
| `event` | `/api/tracker` | `{"events": [payload]}` |

Exactly one is ever set. `target_kind` alone cannot decide it: a registration
produces a `tracked_entity` for a person DHIS2 does not hold yet and an
`enrollment` alone for one it does, under the same kind - and an enrollment that
rides inside a `trackedEntities` wrapper rewrites the person's owning
organisation unit, which is not this submission's to move.

The tracker endpoint is posted with `importStrategy=CREATE` and `async=false`, so
the answer to the request is the import report rather than a job to poll.

```python
async with open_client(profile) as client:
    verdict = await client.post_raw(path, body, params=params)
```

### Pass DHIS2's verdict back under DHIS2's status

**A refused import is not an error.** DHIS2 answers one with `409 Conflict`
carrying its own report, and a payload it will not read at all with a `400`, so
the route catches `Dhis2ApiError` and answers with the instance's own status
and body:

```python
except Dhis2ApiError as error:
    if error.status_code >= SERVER_ERROR_STATUS or not isinstance(error.body, dict):
        raise
    return JSONResponse(status_code=error.status_code, content=error.body)
```

Two things are re-raised rather than passed on. A body that is not a report at
all - an authentication failure, an unreachable instance - is about the run and
not about this capture. And a 5xx is the instance *failing* rather than
answering: DHIS2 and the proxies in front of it wrap a server error in a
`WebMessage` with a `status` in it, and reading that as a verdict would file a
refusal DHIS2 never made.

### The three verdicts the demo drives

The example's `__main__` posts three captures, which are the three answers a
facade can give:

| The capture | Answer | Who decided |
| --- | --- | --- |
| a form the context carries | `200` with the import summary | DHIS2 took it |
| a place the form is not collected at | `409` with conflict `E8022` | DHIS2 refused it |
| a form the context does not carry | `422` with `unknown-form` | the translator refused it |

The middle one is worth a second look, because it is the only capture in these
four examples that is *well formed and still refused*. It answers a served form,
names a published `Location`, states a period the calendar holds, and types
every answer the way the form types it - so the translator has nothing to object
to. What it reports is a chiefdom, and the seeded instance collects Child Health
at facilities. Only the instance knows that, which is why the verdict has to
come back from DHIS2 rather than from the translator.

That division is worth stating plainly, because it decides where your own
failures will come from: the translator guards the payload thoroughly - the
form, the place, the period, the answer types, the codes - so what is left for
DHIS2 to refuse is what only DHIS2 knows. Assignment, as here. And, on a live
instance, the state a demo instance does not carry: a locked period, an approved
data set, sharing that was revoked since the form was published.

### Validate without writing

Both endpoints have a mode that grades a payload and stores nothing -
`dryRun=true` on `/api/dataValueSets`, `importMode=VALIDATE` on `/api/tracker`.
The example's `__main__` posts under it, which is what lets the example run in
`make verify-examples` without leaving data on the instance. A real facade drops
the parameter.

## Rung two: basic

[`examples/fhir/client/basic_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/basic_facade.py) -
the same one route, in the shape a deployment runs it in. Four changes, no new
guarantees about the capture itself.

**Settings resolved once.** `FacadeSettings.resolved()` reads the profile at
startup - `DHIS2_PROFILE`, or the configured default - so a process that cannot
name its instance fails at boot rather than at the first capture.

**One client for the process.** `open_client` reads `/api/system/info` to bind
the version tree, so opening one per capture is a second round trip per capture.
The client is opened in a FastAPI lifespan and held in a small runtime model:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with open_client(settings.profile) as client:
        runtime.client = client
        yield
        runtime.client = None
```

The lifespan is what uvicorn runs at startup and shutdown. Note what the
example's `__main__` has to do about that: `httpx.ASGITransport` calls the
application and nothing else, so a demo that only wrapped the app in a transport
would find `runtime.client` still `None` inside every route. Entering
`app.router.lifespan_context(app)` by hand is the fix, and it is exactly what
`asgi-lifespan`'s `LifespanManager` does for a test suite.

**`/health`.** One uncached read of `/api/system/info`, answered as a small
`HealthReport`: whether DHIS2 is reachable, which instance and profile, and the
version it reported. Uncached on purpose - a cached answer says the instance was
reachable once, which is not the question. An unreachable instance is a `503`
carrying the sentence that explains it.

**One log line per verdict.** Accepted, refused by the translator, refused by
DHIS2 - each is one line through the `logging` module, so a capture six weeks
old is answerable.

The trade is unchanged from rung one and worth naming again: a capture that
arrives while DHIS2 is unreachable is a failed request, and its sender is the
only place it exists.

## Rung three: complex

[`examples/fhir/client/complex_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/complex_facade.py) -
where a capture starts surviving. The route's answer stops being DHIS2's verdict
and becomes a receipt id.

### Receive, write, answer - in that order

```python
result = translate_response(response, runtime.context)  # validation, not the send
if result.is_refused:
    return JSONResponse(status_code=422, content={"refusals": refusals})
runtime.spool.save(envelope)  # durable: fsync, rename, fsync
return JSONResponse(status_code=201, content=accepted.model_dump(mode="json"))
```

Translating at the door is validation: a response the translator will not read is
refused while there is still a client on the other end of the request to tell.
Everything after that is written down first and posted later, and the `201`
carries the id the capture is readable under from then on.

### The spool is the library's, not the example's

Nothing about the receipt tree is reimplemented in the example. It is the same
tree `d2w fhir serve` writes and `d2w fhir forward` drains, through the same
published primitives:

| Side | Module | What the example uses |
| --- | --- | --- |
| write | `dhis2w_fhir_serve.spool` | `ResponseSpool.save`, `get`, `import_report`, `refusal_record` |
| drain | `dhis2w_fhir.spool` | `read_received_responses`, `move_to_forwarded`, `move_to_rejected`, `record_refusal`, `drain_lock` |

`ResponseSpool.save` writes through a temporary sibling, `fsync`s the file,
renames it, and `fsync`s the directory. That ordering is the whole reason a
`201` from this facade is a promise rather than a hope, and it is not a thing
worth having a second version of - which is why the example imports it.

Where the tree sits is `SpoolLayout.resolve(project_root)`, the same resolution
of `[serve] spool_dir` both halves of the served chain read, so a project that
moved its receipts moved them for the writer and the drain at once. The example
uses a scratch directory and says in a comment what a deployment uses instead.

### The drain

A background `asyncio` task, started in the lifespan and cancelled before the
client closes under it. Each pass takes the spool's own `drain_lock` - the same
lock `d2w fhir forward` takes, because this facade's drain is exactly the kind
of second drain that lock exists to refuse - reads `received/`, and files each
receipt the moment its verdict is known:

- DHIS2 took it: `move_to_forwarded(spooled, record)`, with the import counts and
  the cells the payload landed on written into the sidecar beside it.
- DHIS2 refused it: `move_to_rejected(spooled, record)`, with DHIS2's own reasons
  in the sidecar.
- The translator refused it: nothing moves. `record_refusal` leaves the reason
  beside the queued receipt, and the next pass is the retry. A guide can move
  between the capture and the drain, so this is not a case that cannot happen.
- The instance did not answer: nothing moves and nothing is lost. The pass logs
  it and the next pass reads the same queue.

### Reading a receipt back

`GET /receipts/{id}` answers where a capture stands: its state, and whatever the
drain wrote beside it - DHIS2's import counts once a drain has asked, or the
translator refusal record while it is still queued. A receipt is readable in
every state, forever, because expiring the id a client was handed at capture time
would break that client on a schedule nothing told it about.

The example's `__main__` posts one capture, polls its receipt until the drain has
filed it, and prints the journey. It imports for real and deletes the two values
again at the end, so a run leaves the instance as it found it.

## Rung four: advanced

[`examples/fhir/client/advanced_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/advanced_facade.py) -
the durable rung plus the four things it lacked.

**Tracker routing.** `post_payload` branches on which field the translation
filled and posts to the endpoint that shape names, projecting either answer into
one `ForwardImportRecord`: `/api/dataValueSets` answers an `ImportSummary`
wrapped in a `WebMessage`, `/api/tracker` answers a `TrackerImportReport` bare,
and a reader of either wants the same three things - which rule, which object,
what it said. The demo captures an event of a program without registration.

**The coded-answer dial.** `strict` or `lenient` is application configuration
here, resolved at startup and stamped onto the context so every translation the
process runs reads coded answers the same way:

```python
dialled = context.model_copy(update={"coded_answer_mode": settings.coded_answers})
```

It is the same dial `[serve] strict_codes` sets for a served facade and
`d2w fhir forward` inherits - see
[What `--strict-codes` turns into a refusal](401-capture-contract.md#what-strict-codes-turns-into-a-refusal).

**Overwrite naming.** Before a pass posts an aggregate payload it builds
`build_forwarded_cell_index(layout)` - one read of the sidecars in `forwarded/` -
and names every value a forwarded receipt already sent. DHIS2 cannot answer that
question: it replaces such a value in place and counts the write exactly like a
first entry, so no import summary separates the two. Nothing is refused over it;
the drain says so and the operator decides. The demo posts the same two cells
twice to make the naming happen.

**A small `/metadata`.** The forms this facade accepts, the two routes it answers
on, and the dial it is running under - and explicitly **not** a FHIR
CapabilityStatement. A CapabilityStatement is a claim about a FHIR server:
resources served, searches answered, interactions supported. This facade serves
no FHIR resource and answers no search, so publishing one would be a claim it
cannot keep.

## When to stop building

Each rung closes the gap below it. The gap left at the top is not a fifth rung -
it is `d2w fhir serve` plus `d2w fhir forward`, and every item is something the
served chain already does:

| Still missing at rung four | What the served chain provides |
| --- | --- |
| capability discovery | a real `/metadata` CapabilityStatement, stating the resources served, the searches answered, and the operations that exist - [Consume the FHIR API](401-consume-the-fhir-api.md) |
| the guide itself | the published implementation guide served beside the API, so a client reads the forms it is submitting against - [Serve the guide](201-serve.md) |
| the register | `Patient` search and read off the live instance, which is how a client resolves who a person is |
| capture screens | the capture UI a person fills a form in, served from the same process |
| a refused receipt's second chance | `d2w fhir spool` lists the queue and `d2w fhir requeue` puts a rejected receipt back in it once the cause is fixed - [Forward captures into DHIS2](201-forward.md#putting-a-refused-receipt-back-in-the-queue) |
| a drain that is its own process | `d2w fhir forward` runs on its own schedule, so a slow or unreachable instance cannot hold up the process that is receiving captures |
| the five form kinds, all of them | every profile of [the capture contract](401-capture-contract.md), including registration and stage forms |
| completeness registration | a `completed` aggregate response also registers the data set complete, after DHIS2 takes the values - [Data set completeness](201-forward.md#data-set-completeness) |
| a drain report | `ForwardReport` - counts, per-receipt outcomes, rejection reasons rolled up by cause - [`forward_spool.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/forward_spool.py) |

**The rule of thumb.** Take your own route while the answer to the request is
the whole of what the sender needs, and the durability lives in your
application. Climb a rung when a capture has to outlive the request. And when
you find yourself writing the rung above the fourth - a register, a
CapabilityStatement, a requeue command - stop: you are rebuilding
`d2w fhir serve` smaller, and it is one command.

## Next

Read the four files, in order:
[`minimal_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/minimal_facade.py),
[`basic_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/basic_facade.py),
[`complex_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/complex_facade.py),
[`advanced_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/advanced_facade.py).
Each runs with `uv run python examples/fhir/client/<name>.py`. What counts as a
valid submission - the five form kinds, the required extensions, and every rule a
response must meet before any of this applies - is
[The capture contract](401-capture-contract.md). The Python surface itself is
documented in [the `dhis2w_fhir` API reference](api-dhis2w-fhir.md).
