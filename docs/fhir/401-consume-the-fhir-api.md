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
- read one tracked entity's record over time - every event of its enrollments,
  as the responses the guide's own forms describe
- resolve generated codes back to DHIS2 identifiers with `$translate`
- get a valid, reproducible test submission from `$generate`
- evaluate a FHIRPath expression, a CQL library, or a compiled ELM library over
  what the facade serves with `$evaluate`, and read the answer as `Parameters`
- post a capture and read every kind of answer the server gives
- read the two facade endpoints a capture client acts on, `/spool` and
  `/uiconfig`

**The runnable version of this page** is
[`examples/fhir/client/consume_facade.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/consume_facade.py) -
plain httpx against a served project, walking discovery, search, `$generate`, a
capture, the receipt, and `/spool` end to end. Point it at your own facade with
`uv run python examples/fhir/client/consume_facade.py http://localhost:8123`.
The rest of that directory is the library path: `generate_ig.py` builds a guide
from Python and `forward_spool.py` drains one. In Python, `FacadeClient` from
`dhis2w_fhir` is the typed path over the parts of this page a capture client
lives in: `/metadata`, the reads and the searches, `$generate`, the post and its
receipt, and an evaluation. `$translate`, `$summary`, the tracked-entity
endpoints, `/spool`, and `/uiconfig` are addresses a caller asks for itself.
[`examples/fhir/client/send_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/send_with_the_client.py)
is the same submit-and-read-back loop with no request built by hand, and four
files beside it take the rest of that client one at a time:
[`search_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/search_with_the_client.py)
for discovery, search, and canonical resolution,
[`evaluate_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/evaluate_with_the_client.py)
for the two evaluation contexts,
[`authenticate_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/authenticate_with_the_client.py)
for the credential a guarded facade takes, and
[`handle_refusals_with_the_client.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/handle_refusals_with_the_client.py)
for reading a refusal off `FacadeError` rather than out of a parsed body.

**Every endpoint on this page answers the same way with no server running.**
[Embed the facade](401-embed-the-facade.md) builds the application in your own
process and drives it over an ASGI transport, which is the posture for a caller
that wants the FHIR surface as a library rather than as an address.

Every response body on this page is real output from a running facade. The
compiled-store examples run against a project served on port 8389; the
register, enrollment, and record examples, which exist only under `--live`,
against a `d2w fhir serve --live` on port 8391. The Python surface behind all of it is
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
`$generate` on `Questionnaire`, served at `/Questionnaire/{id}/$generate`,
`$translate` on `ConceptMap`, served at `/ConceptMap/$translate`, and
[`$summary`](#summary-one-persons-international-patient-summary) on each register
entry whose subjects are people - and only when the store holds that type. So a
client that follows the statement reaches an endpoint that answers, and
`/metadata` never advertises what the store cannot do.

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
that named formats and named no JSON among them meets the 406. The facade's own
endpoints negotiate nothing, because they answer about this facade rather than
with resources out of it: `/spool` and `/uiconfig` below,
`/tracked-entities/{uid}/enrollments`, `/evaluate`, `/terminology/lookup` and
`/terminology/validate-code`, `/whoami`, and `/cds-services` all answer plain
`application/json` whatever a request asked for.

**`_format` overrides the header, which is what makes a FHIR query a link.**
R4 defines the parameter for the client that cannot set an `Accept` - the one
following a URL somebody pasted - and this server reads it as the override it
is. `_format=json`, `_format=application/json`, and
`_format=application/fhir+json`, in any casing, make JSON acceptable whatever
the header said:

```console
$ curl -s -o /dev/null -w '%{http_code}\n' -H 'Accept: text/html' localhost:8389/metadata
406
$ curl -s -o /dev/null -w '%{http_code}\n' -H 'Accept: text/html' 'localhost:8389/metadata?_format=json'
200
```

A `_format` naming anything else is refused even where the header would have
admitted JSON: the client stated the format it wants, and this server has only
the one.

```console
$ curl -s -H 'Accept: application/json' 'localhost:8389/metadata?_format=xml'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`_format=xml` names a format this server does not serve, and this server answers `application/fhir+json` only; ask for `_format=json`, for `_format=application/json`, or for `_format=application/fhir+json`"}]}
```

An absent `_format` leaves the header to decide alone, and the parameter never
narrows a search: it names the format an answer arrives in, so a route that
screens its search parameters passes over it rather than filtering on it. Every
screen of the capture UI links its own query this way - see
[Capture in the browser](201-capture-ui.md#the-query-behind-every-screen).

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

Eleven definitional types are served. Seven are the published content -
`Questionnaire`, `CodeSystem`, `ValueSet`, `Location`, `Organization`, `List`,
and `ConceptMap` - and four are the guide's own conformance resources,
`StructureDefinition`, `ImplementationGuide`, `OperationDefinition`, and the
requirements `CapabilityStatement` that `/metadata` instantiates, hosted
so that a canonical found on a served resource resolves against the server that
served it ([the guide's own definitions](201-serve.md#the-guides-own-definitions-are-served)).
Beside them is `QuestionnaireResponse`, the one type the facade also receives,
and, under `--live` only, whichever resources
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

### The register search {#the-register-search-identifier}

Every search above answers from what the project published. This one answers
from the DHIS2 instance the server runs against, at request time, which is why
it exists only under `--live` - and why `/metadata` declares the register's
resources only there. A compiled run says so instead of guessing:

```console
$ curl -s localhost:8389/Patient?identifier=SCEN-A-0001
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`Patient` is answered from the DHIS2 instance this facade runs against. This facade serves a compiled implementation guide, so it holds no register to search. Run `d2w fhir serve --live` to search one."}]}
```

**Three parameters search a register, and they ask three different questions.**
`identifier` names which record a value belongs to, `_tag` names which tracked
entity type a record is of, and `d2-attribute` names a value a record holds.
Each has a subsection below, and `/metadata` declares each one on the register
entry that answers it. A register served from a synced copy answers a fourth,
`_content`, which is the last subsection here. Naming two of them asks for the
records that satisfy both - they narrow each other, though several `identifier`
tokens are alternatives among themselves, which that subsection explains.

#### `identifier`: which record a value names

`identifier` takes both of FHIR's token forms. A system-qualified token names
which key the value is:

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

A key whose DHIS2 value type cannot hold what was typed is left out of that
fan-out - a NUMBER key never sees a name - and a key the instance refuses anyway
is that key matching nobody. Either way the keys that could hold the value still
answer, and the search stands.

**Several identifier tokens are alternatives, not conditions.** This is the one
place the facade's search semantics differ from the definitional types above:
there, two parameters narrow each other; here, every token and every
comma-separated value is another key to try, and their matches are unioned. A
client holding two cards for one person asks once.

#### `_tag`: which tracked entity type a record is of

One FHIR resource type is one register over the union of the tracked entity
types the published map takes onto it, so `GET /Device` answers about the cold
chain fridges and the delivery vehicles alike. `_tag` is how a caller asks that
union about one of its types, and it is R4's own token search over exactly the
element each record states its type in - the `meta.tag` every projection
carries:

```bash
curl -s -G localhost:8391/Patient \
  --data-urlencode '_tag=http://dhis2.org/fhir/id/tracked-entity-type|nEenWmSyUEp'

curl -s 'localhost:8391/Patient?_tag=nEenWmSyUEp'
```

Both forms are the same query: there is one tag on these resources, so naming
the code alone is unambiguous. It narrows the identifier search's scope, the
listing's walk, and the `_count=0` count alike, and it rides every `next` and
`previous` link so a walk stays inside the type it started in. A `_tag` naming a
type this resource is not served over is a query nothing can satisfy, and comes
back as an empty searchset rather than a refusal - a tag names a value a record
may or may not hold.

#### `d2-attribute`: what a record holds

`identifier` answers the attributes that name somebody. The attributes that
describe a lot of people - sex, district of residence, whether consent was given
- name nobody, and FHIR has no element for them: their values ride the
`D2TrackedEntityAttributeValue` extension, so the parameter over them is this
project's own, spelled with the `d2-` prefix everything DHIS2-specific here is
spelled with. `d2-attribute={trackedEntityAttributeUid}|{value}` is one
attribute and one value:

```bash
curl -s -G localhost:8391/Patient --data-urlencode 'd2-attribute=cejWyOfXge6|Female'
```

**It answers equality and nothing else** - no prefix, no substring, no range, no
`:missing`, no ordering. Case is the one thing it ignores, because DHIS2's own
`eq` ignores it (BUGS.md 109), so the two search backends agree
on every value in the register rather than on the ones typed the way they were
stored. A caller who wants "starts with" wants `_content` below.

**Two occurrences narrow; a comma does not split.**
`d2-attribute=A|x&d2-attribute=B|y` is whoever holds both, which is what R4 says
two instances of one parameter mean. The value is taken whole rather than split
on commas - this is the one place the token grammar departs from R4 deliberately,
because `Smith, John` is a value somebody actually holds and splitting it would
make them unfindable by it. It narrows the listing, the identifier search, the
`_content` search, and the `_count=0` count alike, under either backend, and it
rides the listing's links the way `_tag` does.

Which attributes a register filters on is what the published registration forms
of its types ask - the same values every record it hands back already carries -
and it is declared per register at `/metadata` and at `/uiconfig`, so a client
reads the set before it searches. There is no configuration key narrowing it:
a dial that hid a filter over data the server hands over anyway would read like
a control and not be one. An attribute a request names and this register does
not filter on is a 400 naming the ones it does.

#### `_content`: a text search over a synced copy

**A register served from a synced copy answers one more parameter.** Where the
operator has configured
[`[serve.search] backend = "projection"`](301-serving.md#search-backend), the
register also answers R4's own parameter for a text search over a resource's
whole content - a case-insensitive substring of any value the person holds:

```console
$ curl -s 'localhost:8391/Patient?_content=minata' | jq '.entry[] | select(.search.mode=="match") | .resource.id'
```

It is `_content` and not `family` on purpose: this server does not know which of
somebody's DHIS2 attribute values is their name and will not guess, for exactly
the reason the identity-only projection below states. `/metadata` declares
`_content` only where it is answered, so a client reads the CapabilityStatement
rather than probing. Under the default backend it is refused like any other
unanswerable parameter, because an exact-match tracker filter cannot search a
content.

**And a projection-served answer says when it was true.** Every searchset it
answers carries an `outcome` entry stating the instant, and an
`X-DHIS2W-Projection-As-Of` header beside it - so an answer out of the copy is
*as of* an instant, never *now*. It also states **no `total`**: the copy counted
its rows under the identity the sync ran as, and how many of them you may see is
the instance's to say one read at a time. `_count=0` is therefore the one
question this backend cannot answer - it comes back with the cursor, no entries,
and no walk to follow. Every record on the page was read from the instance under
your own credentials whichever backend found it, and `GET /Patient/{id}` is
answered from the instance in every posture.

#### What every register search shares

**A parameter this server cannot apply is refused, not ignored.** This is where
the register parts company with the searches above, and for the same reason the
union semantics exist: an unapplied filter here would be answered with the
register itself, and a client that asked for the people called Smith would read
every row of that answer as a Smith. So the server says what it answers on, and
names all three:

```console
$ curl -s 'localhost:8391/Patient?family=Smith'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"`family` is not a search parameter this server answers `Patient` on: it answers `_tag`, `d2-attribute`, `identifier`"}]}
```

`_count` is honoured beside any of them and caps the matches handed back, on
the same terms as every other searchset here - `total` states how many there
were, and `_count=0` states that number alone. `page` belongs to the listing
below and is refused on a search, which is answered whole rather
than paged. A request naming no parameter at all is the listing, unchanged.

An identifier nobody holds, a system this guide publishes nothing for, and a tag
naming a type this resource is not served over are all an empty searchset - never
a 404, which on a search path would say the endpoint does not exist:

```console
$ curl -s 'localhost:8391/Patient?identifier=NO-SUCH-ID' | jq '.type, .total'
"searchset"
0
```

#### What a record comes back as

**The Patient is identity, plus whatever the instance nominated.** No `name`, no
`gender`, no `birthDate` unless
[`[ips.identity]`](301-what-goes-in.md#ips-identity) says which tracked entity
attribute holds each one - DHIS2 has no attribute that means any of those, and
which of an instance's attributes do is a decision each instance makes for
itself. A wrong `gender` on a patient record is a worse answer than none, so
without a nomination the server states only what DHIS2 states:

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
a read, unlike a search, names a specific resource. The very resource this
address answers with is the subject of that person's
[`$summary`](#summary-one-persons-international-patient-summary), so who a
summary is about and who the register serves can never disagree.

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
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`Patient` is not served here: this project's fhir.toml turns the register off, with `[serve.tracked_entities] enabled` set to false. Set that key to true and serve again to search or list the register."}]}
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
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`enrollments` is answered from the DHIS2 instance this facade runs against. This facade serves a compiled implementation guide, so it holds no register to search. Run `d2w fhir serve --live` to search one."}]}
```

`[serve.tracked_entities] enabled = false` takes this endpoint away in the same
line it takes the register away. `listing = false` does **not** touch it: that
switch is about browsing a register with no criteria, and this is a read about
one person you already have.

A UID the instance does not hold is a 404 here, as on any read.

## `/tracked-entities/{uid}/events`: what has happened to one of them

The register says who somebody is. This says what the instance holds about
them: every event of every enrollment that tracked entity has, newest first,
each one served as the `QuestionnaireResponse` the guide already publishes for
its program stage. It is a searchset Bundle, read from DHIS2 while you wait,
under your own authorization where the server runs
[`auth = "dhis2"`](301-serving.md#auth).

**The shape is the capture contract's, read backwards.** A client posting a
tracker event sends a `D2TrackerEventResponse`; this is the same document,
built from what DHIS2 holds now - the stage's `questionnaire`, the tracked
entity as `subject`, the enrollment and the reporting unit as extensions, the
event's own instant as `authored`, and one item per data value under the
`linkId` its data element is asked as. What a client may write is what a client
reads back, so a consumer that already understands one leg understands both.

The subject need not be a person. Here it is a cold chain fridge, whose type
the project publishes as `Device`, and whose record is three hourly temperature
readings:

```console
$ curl -s 'localhost:8391/tracked-entities/geghdTobFoE/events?_count=1' | jq .
{
  "resourceType": "Bundle",
  "type": "searchset",
  "total": 3,
  "link": [
    { "relation": "self", "url": "http://localhost:8391/tracked-entities/geghdTobFoE/events?_count=1&page=bzA" },
    { "relation": "next", "url": "http://localhost:8391/tracked-entities/geghdTobFoE/events?_count=1&page=bzE" }
  ],
  "entry": [
    {
      "fullUrl": "http://localhost:8391/tracked-entities/geghdTobFoE/events/Jb3VgYmqRpD",
      "resource": {
        "resourceType": "QuestionnaireResponse",
        "id": "Jb3VgYmqRpD",
        "meta": { "profile": ["http://localhost:8391/fhir/StructureDefinition/d2-tracker-event-response"] },
        "extension": [
          {
            "url": "http://localhost:8391/fhir/StructureDefinition/d2-organisation-unit",
            "valueReference": { "reference": "Location/DiszpKrYNg8" }
          },
          {
            "url": "http://localhost:8391/fhir/StructureDefinition/d2-tracker-enrollment",
            "valueIdentifier": { "system": "http://dhis2.org/fhir/id/tracker-enrollment", "value": "IsEmT1d3S4X" }
          },
          { "url": "http://localhost:8391/fhir/StructureDefinition/d2-form-type", "valueCode": "tracker-event" }
        ],
        "questionnaire": "http://localhost:8391/fhir/Questionnaire/PsTempRead1",
        "status": "completed",
        "subject": {
          "type": "Device",
          "identifier": { "system": "http://dhis2.org/fhir/id/tracked-entity", "value": "geghdTobFoE" }
        },
        "authored": "2026-08-22T08:00:00Z",
        "item": [
          { "linkId": "UHa1Rmk0lwA", "answer": [{ "valueInteger": 5 }] },
          { "linkId": "vlWx4U5DnZX", "answer": [{ "valueDecimal": 7.9 }] }
        ]
      },
      "search": { "mode": "match" }
    }
  ]
}
```

`id` is the DHIS2 event UID and `fullUrl` is where that one document is served
- `GET /tracked-entities/{uid}/events/{eventUid}` answers it on its own.
`QuestionnaireResponse/{id}` is deliberately *not* that address: that one
answers the spool, where a document of the same id is a receipt of what a client
sent rather than what DHIS2 now holds.

**A coded value carries the concept this guide publishes for it.** DHIS2 stores
an option's own code; the served CodeSystem publishes that code beside the
concept code, so the answer comes back as a coding a consumer can resolve:

```json
{ "linkId": "vTUhAUZFoys",
  "answer": [{ "valueCoding": {
    "system": "http://localhost:8391/fhir/CodeSystem/d2-os-kzgQRhOCadd-cs",
    "code": "sXfZuRdvhl5",
    "display": "Dose 0" } }] }
```

A value the served terminology cannot code comes back as the string DHIS2
stored, and so does a number the instance holds in a spelling its own value
type does not admit. Dropping either would hide a value the instance holds.

**Paging.** `_count` and `page` walk the record the way they walk the register
listing, `_count` clamped at
[`page_size_limit`](301-serving.md#tracked_entities-page_size_limit), and
`_count=0` answers how long the record is and returns nobody's events:

```console
$ curl -s 'localhost:8391/tracked-entities/geghdTobFoE/events?_count=0'
{"resourceType":"Bundle","type":"searchset","total":3,"link":[{"relation":"self","url":"http://localhost:8391/tracked-entities/geghdTobFoE/events?_count=0"}]}
```

`total` is every event this caller may see, counted under their own
credentials. The two parameters above are the whole surface: anything else is
refused rather than ignored, because a parameter this server cannot apply,
ignored, would answer a narrower question with the whole record.

```console
$ curl -s 'localhost:8391/tracked-entities/geghdTobFoE/events?programStage=PsTempRead1'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"`programStage` is not a search parameter this server answers `events` on: it answers `_count`, `page`"}]}
```

**An event of a stage this project publishes no form for is stated rather than
skipped.** It counts in `total`, carries no document - there is no form to name
as its `questionnaire` - and the searchset closes with an `outcome` entry saying
which stage it was of. Generate that stage's Questionnaire and it reads here
like the rest.

Like the register, this is live-only, and
`[serve.tracked_entities] enabled = false` takes it away with the register.
[`events = false`](301-serving.md#tracked_entities-events) takes it away on its
own, for a project that publishes who its subjects are and not what was recorded
about them:

```console
$ curl -s 'localhost:8391/tracked-entities/geghdTobFoE/events'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this facade serves no `events`: this project publishes who its tracked entities are and not what was recorded about them; set `[serve.tracked_entities] events = true` in fhir.toml and serve again"}]}
```

## `$summary`: one person's International Patient Summary

The register says who somebody is and the record says what has happened to them.
`$summary` is one document over both, in the shape the
[International Patient Summary](https://hl7.org/fhir/uv/ips/) defines: a FHIR
document Bundle whose first entry is a `Composition` coded `60591-5` and whose
remaining entries are the resources its sections point at. The operation had a
name before this project existed - the IPS publishes
`OperationDefinition/summary` on `Patient` - so a client that speaks IPS reaches
it without learning an address this project invented.

Two forms, both `GET`, both live-only. Name the person by their DHIS2 tracked
entity UID:

```console
$ curl -s 'localhost:8391/Patient/PLoWmEuLJl2/$summary'
```

or let the register's own identifier search find them, on the same token grammar
`GET /Patient?identifier=` answers - a system-qualified token, or a bare value
tried against every key the register searches:

```console
$ curl -s 'localhost:8391/Patient/$summary?identifier=SCEN-A-0001'
```

An identifier several people hold is refused rather than answered: a summary is
about one person, and handing back the first match would be the server picking
which one. Every parameter other than `identifier` is refused too, since the
operation takes one input and answers one document.

**What comes back.** The `Composition`, the subject as the register already
serves them, and one `Immunization` per recorded dose:

```json
{
  "resourceType": "Bundle",
  "id": "PLoWmEuLJl2-ips",
  "type": "document",
  "identifier": {"system": "urn:ietf:rfc:3986", "value": "urn:uuid:1f6b..."},
  "timestamp": "2026-08-18T09:14:02+00:00",
  "entry": [
    {
      "fullUrl": "urn:uuid:9c02...",
      "resource": {
        "resourceType": "Composition",
        "id": "PLoWmEuLJl2-ips",
        "status": "final",
        "type": {"coding": [{"system": "http://loinc.org", "code": "60591-5", "display": "Patient summary Document"}]},
        "subject": {"reference": "urn:uuid:4ad1..."},
        "title": "International Patient Summary",
        "section": [
          {
            "title": "Problems",
            "code": {"coding": [{"system": "http://loinc.org", "code": "11450-4", "display": "Problem list - Reported"}]},
            "emptyReason": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/list-empty-reason", "code": "unavailable"}]}
          },
          {"title": "Allergies and Intolerances", "code": {"coding": [{"code": "48765-2"}]}, "emptyReason": {"coding": [{"code": "unavailable"}]}},
          {"title": "Medication Summary", "code": {"coding": [{"code": "10160-0"}]}, "emptyReason": {"coding": [{"code": "unavailable"}]}},
          {
            "title": "Immunizations",
            "code": {"coding": [{"system": "http://loinc.org", "code": "11369-6", "display": "History of Immunization Narrative"}]},
            "entry": [{"reference": "urn:uuid:07e5..."}]
          }
        ]
      }
    }
  ]
}
```

Problems, Allergies and Intolerances, and Medication Summary are the three
sections the IPS requires, and each states an `emptyReason` of `unavailable`
rather than carrying content nobody nominated: DHIS2 marks no data element as a
problem, an allergy, or a medication. Immunizations is the one section a project
maps, through
[`[ips.sections.immunizations]`](301-what-goes-in.md#ips-sections) - the data
element is the vaccine and its value is the dose - and the doses come off the
same record `/tracked-entities/{uid}/events` serves. `Immunization.vaccineCode`
carries the data element's own DHIS2 coding, under the namespace
[`D2Section_CM`](401-terminology-and-conceptmaps.md#the-sections-a-recorded-value-feeds)
maps out of. Every entry is addressed by a `urn:uuid` derived from the DHIS2
identity, so two reads of an unchanged record name the same resources and differ
only in `Bundle.timestamp` and `Composition.date`.

**The caveat is part of the answer, and it rides twice.** `Composition.text` says
in the document what the document is and is not, and the same sentence comes back
on the response as `X-DHIS2W-Summary-Caveat` - the idiom
`X-DHIS2W-Projection-As-Of` uses for the same reason, one fact stated where
resources are read and stated again where responses are:

```console
$ curl -sD - -o /dev/null 'localhost:8391/Patient/PLoWmEuLJl2/$summary' | grep -i summary-caveat
x-dhis2w-summary-caveat: Immunizations is mapped and carries 3 doses read from this person's own record. Problems, Allergies and Intolerances, Medication Summary are the three sections the IPS requires, and each states an empty reason rather than carrying content nobody nominated: DHIS2 marks no data element as a problem, an allergy, or a medication, and this project has nominated none. This document is a valid IPS Bundle and does not claim the Creator (IPS) actor's obligations.
```

A project that maps no clinical section at all is still answered, and the caveat
says that instead: no section is mapped, the three required ones state an empty
reason, and the document is a valid IPS Bundle that claims none of the Creator
(IPS) actor's obligations. A mapped section with no dose recorded for this person
is a different fact and reads differently - the section is present with an empty
reason of its own.

**Two refusals.** [`[ips] enabled`](301-what-goes-in.md#ips-enabled) is false by
default, and a summary is a clinical document about a person rather than
something a deployment inherits:

```console
$ curl -s 'localhost:8391/Patient/PLoWmEuLJl2/$summary'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"this server assembles no `Patient` summary: this project sets `[ips] enabled` to false, so it publishes who its subjects are and what was recorded about them and no summary over either; set it true in fhir.toml and serve again to answer `$summary`"}]}
```

And the operation is scoped to the people. The register serves whatever resource
types a project maps its tracked entity types onto, and a summary of a cold chain
fridge is a document nobody has defined, so `$summary` is answered on `Patient`,
`Person`, `Practitioner`, and `RelatedPerson` and refused by name on the rest:

```console
$ curl -s 'localhost:8391/Device/geghdTobFoE/$summary'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported","diagnostics":"`$summary` is a patient summary and `Device` names no person: this server answers it on `Patient`, `Person`, `Practitioner`, `RelatedPerson` alone. Whatever is served under `Device` is served at its own address as usual; a summary of it is a document nobody has defined."}]}
```

`/metadata` declares the operation on each register entry that answers it and on
no other, naming `summary` and the IPS's own definition at
`http://hl7.org/fhir/uv/ips/OperationDefinition/summary`, so a client reads where
a summary lives rather than probing for it.

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
`Questionnaire`, `$translate` on `ConceptMap`, `$summary` on the register's
people where a project publishes summaries, and `$evaluate` at the service base.

**Two plain reads answer the questions those operations would have.**
`GET /terminology/lookup?system=&code=` says what one code means, and
`GET /terminology/validate-code?code=` with either a `valueset` or a `system`
says whether a code is in a published value set or is a code of a published
system at all. Both are typed JSON on lowercase paths and both answer about this
project's own vocabularies and nothing else - a SNOMED CT or a LOINC code comes
back as a code this server publishes no system for, which is true and more useful
than a guess. They are not `$lookup` and `$validate-code` because answering those
properly means answering for the external systems a real implementation guide
composes, which this facade cannot do and should not appear to.
`/metadata` names both in its `description`, so a client finds them without
probing.

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

## `$evaluate`: an expression over what this facade serves

`POST [base]/$evaluate` runs one FHIRPath expression, one CQL library, or one
compiled ELM library over a resource this server serves, and answers a
`Parameters` resource. It is the **system-level** operation - declared at
`rest.operation` in `/metadata`, because what it evaluates over is whatever the
request names as its context and no resource type owns that. Its definition is
this project's own,
`https://winterop-com.github.io/dhis2w-utils/fhir/OperationDefinition/serve-evaluate`,
and this page is where it is defined.

The input is a `Parameters` resource:

| Parameter | Type | What it is |
| --- | --- | --- |
| `language` | `code` | `fhirpath`, `cql`, or `elm`. Required. |
| `source` | `string` | The expression, the CQL library text, or the ELM library as JSON. Required. |
| `expression` | `string` | Which define to answer. Omitted, a library answers every define it declares. |
| `context` | *(parts)* | The one resource the expression may reach. Omitted, it runs over no resource at all. |

`context` carries a `kind` part naming one of three, and the parts that kind
needs - the same three the [Evaluate screen](201-capture-ui.md) offers, and the
only data an expression can reach:

| `kind` | Parts | What it names |
| --- | --- | --- |
| `stored` | `resourceType`, `resourceId` | One resource of the served guide, named the way a read names it. |
| `inline` | `resource` | The resource carried in the request itself. |
| `registered` | `trackedEntityUid`, optionally `resourceType` | One tracked entity, read from the DHIS2 instance a live run holds open and projected the way `GET /Patient/{uid}` projects it. |

One answer rides the parameter named for the define - `value[x]` for a
primitive, `resource` for a resource:

```console
$ curl -s localhost:8389/'$evaluate' -H 'Content-Type: application/fhir+json' -d '{
    "resourceType": "Parameters",
    "parameter": [
      {"name": "language", "valueCode": "fhirpath"},
      {"name": "source", "valueString": "Questionnaire.title"},
      {"name": "context", "part": [
        {"name": "kind", "valueCode": "stored"},
        {"name": "resourceType", "valueCode": "Questionnaire"},
        {"name": "resourceId", "valueString": "BfMAe6Itzgt"}]}]}'
{"resourceType":"Parameters","parameter":[{"name":"expression","valueString":"Child Health"}]}
```

A FHIRPath expression has no define name, so its parameter is named
`expression`. Several values ride one `part` apiece, because a parameter states
one value and a collection is several:

```console
$ # ... "source": "Questionnaire.item.linkId"
{
  "resourceType": "Parameters",
  "parameter": [
    {
      "name": "expression",
      "part": [
        {"name": "value", "valueString": "Y2rk0vzgvAx"},
        {"name": "value", "valueString": "vtOr8PTJVxS"}
      ]
    }
  ]
}
```

A CQL library answers one parameter per define, named by the define, in
declaration order. A define that refuses carries an `OperationOutcome` part of
its own, so the rest of the library still answers - here over one tracked entity
read from DHIS2 at request time:

```console
$ curl -s localhost:8391/'$evaluate' -H 'Content-Type: application/fhir+json' -d '{
    "resourceType": "Parameters",
    "parameter": [
      {"name": "language", "valueCode": "cql"},
      {"name": "source", "valueString": "library RegisteredPerson version '"'"'1.0'"'"'\nusing FHIR version '"'"'4.0.1'"'"'\n\ndefine Person: First([Patient])\ndefine TrackedEntityUid: Person.id\ndefine KnownToTheRegister: exists [Patient]\ndefine Unmapped: Message('"'"'x'"'"', true, '"'"'no-birth-date'"'"', '"'"'Error'"'"', '"'"'DHIS2 states no mapping for Patient.birthDate'"'"')\n"},
      {"name": "context", "part": [
        {"name": "kind", "valueCode": "registered"},
        {"name": "trackedEntityUid", "valueString": "jdXAPyf0K9X"}]}]}'
{
  "resourceType": "Parameters",
  "parameter": [
    {"name": "Person", "resource": {"resourceType": "Patient", "id": "jdXAPyf0K9X", ...}},
    {"name": "TrackedEntityUid", "valueString": "jdXAPyf0K9X"},
    {"name": "KnownToTheRegister", "valueBoolean": true},
    {"name": "Unmapped", "part": [
      {"name": "outcome", "resource": {"resourceType": "OperationOutcome", "issue": [
        {"severity": "error", "code": "processing",
         "diagnostics": "Error evaluating Unmapped: CQL Error [no-birth-date]: DHIS2 states no mapping for Patient.birthDate"}]}}]}
  ]
}
```

**A bad expression is a 200.** Source that will not parse, a define name the
library does not declare - each answers `200` with an `outcome` parameter saying
so, because the request was well formed and this is its answer. The line and the
column the parser stopped on are in the issue's `diagnostics`, counted from one:

```console
$ # ... "source": "define Form: singleton from [Questionnaire]"
{
  "resourceType": "Parameters",
  "parameter": [
    {"name": "outcome", "resource": {"resourceType": "OperationOutcome", "issue": [
      {"severity": "error", "code": "invalid",
       "diagnostics": "line 4, column 29: extraneous input '[' expecting {...}"}]}}
  ]
}
```

What answers an OperationOutcome with a **4xx** is a request this facade cannot
serve at all: a stored resource it does not hold (404), a `registered` context on
a process holding no DHIS2 instance (404), a `language` this server does not
evaluate or a `context` naming a fourth kind (400).

**A define that matched nothing carries no parameter.** FHIR has no empty
collection - a value is present or the element is not there - so an expression
matching nothing answers `{"resourceType": "Parameters"}` and a library answers
only the defines that had something to say.

**The sibling that keeps what `Parameters` cannot carry.** `POST /evaluate`
answers this project's own JSON for the same evaluation: one row per define
whether or not it answered, so "matched nothing" and "was not run" stay apart,
and diagnostics as fields rather than as prose. It is what the capture UI's
Evaluate screen reads, and it takes the same body this operation takes as
`Parameters` - which `$evaluate` also accepts, so a caller who has one body can
choose which shape comes back by choosing an address:

```console
$ curl -s localhost:8389/'$evaluate' -H 'Content-Type: application/json' \
    -d '{"language": "fhirpath", "source": "Questionnaire.title",
         "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": "BfMAe6Itzgt"}}'
{"resourceType":"Parameters","parameter":[{"name":"expression","valueString":"Child Health"}]}
```

A `Parameters` body is what the operation documents and what a FHIR client
should send; the plain body is read for the convenience of a caller already
posting to `/evaluate`.

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
form kind it was validated as, who it was validated under, its warnings, its
lifecycle state, and whatever DHIS2 or the drain said about it. Plain
`application/json`:

```console
$ curl -s localhost:8389/spool | jq '{total, counts, next_url}'
{
  "total": 987,
  "counts": {
    "received": 0,
    "forwarded": 703,
    "rejected": 284,
    "withdrawn": 0,
    "malformed": 0
  },
  "next_url": "http://localhost:8389/spool?_count=50&page=bzUwbjk4Nw"
}
$ curl -s localhost:8389/spool | jq '.responses[0]'
{
  "response_id": "f066e98e279b47689a145710d1f108a7",
  "received_at": "2026-08-10T18:58:04Z",
  "lifecycle": "forwarded",
  "form_kind": "tracker-event",
  "questionnaire": "http://localhost:8080/fhir/Questionnaire/ZzYYXq4fJie",
  "questionnaire_id": "ZzYYXq4fJie",
  "submitted_by": null,
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
  },
  "refusal": null,
  "withdrawal": null
}
```

**Four slots carry what happened to a receipt, and which one is filled follows
from where the receipt sits.** `rejection` and `imported` are the two halves of
what DHIS2 answered a drain - `rejection` only on a `rejected` receipt,
`imported` only on a `forwarded` one. `refusal` is the queue's own history rather
than a DHIS2 answer: it appears only on a `received` receipt the last committing
drain would not translate, and states when that drain looked, how many drains
have refused the receipt so far, and why - the receipt stays queued and the next
drain retries it. `withdrawal` appears only on a `withdrawn` receipt and is what
`d2w fhir withdraw` recorded: the instant, the DHIS2 event it named, what DHIS2
counted as deleted, and the note saying what remains in the instance, because
DHIS2 soft-deletes and a listing that said "deleted" would claim more than the
toolkit can stand behind. A receipt with nothing yet to say about it carries four
nulls. `rejection` and `refusal` each carry an `issues` or `reasons` array, one
entry per thing named against the payload with its `error_code`, `subject`, and
`message` - which is how a `E1023` or an `E8023` reaches the person who has to
fix the capture.

`lifecycle` is which spool directory the receipt is in rather than anything
written into the file, so it is always the current truth. A receipt whose stored
resource will not parse as a `QuestionnaireResponse` is still listed, with the
envelope fields filled and every derived field - `status`, `authored`, `period`,
`organisation_unit`, `tracked_entity` - left null rather than guessed at.

**`counts` has a fifth key that is not a lifecycle state.** `malformed` is the
holding pen: bytes the spool moved aside because they do not read as a receipt at
all. They are not in `total`, they are not in `responses`, and the listing's own
`malformed` array states each one with what stopped it.

**The listing pages, with the same two parameters the register listing uses.**
`_count` is how many rows a page carries - **50** by default, and a request naming
more than **500** is served 500 rather than refused. `page` is an opaque cursor a
client only ever gets from `next_url` or `previous_url`; `self_url` is the page
you are on, as a client may ask for it again and be handed the same one. `total`
is the whole listing on every page of one walk, and `counts` is the whole spool
rather than the page - a queue depth that changed with the page you were looking
at would be no queue depth at all.

```console
$ curl -s 'localhost:8389/spool?_count=abc'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"`_count` was given `abc`, which is not a number of rows"}]}
$ curl -s 'localhost:8389/spool?page=12'
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"`page` is not a page of this listing: its value comes from the `next` or `previous` link of a result, and is not a number a client composes"}]}
```

Every read re-reads the directory, because `d2w fhir forward` and `d2w fhir
withdraw` rename files while this server runs. It is what the capture UI's
Overview and Responses pages read, and the lifecycle states are the spool
directories those two commands move receipts between - see
[Forward captures into DHIS2](201-forward.md).

## `/uiconfig`: what the UI is allowed to know

The handful of run-time settings the capture UI has to act on - today, whether
this run receives submissions at all, which credential it checks and over which
routes, the basemap layers it offers with the attribution the server can honestly
state for each, the address of the DHIS2 instance it resolved a profile for,
which is what an identity on a page links back to, and whether this run answers
about the instance's tracked entities at all. Deliberately not the profile's
name, its credentials, the
host this process listens on, or the strictness dial: those describe the process
to whoever runs it, and a browser that could read them would be a browser that
leaks them.

```console
$ curl -s localhost:8389/uiconfig | jq .
{
  "capture": true,
  "auth": {
    "posture": "none",
    "scope": "write",
    "issuer": null
  },
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
      {
        "resource": "Patient",
        "types": [{ "uid": "nEenWmSyUEp", "name": "Person" }],
        "filter_attributes": [
          { "uid": "cejWyOfXge6", "name": "Gender", "value_type": "TEXT",
            "value_set": "http://localhost:8080/fhir/ValueSet/d2-os-pC3N9N77UmT-vs",
            "types": ["nEenWmSyUEp"] }
        ]
      },
      {
        "resource": "Specimen",
        "types": [{ "uid": "Kd6Nk9wnAJa", "name": "Specimen batch" }],
        "filter_attributes": []
      }
    ]
  }
}
```

`auth` is the posture this run resolved, and it is here because a screen has to
know whether to offer a sign-in before it has been refused once: `posture` is
which credential the server checks, `scope` is whether that check covers every
route or the writes alone, and `issuer` names the OpenID Connect issuer under
`jwt` and is `null` otherwise. It is the posture, never a credential - what a
caller has to present is a fact about the server, and the sign-in gate reads the
same posture off `/metadata`'s security block. A document that omitted `auth`
would read as `none`, which is the right reading of silence for a screen, so this
run always states it.

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
none. The other five settings of that table shape the answers rather than the
screens, so the browser is never told them.

`registers` is the third fact, and it is the published `D2TET_CM` read for a
screen: one entry per FHIR resource this run serves from the instance, each
carrying the tracked entity types riding it under the names the instance holds
for them. It is what lets the navigation entry and the page heading read the
instance's own name for the one type a deployment tracks - **Person**,
**Fridge** - and **Tracked entities** on one tracking something else besides, and
what lets a section on that page be titled *Specimen batch* rather than
`Specimen` - the resource type is this project's projection, and the type's own
name is what a reader working in DHIS2 recognises. It is `[]` whenever
`enabled` is false, because a page the navigation does not offer has no sections
to name.

`filter_attributes` rides each register entry, and it is what a filter control is
drawn from: the attributes
[`d2-attribute`](#d2-attribute-what-a-record-holds) filters that register by, in
the order its forms ask them, each with the name a label reads, the DHIS2 value
type an input is shaped by, the value set a picker is filled from where the
attribute binds one, and which of the register's tracked entity types ask it.
`/metadata` declares the same set in its `d2-attribute` documentation, so a
screen and a FHIR client read one answer.

Both live on single lowercase path segments precisely so they can never
shadow a FHIR resource type, which is PascalCase.

Next: [Identifiers and the D2 extensions](401-identifiers-and-extensions.md)
- the identifier families and extensions every resource this API serves
carries. The
[`dhis2w_fhir_serve` API reference](api-dhis2w-fhir-serve.md) covers the
store, the spool, and the capture path as importable Python, and
[`FacadeClient`](api-dhis2w-fhir.md#a-client-for-a-running-facade) is the
client side of the same surface.
