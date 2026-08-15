# Consume the FHIR API

**Who this is for:** the integration developer talking to a running
`d2w fhir serve` facade - fluent in FHIR, no DHIS2 knowledge assumed.

**Before you start:** a served project ([Serve the guide](201-serve.md)) and
what a valid capture is ([The capture contract](401-capture-contract.md)).

**You will be able to:**

- discover what a facade serves from `/metadata` and nothing else
- read and search the published resources, including the identifier search
  that groups a program's forms
- find a person by identifier and page through the people an instance holds
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

Each operation is declared on the resource entry whose URL answers it -
`$generate` on `Questionnaire`, served at `/Questionnaire/{id}/$generate`, and
`$translate` on `ConceptMap`, served at `/ConceptMap/$translate` - and only when
the store holds that type. So a client that follows the statement reaches an
endpoint that answers, and `/metadata` never advertises what the store cannot do.

## Reads and searches

Seven definitional types are served - `Questionnaire`, `CodeSystem`,
`ValueSet`, `Location`, `Organization`, `List`, and `ConceptMap` - plus
`QuestionnaireResponse`, the one type the facade also receives, and, under
`--live` only, `Patient`. Anything else is refused with an OperationOutcome
saying so, rather than a bare 404 that would read as "no such resource":

```console
$ curl -s localhost:8091/Observation/abc
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this server does not serve the resource type `Observation`"}]}
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

## The register: what the instance holds, one resource per tracked entity type

**Which resource types this section is about is the guide's to say.** A running
server reads `D2TET_CM` - the ConceptMap `d2w fhir generate` publishes over the
tracked entity types the project's forms register - and serves one read surface
per FHIR resource that map names. A project tracking people alone serves
`Patient`; one that also registers specimen batches serves `Specimen` beside it,
over exactly the types the map put there. The published artifact is the contract:
`[generate.tracked_entity_types]` is what produced it, and the server never reads
that table.

Every surface answers identically - the same `identifier` search, the same paged
listing, the same projection. `Patient` is used throughout below because it is
the resource every deployment has; substitute any other the map names and every
request and answer shape here holds unchanged.

```console
$ curl -s localhost:8391/metadata | jq -r '.rest[0].resource[] | select(.searchParam[]?.name == "identifier") | .type'
Patient
Specimen
```

### `Patient`: who a person is in the instance

Every search above answers from what the project published. This one answers
from the DHIS2 instance the server runs against, at request time, which is why
it exists only under `--live` - and why `/metadata` declares `Patient` only
there. A compiled run says so instead of guessing:

```console
$ curl -s localhost:8091/Patient?identifier=SCEN-A-0001
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`Patient` is answered from the DHIS2 instance this facade runs against, and this process serves a compiled implementation guide; start it with `--live` to search people."}]}
```

**`identifier` is the whole search surface**, in both of FHIR's token forms.
A system-qualified token names which key the value is:

```console
$ curl -s -G localhost:8391/Patient \
    --data-urlencode 'identifier=http://dhis2.org/fhir/tracked-entity-attribute/ScTeaAUniq1|SCEN-A-0001' \
    | jq '.total, .entry[].resource.id'
1
"PLoWmEuLJl2"
```

Two systems answer. `{base}/id/tracked-entity` is the DHIS2 tracked entity UID
itself, read directly rather than filtered for - a UID is not an attribute.
`{base}/tracked-entity-attribute/{uid}` is one tracked entity attribute, and
only the attributes DHIS2 declares **unique** get one: uniqueness is what makes
a value name a person rather than describe one, and the guide already publishes
the flag as a `unique` concept property on
[`D2TEA_CS`](401-identifiers-and-extensions.md).

A token naming no system tries every key at once and folds the results,
deduplicated by tracked entity UID, so a client that has scanned a card without
knowing which register issued it can still ask:

```console
$ curl -s 'localhost:8391/Patient?identifier=SCEN-A-0001' | jq .total
1
```

An identifier nobody holds, and a system this guide publishes nothing for, are
both an empty searchset - never a 404, which on a search path would say the
endpoint does not exist:

```console
$ curl -s 'localhost:8391/Patient?identifier=NO-SUCH-ID' | jq '.type, .total'
"searchset"
0
```

**The Patient is identity and nothing else.** No `name`, no `gender`, no
`birthDate` - DHIS2 has no attribute that means any of those, and which of an
instance's attributes do is a decision each instance makes for itself. A wrong
`gender` on a patient record is a worse answer than none, so the server states
only what DHIS2 states:

```json
{
  "resourceType": "Patient",
  "id": "PLoWmEuLJl2",
  "meta": {"tag": [{"system": "http://dhis2.org/fhir/id/tracked-entity-type", "code": "nEenWmSyUEp"}]},
  "identifier": [
    {"system": "http://dhis2.org/fhir/id/tracked-entity", "value": "PLoWmEuLJl2"},
    {"system": "http://dhis2.org/fhir/tracked-entity-attribute/ScTeaAUniq1", "value": "SCEN-A-0001"}
  ],
  "extension": [
    {
      "url": "http://localhost:8090/fhir/StructureDefinition/d2-tracked-entity-attribute-value",
      "extension": [
        {"url": "attributeId", "valueString": "ScTeaComPh1"},
        {"url": "value", "valueString": "+23276111001"}
      ]
    }
  ]
}
```

The tracked entity type rides as a `meta.tag`, because it classifies the
resource rather than naming it. Every attribute value that is not an identifier
rides the `D2TrackedEntityAttributeValue` extension - the attribute UID, its
DHIS2 code where the instance set one, and the value as the string DHIS2 sent.
Values collected at the program are carried alongside the ones collected at the
tracked entity type, so a person found by a program attribute's unique value
comes back holding it.

`GET /Patient/{trackedEntityUid}` reads one person, which is what each Bundle
entry's `fullUrl` points at. A UID the instance does not hold is a 404 there -
a read, unlike a search, names a specific resource.

### The listing: what the instance holds, a page at a time

`GET /Patient` carrying no parameters at all is the listing rather than a
search that matched nothing: what a facade has to offer for "no criteria" is
the register itself, paged. It is what a client browses when nobody has an
identifier to type, and it is live-only for the same reason the search is -
the answer comes from the instance, per request.

```console
$ curl -s localhost:8391/Patient | jq '.type, .total, (.entry | length)'
"searchset"
137
20
```

Entries are the same projection the search answers with, and each `fullUrl`
points at `GET /Patient/{trackedEntityUid}`.

**Two parameters page it: `_count` and `page`.** `_count` is R4's page size.
A call naming none is answered with `[serve.tracked_entities] page_size` entries; a
call naming more than `[serve.tracked_entities] page_size_limit` is answered with
`page_size_limit` of them and a `next` link, rather than refused - a client
that asked for too much should be handed a smaller page, not an error
([Configure serving](301-serving.md#tracked_entities)).

```console
$ curl -s 'localhost:8391/Patient?_count=5' | jq '.entry | length'
5
```

**`page` is an opaque token. Follow the links; never construct one.** The
listing spans every tracked entity type the published map takes onto this
resource, and
DHIS2 pages each type's records on its own, so one page of this listing can sit
part-way through several of the instance's own cursors at once. The token is
how the server carries that position across a request; it is bytes to a client,
with no offset to do arithmetic on and no guarantee about its shape from one
release to the next. What a client does with it is copy the `next` link:

```console
$ curl -s localhost:8391/Patient | jq -r '.link[] | "\(.relation) \(.url)"'
self http://localhost:8391/Patient?_count=20
next http://localhost:8391/Patient?_count=20&page=dDBwMg
```

The first page carries no `previous` and the last carries no `next`, so the end
of the listing is a missing link rather than an empty page you have to ask for
to discover. As everywhere else on this facade, `self` echoes only the
parameters that were applied.

**`total` is the whole searchset, counted.** DHIS2 counts one tracked entity
type at a time, so a listing over several types asks each type for its count -
one count-only request per type, spent on the first page of a walk and carried
through the rest on the page token - and states the sum. Where the instance
stated no count for one of those types the sum is unknowable, and R4 makes
`total` optional precisely so a server can say so: the element is absent rather
than guessed at or filled with a fraction of the truth. An invented total is a
worse answer than no total.

**Naming `identifier` is always the search**, whatever the listing is set to:
the two share an endpoint, and the parameter is what tells them apart.

**What the configuration answers with when it is off.** `[serve.tracked_entities]`
gates the surface, and each of its two switches refuses with the fact and the
line to change ([Configure serving](301-serving.md#tracked_entities)). With
`listing = false`, the search is untouched and the no-parameter call is not
served:

```console
$ curl -s localhost:8391/Patient
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this facade serves no `Patient` listing; name an `identifier` to search for a person, or set `[serve.tracked_entities] listing = true` in fhir.toml and serve again"}]}
$ curl -s 'localhost:8391/Patient?identifier=SCEN-A-0001' | jq .total
1
```

With `enabled = false`, nothing about people is served - the search, the
listing, and the enrollment listing below all answer the same way, and
`/metadata` declares no `Patient` at all, exactly as it does under a compiled
guide:

```console
$ curl -s 'localhost:8391/Patient?identifier=SCEN-A-0001'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`Patient` is not served here: this project sets `[serve.tracked_entities] enabled` to false; set it true in fhir.toml and serve again to search or list people"}]}
```

Which records the two surfaces cover is configuration too:
`[serve.tracked_entities] tracked_entity_types` narrows both to named tracked entity
types - the setting a laboratory instance reaches for, so that specimens are
not listed beside patients - and `[serve.tracked_entities] search_attributes` names the
attributes an identifier keys on, in place of the ones DHIS2 declares unique.
Both are explained for the person editing the file in
[Configure serving](301-serving.md#tracked_entities).

## `/tracked-entities/{uid}/enrollments`: which programs a person is in

A capture client that has found a person still has to answer a stage form
against one of that person's enrollments. This is the list it picks from, and
it is typed JSON on a lowercase path rather than a FHIR resource: whether a
DHIS2 enrollment is an `EpisodeOfCare` or a `CarePlan` is
[still an open decision](../../project/fhir-roadmap.md), and settling it inside
a picker's data feed would settle it by accident.

```console
$ curl -s localhost:8391/tracked-entities/PLoWmEuLJl2/enrollments | jq .
{
  "tracked_entity_uid": "PLoWmEuLJl2",
  "enrollments": [
    {
      "enrollment_uid": "zdXqGWfF8j0",
      "program_uid": "ScProgAaa01",
      "program_name": "Scenario A",
      "status": "ACTIVE",
      "active": true,
      "enrolled_at": "2026-07-25T11:00:00",
      "organisation_unit_uid": "Rp268JB6Ne4",
      "organisation_unit_name": null
    }
  ]
}
```

`program_name` and `organisation_unit_name` are joins onto what this project
published, and stay `null` when it published nothing - a program outside the
selection, or an organisation unit below the registry's `max_level`, gets no
name rather than a guessed one.

**A completed enrollment is listed, and said to be completed.** DHIS2 accepts an
event into one with no error and no warning, so a client that hid it would let a
user capture into a closed episode without a word. The server states the status
and leaves `active` false; refusing the capture is the instance's call to make,
not this facade's.

Like `/Patient`, this listing is live-only, and answers the same
`not-supported` OperationOutcome under a compiled guide - and under
`[serve.tracked_entities] enabled = false`, which takes the whole people surface away
in one line.

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

The organisation unit a response reports for is drawn from the seed like
every other value. The set it is drawn over is the one the form admits: the
organisation units its published assignment names, intersected with the
served registry, and the whole registry for a form publishing no assignment.
Same seed, same organisation unit; a different seed ranges over the rest of
the set, so a corpus generated from a handful of seeds is spread across the
places the form is captured at rather than filed at one of them. Staying
inside the assignment is what keeps that corpus importable - DHIS2 refuses a
capture at an organisation unit the form is not assigned to with `E1029`. A
project that published no registry at all gets a shaped UID, which the
[capture contract](401-capture-contract.md) admits because it checks the
reference's shape rather than its target.

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
basemap layers this run offers with the attribution the server can honestly
state for each, the address of the DHIS2 instance it resolved a profile for,
which is what an identity on a page links back to, and whether this run answers
about the instance's tracked entities at all. Deliberately not the profile's
name, its credentials, the
host this process listens on, or the strictness dial: those describe the process
to whoever runs it, and a browser that could read them would be a browser that
leaks them.

```console
$ curl -s localhost:8091/uiconfig | jq .
{
  "basemaps": [
    {
      "name": "OpenStreetMap",
      "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      "attribution": "&copy; <a href=\"https://www.openstreetmap.org/copyright\" target=\"_blank\" rel=\"noreferrer\">OpenStreetMap</a> contributors"
    }
  ],
  "dhis2_base_url": "https://play.dhis2.org/40",
  "tracked_entities": {
    "enabled": true,
    "listing": true,
    "registers": [
      { "resource": "Patient", "types": [{ "uid": "nEenWmSyUEp", "name": "Person" }] },
      { "resource": "Specimen", "types": [{ "uid": "Kd6Nk9wnAJa", "name": "Specimen batch" }] }
    ]
  }
}
```

`basemaps` is `[]` when this run offers no tiles, and `dhis2_base_url` is
`null` when it resolved no profile. Both are states the UI renders rather than
absences it guesses at: the map's layer control holds `None` alone, and the
screens carry no links out.

`tracked_entities` is what the screens act on. `enabled` and `listing` are the
two switches of `[serve.tracked_entities]` that change what is drawn - `enabled`
false and the register has no entry in the navigation at all, `listing` false and
its page searches without offering to browse. The UI reads them here rather than
discovering them from a refusal, so a control that cannot be answered is never
drawn in the first place. What is reported is what this run does, not what the
file says: a compiled run reports `enabled` false whatever `fhir.toml` states,
because the register answers from an instance and a compiled run is connected to
none. The other four settings of that table shape the answers rather than the
screens, so the browser is never told them.

`registers` is the third fact, and it is the published `D2TET_CM` read for a
screen: one entry per FHIR resource this run serves from the instance, each
carrying the tracked entity types riding it under the names the instance holds
for them. It is what lets the navigation entry and the page heading read the
instance's own name for the one type a deployment tracks - **Person**, **Person
(Play)** - and **Tracked entities** on one tracking something else besides, and
what lets a section on that page be titled *Specimen batch* rather than
`Specimen` - the resource type is this project's projection, and the type's own
name is what a reader working in DHIS2 recognises. It is `[]` whenever
`enabled` is false, because a page the navigation does not offer has no sections
to name.

Both live on single lowercase path segments precisely so they can never
shadow a FHIR resource type, which is PascalCase.

Next: [Identifiers and the D2 extensions](401-identifiers-and-extensions.md)
- the identifier families and extensions every resource this API serves
carries. The
[`dhis2w_fhir_serve` API reference](../../api/fhir-serve.md) covers the
store, the spool, and the capture path as importable Python.
