---
title: Corrections and withdrawals
---

# Corrections and withdrawals: what happens after a receipt is forwarded

A capture receipt is a submission, and submissions are sometimes wrong. This page decides
what the toolkit does about that: how a submitter corrects a value that already reached
DHIS2, and how a submitter withdraws a submission that should never have been made. The
decision itself stays with the owner; this page is the basis for making it, and ratifying
it is merging it.

Two empirical reviews sit underneath. Both ran against a live **DHIS2 2.43.1** (revision
`9cbfbf3`) and read the repository without writing to it. One asked what an update does on
every data surface; the other asked what a delete does. Their findings are compressed here
into the tables that carry the argument, because in this decision the observed wire
behaviour is the argument.

A reader who knows DHIS2 but not FHIR should be able to follow this end to end. Where a
FHIR element or status code is named, what it means is stated.

## The short version

A correction is a new submission that names the fact it corrects. A withdrawal is a new
submission that retracts one. Neither mutates a receipt, because receipts are immutable and
that immutability is what makes the whole scheme reproducible. Both ride the facade's one
existing verb - `POST` - so the facade stays append-only and never grows a `DELETE`.

The mechanism in one line each:

- **Correct**: `QuestionnaireResponse.status = "amended"` plus `basedOn` naming the receipt
  being corrected. The forwarder derives the DHIS2 identity from **the corrected receipt's**
  id, not the correcting one's, and posts `importStrategy=UPDATE`.
- **Withdraw**: `QuestionnaireResponse.status = "entered-in-error"` plus the same reference.
  The forwarder derives the same identity and posts `importStrategy=DELETE`.

Both are off by default, behind two `fhir.toml` dials, per the standing directive that not
every deployment wants a full round trip.

One consequence has to be stated before anything else, because it closes a door people will
otherwise walk into: **withdrawal is terminal.** DHIS2 permanently burns a deleted tracker
UID. A withdrawn receipt can never be forwarded again, and a correction can therefore never
be implemented as "delete the old one, send a new one". That path does not exist.

---

## 1. What DHIS2 actually does

Everything in this section was observed on 2.43.1. Nothing is inferred from documentation.

### 1.1 Aggregate: correction happens whether or not you asked for it

Tuple under test: `BfMAe6Itzgt / s46m5MS0hxu / Prlt0C1RF0s / y77LiPqLMoq / 202601`.

| # | Operation | Query params | importCount | Stored result |
| --- | --- | --- | --- | --- |
| A1 | first write `"10"` on an empty tuple | *(none)* | `imported:0, updated:1` | `10` |
| A2 | re-POST `"20"` | *(none)* | `imported:0, updated:1` | **`20` - corrected in place** |
| A3 | re-POST `"30"` | `dryRun=true` | `imported:0, updated:1` | `20`, unchanged |
| A4 | re-POST `"40"` | `importStrategy=CREATE` | `imported:0, updated:1` | **`40` - CREATE overwrote a live value** |
| A5 | re-POST `"50"` | `importStrategy=UPDATE` | `imported:0, updated:1` | `50` |
| A6 | `value: ""` | *(none)* | `ignored:1` | refused, `E8120 "Value #0 value is required"` |
| A8 | `value: null` | *(none)* | `ignored:1` | same `E8120` |
| A9 | `value` key omitted | *(none)* | `ignored:1` | same `E8120` |
| B2 | POST only DE1, where DE2 and a comment on DE1 already exist | *(none)* | `updated:1` | **DE2 survives; the comment on DE1 is wiped** |

The server echoes its defaults back on every unparameterised POST:

```json
"importOptions":{"importStrategy":"CREATE_AND_UPDATE","mergeMode":"REPLACE","dryRun":false}
"importCount":{"imported":0,"updated":1,"ignored":0,"deleted":0}
```

Four facts fall out, and three of them are load bearing later.

1. **The default strategy is `CREATE_AND_UPDATE`.** Re-posting a tuple corrects it in place,
   silently, with no marker of any kind on the wire.
2. **`importStrategy=CREATE` is not enforced here.** A4 overwrote a live value under CREATE.
   The aggregate endpoint offers no collision protection at all, which is the opposite of
   what the tracker endpoint does with the same parameter (BUGS.md #84).
3. **`importCount` never reports `imported`.** A genuinely first write on a virgin tuple
   reports `updated:1`, verified twice including on an untouched period. The import summary
   cannot distinguish a create from a correction from a clobber (BUGS.md #85).
4. **Blanking is not deletion on 2.43.** `""`, `null`, and an omitted key are all `E8120`
   refusals. This is version-sensitive and is called out again in section 6.

Merge scope is per value. A partial payload never wipes untouched data elements, but within
a value that *is* touched, omitted fields are replaced - the comment vanished in B2.

### 1.2 Aggregate deletion: idempotent, reversible, and it leaves debt

| Operation | Observed |
| --- | --- |
| `POST /api/dataValueSets?importStrategy=DELETE` | `status=OK`, `importCount {"deleted": 1}` |
| plain read afterwards | `"dataValues":[]` - gone from ordinary reads |
| read with `includeDeleted=true` | row present, `"deleted":true`, **`value` preserved** |
| `GET /api/dataValues?de&pe&ou&co` afterwards | `404`, `E1005 "Data value does not exist"` |
| `DELETE /api/dataValues?de&pe&ou&co` | `204`, tombstone left with the `value` key absent |
| re-import the same tuple afterwards | `status=OK`, `{"updated": 1}` - **silent resurrection**, original `created` retained |
| inline `"deleted": true` under the default strategy | soft-deletes, but reports `{"updated": 1}`, never `deleted` |
| `DELETE` of a tuple **never written** | `status=OK`, `{"deleted": 1}` - **and a new tombstone row is materialised** |
| `DELETE /api/dataElements/{uid}` after any soft delete | `409`, `E4030 "associated with another object: DataValue"` |
| `DELETE /api/dataSets/{uid}` after any soft delete | `200` - only the data element is blocked |

Aggregate deletion is the friendly case in one respect and the hostile case in another. The
tuple identity is never burned: delete, re-import, delete, re-import all succeed. But the
row never leaves, and its presence permanently blocks deletion of the parent data element -
BUGS.md #2, reproduced verbatim on 2.43.1 and now tagged **[STILL]**.

Worse than #2: deleting a tuple that never existed does not no-op. It writes a fresh row
carrying the payload's own value, flagged deleted (BUGS.md #87):

```
POST /api/dataValueSets?importStrategy=DELETE
  {"dataElement":"W4cDelTest2","period":"202512","orgUnit":"y77LiPqLMoq","value":"1"}
-> {"deleted": 1}

GET /api/dataValueSets.json?...&period=202512&includeDeleted=true
-> {"value":"1","created":"2026-08-15T15:29:26.128","deleted":true}
```

So a speculative or replayed withdrawal permanently poisons a data element against metadata
deletion, for data that was never there. **Aggregate withdrawal must read before it deletes.**

### 1.3 Tracker: duplicate versus collide, the asymmetry that decides the design

Created `TeCorrTest1` / `EnCorrTest1` / `EvCorrTest1` on `PrAncCare01` at `y77LiPqLMoq`,
carrying `DeAncVisNo1=1`, `DeAncBpSys1=120`, `DeAncDanger=false`.

| # | Operation | Strategy | HTTP | Result |
| --- | --- | --- | --- | --- |
| T1 | create entity + enrollment + event | `CREATE` | 200 | `created:3` |
| T2 | re-import the **same event UID**, changed BP | `CREATE` | **409** | `E1030`, "Event `EvCorrTest1` already exists"; originals untouched |
| T3 | partial payload, only `DeAncBpSys1=145` | `UPDATE` | 200 | BP corrected; **the two omitted values survive** |
| T4 | partial payload, only `DeAncBpSys1=150` | `CREATE_AND_UPDATE` | 200 | same - merges |
| T5 | `dataValues: []` | `UPDATE` | 200 | `updated:1`, nothing wiped - a no-op |
| T6 | `DeAncDanger: ""` | `UPDATE` | 200 | **that one value erased**, others intact |
| T9 | `DeAncDanger: null` on a present value | `UPDATE` | 200 | **that one value erased** |

The collision the forwarder is built on, verbatim:

```
HTTP 409
{"status":"ERROR","stats":{"created":0,"updated":0,"deleted":0,"ignored":1,"total":1}}
errorReports: [{errorCode: E1030, message: "Event: `EvCorrTest1` already exists.",
                trackerType: EVENT}]
```

**On 2.43.1 a partial tracker update merges.** Omitted data values are preserved; erasing a
value requires explicitly sending `""` or `null` for it. That is the safe direction, and it
means a correcting payload would only *need* to carry what changed.

!!! warning "Version flag - the single most dangerous assumption in this page"

    The merge behaviour was tested on 2.43.1 only. Earlier tracker importers were understood
    to replace the whole data-value set on update. **Verify on 2.42 before relying on a
    partial payload.** If 2.42 replaces, a partial correction there would silently wipe every
    value the correcting payload did not mention. The design in section 3 sends complete
    payloads on every version precisely so this question cannot hurt anyone, but the answer
    still needs to be known - see section 6.

Two smaller facts from the same run: data values on a `COMPLETED` event were editable with
no reopen step, and blank values mean opposite things on the two surfaces - `""` erases a
tracker data value and is refused `E8120` on the aggregate one (BUGS.md #86).

### 1.4 Tracker deletion: the UID is burned, permanently

| Operation | Observed |
| --- | --- |
| `POST /api/tracker?importStrategy=DELETE` with `{"events":[{"event":"<uid>"}]}` | `status=OK`, `{"deleted": 1}` - the UID alone suffices |
| `GET /api/tracker/events/{uid}` afterwards | `404`, `E1005` |
| the same GET **with `includeDeleted=true`** | still `404` - the item endpoint ignores the flag |
| the sibling **collection** read with `includeDeleted=true` | row present, `"deleted":true` |
| re-create the deleted UID under `CREATE` | **`E1082` "Event: `<uid>` is already deleted and cannot be modified."** |
| the same under `UPDATE` and `CREATE_AND_UPDATE` | identical `E1082` - strategy-independent |
| delete the same UID twice | `E1082`, `ignored:1` - **not idempotent** |
| delete a UID that never existed | `409`, `E1032` "Event: `<uid>` do not exist." |

Enrollments and tracked entities behave the same way, with cascades:

| Operation | Observed |
| --- | --- |
| delete an enrollment | `{"deleted": 1}`; **its events cascade to soft-deleted** |
| the tracked entity afterwards | survives, and lists `"enrollments":[]` |
| re-enroll the same person under `onlyEnrollOnce=true` | `created: 1` - **a deleted enrollment does not count** |
| re-use the deleted enrollment UID | `E1113` "Enrollment: `<uid>` is already deleted and cannot be modified." |
| delete a tracked entity | its enrollment **and** their events cascade - a full two-level sweep |
| attribute-filtered search afterwards, even `includeDeleted=true` | `[]` - the person is unfindable by identifier |
| listing by explicit UID with `includeDeleted=true` | returns the row, `"deleted":true` |

This is the finding the whole design bends around. Because the forwarder derives an event's
DHIS2 UID deterministically from the receipt id
(`packages/dhis2w-fhir/src/dhis2w_fhir/conversion/payloads.py:263`), **a withdrawn receipt
can never be forwarded again.** The identity it would use is burned server-side, under every
import strategy. Withdrawal is terminal for a receipt id by DHIS2's rule, not by ours.

### 1.5 Enrollment status is not a state machine

Every transition was accepted on `EnCorrTest1`, 200, `updated:1`:

```
ACTIVE    -> COMPLETED   ok, completedAt = 2026-08-15T15:31:43.802
COMPLETED -> ACTIVE      ok, completedAt cleared        (reopening works)
ACTIVE    -> CANCELLED   ok, completedAt stamped
CANCELLED -> ACTIVE      ok, completedAt cleared        (un-cancelling works)
ACTIVE    -> COMPLETED   ok
```

Nothing on the wire prevents a correcting submission from reopening a closed enrollment, and
`CANCELLED` stamps `completedAt` as if it were a completion. Whatever discipline exists here
has to be ours. This sits beside BUGS.md #70, where an event imports into a `COMPLETED`
enrollment with no error and no warning.

### 1.6 The audit trail is a deployment dial, not a platform guarantee

Every audit surface answered empty after roughly a dozen mutations:
`/api/audits/dataValue` returned `total:0` system-wide; the event and tracked-entity
`changeLogs` endpoints returned `[]`; and `/api/tracker/enrollments/{uid}/changeLogs` is
**404 - not a resource on 2.43.1 at all**.

That is not a DHIS2 default. It is this repository's own development stack, `infra/home/dhis.conf`:

```ini
# DHIS2 stores immutable audit rows on every data/metadata change, which blocks
# metadata deletion (E4030: "associated with another object: DataValueAudit").
# For a dev stack we want to freely create + delete throwaway objects, so we
# disable every audit and changelog channel DHIS2 exposes.
audit.metadata = DISABLED
audit.tracker = DISABLED
audit.aggregate = DISABLED

metadata.audit.persist = off
tracker.audit.persist = off
aggregate.audit.persist = off

changelog.aggregate = off
changelog.tracker = off
```

DHIS2 keeps an audit trail by default. It is also a `dhis.conf` key that deployments turn
off for exactly the reason our own comment gives, and it is not readable through any API
(BUGS.md #53), so a client cannot even tell whether the instance it is talking to keeps one.

**The conclusion is sharper than "DHIS2 has an audit trail": the toolkit cannot rely on it.**
That is what makes section 3's spool promise a promise rather than a convenience.

---

## 2. Where the product stands today, honestly

### 2.1 What holds

**Receipts are immutable, and the id is always minted server-side.** `new_response_id()` is a
`uuid4` hex (`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/spool.py:233`), never taken
from the client. Lifecycle is the directory, never a field: `received/` moves to `forwarded/`
or `rejected/` through `os.replace`
(`packages/dhis2w-fhir/src/dhis2w_fhir/spool.py:98`, `:103`). There is exactly one non-GET
route on the facade, and `DELETE` and `PUT` are refused with a well-formed FHIR
`OperationOutcome` rather than a bare framework 405:

```json
DELETE /QuestionnaireResponse/abc123 -> 405 application/fhir+json
{"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-supported",
  "diagnostics":"`DELETE` is not supported on `/QuestionnaireResponse/abc123`"}]}
```

That refusal is correct and the design below preserves it rather than replacing it.

**Tracker forward collides on purpose.** `packages/dhis2w-fhir/src/dhis2w_fhir/service.py:3773`:

```python
_TRACKER_PARAMS = {"importStrategy": "CREATE", "async": "false"}
```

The docstring on `receipt_event_uid` states the intent: forwarding a receipt DHIS2 already
holds the event of is refused as an object that exists, rather than filing a second copy of
one visit. Confirmed on the wire as `E1030` / 409 (T2 above).

**DHIS2-side deletion is fully built, outside the FHIR path.** `d2w data aggregate delete`
(`packages/dhis2w-core/src/dhis2w_core/v42/plugins/aggregate/service.py:171`) and
`d2w data tracker delete` (`.../tracker/service.py:343`) exist in all three version trees, the
tracker ones behind a confirmation prompt. The absence this page is about is specific to the
FHIR surface.

### 2.2 What works by accident

**Aggregate correction by re-capture already works, and nothing says so.** The aggregate
forwarder sets no strategy at all - `service.py:4606`:

```python
if result.data_value_set is not None:
    params = dict(_DATA_VALUE_SETS_DRY_RUN_PARAMS) if dry_run else {}
    body = result.data_value_set.model_dump(by_alias=True, exclude_none=True, mode="json")
```

`exclude_none` drops the model's unset strategy field, so DHIS2 applies its own default,
which section 1.1 measured as `CREATE_AND_UPDATE`. Replaying the product's own model,
serialization, and params against the live instance produced identical wire bytes and the
expected outcome: receipt A wrote `11`, receipt B wrote `22`, final stored value `22`, both
receipts filed `forwarded/`.

So a second capture of the same `(dataSet, period, orgUnit)` overwrites the first.
It works, and because `importCount` reports `updated:1` for creates and corrections alike
(section 1.1, fact 3), **nothing DHIS2 answers can tell that it happened.**

> **Status note.** Slices 1 and 2 are built, and neither changes a byte on the wire. DHIS2 still
> cannot say an overwrite happened; the spool says it. Every forwarded receipt's import report
> records the identity of each cell its payload landed on and the day the receipt arrived, and a
> drain carrying an aggregate payload reads those records back before it posts anything. A run that
> sends a value a forwarded receipt already sent names the value, the receipt that sent it first,
> and when that receipt arrived - on the terminal, under `--details`, in its own section of the
> written report, and in `--json`. A dry run states it as the prediction it is, which is the most
> useful moment for it. What the drain then *does* about it is `[forward] overwrites` (D8):
> `"allow"` - the default - posts the value and names it, which is DHIS2's own last-write-wins
> semantics stated as a chosen posture; `"refuse"` posts no payload holding one at all and
> leaves the response in the queue with every covered cell written down beside it.

### 2.3 What silently duplicates

**Tracker re-capture does not collide - it duplicates.** `receipt_event_uid` derives the
event UID from the *receipt's own* id, and every capture mints a fresh receipt id:

```
receipt A id: edbb74be9d504684ad05cdf1aecedbdb -> event uid pdo2v2jYhgG
receipt B id: cffa2a84ccf64fbfa24ba772b3408072 -> event uid aucnIXY4QLX
same receipt is stable: True
two receipts collide:   False
```

The guarantee that holds is *one receipt names one event*. The guarantee that does **not**
hold is *one encounter names one event*. Re-forwarding the same receipt collides loudly, by
design. Re-capturing the same visit does not collide at all: it creates a second event.
Registrations are worse, because `$generate` mints new tracked-entity and enrollment UIDs,
so a corrected registration produces a duplicate person.

### 2.4 What cannot be withdrawn

**No submission withdraws anything.** Nothing a client can POST retracts what it already sent;
the facade's one non-GET route imports, and `rejected/` is removal-adjacent but it is a
*refusal* - it names something that never landed - not a withdrawal. The route that does
retract belongs to an operator rather than to a submitter, and it is `d2w fhir withdraw`.

The drain's own state enum carries the fourth state that route files into:

```python
class ResponseLifecycle(StrEnum):  # dhis2w_fhir_serve.spool - what the facade serves
    RECEIVED = "received"
    FORWARDED = "forwarded"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class SpoolState(StrEnum):  # dhis2w_fhir.spool - what the drain and the withdrawal file
    RECEIVED = "received"
    FORWARDED = "forwarded"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
```

The two enums are the same layout read by two packages, and they name the same four states. A
withdrawn receipt is counted by `d2w fhir spool` and by `GET /facade/spool` alike, the listing row
carries the record of the delete, and the capture UI states it - the serve-side half of section
3.7. `packages/dhis2w-fhir-serve/tests/test_spool_directory.py` asserts the two vocabularies
level, so a fifth state added to one package fails until the other has it too.

> **Status note.** The heading above states what the *facade* does, and that is still true: no
> submission withdraws anything. What is built is the operator's route. `d2w fhir requeue` is
> the reverse move `rejected/ -> received/`, an `entered-in-error` receipt is *filed* to
> `rejected/` rather than retried forever, and `d2w fhir withdraw <response id>` deletes the
> event a forwarded receipt landed and files that receipt under `withdrawn/` - the fourth state
> of section 3.7, gated on `[forward] withdrawals` and off unless a project says otherwise.
> What the facade now does about a submission that *declares* itself a correction or a withdrawal
> is refuse it where the dial is off, naming the key (section 3.8), and receive it into the spool
> where the dial is on. `basedOn`, supersession, and a drain that acts on a marked receipt are
> still unbuilt.

**`entered-in-error` is a terminal refusal, and the receipt is filed.** The translator still
refuses it, under its own `entered-in-error-is-a-deletion` category, because retracting an
event is a deletion rather than an import. What is different from every other refusal is
what happens to the file: no change to the guide and no change to the instance could ever
make that response convert, so an import files it to `rejected/` with a sidecar naming this
document, rather than leaving a receipt in the queue for every drain to translate again for
the rest of the project's life. `d2w fhir requeue` puts it back for an operator who wants it
tried again. **None of that withdraws anything from DHIS2** - it is bookkeeping about a
receipt, and the withdrawal itself is still unbuilt.

**`amended` is accepted and means nothing.** `EVENT_STATUSES_BY_RESPONSE_STATUS` at
`payloads.py:118` collapses it onto `EventStatus.COMPLETED` with a `STATUS_COLLAPSED` note.
It does not look up a prior event, does not switch strategy, and does not mark anything. On
the aggregate side it never gets that far: capture-time validation hard-requires
`status == "completed"` (`AGGREGATE_REQUIRED_STATUS`,
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/capture/validate.py:109`), so an `amended`
aggregate response is refused with a 4xx before it reaches the spool at all.

**A rejected correction is a dead letter.** No code anywhere branches on `E1030`, `E1082`, or
`"already exists"`. The only error-code branch is
`_ABSENT_ENROLLMENT_ERROR_CODES = frozenset({"E1079", "E1313"})` (`service.py:3814`), for a
*missing* enrollment. A 409 falls through to `REJECTED` and the receipt moves to `rejected/`.

**The capture UI has no amend affordance.** `FormFill.tsx` posts; `Responses.tsx` and
`ResponseDetail.tsx` are read-only - reload, lifecycle filters, a back link, a raw-JSON
toggle. No amend, revise, resubmit, retract, void, or prefill-from-receipt.

### 2.5 The posture in one table

| Path | A second receipt for the same real-world fact | Result today |
| --- | --- | --- |
| aggregate values | same `(dataSet, period, orgUnit, dataElement, categoryOptionCombo)` | **corrected in place**; DHIS2 says nothing about it, and the run names every value it replaced. `[forward] overwrites = "refuse"` leaves the response in the queue instead |
| aggregate completeness | same tuple | re-registered as `updated`; documented as safe |
| tracker event | new receipt, so a new derived UID | **a duplicate event is created** |
| registration | `$generate` mints fresh UIDs | **a duplicate person and enrollment** |
| replay of an identical body | the same client-minted UIDs | 409 to `rejected/`, no automatic retry; `d2w fhir requeue` is the operator putting it back |
| `status: "amended"` | - | refused at capture with a 422 naming `[forward] corrections`, unless the project sets it to `"amend"`; where it does, the receipt is spooled and a drain still collapses it to `COMPLETED` |
| `status: "entered-in-error"` | - | refused at capture with a 422 naming `[forward] withdrawals`, unless the project sets it to `"retract"`; where it does, the receipt is spooled and a drain still files it to `rejected/` as terminal |

Aggregate corrections work, every one of them is named in the run that makes it, and a deployment
that wants them blocked rather than reported has a dial for that. Tracker corrections are
impossible. Withdrawal is an operator's command over a forwarded receipt - `d2w fhir withdraw`,
behind `[forward] withdrawals` - and not yet anything a submission can ask for: a project with the
dial on *receives* a marked submission and keeps it, and what a drain does with the marker is the
slices that follow.

---

## 3. The design

### 3.1 The principle

**A correction is a new submission that names the fact it corrects. A withdrawal is a new
submission that retracts one.** Receipts stay immutable. The correcting or withdrawing
receipt is a first-class receipt carrying a pointer, and everything else follows from that
sentence plus one derived rule:

> **The DHIS2 identity derives from the corrected receipt's id, not from the correcting
> receipt's own id.**

That single change turns "collide loudly" from a dead end into the mechanism. `E1030` was
protecting the event; now the same derivation lands deliberately on it.

### 3.2 The FHIR vocabulary already exists

R4 has both states, and this project should not invent alternatives.

- A **correction** is a new `QuestionnaireResponse` with `status: "amended"`, pointing at what
  it corrects through **`basedOn`**. (`Provenance` with `activity = CORRECT` would also work
  and needs a second resource; `basedOn` is lighter and needs none.)
- A **withdrawal** is a new `QuestionnaireResponse` with `status: "entered-in-error"`, using
  the same `basedOn` reference.
- **The corrected receipt is never mutated.** Its own status stays whatever it was.
  Superseded-ness is derived by the reader from the existence of a successor - exactly as the
  spool already derives lifecycle from the directory rather than from a field in the file.

The marker that makes the forwarder change strategy is therefore **both conditions, never
either**: a lifecycle status of `amended` or `entered-in-error`, *and* a `basedOn` that
resolves to a receipt this spool has already forwarded. An amendment that names nothing to
amend is a capture error, not a correction, and stays a refusal.

### 3.3 Identity

```
correcting receipt R' with basedOn -> R
    event uid  :=  receipt_event_uid(R)          # the ORIGINAL receipt's id
    import     :=  importStrategy=UPDATE

withdrawing receipt R" with basedOn -> R
    event uid  :=  receipt_event_uid(R)          # the same identity
    import     :=  importStrategy=DELETE
```

`receipt_event_uid` needs no change whatsoever. Only its *argument* changes, from
`response.id` to the id of the receipt at the root of the `basedOn` chain. Immutability is
what makes this sound: `R` is on disk and never changes, so the derivation is reproducible
forever. A chain (`R''' -> R'' -> R`) resolves transitively to the root, so the UID stays
stable across any number of amendments.

Registrations are the exception: tracked-entity and enrollment UIDs are the client's and
travel as sent, so a correcting registration simply reuses them. That needs
`CREATE_AND_UPDATE` and carries the BUGS.md #73 hazard, where enrolling an existing entity
silently rewrites its owning organisation unit - which is why registrations come late in the
plan and use the top-level `enrollments` key that exists for exactly this reason.

### 3.4 Complete payloads, never diffs

**A correcting payload carries the complete state, not the delta** - on both surfaces, on
every version, even though 2.43.1 would merge a partial one. Two reasons:

1. The merge behaviour is version-sensitive and unverified on 2.42 (section 1.3). A complete
   payload is correct whether the server merges or replaces.
2. A receipt that carries the whole corrected state is self-describing evidence of what the
   submitter asserted. A diff is only meaningful against a file you also have to read.

Erasures are then explicit: a `""` value, which 2.43.1 honours per value on the tracker side.
On the aggregate side the correcting receipt carries the whole
`(dataSet, period, orgUnit)` cell set, and if the toolkit ever starts sending comments it
must resend them too, because B2 showed a touched value's comment is replaced rather than
preserved.

### 3.5 Withdrawal is terminal, and the copy has to say so

Section 1.4 is not a hazard to route around - it is a property to expose. Once a withdrawal
is forwarded:

- the DHIS2 UID is burned under every strategy, so **that receipt can never be forwarded
  again**;
- a correction can therefore **never** be modelled as delete-then-recreate on the derived
  identity, which is why section 3.3 gives corrections `UPDATE` rather than
  `DELETE` + `CREATE`;
- a redelivered withdrawal is safe anyway, because the withdrawal has its own receipt and the
  existing replay machinery deduplicates it before it reaches `E1082`.

The user-facing copy must state what actually remains, which is not what "deleted" implies.
DHIS2 soft-deletes: the row stays, carrying its value, invisible to ordinary reads. Per the
copy rules, name the actual subject and state the fact rather than the verb - something in
the shape of *"Withdrawn. This DHIS2 instance keeps a hidden copy of the value; it no longer
appears in reports."* Never a bare "deleted", which the toolkit cannot stand behind.

Aggregate withdrawal carries one extra obligation: because deleting a tuple that was never
written *materialises* a tombstone and permanently blocks the parent data element
(section 1.2), **an aggregate withdrawal reads before it deletes.** It is never issued
speculatively.

### 3.6 The spool is the provenance record - as a product promise

Given section 1.6, the toolkit does not rely on DHIS2's audit trail. It is a `dhis.conf`
dial, this repository's own stack has it off, and enrollment change logs are not a resource
on 2.43.1 at all.

What the toolkit relies on instead is the spool, which is already the right shape: immutable
receipts, lifecycle by directory, one import-report sidecar per receipt. A chain
`R'' -> R' -> R` is a complete, replayable record of who asserted what, when, and what
superseded it - and it survives an instance that keeps no audit at all.

**This should be documented as a guarantee, because it is one, and it is stronger than what
the platform underneath offers.** Stated for the guide: a DHIS2 instance holds only the
current value of a cell; the history of what was asserted and when lives in this project's
spool.

### 3.7 The fourth spool state

The spool gains `withdrawn/`, and it applies to **the original receipt** - the withdrawing
receipt itself follows the ordinary `received/` to `forwarded/` path, because it is a
submission that landed.

| State | Meaning |
| --- | --- |
| `received/` | captured, not yet drained |
| `forwarded/` | DHIS2 accepted it |
| `rejected/` | DHIS2 refused it; it never landed |
| `withdrawn/` | it landed, and a later submission retracted it |

`d2w fhir withdraw <response id>` is the move: it reads the forwarded receipt, recomputes
`receipt_event_uid` off that receipt's own id, posts `importStrategy=DELETE`, writes the
record of what DHIS2 answered into `withdrawn/`, and renames the receipt in after it. The
receipt is never rewritten, and the import report that said what it landed stays in
`forwarded/` - two answers to two questions. A dry run is the default, because a terminal act
is the one that most deserves a rehearsal.

The served facade names the same four. `ResponseLifecycle` carries `WITHDRAWN`, `GET /facade/spool`
counts it and lists the row, and `ResponseSpool.withdrawal_record` reads the record beside the
receipt - which is the one sidecar that is not an import report, so it is read out of `withdrawn/`
by its own accessor rather than parsed as the report it is not. The receipt itself still reads
back at `GET /QuestionnaireResponse/{id}`: retracting data from an instance does not unsay a
submission, and an id a client was handed at capture must not expire on a schedule nothing told it.

The capture UI states the same fact in the same words. The Responses filter and the Overview tile
carry a fourth state, the receipt page renders the record's own note rather than a paraphrase of
it - *"Withdrawn. This DHIS2 instance keeps a hidden copy of the event; it no longer appears in
reports."* - and the page still shows every answer the receipt carries. One sentence, written where
the delete is posted, shown in the terminal and in the browser alike, so the two cannot drift.

### 3.8 The dials

Per the standing directive - keep `fhir.toml` in mind and expand it as needed, because not
everyone wants a full round trip - each capability arrives behind its own dial. The two
correction and withdrawal dials default to off; the overwrite dial defaults to `"allow"`.
`ForwardConfig` (`packages/dhis2w-fhir/src/dhis2w_fhir/config.py`) is `frozen=True,
extra="forbid"`, so a new key must be modelled and not merely written into the TOML.

```toml
[forward]
live = true
overwrites = "allow"   # "allow" | "refuse"
corrections = "off"    # "off" | "amend"     -- gates capture; the drain's correction path is unbuilt
withdrawals = "off"    # "off" | "retract"   -- gates capture and `d2w fhir withdraw`
```

All three are on `ForwardConfig`, resolved in `forward_responses` in the order every dial
resolves - the flag, then the table, then the default - with `--overwrites`, `--corrections`,
and `--withdrawals` on `d2w fhir forward`. `withdrawals` is what `d2w fhir withdraw` requires
before it posts anything. `corrections` is stated by a run rather than acted on by one, which
is what "control ships before capability" amounts to on the drain side of the facade.

The precedent to copy is `[serve] strict_codes` (`config.py`): a configured default that
the forwarder reads and a per-invocation CLI flag can override. With a correction or
withdrawal dial off, the facade **refuses the corresponding status at capture time with a 422
`OperationOutcome` naming the config key**, rather than accepting a submission the forwarder
will never act on. Both halves are built: the keys, the flags, and the gate on
`d2w fhir withdraw` in the drain package, and the capture-time refusal in the serve package -
`CaptureLifecyclePostures` reads the two keys off `fhir.toml` onto the capture state, and the
refusal runs before the profile invariants so a client that sent a correction is told the one
thing that decided the request. A run's `--strict-codes` says nothing about either: strictness
is a property of a run, and these two are a property of the project.

With a dial on, capture *receives* the submission and stores it like any other receipt, status
preserved on the stored copy. That is deliberately all it does: the marked receipt waits in
`received/`, and the strategy a drain then takes from the marker is slices 5 through 9. A dial on
is a deployment saying it accepts these submissions, not a claim that DHIS2 has been told anything
about them.

The two families of dial govern different things, and the difference is the whole reason there
are three keys rather than two. `corrections` and `withdrawals` govern a *marked* submission -
one that says what it is amending. `overwrites` governs an *unmarked* one: the accidental
aggregate overwrite of section 2.2, which carries no marker at all and is simply a second
capture of the same tuple. Making that path visible is slice 2, which is built; deciding what
a drain does about it is `overwrites` (D8), which is built too. `"allow"` posts the value and
names it - DHIS2's own last-write-wins semantics, chosen rather than inherited by default.
`"refuse"` posts no payload holding one and leaves the response queued with the covered cells
recorded beside it, which is the posture for a deployment where forwarded data changes only
through a declared correction. Once `corrections` ships, a marked correction is what a
`"refuse"` deployment routes its changes through.

---

## 4. The slice plan

One ordered list across both halves, smallest first. Documentation and naming come first
because they cost nothing and close the "is this supported?" question today. Dials come
before the capabilities they gate, so no deployment is surprised by a capability arriving.
Events come before aggregates because the aggregate leg on both sides needs a guard the
event leg does not. Registrations come after both, and the cascade comes last.

| # | Slice | Depends on | Why here |
| --- | --- | --- | --- |
| 1 | **[SHIPPED] Name the current behaviour.** Docs and `features.md`: aggregate re-capture overwrites in place, tracker re-capture duplicates, a receipt cannot be withdrawn, and `d2w data tracker delete` is the raw escape hatch. No code. | - | The worst problem is that none of this is written down. |
| 2 | **[SHIPPED] Report aggregate overwrites.** When a drain posts an aggregate cell a prior forwarded receipt already covered, say so in the run report. Spool-local; no wire change, no config. | 1 | Turns a silent clobber into a visible one. DHIS2 cannot tell us, so the spool must. |
| 2a | **[SHIPPED] Decide what a drain does about an overwrite.** `[forward] overwrites` on `ForwardConfig`, `"allow"` by default, with `--overwrites` overriding it for one run. `"refuse"` sends no payload holding an already-sent cell and leaves the response queued with a refusal record naming each. | 2 | Slice 2 made the overwrite visible; this is the posture a deployment takes about it (D8). |
| 3 | **[SHIPPED] Both correction dials, defaulting off.** `[forward] corrections` and `[forward] withdrawals` are on `ForwardConfig` with `--corrections` and `--withdrawals` on `d2w fhir forward`, resolved in `forward_responses` and stated by the run. The facade reads the same two keys at capture: an `amended` or `entered-in-error` submission is refused with a 422 naming the key while the dial is off, and stored like any other receipt where it is on. | - | Control ships before capability. |
| 4 | **[SHIPPED] Withdraw an event, CLI only.** `d2w fhir withdraw <response-id>` reads the forwarded receipt, recomputes `receipt_event_uid`, posts `importStrategy=DELETE`, writes the record beside `withdrawn/`, and moves the receipt in after it. Dry run by default. `d2w fhir spool` and `GET /facade/spool` both count the fourth state, the listing row carries the record of the delete, and the capture UI states what the instance keeps. | 3 | The smallest slice that delivers real capability - one object, no cascade, no wire-contract change. Introduces the fourth state. |
| 5 | **`basedOn` on the wire.** Parse it, resolve the chain to its root, refuse an `amended` or `entered-in-error` receipt whose `basedOn` names nothing this spool forwarded - a second capture-time check, on top of slice 3's, for the submissions a dial-on project now receives. No strategy change yet. | 3 | The correction is recorded and validated before it is applied. |
| 6 | **Tracker event corrections.** Derive the event UID from the `basedOn` root, post `importStrategy=UPDATE`, require a complete value set. | 5 | The one genuinely new mechanism in the whole plan. |
| 7 | **Withdraw an event through the facade.** Accept `entered-in-error` submissions; the forwarder translates. Calls slice 4's service layer. | 4, 5 | Where the design actually lands for withdrawals. |
| 8 | **Aggregate corrections.** Widen `AGGREGATE_REQUIRED_STATUS` to admit `amended`. The forward path needs no change at all, beyond a marked correction passing an `overwrites = "refuse"` drain that an unmarked one does not. | 2a, 5 | The cheapest real capability, because DHIS2 already does the work - but it needs slice 2's visibility and slice 2a's posture first. |
| 9 | **Aggregate withdrawals.** With the read-before-delete guard that events do not need. | 4, 8 | Deliberately after events despite being technically easier, because of the phantom-tombstone hazard. |
| 10 | **Capture UI: amend and withdraw from a receipt.** A control on `ResponseDetail` that prefills a new form from the receipt and submits it with the right status and `basedOn`. | 6, 7 | Pure frontend once the server legs exist. |
| 11 | **Registration corrections.** Tracked entity and enrollment through the top-level `enrollments` key, minding BUGS.md #73. | 6 | Client-minted UIDs, `CREATE_AND_UPDATE`, and a known hazard - late for good reason. |
| 12 | **Enrollment and tracked-entity withdrawals.** Last, and possibly never. | 9, 11 | See below. |

**Why slice 12 may never ship.** Section 1.4 measured a full two-level cascade: withdrawing
one enrollment soft-deletes every event under it, and withdrawing a tracked entity sweeps
both levels. Those events can come from *other receipts* - receipts still sitting in
`forwarded/`, whose recorded state would then be a lie, because the objects they name no
longer exist. **Do not ship this until the spool can mark collaterally-withdrawn receipts.**
Until it can, the honest answer to "withdraw this person" is that the toolkit does not do
that, and `d2w data tracker delete` is the deliberate, prompted escape hatch.

Slices 1 through 3 are documentation, reporting, and configuration, and they carry no wire
risk at all. Slice 4 is the first that writes to DHIS2, and what it writes is a delete: one
event, named by an operator, behind a dial that is off unless a project turned it on.

---

## 5. What the owner decides

Merging this page ratifies the answers written above. These are the specific calls it
contains, listed so that disagreeing with one is easy.

- **D1 - The correction shape.** `status: "amended"` plus `basedOn`, with the DHIS2 identity
  derived from the corrected receipt's id and posted under `importStrategy=UPDATE`.
  *Alternative considered: a `Provenance` resource with `activity = CORRECT`, which carries
  the same information and costs a second resource on every correction.*
- **D2 - The withdrawal shape.** `status: "entered-in-error"` arriving as an ordinary `POST`,
  translated by the forwarder into `importStrategy=DELETE`. The facade gains no `DELETE` verb
  and the existing 405 `OperationOutcome` stays true.
- **D3 - Withdrawal is terminal, and stated as such.** A withdrawn receipt is never
  re-forwardable, because DHIS2 burns the UID. Corrections are never delete-then-recreate.
- **D4 - Complete payloads, never diffs**, on both surfaces and every version.
- **D5 - Two dials, `[forward] corrections` and `[forward] withdrawals`, both defaulting to
  off**, with capture-time 422 refusals naming the config key. The value vocabulary
  (`"off" | "amend"`, `"off" | "retract"`) is part of this call. The keys, the flags, and the
  gate on `d2w fhir withdraw` are built; the capture-time refusal is the serve package's half.
- **D6 - The fourth spool state is `withdrawn/`**, and it applies to the original receipt.
  Built on the drain's `SpoolState`, which is what `d2w fhir withdraw` files into and what
  `d2w fhir spool` counts. The served facade's `ResponseLifecycle` still names three.
- **D7 - The spool is documented as the provenance guarantee**, in place of DHIS2's audit
  trail, which the toolkit does not rely on.
- **D8 - What happens to an unmarked aggregate overwrite is `[forward] overwrites`, and it
  defaults to `"allow"`.** Both halves are built. Visibility: every such cell is named, with
  the receipt that covered it and when that receipt arrived, on a dry run as well as on an
  import. Posture: `"allow"` posts the cell and names it, which is DHIS2's own last-write-wins
  semantics adopted deliberately rather than inherited by omission - the platform underneath
  keeps the newest number whatever a client does, and the common case is a clerk re-entering a
  month they got wrong. `"refuse"` sends no payload holding such a cell at all; the response is
  refused whole and non-terminally, staying in `received/` with a refusal record naming every
  covered cell, the receipt that sent it, and when that receipt arrived, so
  `d2w fhir spool` shows it as refused-but-queued and a later drain under `"allow"` posts it.
  The refusal is per response rather than per cell, because a payload posted in part would tear
  one submission across two postures. The dial reaches aggregate cells alone.
- **D9 - Whether slice 12 is ever built.** Enrollment and tracked-entity withdrawal is
  designed and deliberately unscheduled, because of the collateral-receipt problem.
- **D10 - Whether the MCP read-only gate gains a destructive tier.** Today
  `packages/dhis2w-mcp/src/dhis2w_mcp/readonly.py` classifies `push` as a write, so a delete
  and an append carry identical privilege.

---

## 6. Open verifications

Ordered by how much of the design leans on the answer.

1. **2.42 tracker partial-update semantics - the top follow-up.** Section 1.3 measured merge
   behaviour on 2.43.1 only. If 2.42 replaces the data-value set instead, a partial
   correction there would silently wipe every value the payload omitted. The design already
   sends complete payloads (D4), so the answer changes no code - but it decides whether that
   rule is belt-and-braces or the only thing standing between a correction and data loss, and
   it belongs in the guide either way.
2. **2.42 blank-value semantics on `/api/dataValueSets`.** On 2.43.1, `""` and `null` are
   `E8120` refusals. Historically an empty value on this endpoint was treated as a delete.
   If 2.42 still deletes, then a correcting aggregate payload that clears a cell means
   different things on different majors, and BUGS.md #86 needs a per-version table.
3. **Whether `importStrategy=CREATE` is unenforced on 2.41 and 2.42 as well** (BUGS.md #84),
   and whether `importCount` reports `imported` on those majors (BUGS.md #85). Slice 2's
   overwrite detection is only necessary where the import summary cannot answer the question.
4. **Whether the tracker UID burn holds on 2.41 and 2.42** (`E1082` / `E1113`). D3 is the
   most consequential claim in this page and it rests on one major.
5. **A browser-driven end-to-end run.** The aggregate overwrite in section 2.2 was proven by
   replaying the forwarder's own model, serialization, and params against the live instance,
   producing identical wire bytes. That is sound, but it is not a capture through the UI
   followed by a drain, and slice 1's documentation should rest on one.
6. **Whether `expiryDays` and data-entry locking block corrections.** Section 1.3 corrected
   values on a `COMPLETED` event with no reopen step, but data-entry locking is deployment
   configuration that the run did not exercise. A deployment that locks periods will refuse
   corrections for reasons that have nothing to do with this design, and the refusal needs to
   read clearly.
7. **Whether enrollment `changeLogs` exist on 2.41 and 2.42.** The endpoint 404s on 2.43.1.
   It has no bearing on D7, which relies on the spool regardless, but it belongs in the
   version-differences table.

---

## See also

- [FHIR roadmap and review guide](roadmap.md) - the settled and open decisions this
  page sits beside.
- [The enrollment resource](enrollment-resource.md) - the same decision-document shape,
  ratified by merge.
- [The FHIR conversion layer](conversion.md) - where `importStrategy` is chosen and the
  payloads this page corrects are built.
- [Upstream DHIS2 quirks](../../project/upstream-quirks.md) - `BUGS.md` rendered, including entries #2,
  #84, #85, #86, #87, #88, #89, #90, and #91, all of which this page cites.
- [Forward captures into DHIS2](../201-forward.md) - the operator-facing
  version of the drain this page decides the semantics of.
- [Glossary](../glossary.md) - the spool, the receipt, and the sidecar in one
  sentence each.
