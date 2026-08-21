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

**The runnable version of this page** is
[`examples/fhir/client/consume_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/consume_facade.py) -
plain httpx against a served project, walking discovery, search, `$generate`, a
capture, the receipt, and `/spool` end to end. Point it at your own facade with
`uv run python examples/fhir/client/consume_facade.py http://localhost:8123`.
The rest of that directory is the library path: `generate_ig.py` builds a guide
from Python and `forward_spool.py` drains one.

Every response body on this page is real output from a running facade. The
compiled-store examples run against a project served on port 8389; the
register and enrollment examples, which exist only under `--live`, against a
`d2w fhir serve --live` on port 8391. The Python surface behind all of it is
documented in [the `dhis2w_fhir_serve` API reference](api-dhis2w-fhir-serve.md).

## Discovery: `/metadata`

The facade's only contract - it publishes no OpenAPI document. A `kind
#instance` CapabilityStatement that instantiates the IG's own
`D2CaptureServer` requirements statement, narrowed to what this store
actually holds:

```console
$ curl -s localhost:8389/metadata | jq '.software, .implementation.description'
{
  "name": "d2w fhir serve",
  "version": "1.7.0.dev0"
}
"DHIS2 FHIR capture facade (compiled store); stored QuestionnaireResponses are submissions as received - receipts, not a live view of DHIS2 data"
```

Each operation is declared on the resource entry whose URL answers it -
`$generate` on `Questionnaire`, served at `/Questionnaire/{id}/$generate`, and
`$translate` on `ConceptMap`, served at `/ConceptMap/$translate` - and only when
the store holds that type. So a client that follows the statement reaches an
endpoint that answers, and `/metadata` never advertises what the store cannot do.

## `Accept` and the service base

**Every FHIR interaction answers `application/fhir+json`, and nothing else.**
`/metadata` states that too - `format` names `json` alone - so a request that
rules JSON out is told, rather than handed a body it has declared it cannot
read:

```console
$ curl -s -H 'Accept: application/fhir+xml' localhost:8389/Questionnaire/BfMAe6Itzgt
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`application/fhir+xml` accepts no JSON, and this server answers `application/fhir+json` only; ask for that, for `application/json`, or for `*/*`"}]}
```

The test is one question, deliberately: does any media range in the header admit
JSON? `*/*`, `application/*`, `application/json`, `application/fhir+json`, and
every other `application/…+json` do, so an absent header, a browser's header,
and a `curl` with no flags are all answered exactly as before. Only a client
that named formats and named no JSON among them meets the 406. The two non-FHIR
endpoints below, `/spool` and `/uiconfig`, negotiate nothing: they answer plain
`application/json` about this facade rather than resources out of it.

**`POST /` is where FHIR posts a batch or a transaction, and this server runs
neither.** It says so, rather than answering the 404 an unrouted path would
give - the address was right and the interaction was not:

```console
$ curl -s -X POST localhost:8389/ -H 'Content-Type: application/fhir+json' \
    -d '{"resourceType":"Bundle","type":"batch"}'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`POST /` is not served here: this server runs no batch and no transaction. Post one QuestionnaireResponse per request to `/QuestionnaireResponse`."}]}
```

`PUT`, `PATCH`, and `DELETE` on the base answer the same way, each naming the
method it refuses. `GET /` is the capture UI's under `--ui`
([Capture in the browser](201-capture-ui.md)) and served by nothing otherwise.

## Reads and searches

Seven definitional types are served - `Questionnaire`, `CodeSystem`,
`ValueSet`, `Location`, `Organization`, `List`, and `ConceptMap` - plus
`QuestionnaireResponse`, the one type the facade also receives, and, under
`--live` only, whichever resources
[the register](#the-register-what-the-instance-holds-one-resource-per-tracked-entity-type)
publishes. Anything else is refused with an OperationOutcome saying so, rather
than a bare 404 that would read as "no such resource":

```console
$ curl -s localhost:8389/Observation/abc
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this server does not serve the resource type `Observation`"}]}
```

A read is byte-faithful to what the project published; a missing id names
itself:

```console
$ curl -s localhost:8389/Questionnaire/BfMAe6Itzgt | jq .title
"Child Health"
$ curl -s localhost:8389/Questionnaire/NoSuchForm1
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-found","diagnostics":"no Questionnaire with id `NoSuchForm1` is served here"}]}
```

Searches answer a searchset Bundle. The definitional types take `_id`,
`url`, and `identifier`; `QuestionnaireResponse` takes `_id` and
`questionnaire`. `/metadata` states the same table, per resource, and is the
authority on it.

**Within one parameter, values are alternatives; across parameters they
combine.** `_id=a,b` and `_id=a&_id=b` are the same query, and both narrow when
a second parameter joins them. An empty value is refused - ``` `_id` was given an
empty value ``` - because a client that sent one meant something.

```console
$ curl -s 'localhost:8389/Questionnaire?_id=BfMAe6Itzgt,TuL8IOPzpHh' | jq .total
2
```

**On the store's own types an unrecognised parameter is ignored rather than
refused, and the Bundle's `self` link echoes back only the parameters the server
actually applied**, so a client can see what it got rather than assume:

```console
$ curl -s 'localhost:8389/Questionnaire?_id=BfMAe6Itzgt,TuL8IOPzpHh&bogus=1' \
    | jq -r '.link[].url'
http://localhost:8389/Questionnaire?_id=BfMAe6Itzgt%2CTuL8IOPzpHh
```

The register is the exception, and refuses instead
([the register search](#the-register-search-identifier)): what it would
otherwise answer an unapplied filter with is the whole register, which reads as
a match set rather than as a query nobody ran.

`total` is always stated on these searches, `0` included, and `entry` is absent
rather than empty when nothing matched.

**`_count` caps a definitional search; it does not page one.** The store is what
one project published, so a search answers it whole unless the client asks for
less: `total` states every match, `entry` carries the first `_count` of them,
and there is no `next` link to follow - there is no walk to continue, only a
result the client chose to see less of. The `self` link names the cap beside the
parameters that selected the matches:

```console
$ curl -s 'localhost:8389/Questionnaire?_id=BfMAe6Itzgt,TuL8IOPzpHh&_count=1' \
    | jq '.total, (.entry | length), .link[0].url'
2
1
"http://localhost:8389/Questionnaire?_id=BfMAe6Itzgt%2CTuL8IOPzpHh&_count=1"
```

`_count=0` is R4's request for the total alone: the Bundle states how many
matched and carries no `entry` at all. A `_count` that is not a whole number, or
is negative, is a 400 saying which. Every searchset this facade answers reads
`_count` on those terms - the definitional types, the register's identifier
search, and the register listing alike.

`GET /QuestionnaireResponse` is the one search here that also **pages**, because
a spool grows with every capture while the published artifacts do not. It takes
`_count` (50 by default, 500 at most) and the same opaque `page` token the
register listing uses, `total` is the whole searchset on every page of a walk,
and a client's whole job is to follow the `next` link
([the listing](#the-listing-what-the-instance-holds-a-page-at-a-time) describes
that token in full).

An `identifier` token takes either form. `system|value` matches only under that
system; a bare `value` matches under any. A token naming a system but no value
is refused - ``` `identifier` token `sys|` names a system but no value ```.

The identifier search is how a program's forms are grouped: every artifact
generated from one DHIS2 object carries that object's identifier, so a
system-qualified token selects a tracker program's registration form and
every stage form in one query -

```console
$ curl -s 'localhost:8389/Questionnaire?identifier=http://dhis2.org/fhir/id/program|PrAncCare01' \
    | jq -r '.entry[].resource.title'
Antenatal care
ANC follow-up - ANC visit
```

The registration form comes back beside every stage of its program, because a
registration form's own identity *is* the program's
([which identifiers a Questionnaire carries](401-identifiers-and-extensions.md#which-identifiers-a-questionnaire-carries)).

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

Three rules decide that set, and a consumer can predict it from the published
artifacts alone.

- **The forms decide which types are served.** A tracked entity type is in the
  register because some published Questionnaire registers into it, carrying its
  UID under `{base}/id/tracked-entity-type`. A type `D2TET_CM` names that no form
  registers into is not served.
- **The map decides which resource each becomes.** A type the map takes onto
  `Specimen` is served as `Specimen`. A type the map does not name - or names
  with no target - is served as `Patient`, which is also what a project with no
  `D2TET_CM` at all gets for every type it registers.
- **Each resource searches only its own types.** `GET /Specimen` never returns a
  person, because the surface asks DHIS2 only for the tracked entity types the
  map put on `Specimen`.

`[serve.tracked_entities] tracked_entity_types` narrows the served set further,
and it is taken verbatim rather than intersected with the published one - a UID
it names that the guide never published is served as a `Patient`
([Configure serving](301-serving.md#tracked_entities)).

### The register search: `identifier`

Every search above answers from what the project published. This one answers
from the DHIS2 instance the server runs against, at request time, which is why
it exists only under `--live` - and why `/metadata` declares the register's
resources only there. A compiled run says so instead of guessing:

```console
$ curl -s localhost:8389/Patient?identifier=SCEN-A-0001
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`Patient` is answered from the DHIS2 instance this facade runs against, and this process serves a compiled implementation guide; start it with `--live` to search the register."}]}
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

Two families of system answer.

- **`{base}/id/tracked-entity`** is the DHIS2 tracked entity UID itself, read
  directly rather than filtered for - a UID is not an attribute. A value that is
  not UID-shaped matches nothing without a request leaving the process.
- **`{base}/tracked-entity-attribute/{uid}`** is one tracked entity attribute.

**Which attributes get one is `unique` *or* `searchable`, not `unique` alone.**
A unique attribute's value names a person; a searchable one is a value DHIS2
lets a clerk look somebody up by even though nothing stops two people sharing
it - a date of birth is the ordinary case. A facade keying on uniqueness alone
would refuse the lookup the instance permits. Both flags are published as
concept properties on
[`D2TEA_CS`](401-identifiers-and-extensions.md#the-concept-property-namespace),
so a client can read the whole key set out of the guide before it searches.

`[serve.tracked_entities] search_attributes` replaces that default outright when
it is set: the attributes it names become the keys whether or not DHIS2 declares
them either thing ([Configure serving](301-serving.md#tracked_entities)).

A token naming no system tries every key at once and folds the results,
deduplicated by tracked entity UID, so a client that has scanned a card without
knowing which register issued it can still ask:

```console
$ curl -s 'localhost:8391/Patient?identifier=SCEN-A-0001' | jq .total
1
```

**Several identifier tokens are alternatives, not conditions.** This is the one
place the facade's search semantics differ from the definitional types above:
there, two parameters narrow each other; here, every token and every
comma-separated value is another key to try, and their matches are unioned. A
client holding two cards for one person asks once.

**A parameter other than `identifier` is refused, not ignored.** This is the
second place the register parts company with the searches above, and for the
same reason the union semantics exist: an unapplied filter here would be
answered with the register itself, and a client that asked for the people called
Smith would read every row of that answer as a Smith. So the server says what it
answers on:

```console
$ curl -s 'localhost:8391/Patient?family=Smith'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"`family` is not a search parameter this server answers `Patient` on: `identifier` is the one it supports"}]}
```

`_count` is honoured beside `identifier` and caps the matches handed back, on
the same terms as every other searchset here - `total` states how many there
were, and `_count=0` states that number alone. `page` belongs to the listing
below and is refused on an identifier search, which is answered whole rather
than paged. A request naming no parameter at all is the listing, unchanged.

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
A call naming none is answered with `[serve.tracked_entities] page_size` entries,
**20** by default; a call naming more than `[serve.tracked_entities]
page_size_limit`, **100** by default, is answered with `page_size_limit` of them
and a `next` link, rather than refused - a client that asked for too much should
be handed a smaller page, not an error
([Configure serving](301-serving.md#tracked_entities)). A `_count` that is not a
whole number, or is negative, is a 400 saying which.

```console
$ curl -s 'localhost:8391/Patient?_count=5' | jq '.entry | length'
5
```

`_count=0` asks how large the register is and is answered with that and nobody -
the total, no `entry`, and no page to follow. It costs one count of each tracked
entity type in scope and never builds a page at all:

```console
$ curl -s 'localhost:8391/Patient?_count=0' | jq '.total, (.entry | length), (.link | length)'
137
0
1
```

**`page` is an opaque token. Follow the links; never construct one.** The
listing spans every tracked entity type the published map takes onto this
resource, and
DHIS2 pages each type's records on its own, so one page of this listing can sit
part-way through several of the instance's own cursors at once. The token is
how the server carries that position across a request; it is bytes to a client,
with no offset to do arithmetic on and no guarantee about its shape from one
release to the next. A token the server cannot read says exactly that:

```console
$ curl -s 'localhost:8391/Patient?page=12'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"`page` is not a page of this search: its value comes from the `next` or `previous` link of a result, and is not a number a client composes"}]}
```

It is stateless, so a link handed out an hour ago still resolves. What a client
does with it is copy the `next` link:

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
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this facade serves no `Patient` listing; name an `identifier` to search for one, or set `[serve.tracked_entities] listing = true` in fhir.toml and serve again"}]}
$ curl -s 'localhost:8391/Patient?identifier=SCEN-A-0001' | jq .total
1
```

With `enabled = false`, nothing about the register is served - the search, the
listing, and the enrollment listing below all answer the same way, and
`/metadata` declares no register resource at all, exactly as it does under a
compiled guide:

```console
$ curl -s 'localhost:8391/Patient?identifier=SCEN-A-0001'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`Patient` is not served here: this project sets `[serve.tracked_entities] enabled` to false; set it true in fhir.toml and serve again to search or list the register"}]}
```

`enabled = false` is checked before the store's own mode, so a **compiled** run
with the switch off answers this body rather than the `--live` one above. A live
run over a project that publishes no registration form at all answers a third:
`this project publishes no registration form, so no tracked entity type is
served here and `Patient` cannot be searched; generate a tracker program's
registration form first.`

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
[still an open decision](design/roadmap.md), and settling it inside
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

Like the register, this listing is live-only. Under a compiled guide it answers
the same `not-supported` OperationOutcome, with `enrollments` in the slot the
resource type occupies there:

```console
$ curl -s localhost:8389/tracked-entities/PLoWmEuLJl2/enrollments
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`enrollments` is answered from the DHIS2 instance this facade runs against, and this process serves a compiled implementation guide; start it with `--live` to search the register."}]}
```

`[serve.tracked_entities] enabled = false` takes this endpoint away in the same
line it takes the register away. `listing = false` does **not** touch it: that
switch is about browsing a register with no criteria, and this is a read about
one person you already have.

A UID the instance does not hold is a 404 here, as on any read.

## `$translate`: generated codes back to DHIS2 identifiers

R4's type-level `ConceptMap/$translate`, answered over every ConceptMap the
project publishes. It is **type-level only** - there is no
`/ConceptMap/{id}/$translate`, because the question a client has is "what is
this code" and not "what does this particular map say about it".

`system` and `code` are required, and `targetsystem` optionally narrows to one
target namespace (R4's lowercase spelling and the `targetSystem` real clients
also send are both read, lowercase first):

```console
$ curl -s 'localhost:8389/ConceptMap/$translate?system=http://localhost:8080/fhir/CodeSystem/d2-os-OsSymptom01-cs&code=OpFever0001&targetsystem=http://dhis2.org/fhir/id/option-code' \
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
          "code": "FEVER",
          "display": "Fever"
        }
      },
      {
        "name": "source",
        "valueUri": "http://localhost:8080/fhir/ConceptMap/d2-os-OsSymptom01-cm"
      }
    ]
  }
]
```

Without `targetsystem` the answer carries one `match` per namespace the maps
target - for an option that is both the DHIS2 option UID and the option
code. A code the maps say nothing about **is not an error**: it is a `200`
carrying `result: false` and a message, because "no mapping" is a valid answer
to a valid question:

```console
$ curl -s 'localhost:8389/ConceptMap/$translate?system=http://localhost:8080/fhir/CodeSystem/d2-os-OsSymptom01-cs&code=NotACode' \
    | jq '.parameter'
[
  {
    "name": "result",
    "valueBoolean": false
  },
  {
    "name": "message",
    "valueString": "no ConceptMap served here maps `NotACode` from `http://localhost:8080/fhir/CodeSystem/d2-os-OsSymptom01-cs`; the code system, the code, or the target system is not one this server holds a mapping for"
  }
]
```

Naming a `targetsystem` that maps nothing folds into the same message, with
`` into `<targetsystem>` `` spliced in after the source system. A **missing**
parameter, by contrast, is a 400 - the request itself was not answerable:

```console
$ curl -s 'localhost:8389/ConceptMap/$translate?system=x'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"`$translate` needs a `code` parameter"}]}
```

`system` is checked first, so a call naming neither reports `system`.

The maps are served as documents too: `GET /ConceptMap/<id>` answers the
published map verbatim, and `GET /ConceptMap` searches them like any other
type. A read hands over the whole mapping table for a person to look at; the
operation answers the one question a client has without walking groups and
elements.

**There is no `$lookup` and no `$expand`.** A concept's properties and a value
set's members are elements of documents this facade already serves whole, so a
client reads `GET /CodeSystem/{id}` and `GET /ValueSet/{id}` and walks them.
`/metadata` is the authority on which operations exist: `$generate` on
`Questionnaire` and `$translate` on `ConceptMap`, and nothing else.

## `$generate`: a valid submission on demand

Hand it a served form and it answers with a synthetic
`QuestionnaireResponse` filled in against that form's own rules - period,
subject, extensions, and answers included:

```console
$ curl -s 'localhost:8389/Questionnaire/BfMAe6Itzgt/$generate?seed=4242' \
    | jq '{identifier, questionnaire, status, subject}'
{
  "identifier": {
    "system": "http://localhost:8080/fhir/id/generate-seed",
    "value": "4242"
  },
  "questionnaire": "http://localhost:8080/fhir/Questionnaire/BfMAe6Itzgt",
  "status": "completed",
  "subject": {
    "reference": "Location/YuQRtpLP10I"
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
curl -s 'localhost:8389/Questionnaire/BfMAe6Itzgt/$generate?seed=4242'

curl -s -X POST 'localhost:8389/Questionnaire/BfMAe6Itzgt/$generate' \
  -H 'Content-Type: application/fhir+json' \
  -d '{"resourceType":"Parameters","parameter":[{"name":"seed","valueInteger":4242}]}'
```

A body seed wins over a query seed on a POST, and a bare POST with no body at
all is legal - it means "any seed". A call naming no seed is answered from one
the server drew, which comes back as the response's business identifier under
`{canonical}/id/generate-seed` (visible above). It survives the post into the
stored receipt, so a corpus generated last week can be regenerated exactly by
reading the seeds off it.

Seeds are R4 `integer`s, `0` to `2147483647`. Anything else is a 400 naming
which rule it broke:

```console
$ curl -s 'localhost:8389/Questionnaire/BfMAe6Itzgt/$generate?seed=abc'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"`seed` takes a whole number, not `abc`"}]}
```

A whole number outside the range answers ``` `seed` takes a value between 0 and
2147483647 ```, and a `Parameters` body carrying a `seed` with neither a
`valueInteger` nor a `valueString` answers ``` the `seed` parameter carries no
`valueInteger` ```.

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

A Questionnaire the server does not hold is a 404 OperationOutcome - the same
``no Questionnaire with id `x` is served here`` a read answers with. One it holds
but cannot read as a capture form is a 422: ``` `Questionnaire/{id}` cannot be
generated against: ``` followed by what stopped it.

## Posting a capture

`POST /QuestionnaireResponse` is the only write, and a server may decline to
offer it. A project serving `[serve] capture = false`
([`capture`](301-serving.md#capture)) refuses every submission with **405** and
names the key that decided it, while every read on the same resource type keeps
answering:

```console
$ curl -s -X POST localhost:8389/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @response.json
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this server receives no QuestionnaireResponse: this project sets `[serve] capture` to false, so it serves its guide and stores nothing new; set it true in fhir.toml and serve again to capture"}]}
```

Such a server says so before it is asked: its `/metadata` declares `read` and
`search-type` on QuestionnaireResponse and no `create`, so a client that reads
the statement first never posts. `$generate` is unaffected - it reads a
published form and answers with a draft - and so are the receipts already
stored, which are read, searched, and counted exactly as below. Everything that
follows is a server that receives.

The body has to be JSON - a
`Content-Type` that is not `application/fhir+json`, `application/json`, or
something ending `+json` is a **415** before the body is read at all:

```console
$ curl -s -X POST localhost:8389/QuestionnaireResponse \
    -H 'Content-Type: text/plain' --data-binary @response.json
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`text/plain` is not a media type this server reads; send the body as `application/fhir+json`"}]}
```

One response per request:

```console
$ curl -s -X POST localhost:8389/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' \
    -d '{"resourceType":"Bundle","type":"collection"}'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this endpoint accepts one QuestionnaireResponse per request; post each response on its own request","expression":["Bundle"]}]}
```

An accepted capture answers `201 Created`, a `Location` header naming where
the receipt is served from, and an OperationOutcome that says what storage
means here:

```console
$ curl -s 'localhost:8389/Questionnaire/BfMAe6Itzgt/$generate?seed=4242' -o response.json
$ curl -s -X POST localhost:8389/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @response.json -D -
HTTP/1.1 201 Created
date: Mon, 10 Aug 2026 19:43:24 GMT
server: uvicorn
location: http://localhost:8389/QuestionnaireResponse/d78a53c1afe54f09aeb104d0fd1844c2
content-length: 252
content-type: application/fhir+json

{"resourceType":"OperationOutcome","issue":[{"severity":"information","code":"informational","diagnostics":"stored response d78a53c1afe54f09aeb104d0fd1844c2; a stored response is the submission as received - a receipt, not a live view of DHIS2 data"}]}
```

Validation runs in phases, and the phase that finds an error is the last one
to run, so a rejection is readable rather than a wall of consequences:

| Phase | What it checks | Status |
| --- | --- | --- |
| 0 | the body is JSON, is a `QuestionnaireResponse`, and parses as one - **every model is closed, so an unknown key anywhere is refused here** | 400 |
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
$ curl -s -X POST localhost:8389/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @bad.json
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-found","diagnostics":"`notAQuestion` is not a question of `http://localhost:8080/fhir/Questionnaire/BfMAe6Itzgt`","expression":["QuestionnaireResponse.item.where(linkId='notAQuestion')"]}]}
```

Warnings never reject: they ride back on the accepted capture's
OperationOutcome, after the informational issue naming the stored id, and into
the stored receipt. Which findings are warnings, which are always refusals, and
which five the `--strict-codes` dial moves between the two is enumerated in
[the capture contract](401-capture-contract.md#what-the-server-refuses-and-what-it-only-warns-about).

A rejection body carries everything the failing phase found - including any
warning-severity issues that phase collected alongside the error, so a client
fixing the refusal sees the advice that came with it in the same round trip.

Reading receipts back is plain FHIR - `GET /QuestionnaireResponse/{id}`
answers the submission verbatim in whatever lifecycle state it is in,
because forwarding a receipt must not expire the id its sender was handed.

## `/spool`: the receipt envelopes

The one read that is not FHIR, because what it serves are not elements of a
QuestionnaireResponse: the instant the facade accepted each submission, the
form kind it was validated as, its warnings, its lifecycle state, and
DHIS2's import report behind a rejection. Plain `application/json`:

```console
$ curl -s localhost:8389/spool | jq '{total, counts}'
{
  "total": 987,
  "counts": {
    "received": 0,
    "forwarded": 703,
    "rejected": 284,
    "withdrawn": 0
  }
}
$ curl -s localhost:8389/spool | jq '.responses[0]'
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
  "rejection": null,
  "imported": {
    "status": "OK",
    "message": null,
    "created": 14,
    "updated": 0,
    "ignored": 0,
    "deleted": 0
  }
}
```

**`rejection` and `imported` are the two halves of what DHIS2 answered**, and at
most one is ever present: `rejection` only on a `rejected` receipt, `imported`
only on a `forwarded` one, both `null` on a `received` one that has not been
forwarded yet. `rejection` additionally carries an `issues` array, one entry per
DHIS2 import error with its `error_code`, `subject`, and `message` - which is
how a `E1023` or an `E8023` reaches the person who has to fix the capture.

`lifecycle` is which spool directory the receipt is in rather than anything
written into the file, so it is always the current truth. A receipt whose stored
resource will not parse as a `QuestionnaireResponse` is still listed, with the
envelope fields filled and every derived field - `status`, `authored`, `period`,
`organisation_unit`, `tracked_entity` - left null rather than guessed at.

It is what the capture UI's Overview and Responses pages read, and the
lifecycle states are the spool directories the forwarder moves receipts
between - see [Forward captures into DHIS2](201-forward.md).

## `/uiconfig`: what the UI is allowed to know

The handful of run-time settings the capture UI has to act on - today, whether
this run receives submissions at all, the basemap layers it offers with the
attribution the server can honestly state for each, the address of the DHIS2
instance it resolved a profile for, which is what an identity on a page links
back to, and whether this run answers
about the instance's tracked entities at all. Deliberately not the profile's
name, its credentials, the
host this process listens on, or the strictness dial: those describe the process
to whoever runs it, and a browser that could read them would be a browser that
leaks them.

```console
$ curl -s localhost:8389/uiconfig | jq .
{
  "capture": true,
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

`capture` is `[serve] capture` as this run resolved it, and the screens gate
their **Submit** on it: false, and a form still opens and fills and reads, with
the sentence *This server does not accept submissions* where the button was.
The CapabilityStatement says the same thing in its own terms; this field is
here so a screen decides what to draw without parsing a conformance document.
A server that states nothing is read as receiving, which is the opposite of how
`tracked_entities` reads silence - a page nobody is offered is a page nobody
misses, while withholding the one control these screens exist for, over a
setting the browser could not read, would take the app away.

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
[`dhis2w_fhir_serve` API reference](api-dhis2w-fhir-serve.md) covers the
store, the spool, and the capture path as importable Python.
