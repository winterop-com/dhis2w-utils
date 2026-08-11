# Consume the FHIR API

**Who this is for:** the integration developer talking to a running
`d2w fhir serve` facade - fluent in FHIR, no DHIS2 knowledge assumed.

**Before you start:** a served project ([Serve the guide](201-serve.md)) and
what a valid capture is ([The capture contract](401-capture-contract.md)).

**You will be able to:**

- discover what a facade serves from `/metadata` and nothing else
- read and search the published resources, including the identifier search
  that groups a program's forms
- resolve generated codes back to DHIS2 identifiers with `$translate`
- get a valid, reproducible test submission from `$generate`
- post a capture and read every kind of answer the server gives
- read the two non-FHIR endpoints, `/spool` and `/uiconfig`

Every response body on this page is real output from a running facade. The
GET examples run against a project served on port 8091; the POST transcripts
against a freshly scaffolded project on port 8378, because posting to
somebody's project spool is not a demo. The Python surface behind all of it
is documented in [the `dhis2w_fhir_serve` API reference](../../api/fhir-serve.md).

## Discovery: `/metadata`

The facade's only contract - it publishes no OpenAPI document. A `kind
#instance` CapabilityStatement that instantiates the IG's own
`D2CaptureServer` requirements statement, narrowed to what this store
actually holds:

```console
$ curl -s localhost:8091/metadata | jq '.software, .implementation.description'
{
  "name": "d2w fhir serve",
  "version": "1.6.0.dev0"
}
"DHIS2 FHIR capture facade (compiled store); stored QuestionnaireResponses are submissions as received - receipts, not a live view of DHIS2 data"
```

Operations are declared where R4 puts them - `$translate` at `rest.operation`
(type-level), `$generate` on the `Questionnaire` resource entry
(instance-level) - and only when the store can actually answer them:
`/metadata` never advertises what the store cannot do.

## Reads and searches

Seven definitional types are served - `Questionnaire`, `CodeSystem`,
`ValueSet`, `Location`, `Organization`, `List`, and `ConceptMap` - plus
`QuestionnaireResponse`, the one type the facade also receives. Anything
else is refused with an OperationOutcome saying so, rather than a bare 404
that would read as "no such resource":

```console
$ curl -s localhost:8091/Patient/abc
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this server does not serve the resource type `Patient`"}]}
```

A read is byte-faithful to what the project published; a missing id names
itself:

```console
$ curl -s localhost:8091/Questionnaire/BfMAe6Itzgt | jq .title
"Child Health"
$ curl -s localhost:8091/Questionnaire/NoSuchForm1
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-found","diagnostics":"no Questionnaire with id `NoSuchForm1` is served here"}]}
```

Searches answer a searchset Bundle. The definitional types take `_id`,
`url`, and `identifier`; the spool takes `_id` and `questionnaire`. Within
one parameter, comma-separated values are alternatives; across parameters
they combine. An unrecognised parameter is ignored rather than refused, and
the Bundle's `self` link echoes back only the parameters the server actually
applied, so a client can see what it got.

```console
$ curl -s 'localhost:8091/Questionnaire?_id=BfMAe6Itzgt,TuL8IOPzpHh' | jq .total
2
```

The identifier search is how a program's forms are grouped: every artifact
generated from one DHIS2 object carries that object's identifier, so a
system-qualified token selects a tracker program's registration form and
every stage form in one query -

```console
$ curl -s 'localhost:8091/Questionnaire?identifier=http://dhis2.org/fhir/id/program|IpHINAT79UW' \
    | jq '.entry[].resource.title'
"Child Programme - Birth"
"Child Programme"
"Child Programme - Baby Postnatal"
```

## `$translate`: generated codes back to DHIS2 identifiers

R4's type-level `ConceptMap/$translate`, answered over every ConceptMap the
project publishes. `system` and `code` are required - omitting either is a
400 OperationOutcome - and `targetsystem` optionally narrows to one target
namespace (R4's lowercase spelling and the `targetSystem` real clients also
send are both read):

```console
$ curl -s 'localhost:8091/ConceptMap/$translate?system=http://localhost:8080/fhir/CodeSystem/d2-os-OsVaccType1-cs&code=OptVacBCG01&targetsystem=http://dhis2.org/fhir/id/option-code' \
    | jq '.parameter'
[
  {
    "name": "result",
    "valueBoolean": true
  },
  {
    "name": "match",
    "part": [
      {
        "name": "equivalence",
        "valueCode": "equal"
      },
      {
        "name": "concept",
        "valueCoding": {
          "system": "http://dhis2.org/fhir/id/option-code",
          "code": "BCG",
          "display": "BCG"
        }
      },
      {
        "name": "source",
        "valueUri": "http://localhost:8080/fhir/ConceptMap/d2-os-OsVaccType1-cm"
      }
    ]
  }
]
```

Without `targetsystem` the answer carries one `match` per namespace the maps
target - for an option that is both the DHIS2 option UID and the option
code. A code the maps say nothing about is not an error; it is `result:
false` with a message:

```console
$ curl -s 'localhost:8091/ConceptMap/$translate?system=http://localhost:8080/fhir/CodeSystem/d2-os-OsVaccType1-cs&code=NotACode' \
    | jq '.parameter'
[
  {
    "name": "result",
    "valueBoolean": false
  },
  {
    "name": "message",
    "valueString": "no ConceptMap served here maps `NotACode` from `http://localhost:8080/fhir/CodeSystem/d2-os-OsVaccType1-cs`; the code system, the code, or the target system is not one this server holds a mapping for"
  }
]
```

The maps are served as documents too: `GET /ConceptMap/<id>` answers the
published map verbatim, and `GET /ConceptMap` searches them like any other
type. A read hands over the whole mapping table for a person to look at; the
operation answers the one question a client has without walking groups and
elements.

## `$generate`: a valid submission on demand

Hand it a served form and it answers with a synthetic
`QuestionnaireResponse` filled in against that form's own rules - period,
subject, extensions, and answers included:

```console
$ curl -s 'localhost:8091/Questionnaire/BfMAe6Itzgt/$generate?seed=4242' \
    | jq '{identifier, questionnaire, status, subject}'
{
  "identifier": {
    "system": "http://localhost:8080/fhir/id/generate-seed",
    "value": "4242"
  },
  "questionnaire": "http://localhost:8080/fhir/Questionnaire/BfMAe6Itzgt",
  "status": "completed",
  "subject": {
    "reference": "Location/ABM75Q1UfoP"
  }
}
```

**Its output posted back to the same server answers 201.** That is the
whole point, and it is a test in this repository rather than a claim - per
form kind, in both store modes, with strict codes on. A capture UI gets its
"fill with test data" button from it; a stress corpus becomes an API loop.

It is deliberately **not** SDC's `$populate` - that means *fill this form
from real context about a real subject*, and answering it with invented
values would mislead every client that knows what it means. So it is a
custom operation with its own OperationDefinition, published by the
project's IG at `{canonical}/OperationDefinition/d2-generate`.

The `seed` makes it reproducible: same form, same seed, same bytes. Name it
on the query (GET) or in a `Parameters` body (POST) -

```bash
curl -s 'localhost:8091/Questionnaire/BfMAe6Itzgt/$generate?seed=4242'

curl -s -X POST 'localhost:8091/Questionnaire/BfMAe6Itzgt/$generate' \
  -H 'Content-Type: application/fhir+json' \
  -d '{"resourceType":"Parameters","parameter":[{"name":"seed","valueInteger":4242}]}'
```

- and a call naming no seed is answered from one the server drew, which
comes back as the response's business identifier under
`{canonical}/id/generate-seed` (visible above). It survives the post into
the stored receipt, so a corpus generated last week can be regenerated
exactly by reading the seeds off it. Seeds are R4 `integer`s, `0` to
`2147483647`; anything else is a 400 OperationOutcome.

A generated **registration** mints the tracked entity and the enrollment it
creates, exactly as a real client does - shaped UIDs, which is what the
[capture contract](401-capture-contract.md) checks. A generated **stage**
response answers against a pair that already exists: the one a registration
receipt in this project's spool minted, preferring a forwarded registration
over a received one and the newest of either, on the program the two forms
share. That is what makes a generated stage event importable - DHIS2 refuses
an event naming an enrollment it cannot resolve with `E1079` and `E1313`. Only
where the spool holds no registration of that program does a stage response
mint a pair of its own. So a stage response is reproducible from its seed
*and* the spool it was drawn against: running `d2w fhir forward` between two
calls can move which registration is answered against.

A Questionnaire the server does not hold is a 404 OperationOutcome; one it
holds but cannot read as a capture form is a 422 saying so.

## Posting a capture

`POST /QuestionnaireResponse` is the only write. One response per request:

```console
$ curl -s -X POST localhost:8378/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' \
    -d '{"resourceType":"Bundle","type":"collection"}'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this endpoint accepts one QuestionnaireResponse per request; post each response on its own request","expression":["Bundle"]}]}
```

An accepted capture answers `201 Created`, a `Location` header naming where
the receipt is served from, and an OperationOutcome that says what storage
means here:

```console
$ curl -s 'localhost:8378/Questionnaire/BfMAe6Itzgt/$generate?seed=4242' -o response.json
$ curl -s -X POST localhost:8378/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @response.json -D -
HTTP/1.1 201 Created
date: Mon, 10 Aug 2026 19:43:24 GMT
server: uvicorn
location: http://127.0.0.1:8378/QuestionnaireResponse/d78a53c1afe54f09aeb104d0fd1844c2
content-length: 252
content-type: application/fhir+json

{"resourceType":"OperationOutcome","issue":[{"severity":"information","code":"informational","diagnostics":"stored response d78a53c1afe54f09aeb104d0fd1844c2; a stored response is the submission as received - a receipt, not a live view of DHIS2 data"}]}
```

Validation runs in phases, and the phase that finds an error is the last one
to run, so a rejection is readable rather than a wall of consequences:

| Phase | What it checks | Status |
| --- | --- | --- |
| 0 | the body is JSON, is a `QuestionnaireResponse`, and parses as one | 400 |
| 1 | the `D2FormType` kind, then the invariants that kind's profile pins | 422 |
| 2 | the `questionnaire` canonical, the served Questionnaire it names, and its item index | 422 |
| 3 | the organisation unit the response reports for, against the form's published assignment | 422 |
| 4 | the `D2AttributeOptionCombo`, against the vocabulary the form declares | 422 |
| 5 | an aggregate response's `D2Period` - its ISO period, its type, and the range it claims | 422 |
| 6 | every answer against the index: link ids, cardinality, value types, terminology | 422 |

Inside one phase every issue is collected, so one round trip reports every
problem at that level, each locating itself with a FHIRPath `expression`.
Here the posted response answers a question the form does not ask:

```console
$ curl -s -X POST localhost:8378/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @bad.json
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-found","diagnostics":"`notAQuestion` is not a question of `http://localhost:8080/fhir/Questionnaire/BfMAe6Itzgt`","expression":["QuestionnaireResponse.item.where(linkId='notAQuestion')"]}]}
```

Warnings never reject: they ride back on the accepted capture's
OperationOutcome and into the stored receipt. What is a warning by default
and a refusal under `--strict-codes` is the operator's dial, enumerated in
[Serve the guide](201-serve.md#coded-answers-lenient-by-default).

Reading receipts back is plain FHIR - `GET /QuestionnaireResponse/{id}`
answers the submission verbatim in whatever lifecycle state it is in,
because forwarding a receipt must not expire the id its sender was handed.

## `/spool`: the receipt envelopes

The one read that is not FHIR, because what it serves are not elements of a
QuestionnaireResponse: the instant the facade accepted each submission, the
form kind it was validated as, its warnings, its lifecycle state, and
DHIS2's import report behind a rejection. Plain `application/json`:

```console
$ curl -s localhost:8091/spool | jq '{total, counts}'
{
  "total": 987,
  "counts": {
    "received": 0,
    "forwarded": 703,
    "rejected": 284
  }
}
$ curl -s localhost:8091/spool | jq '.responses[0]'
{
  "response_id": "f066e98e279b47689a145710d1f108a7",
  "received_at": "2026-08-10T18:58:04Z",
  "lifecycle": "forwarded",
  "form_kind": "tracker-event",
  "questionnaire": "http://localhost:8080/fhir/Questionnaire/ZzYYXq4fJie",
  "questionnaire_id": "ZzYYXq4fJie",
  "status": "completed",
  "authored": "2026-07-26T08:00:00Z",
  "answer_count": 14,
  "warnings": [],
  "period": null,
  "period_type": null,
  "organisation_unit": "ABM75Q1UfoP",
  "tracked_entity": "F5i3IZaKsND",
  "tracker_enrollment": "uamxA0u4wdf",
  "rejection": null
}
```

It is what the capture UI's Overview and Responses pages read, and the
lifecycle states are the spool directories the forwarder moves receipts
between - see [Forward captures into DHIS2](201-forward.md).

## `/uiconfig`: what the UI is allowed to know

The handful of run-time settings the capture UI has to act on - today, the
basemap tile template and the attribution the server can honestly state for
it. Deliberately not the profile, the host, or the strictness dial: those
describe the process to whoever runs it, and a browser that could read them
would be a browser that leaks them.

```console
$ curl -s localhost:8091/uiconfig | jq .
{
  "basemap": {
    "template": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "attribution": "&copy; <a href=\"https://www.openstreetmap.org/copyright\" target=\"_blank\" rel=\"noreferrer\">OpenStreetMap</a> contributors"
  }
}
```

Both live on single lowercase path segments precisely so they can never
shadow a FHIR resource type, which is PascalCase.

Next: [Identifiers and the D2 extensions](401-identifiers-and-extensions.md)
- the identifier families and extensions every resource this API serves
carries. The
[`dhis2w_fhir_serve` API reference](../../api/fhir-serve.md) covers the
store, the spool, and the capture path as importable Python.
