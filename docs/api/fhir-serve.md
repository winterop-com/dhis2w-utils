# FHIR facade server (`dhis2w_fhir_serve`)

`dhis2w_fhir_serve` is the package behind [`d2w fhir serve`](../guides/fhir/201-serve.md):
a FastAPI application that serves one generated IG as a FHIR endpoint and receives
QuestionnaireResponse captures against it. It is its own workspace member because it needs FastAPI
and uvicorn, and `dhis2w-fhir` - which generates a file tree - needs neither; `pip install
'dhis2w-cli[serve]'` (or `uv add dhis2w-fhir-serve`) is what puts the command on the CLI.

Everything a running facade serves is loaded once at startup and held on `app.state.context`, so a
request is index lookups and nothing else. The store is either the compiled IG on disk or - under
`--live` - the same read set built off a DHIS2 instance through one client opened during startup
and closed before the first request arrives.

The receipt spool is the one exception, and deliberately so: it is a path rather than a loaded
index, and every read of it re-reads the directory. `d2w fhir forward` runs as a separate process
and renames receipt files between the spool's three lifecycle directories while the server is up,
so anything cached would be stale within seconds of a drain.

## When to reach for it

- Embed the facade in another ASGI process (`create_app`, `ServeSettings`).
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

## Reference

### Settings

What one running facade is built from: the project it serves, whether the store is built live,
which DHIS2 profile that build reads with, and how strictly a received code is checked.

::: dhis2w_fhir_serve.settings

### Application

The app factory and the lifespan that loads the project, its store, and its spool once.

::: dhis2w_fhir_serve.app

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
