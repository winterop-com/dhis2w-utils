# Forward captures into DHIS2

**Who this is for:** the operator draining a served project's spool into the
DHIS2 instance - the one step in the whole loop that writes.

**Before you start:** a project with receipts in
`.serve/responses/received/` ([Serve the guide](201-serve.md)), a compiled
IG on disk, and a DHIS2 profile the run can resolve.

**You will be able to:**

- validate an entire spool against the real instance without writing a byte
- read a run's report and tell a translator refusal from a DHIS2 rejection
- retry each failure mode the way it wants to be retried

`d2w fhir forward` is the last leg of the loop, and it closes it:

```
DHIS2 metadata -> d2w fhir generate -> the IG -> d2w fhir serve -> a form a client fills
      ^                                                                     |
      |                                                                     v
      +---------------- d2w fhir forward <------------- a captured QuestionnaireResponse
```

Everything before this point reads DHIS2 or reads the guide. `forward` is
the one verb that writes to the instance, so it is deliberately the one verb
you have to ask twice:

```bash
d2w fhir forward            # dry run: validate the whole spool against DHIS2, change nothing
d2w fhir forward --import   # commit
```

## Dry run first, always

A bare `d2w fhir forward` is a dry run, and the terminal opens and closes
with a banner saying so. It is not a local simulation: every payload is
posted to the real endpoint on the real instance, under that endpoint's own
validate-only mode.

| Payload | Endpoint | Dry run | Import |
| --- | --- | --- | --- |
| Aggregate response | `POST /api/dataValueSets` | `dryRun=true` | *(no extra parameter)* |
| Tracker registration | `POST /api/tracker` | `importMode=VALIDATE` | *(no extra parameter)* |
| Enrollment of an existing person | `POST /api/tracker` | `importMode=VALIDATE` | *(no extra parameter)* |
| Person-only registration | `POST /api/tracker` | `importMode=VALIDATE` | *(no extra parameter)* |
| Event / tracker event | `POST /api/tracker` | `importMode=VALIDATE` | *(no extra parameter)* |

Both endpoints run every rule they would run for a committed import and
persist nothing, so a green dry run means DHIS2 itself has agreed to the
whole spool. A dry run **moves nothing**: the queue after it is the queue
before it, so the natural workflow is to run it until it is clean and then
run the same command with `--import`.

## What one run does

Six steps, each narrated on stderr:

1. **Read the spool** - every `.serve/responses/received/*.json`, in
   file-name order.
2. **Read the published guide** - the same two trees `d2w fhir serve`
   loads. Forwarding an uncompiled project is a one-line refusal naming
   `d2w fhir generate` and `make sushi`.
3. **Read the value types** - one id-only request per kind, for the one
   fact the compiled IG cannot carry: R4 spells DHIS2's `BOOLEAN` and
   `TRUE_ONLY` as the same `#boolean` item type, and only the value type
   tells them apart.
4. **Translate** - each response through `dhis2w_fhir.conversion`,
   all-or-nothing.
5. **Post** - one payload per response, **people first and then the payloads
   that create an enrollment**, through the one client the run opened.
6. **File** - each receipt into what it became (import runs only).

The posting order is what one drain's own creations depend on: a person-only
capture creates the person a registration of the same drain enrols, and a
registration creates the enrollment a stage event names - DHIS2 refuses an
event whose enrollment it cannot find with `E1313`. The full order is
person-only registrations, then registrations, then enrollments of people the
instance already holds, then aggregate reports, then both event kinds. There
is no dependency graph beyond that ordering:
a registration DHIS2 rejects leaves its stage events to fail `E1313` exactly
as they would have, the receipts stay in the queue, and the next run is the
retry. One POST per response is deliberate - DHIS2 answers a bundle with one
report for the bundle, and a spool whose receipts move individually needs
one answer each.

## What a dry run cannot check

A dry run writes nothing, so the enrollment a registration mints does not
exist when the stage event naming it is validated in the same run. DHIS2
answers that event `E1313` for the enrollment nobody has, plus the `E1079`
program mismatch it asserts against that same absent enrollment. The pair is
the dry run's own doing, not a fault in the data: the run counts those
responses **unverifiable in a dry run** rather than rejected, and states why
in its own section.

An import posts registrations first, so the same spool imports clean.

A stage event naming an enrollment **no registration of the run mints** is a
different thing - nothing in the drain would ever create it - and stays a
rejection in both modes.

Exit codes follow that split. A DHIS2 rejection exits 1. A dry run whose
only failures are unverifiable exits 0: it proved everything a dry run can
prove, and the unverifiable section says what is left for `--import` to
answer.

## The three states a receipt can end in

```
.serve/responses/
  received/    captured, not yet forwarded  - the queue
  forwarded/   DHIS2 accepted it
  rejected/    DHIS2 refused it, and <id>.report.json says why
```

Moves are renames within one filesystem, so a receipt is in exactly one
state at every instant. A rejection's report is written before the receipt
moves, so a process killed mid-move leaves a report with no receipt - which
the next run overwrites - rather than a rejected receipt nothing explains.

## Refusal is not rejection

The two failure modes are different jobs, and the terminal never collapses
them:

| | Refused | Rejected |
| --- | --- | --- |
| Who said no | the translator, before DHIS2 saw it | DHIS2, on the import |
| Where to look | the response, the guide, or `fhir.toml` | the import summary on the outcome |
| Typical cause | a canonical the guide does not publish, a missing `D2Period`, an attribute option combo the form declares and the response does not name | a data element outside the data set, an org unit the user cannot write to, a locked period |
| What happens to the file | **stays in `received/`** | moves to `rejected/` with its report |
| How to retry | fix locally, run again - the receipt never left the queue | fix the instance or the data, move the file back, run again |

A refused response stays put precisely because the retry is natural: nothing
was written, nothing was moved, and the same command is the retry once the
guide or the data is fixed.

Unverifiable is a third reading, and only a dry run produces it. DHIS2 named
a reason, but the reason is one the dry run created by writing nothing - see
[What a dry run cannot check](#what-a-dry-run-cannot-check). The receipt
stays in `received/`, and `--import` is what answers it.

## What a translated payload is built from

Every field of a DHIS2 payload is read out of the response through an
identifier or an extension, never off a URL - a questionnaire canonical ends
in an identity stem, and under `naming.source = "code"` that stem is not a
DHIS2 UID. A missing field is a **refusal** with the reason named. The
aggregate envelope (`POST /api/dataValueSets`):

| DHIS2 field | Read from | If it is missing |
| --- | --- | --- |
| `dataSet` | the form's `{base}/id/data-set` identifier | refused (`missing-target-identifier`) |
| `period` | the `D2Period` extension's `iso` sub-extension, re-parsed | refused (`missing-period` / `malformed-period`) |
| `orgUnit` | `subject.reference`, resolved through the published Location's `{base}/id/org-unit` identifier | refused (`missing-organisation-unit` / `unresolvable-organisation-unit`) |
| `attributeOptionCombo` | the `D2AttributeOptionCombo` extension's coding, resolved against the vocabulary the form declares | refused where the form declares one; unset where it does not |
| `completeDate` | the day of the response's `authored` instant, noted | left unset |
| `dataValues[].dataElement` / `.categoryOptionCombo` | the answered item's link id, `<dataElement>.<categoryOptionCombo>` for a disaggregated cell | refused (`unknown-link-id`) |
| `dataValues[].value` | the answer's `value[x]`, per the question's DHIS2 value type | refused, per the reason |

A registration response becomes one `/api/tracker` `trackedEntities` entry
carrying the single enrollment it creates. Both DHIS2 identities travel as
the client minted them, which is the whole point of the contract:

| DHIS2 field | Read from | If it is missing |
| --- | --- | --- |
| `trackedEntity` | `subject.identifier` under `{base}/id/tracked-entity` | refused (`missing-subject`) |
| `trackedEntityType` | the form's `{base}/id/tracked-entity-type` identifier | refused (`missing-tracked-entity-type`) |
| `orgUnit` | the `D2OrganisationUnit` extension, resolved through the published Location | refused (`missing-organisation-unit` / `unresolvable-organisation-unit`) |
| `attributes[]` | the answers of items whose `D2EntityLevel` is `true` or absent; items marked `false` land on the enrollment instead | refused (`unknown-link-id`) per answer |
| `enrollments[].enrollment` | the `D2TrackerEnrollment` extension's identifier under `{base}/id/tracker-enrollment` | refused (`missing-enrollment`) |
| `enrollments[].program` | the form's `{base}/id/program` identifier | refused (`missing-target-identifier`) |
| `enrollments[].enrolledAt` | the `D2EnrolledAt` extension, read back to the zone-less wall clock DHIS2 stores | refused (`missing-enrollment-date` / `malformed-enrollment-date`) |
| `enrollments[].occurredAt` | the `D2IncidentAt` extension, the same way | left unset |
| `enrollments[].status` | fixed `ACTIVE` - a registration form is answered when a person is enrolled | n/a |

A registration whose response states `D2SubjectExists` becomes a **top-level
`enrollments` array** instead - the same enrollment fields as above, plus a
`trackedEntity` naming the person the instance already holds, and no
`trackedEntities` wrapper at all. The wrapper would force
`importStrategy=CREATE_AND_UPDATE`, which silently rewrites that person's
owning organisation unit (`BUGS.md` 73), so the enrollment goes on its own
under plain `CREATE`. The program's own attributes ride the enrollment,
because DHIS2 answers `E1018` to a mandatory program attribute that arrives on
nothing - and an answer belonging to the person's own record (`D2EntityLevel`
`true` or absent) refuses the response with
`entity-level-answer-on-existing-subject`, naming each question, because an
enrollment-only import has nowhere to put it and dropping it would be a
captured value that reaches no instance.

The report and the rejection sidecar both name the payload kind, so
`tracker-enrollment` in the `Target` column is how an operator tells an
enrollment of an existing person from a registration that created one.

The payload models are the generated OpenAPI ones - `TrackerTrackedEntity`,
`TrackerEnrollment`, `TrackerAttribute`, `TrackerEvent` - and a response
filed under an attribute option combo the published vocabulary does not hold
is refused rather than posted, because DHIS2 refuses that write with `E8023`
and a payload we know it will not take is worse than a named refusal.

## Every payload names the DHIS2 object it imports

No payload waits on the instance to be told what it is. A registration reads
both its identities off the response - the tracked entity UID from
`subject.identifier`, the enrollment UID from the `D2TrackerEnrollment`
extension - because whoever filled the form minted them. An event carries no
such field for a client to fill, so the forwarder derives one: SHA-256 over
the receipt's own logical id, shaped into the eleven characters DHIS2 reads
as a UID. One receipt names one event, on every run and every machine.

Two things follow, and both are why the derivation exists:

- **A dry run and the import behind it name the same objects.** The UID in a
  validate-only diagnostic is the UID of the event the committing run then
  creates, so a rejection you read before the import points at an object you
  can look up after it.
- **Forwarding one receipt twice is refused, not duplicated.** Every event
  goes to `/api/tracker` under `importStrategy=CREATE`, so a receipt whose
  event the instance already holds is refused as an object that exists - the
  same refusal a re-forwarded registration earns on its tracked entity UID.
  Moving a receipt back out of `forwarded/` and running again is a retry,
  never a second copy of one visit.

A response carrying no logical id at all - one handed to the translator
directly rather than drained off the spool - leaves `event` unset and lets
DHIS2 mint it, because there is no receipt identity to derive from.

A load set posted at a running facade is a different question: the facade
mints a fresh receipt id per capture, so posting one corpus twice produces
two sets of receipts and two sets of events. What the instance refuses on the
second import is the registrations, whose UIDs the corpus itself carries -
see [Troubleshooting](201-troubleshooting.md) for the `--salt` answer.

## Coded answers: the same dial the facade captures under

`[serve] strict_codes` is the default, so a project that captures strictly
forwards strictly without stating it twice. **Lenient** (the default)
resolves a coded answer's concept code first, then the DHIS2 option UID,
then the DHIS2 option code, recording a note naming which tier matched; a
code the context holds no terminology for is sent to DHIS2 unchecked, with
its own note. **Strict** accepts only the concept code the served CodeSystem
publishes, and refuses anything else. `--strict-codes` /
`--no-strict-codes` overrides the table for one run. The dial reaches the
attribute option combo too, on the same tiers.

## A worked run

The dry run over a load-set-sized spool, as the repository's own guide
records it:

```console
$ d2w fhir forward
[1/6] spool: 286 pending response(s)
[2/6] compiled IG: 1,412 resource(s), 7 form(s)
[3/6] value types: 214 of 214 data element(s) typed
[4/6] translate: 284 translated, 2 refused
[5/6] post: 284 payload(s) posted (validate only)
[6/6] spool: 286 spooled, 284 translated, 2 refused, 284 posted, 281 accepted, 2 rejected,
      1 unverifiable in a dry run

dry run: DRY RUN - every payload was posted to DHIS2 under its own validate-only mode
(dataValueSets dryRun=true, tracker importMode=VALIDATE). Nothing was written to the
instance and no receipt moved. Re-run with --import to commit.

              fhir forward
  profile                     local (fhir.toml)
  project                     /home/me/demo-ig
  mode                        DRY RUN (validate only)
  coded answers               lenient
  spooled                     286
  translated                  284
  refused                     2
  posted                      284
  accepted                    281
  rejected                    2
  unverifiable in a dry run   1

                    rejection reasons
  Code    What DHIS2 said                                          Responses
  E1029   Event OrganisationUnit: `...` and Program: `...`, do             2
          not match.

                       unverifiable in a dry run
  What a dry run cannot check                                    Responses
  The enrollment this event answers into is created by a                 1
  registration validated in the same run. A dry run writes
  nothing to the instance, so there is no enrollment for DHIS2
  to check the event against. An import posts registrations
  first, and the event is checked against the enrollment one
  created.

note: 286 response(s), 41 note(s); full outcomes in
      /home/me/demo-ig/reports/fhir-forward-report.md (--details to print)
error: 2 response(s) rejected by DHIS2; exiting 1 - read the import summary, fix the
       instance or the data, and forward again
note: 2 response(s) refused by the translator - they stay in the spool, so fixing the
      guide or the data and forwarding again is the retry
note: 1 response(s) this dry run could not check - each is a stage event whose enrollment
      a registration of the same run creates, and only an import creates it
```

The rollup is what makes a large rejection readable. DHIS2 states a rule
once and then names every object that broke it, so two hundred rejections
are usually three causes; the run groups them by error code plus the message
with its quoted identifiers generalised away, and a response counts once per
distinct cause it met. `--details` replaces the counted hint with one row
per receipt; `--json` puts the whole `ForwardReport` on stdout and nothing
else, import summaries included, so a caller pipes it into `jq` without
filtering the narration out.

The written report opens with the same table and then lists each response
with its own notes. Here is the head of a real one, from an `--import` run
that drained three receipts:

```markdown
# fhir forward report

- Profile: local_basic (http://localhost:8080)
- Mode: import
- Coded answers: lenient
- Forwarded: 2026-08-10T18:58:14+00:00
- Counts: 3 spooled, 3 translated, 0 refused, 3 posted, 3 accepted, 0 rejected, 0 unverifiable in a dry run

## Accepted

- `060c00b1c11841c78a9bcfc28b1bec26` (http://localhost:8080/fhir/Questionnaire/A03MvHHogjR) - .serve/responses/forwarded/060c00b1c11841c78a9bcfc28b1bec26.json
    - 1 created, 0 updated, 0 ignored
    - note: wall-clock-derived: the zoned timestamp was read in `UTC` and written as the zone-less wall clock `2026-07-26T08:00:00` DHIS2 stores
    - note: status-collapsed: `completed` is written as `COMPLETED`; DHIS2 reads COMPLETED, OVERDUE, SCHEDULE, VISITED all as `completed`, so which of them the event stood at is not recoverable
```

The notes are the run recording what it had to interpret - the same honesty
the capture path's warnings carry - so a payload's translation is auditable
after the fact.

A rejection, as the served spool reports it afterwards (`GET /spool`, the
same envelope the capture UI's Responses page reads):

```json
"rejection": {
  "status": "ERROR",
  "message": null,
  "created": 0,
  "updated": 0,
  "ignored": 1,
  "issues": [
    {
      "error_code": "E1313",
      "subject": "j0jTgSvqWaT",
      "message": "Event `j0jTgSvqWaT` of an Enrollment does not reference a TrackedEntity."
    },
    {
      "error_code": "E1079",
      "subject": "j0jTgSvqWaT",
      "message": "Event: `j0jTgSvqWaT` Program: `IpHINAT79UW` is different from Program defined in Enrollment `nKQZNrXY5iV`."
    }
  ]
}
```

Every `errorCode`, object, and message DHIS2 took the trouble to name
survives onto the outcome, and the endpoint's own generated model
(`ImportSummary` / `TrackerImportReport`) rides along untouched beside it.

## Make targets

The scaffold ships both, reading the same `fhir.toml` every other target
does; an existing project gains them from `d2w fhir init . --refresh`:

```bash
make forward          # the dry run
make forward-import   # the committing run
```

What the translator builds each payload from, field by field, is the
integration developer's contract - see
[The capture contract](401-capture-contract.md) for what a response must
carry, and [the FHIR conversion layer](../../project/fhir-conversion.md) for
why the forwarder is a typed translator.

Next: [Troubleshooting](201-troubleshooting.md) - the failure modes of the
whole loop, this page's included, in one table.
