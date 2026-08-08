# FHIR facade server (`dhis2w_fhir_serve`)

`dhis2w_fhir_serve` is the package behind [`d2w fhir serve`](../guides/fhir-ig.md#serving-the-ig):
a FastAPI application that serves one generated IG as a FHIR endpoint and receives
QuestionnaireResponse captures against it. It is its own workspace member because it needs FastAPI
and uvicorn, and `dhis2w-fhir` - which generates a file tree - needs neither; `pip install
'dhis2w-cli[serve]'` (or `uv add dhis2w-fhir-serve`) is what puts the command on the CLI.

Everything a running facade serves is loaded once at startup and held on `app.state.context`, so a
request is index lookups and nothing else. The store is either the compiled IG on disk or - under
`--live` - the same read set built off a DHIS2 instance through one client opened during startup
and closed before the first request arrives.

## When to reach for it

- Embed the facade in another ASGI process (`create_app`, `ServeSettings`).
- Load a project's served resources without an HTTP server (`load_compiled_store`, `ResourceStore`,
  `SearchQuery`, `IdentifierToken`).
- Read or write the received-response spool a running facade keeps
  (`ResponseSpool`, `StoredResponseEnvelope`, `RECEIVED_RESPONSES_RELATIVE_PATH`).
- Validate a QuestionnaireResponse against a served IG outside the endpoint
  (`validate_response`, `build_capture_index`, `CaptureNaming`, `CodingResolverSet`).
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

Every received QuestionnaireResponse, held in memory and mirrored atomically to
`.serve/responses/received/`. A stored response is a receipt - the submission as it arrived, never
a live view of DHIS2 data.

::: dhis2w_fhir_serve.spool

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
