# The materialized projection: a synced FHIR server over a DHIS2 instance

What it takes for `d2w fhir serve` to be a FHIR server with a proper backend rather
than a proxy that answers each request by asking DHIS2 - measured against a live
2.43.1 instance, not asserted. This is the working paper behind the freshness
question roadmap [9.3](roadmap.md#93-long-term) reserves in one parenthesis:
"per-request reads versus a refresh cadence against a national instance's
latencies". The recommendation in section 9 is a recommendation; the decisions
stay with the owner and are listed in section 11.

Every number below was measured on `dhis2/core` **2.43.1** started by `make
dhis2-run`, reached over loopback on the same host, no TLS, against the seeded
Child Programme (`IpHINAT79UW`) with a 500-person baseline register. Loopback is
the friendliest possible network, which matters: it makes the round-trip *counts*
in section 3 the honest part of the finding and the *seconds* the flattering part.
Every repro in this paper is copy-pasteable and every entity it creates is deleted
by the end of section 3.

## The short version

The facade's live-proxy model is right, and it is the default forever. It also has
three walls, and all three are the same wall: **an answer that needs many DHIS2
rows cannot be assembled one DHIS2 request at a time.** Evaluating a measure over
a cohort costs a measured 0.0955 s and one request per patient on loopback, which
is 16 minutes and 10,000 requests for a 10,000-person cohort before any network
exists. Finding a person by name costs a `:eq:` exact match, which measurably
cannot find `ສົມສັກ` from `Somsack`, cannot survive a one-character typo in either
script, and is refused outright by the facade rather than degraded. And a document
the facade hands out is either regenerated on every read or not stored at all.

The answer is a **materialized FHIR projection**: a durable document backend
holding the mapped scope of a DHIS2 instance as FHIR resources, filled by an
initial full materialization and kept current by incremental `lastUpdated` cursor
runs. This is a **product mode**, not a cache tier - start a FHIR server with a
proper backend, then sync it with a DHIS2 instance. The projection is derived,
cursor-stamped, rebuildable from zero, written by nothing but the sync, and never
a second system of record. Captures still travel spool to DHIS2 and only then back
through sync, so a value a client submitted appears in the server one sync
interval after DHIS2 accepted it - and the paper states that latency rather than
hiding it.

Two measurements went better than expected and one went worse. Deletions **are**
incrementally discoverable: `updatedAfter` plus `includeDeleted=true` returns a
tombstone carrying `deleted: true` and a fresh `updatedAt`, so a cursor sync can
learn that a person was removed. A bulk cohort read is fast - 800 people with
1,571 events in 0.595 s over five pages. What is slow is the *shape* the FHIR side
uses: one read per patient, which the engine's `DataSource` protocol makes the
natural shape and which costs 260x the bulk path per patient.

The backend recommendation is **PostgreSQL with `jsonb` as the document store and
OpenSearch as the search index beside it**, not OpenSearch alone, because the sync
cursor must advance in the same transaction as the documents it describes and
OpenSearch has no transaction to put it in. OpenSearch-alone is the documented
alternative and wins outright in one stated case.

And the sharpest reserved decision is not a backend at all. It is authorization:
DHIS2 enforces sharing, organisation unit scope, and tracker ownership *in the
request path*, and a projection takes DHIS2 out of the request path. Section 7
names the four honest options and recommends the narrow one.

## 1. How to use this document

This paper tees up five owner calls, listed in full in section 11: the tier-2
default backend, where the synced mode lives in the workspace, the store for
attested documents, the sync transport, and how a projection's freshness is
surfaced to a client. Sections 2 to 4 are evidence. Sections 5 to 8 are design.
Sections 9 and 10 are the recommendation and the sequence that lands it.

It assumes the reader knows what the facade serves today. If not, read
[the library surface](library.md) sections 3.1 and 3.2 first: the composition
contract this paper adds two Protocols to is the one that page proposes.

## 2. Where the facade stands today

Three facts, each cited, because the rest of the paper is only interesting if
these are true.

**The register is read live, per request, by exact match.**
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/register/wire.py:229` issues
`filter={attributeUid}:eq:{value}` against `/api/tracker/trackedEntities`. There
is no `:like:` anywhere in `dhis2w-fhir-serve`. One bare `identifier={value}`
lookup costs one UID read plus one filtered search per search-key attribute per
tracked entity type mapped to that resource, each a sequential `await`.

**A name search is refused, not degraded.**
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/routes/register.py:123` names
`identifier` as the one search parameter the register answers;
`_require_answerable_parameters` raises `UnsupportedSearchParameterError` for
anything else. The module docstring gives the reason, and it is the right reason:
"`family=Smith` answered with the listing is every registered person handed back
as though each were a Smith." A projection does not change that principle. It
changes what the facade is able to answer honestly.

**The CQL engine's data seam is unclaimed.** `DataSource` is a two-method
`typing.Protocol` at
`packages/dhis2w-fhir-engine/src/dhis2w_fhir_engine/engine/cql/context.py:22`:

```python
class DataSource(Protocol):
    """Protocol for CQL data retrieval."""

    def retrieve(self, resource_type: str, context: "CQLContext | None" = None, ...) -> list[dict[str, Any]]: ...
    def resolve_reference(self, reference: str) -> dict[str, Any] | None: ...
```

Every implementation that exists is in-memory: `InMemoryDataSource`,
`BundleDataSource`, `PatientBundleDataSource`, all in
`packages/dhis2w-fhir-engine/src/dhis2w_fhir_engine/r4/datasource.py`. The only
use outside the engine is
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/evaluation.py:234`, which builds
a `BundleDataSource` over a single subject. **Nothing DHIS2-aware implements it.**

Two properties of that Protocol shape everything in section 6. It is
**synchronous**, in a codebase that is `async` throughout - so an implementation
cannot `await` a DHIS2 client inside `retrieve`, and per-patient live retrieval is
not merely slow but structurally awkward. And `MeasureEvaluator.evaluate_population`
(`r4/measure.py:475`) does not fetch a cohort: it takes the patient list from its
caller and loops `evaluate_patient`. **Cohort selection is not the engine's
problem today, and there is nowhere in the Protocol to put it.**

The one worked example proves the point by working around it.
`examples/fhir/engine/e2e_measure_from_dhis2.py` reads one page of twelve tracked
entities in a single `GET`, maps them into one collection `Bundle`, and evaluates
a measure whose `"Initial Population"` is the literal `true` - because the DHIS2
query *is* the initial population and CQL cannot express it. That example already
builds a small materialized projection by hand. This paper generalizes exactly
that.

## 3. The three scenarios, measured

### 3.1 Patient-level evaluation is live, and stays live

One patient, one summary, one `$evaluate` - the facade's existing shape - costs one
subject read and evaluates over a `BundleDataSource` built from it. Measured on
the live stack, a single nested tracked entity read has a **median latency of
0.0943 s** (n=100, p95 0.1087 s), which is the whole cost of the data half of a
patient-level answer.

Nothing in this paper proposes changing that. A patient-level read is correct,
cheap, always current, and enforces DHIS2's own authorization by carrying the
caller's credentials into DHIS2. **Live is the right answer for one patient and
remains the default.** The projection exists for the answers that are not about
one patient.

### 3.2 Population evaluation: the measured wall

**Method.** 300 tracked entities were created in Child Programme, each with one
enrollment and two completed events, taking the register from its 500-person
baseline to 800 people and 1,571 events. Three access shapes were then timed
against that cohort. Repro:

```bash
# Bulk: the shape examples/fhir/engine/e2e_measure_from_dhis2.py uses, paged out.
FIELDS='trackedEntity,orgUnit,attributes[attribute,value],enrollments[enrollment,program,enrolledAt,status,events[event,programStage,occurredAt,status,dataValues[dataElement,value]]]'
time curl -s -g -u admin:district \
  "http://localhost:8080/api/tracker/trackedEntities?program=IpHINAT79UW&ouMode=ACCESSIBLE&fields=$FIELDS&pageSize=200&page=1&order=createdAt:asc" \
  > /dev/null

# Per patient, nested: one read per patient, the shape a DataSource makes natural.
time curl -s -g -u admin:district \
  "http://localhost:8080/api/tracker/trackedEntities/$UID?program=IpHINAT79UW&fields=$FIELDS" > /dev/null

# Per patient, per resource type: Patient, then enrollments, then events.
```

**Measurements.** Loopback, same host, no TLS, warm instance.

| Access shape | Requests per patient | Measured wall | Seconds per patient | Median request latency |
| --- | --- | --- | --- | --- |
| Bulk paged, `pageSize=200`, 800 people | 0.00625 | 0.595 s / 5 pages | 0.00074 | 0.120 s |
| Bulk paged, `pageSize=100`, 800 people | 0.01125 | 0.885 s / 9 pages | 0.00111 | 0.101 s |
| Bulk paged, `pageSize=50`, 800 people | 0.02125 | 1.586 s / 17 pages | 0.00198 | 0.092 s |
| Per patient, nested read (n=100) | 1 | 9.555 s | 0.0955 | 0.0943 s (p95 0.1087) |
| Per patient, one read per resource type (n=100) | 3 | 24.793 s | 0.2479 | 0.0824 s (p95 0.0896) |

The bulk path returned **946 bytes per entity** of DHIS2 JSON (756,672 bytes for
800 people with 1,571 events, five pages).

**Extrapolation - arithmetic, not a measurement, and not a promise.** Multiplying
the measured seconds-per-patient by cohort size, on the same loopback conditions:

| Cohort | Bulk paged (`pageSize=200`) | Per patient, nested | Per patient, per resource type |
| --- | --- | --- | --- |
| 10,000 | ~7.4 s, ~50 pages, ~9.5 MB | ~955 s (~16 min), 10,000 requests | ~2,479 s (~41 min), 30,000 requests |
| 50,000 | ~37 s, ~250 pages, ~47 MB | ~4,775 s (~80 min), 50,000 requests | ~12,393 s (~3 h 27 min), 150,000 requests |

**What this actually shows, stated carefully.** DHIS2's bulk read is *not* the
wall. 47 MB over 250 pages against a national instance is a batch job, not a
crisis. The wall is three-layered, and only the first layer is about seconds:

1. **The request count, once a network exists.** The per-patient shapes cost
   10,000 to 150,000 round trips. On loopback a round trip is free; across a WAN
   at 60 ms it adds 10 to 150 minutes of pure latency to numbers that already
   included none. The count is the durable finding; the seconds are the
   flattering one.
2. **The shape the FHIR side reaches for is the expensive one.** `DataSource` is
   synchronous and per-resource-type; `evaluate_population` loops `evaluate_patient`.
   Nothing in the engine wants a bulk page. Getting the bulk path requires the
   caller to assemble the cohort *outside* CQL and hand it in - which is precisely
   what the one worked example does, with `"Initial Population": true` as the
   admission.
3. **The cost repeats per evaluation.** A live facade holds nothing between
   requests. Ten measures over the same 50,000-person cohort is ten full reads and
   ten full FHIR conversions of ~47 MB of DHIS2 JSON, and `[Condition: code]`
   cannot be pushed down to DHIS2 as a coded query at all - the cohort is fetched
   whole and filtered in process, every time.

A projection collapses all three: the read happens once per sync rather than once
per evaluation, `[Condition: code]` becomes one indexed query, and the request
count against DHIS2 drops to one idle poll per interval (measured in section 3.4
at 56 bytes and 0.081 s).

### 3.3 Multilingual person search: the measured table

**Method.** Seven tracked entities were created in Child Programme carrying first
names in Lao script, Khmer script, and Latin - including one Lao name and one
Khmer name stored **only** in Latin transliteration, the case a real registry
produces when a clerk types what they hear. Then `filter=w75KJ2mc4zz:like:<value>`
was probed thirteen ways. Repro:

```bash
# Create (abbreviated - one of seven):
curl -s -u admin:district -H 'Content-Type: application/json' \
  -X POST 'http://localhost:8080/api/tracker?async=false&importStrategy=CREATE' -d '{
  "trackedEntities": [{"trackedEntityType":"nEenWmSyUEp","orgUnit":"sYJCxNdKHxR",
    "attributes":[{"attribute":"w75KJ2mc4zz","value":"ສົມສັກ"},
                  {"attribute":"zDhUuAYrxNC","value":"ພົມມະຈັນ"}]}]}'

# Probe (URL-encode the value; --data-urlencode does it):
curl -s -G -u admin:district "http://localhost:8080/api/tracker/trackedEntities" \
  --data-urlencode 'program=IpHINAT79UW' --data-urlencode 'ouMode=ACCESSIBLE' \
  --data-urlencode 'filter=w75KJ2mc4zz:like:ສົມ' --data-urlencode 'fields=trackedEntity'
```

**Measurements.** Stored names: `ສົມສັກ` (Lao, "Somsack"), `ສົມພອນ` (Lao,
"Somphone"), `សុភា` (Khmer, "Sophea"), `ដារា` (Khmer, "Dara"), and the Latin-only
records `Somsack`, `Sophea`, `SOMBOUN`.

| Probe | Filter value | Hits | Found | Verdict |
| --- | --- | --- | --- | --- |
| Exact native match, Lao | `ສົມສັກ` | 1 | `ສົມສັກ` | works |
| Native prefix, Lao (2 of 3 syllables) | `ສົມ` | 2 | `ສົມສັກ`, `ສົມພອນ` | works |
| Native interior substring, Lao (no word boundary) | `ມສັກ` | 1 | `ສົມສັກ` | works |
| Exact native match, Khmer | `សុភា` | 1 | `សុភា` | works |
| Native prefix, Khmer | `សុ` | 1 | `សុភា` | works |
| Bare Khmer consonant, no vowel sign | `ស` | 1 | `សុភា` | works |
| Case variance, all lower | `somboun` | 1 | `SOMBOUN` | works |
| Case variance, all upper | `SOPHEA` | 1 | `Sophea` | works |
| NFD-decomposed form of the Lao name | `ສົມສັກ` (NFD) | 1 | `ສົມສັກ` | works |
| **Latin transliteration of a Lao name** | `Somsack` | 1 | `Somsack` only - **not** `ສົມສັກ` | **fails** |
| **Latin transliteration of a Khmer name** | `Sophea` | 1 | `Sophea` only - **not** `សុភា` | **fails** |
| **One-character typo, Latin** | `Somsck` | 0 | nothing | **fails** |
| **One-character typo, Lao (wrong vowel)** | `ສົມສີກ` | 0 | nothing | **fails** |
| **Latin with a diacritic, record stored without** | `Sophéa` | 0 | nothing | **fails** |
| Exact match, `:eq:` operator, Lao | `ສົມສັກ` | 1 | `ສົມສັກ` | works |

**What the table says, in four findings.**

1. **`:like:` is a case-insensitive substring match, and substring is enough for
   unspaced scripts.** The interior-substring and bare-consonant probes both hit.
   This is better than expected: Lao and Khmer write without spaces, and a
   tokenizing search engine that segments them badly would do *worse* than
   substring. Any index that replaces `:like:` must not regress this.
2. **Script is a wall.** `Somsack` cannot find `ສົມສັກ` and `ສົມສັກ` cannot find
   `Somsack`. A register where some clerks typed native script and some typed what
   they heard is, today, two disjoint registers that no single query spans. This
   is the finding that most directly costs a real deployment a person.
3. **There is no fuzziness in either script.** One dropped character returns
   nothing. One wrong Lao vowel returns nothing. One French diacritic on a name
   stored without it returns nothing. A registry clerk gets exactly one chance to
   spell it the way it was stored.
4. **Unicode normalization is not a problem.** NFD and NFC forms of the Lao name
   both matched, so the store is normalizing or the forms coincide. Nothing here
   needs solving.

Findings 2 and 3 are not DHIS2 defects. `:like:` is a SQL `LIKE`, and a SQL `LIKE`
behaving like a SQL `LIKE` is not a bug. They are the precise statement of what a
name search needs that a database predicate cannot give it: **an analysis chain -
ICU transliteration, folding, and n-grams - applied at index time, to both the
stored name and the query.**

And the facade cannot even reach `:like:` today: the register answers `identifier`
alone (section 2). So the honest description of person search in the facade right
now is *not implemented*, and the projection is what makes implementing it
honest rather than misleading.

### 3.4 Sync and deletion: what a cursor can and cannot learn

**Method.** One of the seven entities above was deleted with
`importStrategy=DELETE`, with the server clock captured immediately before the
delete as a cursor. Six probes then asked whether a `lastUpdated`-style poll can
learn of the removal. Repro:

```bash
CURSOR=$(curl -s -u admin:district http://localhost:8080/api/system/info | python3 -c 'import json,sys;print(json.load(sys.stdin)["serverDate"][:19])')
curl -s -u admin:district -H 'Content-Type: application/json' \
  -X POST 'http://localhost:8080/api/tracker?async=false&importStrategy=DELETE' \
  -d '{"trackedEntities":[{"trackedEntity":"'"$UID"'"}]}'

# The poll a syncer would run:
curl -s -g -u admin:district \
  "http://localhost:8080/api/tracker/trackedEntities?program=IpHINAT79UW&ouMode=ACCESSIBLE&updatedAfter=$CURSOR&includeDeleted=true&fields=trackedEntity,deleted,updatedAt"
```

**Measurements.**

| Probe | Result |
| --- | --- |
| Cursor poll, `updatedAfter` only | 0 rows - the deletion is **invisible** |
| Cursor poll, `updatedAfter` + `includeDeleted=true` | 1 row: `{"trackedEntity":"SE8R7XpX34l","updatedAt":"2026-08-21T16:42:43.310","deleted":true}` |
| Same, scoped by `trackedEntityType` instead of `program` | 1 row, identical tombstone |
| `/api/tracker/enrollments`, cursor + `includeDeleted=true` | 1 row, the cascaded enrollment, `deleted: true` |
| `/api/tracker/enrollments`, cursor only | 0 rows |
| `/api/tracker/events`, cursor + `includeDeleted=true` | 0 rows (this entity had no events) |
| `GET /api/tracker/trackedEntities/{uid}` | **404 E1005**, "could not be found" |
| `GET /api/tracker/trackedEntities/{uid}?includeDeleted=true` | **404 E1005** - the flag has no effect on the single-resource route |
| Collection with `trackedEntities={uid}&includeDeleted=true` | 1 row, the tombstone |
| Collection with `trackedEntity={uid}` (singular) | **50 rows** - the parameter is silently ignored |
| Idle poll, cursor = now, no changes | 0 rows, **56 bytes, 0.081 s median** (n=5) |

**Four findings, one of them good news.**

1. **Deletions are incrementally discoverable, and a cursor sync therefore works.**
   `updatedAfter` plus `includeDeleted=true` returns a tombstone carrying
   `deleted: true` and a fresh `updatedAt`. This was the measurement most likely
   to sink the whole design, and it did not. The syncer polls with
   `includeDeleted=true` always, and treats `deleted: true` as a delete.
2. **`includeDeleted=true` is mandatory, and its absence is silent.** A syncer
   that forgets it does not error - it simply never learns that anyone left. That
   is the single most dangerous line in a sync implementation, and it must be a
   constant, not a parameter.
3. **A tombstone is enumerable but not readable.** The collection route returns it;
   `GET /api/tracker/trackedEntities/{uid}` answers 404 E1005 even with
   `includeDeleted=true`. So a syncer can learn *that* an entity is gone and never
   *what it was* - which is fine for a projection (delete the row) and fatal for
   anything trying to archive a final state at deletion time. Recorded as
   **BUGS.md #99**. It compounds with the already-recorded BUGS.md #90: an
   attribute-filtered search drops soft-deleted rows even with
   `includeDeleted=true`, so a deleted person is unfindable by name as well as
   unreadable by UID.
4. **The singular `trackedEntity=` parameter is silently ignored**, returning a
   full unscoped page where the caller asked for one entity. The tracker
   collection endpoint ignores unknown query parameters generally - a garbage
   parameter name behaves identically - and the endpoint's own `E1003` message
   names `trackedEntities`, plural. A UID-scoped read that silently becomes an
   unscoped page is a data-disclosure shape, not just a wrong answer. Recorded as
   **BUGS.md #98**, same family as the already-recorded #91.

**The cost of staying current is negligible.** An idle incremental poll is one
request, 56 bytes, 0.081 s. Against a national instance polling every five
minutes, that is 288 requests a day to learn that nothing changed - versus the
50,000-request full read that a live facade performs *per evaluation*. The
economics of the sync are not close.

### 3.5 Cleanup, verified

Every entity created for sections 3.2 to 3.4 was deleted with
`importStrategy=DELETE` and the baseline re-verified:

```
marked entities found: 300
  delete batch: OK {'deleted': 100}   (x3)
marker search (last name Zzprojpaper) -> 0
marker search (first name Cohort*)    -> 0
like:'ສົມສັກ' -> 0    like:'ສົມພອນ' -> 0    like:'សុភា' -> 0    like:'ដារា' -> 0
like:'Somsack' -> 0   like:'Sophea' -> 0    like:'SOMBOUN' -> 0
register count now: 500        enrollments total: 500        events total: 971
```

500 / 500 / 971 are the pre-measurement baseline figures, re-read after teardown.

## 4. The doctrine

The repo already holds a storage position, and it is the right one. From
[`docs/fhir/201-serve.md`](../201-serve.md), *Stored responses are receipts*:

> DHIS2 remains the system of record; a receipt is evidence of a submission, not a
> view of data.

And from `docs/decisions.md`, 2026-08-08:

> `GET /QuestionnaireResponse/{id}` returns the submission exactly as it arrived,
> stamped with the id it is served under. It is never a projection of what DHIS2
> currently holds.

The projection extends that position rather than qualifying it. Seven rules.

**D1 - DHIS2 is the record for everything DHIS2 can hold.** Not "mostly". Not
"except for performance". If a fact can live in a tracked entity, an enrollment, an
event, or a data value, then DHIS2 holds it and the projection holds a copy.

**D2 - The projection is derived, and its derivation is the only thing that writes
it.** No API writes to it. No operator writes to it. No repair script writes to it.
A projection row that disagrees with DHIS2 is a sync defect, and the fix is a
resync, never an edit.

**D3 - The projection is rebuildable from zero, and rebuild is a routine operation
rather than a disaster recovery step.** If a rebuild is frightening, the projection
has become a record and D1 has been broken. Rebuild is how a mapping change ships.

**D4 - Every row is cursor-stamped, and every answer served from the projection
states its cursor.** A projection answer is always "as of `<instant>`", never
"now". A client that cannot tolerate staleness reads live; the facade's job is to
make the difference visible, not to paper over it.

**D5 - Writes travel only through the spool.** A capture goes to the spool, the
forwarder sends it to DHIS2, DHIS2 accepts or refuses it, and the sync brings it
back. **A captured value therefore appears in the synced server one sync interval
after DHIS2 accepted it, not when the client submitted it.** That is a real,
user-visible latency and this design states it rather than hiding it behind a
write-through shortcut. A write-through would make the projection a record on the
write path, and D1 and D2 would both be gone. The compensations are honest ones:
the receipt is readable from the spool immediately (which is what the spool is
for), and a forward can trigger a targeted sync of the entities it touched so the
interval is bounded by the forward rather than by the poll.

**D6 - The projection is not a second API.** It changes what the facade can answer
and how fast. It does not add resource types, endpoints, or semantics that the
live mode lacks. A client should not be able to tell which mode it is talking to,
except by reading the cursor.

**D7 - The one carve-out: attested documents.** A signed IPS handed to a patient is
not derived. Regenerating it produces a different document - a different
`Bundle.timestamp`, a different `Composition.date`, and, the moment DHIS2 has moved
on, different content - and if it carried a signature, the signature no longer
verifies. R4 in [the IPS paper](ips.md) buys byte-identical regeneration *apart
from* those two timestamps, which is exactly the margin a signature does not
tolerate. So an attested document is a **first-class stored artifact**, not a
projection row: small in volume (one per hand-off, not one per person per read),
immutable, doctrinally distinct, and outside the rebuild. This is the same
distinction `docs/decisions.md` drew for the spool - "this is not state, it is
artifact persistence" - applied to the output side. Where those artifacts live is
a reserved decision (section 11).

## 5. The product mode: a FHIR server that syncs

Stated as the owner states it: **start up a FHIR server with a proper backend,
then sync it with a DHIS2 instance - initial first, then updates based on time.**

### 5.1 The two commands

`d2w fhir sync` fills and maintains the projection.

- **Initial materialization.** Walk the mapped scope - the tracked entity types
  `[serve.tracked_entities]` publishes, their enrollments and events - bulk-paged
  the way section 3.2 measured, converting each page to FHIR and writing it. At
  50,000 people this is ~250 pages and ~47 MB of DHIS2 JSON; it is a batch job with
  a progress bar, and it is the *only* place the population-scale read cost is
  paid.
- **Incremental runs.** Poll each tracker collection with `updatedAfter=<cursor>`
  and `includeDeleted=true`, apply creates, updates, and tombstones, then advance
  the cursor. Measured idle cost: one request, 56 bytes, 0.081 s.
- **Full rebuild, always available.** `d2w fhir sync --rebuild` drops and refills.
  Per D3 this is routine, and it is how a `fhir.toml` mapping change reaches the
  projection.

`d2w fhir serve` gains a synced posture: given a configured backend, the register,
search, and evaluation read from the projection instead of from DHIS2, and every
response carries the projection's cursor.

### 5.2 The cursor, and the three things that make it correct

The cursor is a **watermark**, and it is the first genuinely stateful thing on the
FHIR side of this repo. `ListingCursor` and `SpoolCursor` are deliberately
stateless position tokens
(`register/listing.py:76`, `spool.py:209`); this is not one of those, and calling
it a cursor should not blur that.

1. **It advances only after the documents it describes are durable.** The sync
   writes the batch and the new watermark in one transaction, or it does not
   advance. A watermark ahead of the data is silent permanent data loss - the rows
   in the gap are never polled again. This is the single strongest argument in the
   backend comparison (section 8).
2. **It overlaps.** `updatedAfter` boundary semantics, clock skew between the
   syncer's host and DHIS2's, and in-flight transactions at the instant of the poll
   all conspire to drop rows at the edge. The syncer re-polls from
   `watermark - overlap` and relies on writes being idempotent by resource id.
   The overlap window is a configured duration, not a constant discovered by
   incident.
3. **It is per-endpoint.** Tracked entities, enrollments, and events each carry
   their own watermark, because section 3.4 measured them as three independent
   polls with independent tombstone behaviour. A single global cursor would be a
   guess about which endpoint's clock leads.

### 5.3 What sync does not do

It does not reconcile. A sync that diffs the projection against DHIS2 to find rows
it missed is a sync that has been given the job of being right *without* being
correct, and the honest version of that operation is `--rebuild`. It does not
write to DHIS2 - that is the forwarder's job and it stays the forwarder's job. And
it does not run inside the server process by default; a sync that shares a process
with the request path is a sync whose backlog becomes a latency spike.

## 6. Authorization for projection-served data

This is the part of the design that is *harder*, not easier, in the synced mode,
and it is the reason section 9 recommends starting narrow.

**What the live mode gets for free.** Today the facade holds a `Dhis2Client`
carrying the operator's credentials and every register read is a DHIS2 request. So
DHIS2's sharing ACLs, organisation unit scopes, and tracker ownership rules
enforce themselves, in DHIS2, on every read - the facade never implements them
because it never has to. (`wire.py` uses `ouMode=ACCESSIBLE` precisely to let
DHIS2 decide.) **A projection takes DHIS2 out of the request path, and that
enforcement goes with it.** A synced server that serves a person's record has, by
construction, already decided that the caller may see it.

Four honest options. There is no fifth that avoids the choice.

| Option | What it is | What it costs |
| --- | --- | --- |
| **(i) Materialize sharing, evaluate facade-side** | Sync sharing metadata, organisation unit trees, and ownership alongside the data; re-implement DHIS2's access rules over the projection | Reimplementation risk, and the failure mode is silent over-disclosure. DHIS2's tracker ownership rules are subtle, versioned, and not fully specified in the API; a faithful re-implementation is a permanent maintenance liability that must track three majors |
| **(ii) Scope a projection to one audience at build time** | One projection per user group or per organisation unit subtree - authorization by construction, because the projection contains only what its audience may see | N projections, N syncs, N rebuilds; re-scoping means rebuilding; cross-audience queries are impossible by design (which is sometimes the point) |
| **(iii) Restrict the projection to non-sensitive artifacts** | Aggregate values, de-identified cohorts, and a name-search index that returns **only identifiers**; every person-level read stays live and caller-credentialed | Gives up projection-served person-level reads. Does **not** give up the three scenarios this paper is about |
| **(iv) Coarse scopes over a trusted-service posture** | The projection serves a service account within a trust boundary; a coarse scope (one programme, one region) bounds the blast radius | Depends on the deployment being genuinely closed. Honest for an internal analytics service, dishonest for anything a browser reaches |

**Recommended starting posture: (iii).** The reason is specific rather than
cautious: **the `NameSearchIndex` can do its whole job while disclosing nothing.**
A search returns a list of DHIS2 UIDs and a relevance ordering. Resolving any of
those UIDs into a record goes through the **live, caller-credentialed path** -
`fetch_tracked_entity` as it exists today - which means DHIS2 decides, per UID, per
caller, exactly as it does now. A caller who may not see a person gets a 404 from
DHIS2 on resolution and learns nothing from the search but that some identifier
exists. The multilingual search problem, which is the sharpest of the three
scenarios, is therefore solvable **without** taking on any authorization
liability at all.

The same posture covers population evaluation: a `MeasureReport` is a count. It
discloses aggregate structure, not people, and the initial-population membership
never leaves the server. Attested documents (D7) are likewise addressed by a
capability the recipient already holds, not browsed.

What (iii) gives up is a projection-served `GET /Patient/{uid}` - the very thing a
"proper FHIR backend" most obviously suggests. That is a real cost and it is the
reason the (i)-versus-(ii) choice is reserved rather than settled: the moment a
deployment wants person-level FHIR reads served from the backend, one of those two
must be built, and they are very different projects. (ii) is the smaller and safer
one and this paper's instinct; (i) is the one that scales to a multi-tenant
national deployment. A parallel comparison is being produced separately.

**One rule regardless of which option wins.** The projection stores what a
configured *build* identity could read, and the facade must never let a caller's
own identity imply more than that. A synced answer states its cursor (D4) and its
scope; a scope that is not stated will be assumed to be "everything".

## 7. The seams

Four, matched to what already exists. Every one follows the `AuthProvider` pattern
(`packages/dhis2w-client/src/dhis2w_client/v43/auth/base.py`): a `Protocol` in its
own `base.py`, frozen-pydantic implementations one per file beside it, a
`build_x(config) -> X` factory dispatching on a `Literal` config field.

### 7.1 `ProjectionStore`

The durable document backend, in the serve layer. Async, because everything in
serve is:

```python
@runtime_checkable
class ProjectionStore(Protocol):
    """Holds the FHIR projection of a DHIS2 instance, written only by sync."""

    async def read(self, resource_type: str, resource_id: str) -> ProjectedResource | None: ...
    async def search(self, query: ProjectionQuery) -> ProjectionPage: ...
    async def write(self, batch: ProjectionBatch) -> ProjectionCursor: ...
    async def cursor(self) -> ProjectionCursor: ...
    async def rebuild(self) -> None: ...
```

`ProjectedResource`, `ProjectionQuery`, `ProjectionPage`, `ProjectionBatch`, and
`ProjectionCursor` are all `BaseModel`s per rule 7. `ProjectedResource.body` is a
`dict[str, Any]` holding the FHIR document verbatim, following the precedent
`docs/decisions.md` set for `StoreEntry.body`: the store parses just enough to
index and passes the rest through untouched.

`write` returning the cursor rather than taking it is deliberate - it makes "the
watermark advances with the batch" a property of the signature rather than a
convention the caller has to honour (section 5.2, rule 1).

### 7.2 `NameSearchIndex`

Separate from `ProjectionStore` because it is separately adoptable, separately
backed, and - per section 6 - separately *safe*. It returns identifiers, not
records.

```python
@runtime_checkable
class NameSearchIndex(Protocol):
    """Finds candidate tracked entity identifiers by name, across scripts."""

    async def index(self, entries: Sequence[IndexedName]) -> None: ...
    async def find(self, query: NameQuery) -> NameMatches: ...
    async def forget(self, uids: Sequence[str]) -> None: ...
```

`NameMatches` carries `tuple[NameMatch, ...]` where a `NameMatch` is a DHIS2 UID
plus a score plus the cursor the index was built at - and nothing else. No name, no
attribute value, no organisation unit. That is what makes the (iii) posture
tight rather than aspirational.

**The `dhis2` backend goes first and improves nothing.** It implements `find` by
calling the `:like:` filter section 3.3 measured - so it is exactly as weak as
today, with exactly today's authorization properties. Its entire value is that it
proves the seam: once `find` is the only path person search takes, swapping the
backend is a config line rather than a refactor.

### 7.3 `ProjectionDataSource`

Implements the engine's existing `DataSource` protocol
(`dhis2w_fhir_engine.engine.cql.context:22`), and **lives in the serve layer, never
in the engine**. `examples/fhir/engine/e2e_measure_from_dhis2.py` ends with the
invariant that must not break:

> The engine imported no DHIS2 module. Everything above the Bundle is this file's
> work; everything below it is FHIRPath, CQL, and a MeasureReport.

This is what turns `[Condition: code]` from "fetch the cohort and filter in
process" into one indexed query: `retrieve(resource_type="Condition", codes=[...])`
becomes a predicate the backend evaluates.

**The synchronous-Protocol constraint is real and must be designed for, not
discovered.** `DataSource.retrieve` is sync; a projection read is I/O. Three ways
out, in preference order:

1. **Pre-load per evaluation.** The population flow resolves the cohort and its
   in-scope resources into memory once, then evaluates over an in-memory
   `DataSource`. This is what the example does by hand, and the projection makes
   the pre-load cheap and indexed instead of a 50,000-request crawl. It requires
   no change to the engine and no async Protocol.
2. **A sync driver on the projection connection**, used only inside `retrieve`,
   from a worker thread. Correct, and it puts a blocking call one `asyncio.to_thread`
   away from the request path.
3. **An async `DataSource` protocol in the engine.** Cleanest and largest; it
   changes a published Protocol and every implementation. Not first.

Recommendation: **(1)**, with the cohort resolution being the new work and the
engine untouched.

### 7.4 The `[serve.search]` dial

Following `TrackedEntitiesConfig` (`packages/dhis2w-fhir/src/dhis2w_fhir/config.py:259`) -
frozen, `extra="forbid"`, defaults that mean "behave as today":

```toml
[serve.search]
backend = "dhis2"        # "dhis2" | "index"
transliterate = true     # index backends only
```

`backend = "dhis2"` is the default and is exactly today's behaviour. Per the
`ServeSettings` rule that a key changing `/metadata` gets no CLI flag, this table
has no flag: which searches the register answers is the server's contract, not a
property of one invocation.

### 7.5 Transliteration is an index-time fact

Finding 2 of section 3.3 - `Somsack` cannot find `ສົມສັກ` - is closed by
**ICU transliteration applied at index time to both the stored name and the
query**, producing a Latin key alongside the native one. `ສົມສັກ` indexes as
`ສົມສັກ` *and* `somsak`; the query `Somsack` transliterates to `somsack` and
n-gram-matches `somsak`, closing findings 2 and 3 in one mechanism.

Three rules keep it honest. **The transliteration is never displayed** - it is a
search key, and showing a person a machine romanization of their own name is a
copy defect. **The native form is never replaced**, only accompanied. And
**substring behaviour must not regress**: the measured wins in section 3.3 - the
interior substring, the bare Khmer consonant - come from `LIKE` semantics that a
word-tokenizing analyzer would lose. Character n-grams over the unspaced scripts,
not word tokens.

## 8. Backends: the deployment postures and the argument

### 8.1 Three postures, one product

The tier framing survives the reframe as **deployment postures**. The synced
server is the headline; live-only remains the zero-ops default.

| Posture | What it is | Ops cost | Default? |
| --- | --- | --- | --- |
| **Live** | Today: register read per request, `BundleDataSource` per subject, store on disk, spool as files | None. One process, no services | **Yes, forever** |
| **Embedded** | Derived indexes with no service: a SQLite index over the spool, DuckDB over the projection's JSON for analytic reads | One file. `make install` and nothing else | Opt-in |
| **Synced** | The product mode: a document backend plus a search index, filled by `d2w fhir sync` | Real services, real operations | Opt-in, backend client an optional extra |

The **Live** posture is not a lesser product. It is the correct answer for a
country that wants a FHIR facade over one district's tracker, and it is the only
posture that needs no operator. Nothing in the synced mode may make it harder to
run, and no default may move.

The **Embedded** posture matters more than it looks. CLAUDE.md rule 10 mandates
SQLAlchemy + SQLite for state and even pre-names `.dhis2/cache.sqlite`. A
projection is *state* - derived, mutable, queried by predicate - which is
precisely the side of the line `docs/decisions.md` drew twice when it kept the
spool as files on the grounds that receipts are immutable artifacts. So a SQLite
`ProjectionStore` is not an odd fit for this repo; it is the rule's default, and it
should exist as the reference implementation of the Protocol whether or not anyone
runs it in production.

### 8.2 R1's backend: PostgreSQL with `jsonb`, OpenSearch beside it

**PostgreSQL is the document store. OpenSearch is the search index. The projection
rebuilds the index from the store; the store never rebuilds from the index.**

The argument, in the order the arguments actually weigh:

**The cursor needs a transaction, and OpenSearch has none.** Section 5.2 rule 1
says the watermark advances only when the batch it describes is durable, because a
watermark ahead of its data is silent, permanent, undetectable data loss. In
PostgreSQL that is one `COMMIT` covering both. In OpenSearch it is two writes, a
`refresh` interval between indexing and visibility, and a hand-rolled protocol for
the window in between. Every distributed-systems bug this design could have lives
in that window, and Postgres deletes the window rather than managing it.

**"Rebuildable from zero" needs something to rebuild *from*.** D3 makes rebuild
routine. A search index is a derived artifact by nature and should be reproducible
from a durable source. If OpenSearch is also the durable source, then a rebuild is
a re-fetch of the entire DHIS2 instance - the 250-page, 47-MB batch job - rather
than a reindex from local storage. Splitting them makes a mapping change or an
analyzer change cheap: reindex from Postgres, never touch DHIS2.

**Ops.** Every ministry-adjacent deployment this toolchain will meet already runs
PostgreSQL, because DHIS2 does. Backup, restore, point-in-time recovery, and
monitoring are solved and staffed. The marginal operational ask is a schema in an
existing engine, not a new class of system.

**Fit with the repo.** Rule 10 already mandates SQLAlchemy. The same `Mapped[...]`
models and the same Alembic migrations serve SQLite in the Embedded posture and
PostgreSQL in the Synced one, so the reference implementation and the production
implementation are one code path with two URLs. Rule 10's "No Postgres" is written
for profile-local state living beside `.dhis2/`; a shared, multi-consumer,
population-scale document store is a different object, and the reserved decision in
section 11 is the right place to confirm that reading.

**Why OpenSearch is still there and is not optional for search.** Section 3.3
measured what person search needs: ICU transliteration, folding, fuzziness, and
character n-grams over unspaced scripts, applied at index time. `pg_trgm` gives
character trigrams and similarity scoring, which is genuinely serviceable and is
the fallback - but ICU transliteration becomes an application-side preprocessing
step, fuzziness becomes a similarity threshold to tune by hand, and the analyzer
chain becomes bespoke SQL. OpenSearch has all of it as a configured analyzer,
Apache-2.0, and it is the only credible Lao and Khmer search backing in the
comparison. So: **Postgres alone is a complete and honest deployment with weaker
search; adding OpenSearch is what makes finding `ສົມສັກ` from `Somsack` a
configuration rather than a project.**

### 8.3 The documented alternative: OpenSearch alone

One service instead of two, carrying document store, search, and retrieve
together. This is a real option and it wins outright in one stated case: **when
search *is* the workload** - a facility-facing person-lookup service where the
projection exists to find people, person-level reads resolve live under caller
credentials per section 6(iii), and the "document store" is therefore only the
search index with fields attached. In that shape the second service earns nothing,
the transactional-cursor argument shrinks to "keep the watermark in a small SQLite
file beside the syncer", and the operational saving is genuine.

It loses when the projection is asked to be a FHIR server's storage - which is the
framing of this paper - because then the cursor guards data nothing else holds.

### 8.4 MongoDB: no role

It would be a document store with weaker transactional guarantees than PostgreSQL
and weaker search than OpenSearch, chosen for a JSON-shaped-data argument that
`jsonb` already answers, under a licence (SSPL) that this workspace's Apache-2.0
and BSD dependencies have no reason to invite.

## 9. Recommendations

R1 to R11, independently adoptable. Adopting R2 to R5 without R1 is a coherent
position; adopting R1 without R2 is not.

**R1 - PostgreSQL with `jsonb` is the document store; OpenSearch is the search
index beside it.** The store holds the projection and the watermark, and advances
them in one transaction. The index is derived from the store and rebuildable from
it without touching DHIS2. Postgres alone is a complete deployment with `pg_trgm`
search; OpenSearch alone is the documented alternative and wins when search is the
entire workload (8.3). Both arrive behind an optional extra; neither is ever
required to run the facade.

**R2 - The projection is derived and the sync is its only writer.** No API, no
operator, no repair script writes a projection row. A row that disagrees with
DHIS2 is a sync defect and the fix is a resync. This is D1 and D2, and it is what
keeps the backend from quietly becoming a second system of record.

**R3 - Every projection-served answer states its cursor.** "As of `<instant>`",
carried in the response, not inferred from a header nobody reads. A `MeasureReport`
computed over a projection says which instant it counted; a search result says
which instant it indexed. How, exactly, is reserved (section 11).

**R4 - The capture loop is unchanged, and its latency is stated.** Spool, forward,
DHIS2, sync, projection. A captured value appears in the synced server one sync
interval after DHIS2 accepted it; the receipt is readable from the spool
immediately, and a forward may trigger a targeted sync of the entities it touched.
No write-through, ever.

**R5 - Two Protocols in the serve layer, `dhis2`-backed first.** `ProjectionStore`
and `NameSearchIndex`, shaped like `AuthProvider`, selected by a `Literal` config
field. The `dhis2` backend of `NameSearchIndex` improves nothing and is built
first, because a seam nothing has crossed is not a seam.

**R6 - `ProjectionDataSource` implements the engine's existing `DataSource`, in the
serve layer.** No DHIS2 module is imported by `dhis2w-fhir-engine`, then or ever.
The synchronous Protocol is satisfied by resolving the cohort ahead of evaluation
(7.3 option 1), not by changing the engine.

**R7 - Search is a dial, not a rewrite.** `[serve.search] backend = "dhis2" |
"index"`, frozen and `extra="forbid"`, defaulting to `dhis2` - today's behaviour,
byte for byte. No CLI flag, because it changes what `/metadata` declares.

**R8 - Transliteration is an index-time fact.** ICU transliteration produces a
Latin search key alongside the native form. The key is never displayed, the native
form is never replaced, and character n-grams - not word tokens - preserve the
substring and bare-consonant matches section 3.3 measured on unspaced scripts.

**R9 - Authorization by construction: the tier-2 starting posture serves only
non-sensitive artifacts.** Aggregate values, de-identified cohorts, and a name
index that returns identifiers and scores and nothing else. Resolving a match into
a record goes through the live, caller-credentialed path, so DHIS2 decides per UID
per caller exactly as it does now. Person-level projection-served reads wait for a
decided answer to (i)-versus-(ii).

**R10 - Deletions are synced from the tombstone poll, and `includeDeleted=true` is
a constant.** Every incremental poll carries it; it is never a parameter and never
a default someone can turn off, because its absence is silent (finding 2 of
section 3.4). A tombstone is enumerable but not readable (BUGS.md #99), so a
deletion means "remove the row", never "archive the final state".

**R11 - The live posture stays the default and stays zero-ops.** No new required
service, no new required config key, no behaviour change to a facade started
without a backend. The synced mode is something an operator opts into by
configuring a backend, and its absence is not a degraded mode - it is the product.

## 10. The PR sequence

Ten steps, each green on its own, each shippable without the next. The first three
change no behaviour at all.

1. **The Protocols, and the `dhis2` backend of `NameSearchIndex`.** `ProjectionStore`
   and `NameSearchIndex` in `dhis2w-fhir-serve`, their models, and one
   implementation: `Dhis2NameSearchIndex`, calling the `:like:` filter section 3.3
   measured. Route the register's existing lookups through it. **Improves nothing.
   Proves the seam.** Tests assert the measured behaviour of section 3.3 - including
   that `Somsack` does not find `ສົມສັກ` - so the weakness is characterized, not
   assumed.
2. **`[serve.search]`, defaulting to `dhis2`.** The config table, frozen and
   `extra="forbid"`, with `backend = "index"` refused with a typed `ServeError`
   naming the extra to install. Zero behaviour change, and the refusal message is
   the feature.
3. **The SQLite `ProjectionStore`.** SQLAlchemy + `aiosqlite` per rule 10,
   `Mapped[...]` columns, Alembic migration, the watermark in the same transaction
   as the batch. Reference implementation of the Protocol; the Embedded posture's
   whole backend; the thing every later test runs against. **Shipped** -
   `dhis2w_fhir_serve.projection.schema` and `.sqlite_store`, selected by
   `[serve.projection] store = "sqlite"`.
4. **`d2w fhir sync`, incremental and full, against the SQLite store.** The
   watermark, the overlap window, the per-endpoint cursors, `includeDeleted=true` as
   a constant, `--rebuild`. Ends with a CLI example under `examples/fhir/cli/` and
   an entry in `docs/project/features.md`. **Shipped** -
   `dhis2w_fhir_serve.projection.sync`, `d2w fhir sync`, `examples/fhir/cli/sync.sh`.
5. **Serve from the projection, cursor stated.** `GET /{RegisterType}/{uid}` and
   the listing answered from `ProjectionStore` when one is configured, each
   response carrying its cursor. The live path stays the default and stays tested.
   **Shipped** - `[serve.search] backend = "projection"`, and section 10.1 states
   where it came out narrower than this line reads.
6. **The OpenSearch `NameSearchIndex`, behind an extra.** ICU transliteration in
   the analyzer, character n-grams, fuzziness. `[serve.search] backend = "index"`
   becomes real. The extra follows the `[browser]` / `[serve]` pattern - pinned
   workspace dependency, `ImportError` caught into a message naming both install
   paths. The section 3.3 probe table becomes the test suite, with the four failing
   rows flipped.
7. **The PostgreSQL `ProjectionStore`.** Same SQLAlchemy models, different URL,
   `jsonb` column type, `pg_trgm` as the no-OpenSearch search fallback. Nothing
   above the Protocol changes.
8. **`ProjectionDataSource`.** Implements the engine's `DataSource` over
   `ProjectionStore`, in the serve layer, with the cohort resolved ahead of
   evaluation. `[Condition: code]` becomes one indexed query. The e2e measure
   example gains a projection-backed sibling.
9. **The population-evaluation flow.** Cohort selection expressed against the
   projection, `evaluate_population` fed from it, `MeasureReport` stamped with the
   cursor. This is the step section 3.2 exists to justify, and it is deliberately
   last of the functional steps.
10. **The measured comparison, published.** Re-run section 3.2 and 3.3 against a
    projection-backed facade and put both columns in this page. The paper's own
    numbers become its regression test.

Steps 1 to 5 are the smallest coherent slice: they land a synced FHIR server with
no new service, on SQLite, with today's search. Steps 6 and 7 are the "proper
backend". Steps 8 and 9 are population evaluation.

### 10.1 What steps 3 to 5 shipped as, where it differs from what was proposed

Six differences, each one a thing this paper proposed and the code decided
otherwise about. They are here rather than in a commit message because the paper
is what the next step will be read against.

**The search dial gained `projection`, not `index`.** Section 7.4 wrote the dial
as `"dhis2" | "index"` and reserved `index` for OpenSearch. A projection-backed
search is a different thing from a search-engine-backed one - different backend,
different guarantees, different install - so it took its own word.
`[serve.search] backend = "projection"` names the store that answers it and
`[serve.projection] store` names where that store is; `index` stays reserved for
step 6, and the file still refuses it by name.

**There are two watermarks, not three.** Section 5.2 rule 3 argued for one per
endpoint and named tracked entities, enrollments, and events. Events are not
polled: a projected register resource carries identity and attribute values
(`register.projection`), an event carries neither, so an event that moved is not a
change to anything the projection holds, and a poll for one would be a request per
interval spent to learn nothing. `ProjectionEndpoint` has two members, and the
third arrives with the resources that need it at steps 8 and 9.

**The enrollment poll is scoped by programme, because the endpoint admits nothing
else.** `/api/tracker/enrollments` answers `E1003 "Program is mandatory"` to a
query naming a tracked entity type or naming nothing at all, so the poll walks the
programmes the guide publishes rather than the types the register serves. Its
sibling `/api/tracker/events` refuses the same shape with an HTML error page
rather than JSON. Both recorded as **BUGS.md 102**.

**The watermark advances after its walk rather than inside it.** Rule 1 says the
batch and the watermark land in one transaction, and `ProjectionStore.write` still
offers exactly that. But a walk pages by `createdAt` - `updatedAt` is the column
the filter moves, and paging by it drops rows - so a later page can carry an
earlier `updatedAt`, and no page knows the watermark. Each page is written as its
own batch and the walk is closed by a batch carrying the new watermark once every
row it describes is durable. That is rule 1 in the direction that matters: behind
its data costs a re-read, ahead of it is silent loss.

**There is no migration, and that is the design.** Step 3 asked for an Alembic
migration. D3 makes rebuilding routine rather than a recovery step, so the way a
schema change reaches a projection is `d2w fhir sync --rebuild`: the tables are
created when absent, and a projection whose shape has moved on is refilled from
the instance that is the record for all of it. A migration would be machinery for
carrying forward a copy that is cheaper to make again.

**Step 5 shipped at the R9(iii) boundary, and the boundary is at the response
rather than at the row.** Step 5's line reads as though `GET /{RegisterType}/{uid}`
is answered out of the store. Section 6 recommends posture (iii), under which every
person-level read stays live and caller-credentialed, and (iii) is what shipped:
the projection decides the membership of a searchset, its paging, and its
`_content` answer, and every record on the page is read from the instance under the
credentials of whoever asked. A read of one entity by its id is a person-level read
and is answered live whatever the backend says. A projection-served searchset also
states **no `total`** - the projection counted under the identity the sync ran as,
and telling a caller scoped to one district how large the national register is
would be a disclosure nothing authorized. Both are reversible the day
(i)-versus-(ii) is decided, and neither is reversible by accident.

**And one thing section 11 reserved is now answered.** "How projection freshness
reaches a client" is an `outcome` entry in the searchset - R4 3.1.1.4's own
mechanism for a server to say something about a search inside the search's answer,
which no client has to be told about to read - plus an `X-DHIS2W-Projection-As-Of`
header beside it. `Bundle.meta.lastUpdated` was the alternative and was not taken:
it would say when the Bundle changed, and a searchset assembled this second out of
rows read yesterday has those as two different instants.

## 11. Owner decisions this paper reserves

- **The tier-2 default backend.** Section 8 recommends PostgreSQL plus OpenSearch
  and argues OpenSearch-alone as the alternative that wins when search is the
  entire workload. The call includes whether CLAUDE.md rule 10's "No Postgres" is
  read as scoped to profile-local state - which is how section 8.2 reads it - or as
  absolute, in which case the Synced posture is SQLite plus OpenSearch and the
  transactional-cursor argument gets a different answer.
- **Where the synced mode lives.** Inside `dhis2w-fhir-serve` behind a
  `[projection]` extra, or as a new workspace member `dhis2w-fhir-sync`. The
  argument for a new member is that a sync is a batch process with a different
  dependency set and a different operational lifetime than a server, and section
  5.3 says it should not share a process. The argument against is that it needs the
  same conversion layer, the same config model, and the same Protocols, and a
  twelfth member is not free.
- **Authorization: (i) versus (ii).** Section 6 recommends (iii) as the starting
  posture and that recommendation does not need this call. But the moment a
  deployment wants person-level FHIR reads served from the backend, either sharing
  metadata is materialized and DHIS2's rules re-implemented facade-side, or a
  projection is scoped to one audience at build time. They are different projects
  with different failure modes, and a parallel comparison is in progress.
- **The attested-documents store.** D7 makes a signed IPS a first-class stored
  artifact outside the projection. Whether it lives beside the spool as files -
  which is what `docs/decisions.md` decided twice for artifact persistence, and the
  volume is comparable - or in the projection backend under a different doctrine,
  or in neither because attestation is out of scope, is unresolved. Whether a
  document is signed at all is a prior question this paper does not open.
- **Sync transport: poll versus push.** This paper designs a poll, because a poll
  is what was measured to work (section 3.4) and it costs 56 bytes when idle. What
  exists on the DHIS2 side, stated plainly: **there is no change-feed or webhook
  API**. `/api/routes` is an outbound proxy - DHIS2 forwarding a caller's request
  to a third-party system - not a change notification, and this repo has already
  logged several of its quirks (BUGS.md #4e, #57). Job configurations and the
  messaging surface are neither general nor a data feed. So push would mean either
  a DHIS2-side app or an upstream feature request, and the poll is not a
  compromise - it is the API's only shape. The reserved part is the interval, and
  whether a forward triggers a targeted sync of the entities it touched.
- **How projection freshness reaches a client.** R3 requires that every answer
  state its cursor; it does not say how. The candidates are `Meta.lastUpdated` on
  each projected resource (which today the register does not set at all), a
  `Bundle.meta` stamp on a searchset, an `OperationOutcome` `information` issue
  attached to a `MeasureReport`, `MeasureReport.date` versus a separate
  as-of extension, and a plain response header. They are not equivalent: a header
  is invisible to a FHIR client's data model, and an extension is invisible to a
  client that does not know it. This is a copy and contract decision as much as a
  technical one.

## See also

- [FHIR roadmap and review guide](roadmap.md) - section 9.3's "full circle" item,
  whose reserved freshness question this page answers, and the tracked entity
  history surface a person-level projection would serve.
- [The library surface](library.md) - the composition contract these two Protocols
  extend, and the five seams that are not seams yet.
- [The IPS document](ips.md) - R4's deterministic regeneration, which is the exact
  property D7's attested documents cannot have.
- [Corrections and withdrawals](data-lifecycle.md) - the cascade and deletion
  findings this page's section 3.4 measures the sync-visibility half of.
- [Serve a project](../201-serve.md) - "Stored responses are receipts", the
  storage position section 4 extends.
- [Upstream DHIS2 quirks](https://github.com/winterop-com/dhis2w-utils/blob/main/BUGS.md) -
  entries #90, #91, #98, and #99, all of which a syncer has to know.
