# Build your own facade

**Who this is for:** the developer who already has a FastAPI application and
wants it to receive FHIR captures - fluent in Python, DHIS2 knowledge optional.

**Before you start:** a project whose guide you can build a translation context
from ([Set up an IG project](201-set-up-a-project.md)) and what a valid
submission is ([The capture contract](401-capture-contract.md)).

**You will be able to:**

- decide between the complete served facade and one route of your own
- build a `ConversionContext` and translate a `QuestionnaireResponse` with it
- post each translated payload to the DHIS2 endpoint its shape names
- answer a refusal with the categories, elements, and reasons the translator gave
- state plainly what the small facade trades away, and when that trade is wrong

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

| Take the served facade when | Take your own route when |
| --- | --- |
| the submitting side is somebody else's client, and discovery matters | you write both sides, and the contract is agreed out of band |
| a refused capture must survive until a person fixes it | your application already owns the retry |
| the receipts are the record of what was submitted | your own store is the record |
| you want the guide, the register, and the capture screens served too | you want one route inside an application that exists |

The two are not exclusive. A deployment often serves the guide from
`d2w fhir serve` for discovery and reads, and receives its own traffic on its own
route, both built from the same published artifacts.

## The recipe

The runnable version is
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

**A refused import is not an error.** DHIS2 answers one with `409 Conflict`
carrying its own report, so the route catches `Dhis2ApiError`, passes the body
back when there is one, and re-raises when there is not - a failure to
authenticate or an unreachable instance is about the run, not about this
capture.

Whether you open a client per request or hold one for the process is your call.
`open_client` reads `/api/system/info` to bind the version tree, so a facade
taking captures continuously should hold one open in a FastAPI lifespan; the
example opens one per request because that keeps the recipe a single function.

### Validate without writing

Both endpoints have a mode that grades a payload and stores nothing -
`dryRun=true` on `/api/dataValueSets`, `importMode=VALIDATE` on `/api/tracker`.
The example's `__main__` posts under it, which is what lets the example run in
`make verify-examples` without leaving data on the instance. A real facade drops
the parameter.

## What the small facade gives up

Every one of these is a thing `d2w fhir serve` plus `d2w fhir forward` does and
this route does not. None of them is an accident, and each is a reason to reach
for the served chain instead.

- **Durable receipts.** The served facade stores every submission as received and
  serves it back by id, forever. Here, the verdict is the answer to the request
  and nothing is written down.
- **The retryable spool.** A capture that arrives while DHIS2 is unreachable
  waits in the spool and drains later. Here, an unreachable instance is a failed
  request, and retrying it is the caller's job.
- **The refused queue.** A receipt DHIS2 rejected is kept, readable, and put back
  in the queue with `d2w fhir requeue` once the cause is fixed. Here, a refusal is
  a 422 body and then it is gone.
- **Capability discovery.** `/metadata` states which resources are served, which
  searches answer, and which operations exist, so a client learns the surface
  rather than being told it. Here there is one route at one address.
- **The register.** `Patient` search and listing, answered from the live
  instance, is how a client resolves who a person is. Here, your own application
  answers that.
- **The strict/lenient dial on coded answers.** `--strict-codes` moves five
  findings between warning and refusal on a served facade. Here, the behaviour is
  whatever `ConversionContext` the process was handed, and changing it means
  building a different context.
- **Overwrite naming on drains.** A drain says which values a previous submission
  already sent, so an operator can see a resubmission before it lands. Here, each
  capture is posted on its own, with no memory of the last.

The full chain remains the durable posture. Reach for the recipe when the
submitting side is yours and the durability lives in your application; reach for
[Serve the guide](201-serve.md) and
[Forward captures into DHIS2](201-forward.md) when it has to live here.

## Next

Read the file:
[`examples/fhir/client/minimal_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/minimal_facade.py),
and run it with `uv run python examples/fhir/client/minimal_facade.py`. What
counts as a valid submission - the five form kinds, the required extensions, and
every rule a response must meet before any of this applies - is
[The capture contract](401-capture-contract.md). The Python surface itself is
documented in [the `dhis2w_fhir` API reference](api-dhis2w-fhir.md).
