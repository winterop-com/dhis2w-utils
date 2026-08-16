# Forward captures into DHIS2

Everything so far has read your instance. This is the step that writes to it:
it takes the submissions the server collected and imports them as data
values, tracked entities, enrollments, and events - through `/api/dataValueSets`
and `/api/tracker`, the same endpoints any DHIS2 import uses, under the same
rules, with the same error codes coming back. Run it once and it validates
the whole queue without writing a byte; run it again with `--import` and it
commits.

**Who this is for:** the operator draining a served project's queue into the
DHIS2 instance - the one step in the whole loop that writes.

**Before you start:** a project with receipts in
`.serve/responses/received/` ([Serve the guide](201-serve.md)) and a DHIS2
profile the run can resolve. A compiled IG on disk is the usual case and the
faster one; a project that has never run SUSHI forwards too.

**You will be able to:**

- validate an entire spool against the real instance without writing a byte
- read a run's report and tell a translator refusal from a DHIS2 rejection
- read the queue, and put a refused receipt back in it
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

Two verbs sit beside it and touch no instance at all - `d2w fhir spool` reads
the queue, and `d2w fhir requeue` puts a refused receipt back in it.

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

Seven steps, each narrated on stderr:

1. **Read the spool** - every `.serve/responses/received/*.json`, in
   file-name order.
2. **Read the guide** - the same two trees `d2w fhir serve` loads. A project
   holding no compiled guide has one built off the instance instead, by the
   very builders `d2w fhir serve --live` answers reads from (see
   [A project with no compiled guide](#a-project-with-no-compiled-guide)).
3. **Read the value types** - one id-only request per kind, for the one
   fact the compiled IG cannot carry: R4 spells DHIS2's `BOOLEAN` and
   `TRUE_ONLY` as the same `#boolean` item type, and only the value type
   tells them apart.
4. **Translate** - each response through `dhis2w_fhir.conversion`,
   all-or-nothing.
5. **Post** - one payload per response, **people first and then the payloads
   that create an enrollment**, through the one client the run opened.
6. **Register completeness** - the tuple every `completed` aggregate response
   claimed, and only once DHIS2 has taken its values.
7. **File** - each receipt into what it became (import runs only).

An empty spool stops after step 1, or after step 2 when the project holds a
compiled guide to read off disk. Every step past that exists to translate
receipts, so a run with none opens no client and reads nothing from the
instance - which on a large instance is the difference between a report that
says zero in a moment and one that reads the whole metadata surface to say it.
An unreadable receipt still fails the run, because the spool is read first.

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

## A project with no compiled guide

A drain translates each receipt against the published Questionnaires and
terminology. A project that has run `d2w fhir generate` and `make sushi` has
them in `ig/fsh-generated/resources`, and the run reads them off disk.

`d2w fhir serve --live` has no build step in front of it, so a project captured
that way has never written those files. Rather than refuse the receipts a
working capture screen produced, the run builds the same documents off the
instance - one metadata read through the same builders the live facade serves
from, so the forms a response was captured against and the forms it is
translated against are built by the same code from the same read.

Which path a run takes is decided by what the project holds, not by a flag:

| The project holds | The run reads | Cost |
| --- | --- | --- |
| `ig/fsh-generated/resources` | the compiled guide, off disk | a directory listing |
| no compiled guide | a guide built off the instance | one full metadata read per drain |

While the read is happening, the spinner names it - *building the guide off
the instance, this project holding no compiled one*. The line that lands in
the log is the completion, and it counts the same way whichever path ran, so
a redirected log tells the two apart by the resource count and the seconds
rather than by the words:

```
[2/7] guide: 1,419 resource(s), 14 form(s)     # read off the compiled guide
[2/7] guide: 1,403 resource(s), 14 form(s)     # built off the instance
```

A deployment that wants its forwards reading a reviewed, published guide and
nothing else turns the stand-in off:

```toml
[forward]
live = false
```

Forwarding an uncompiled project is then the one-line refusal, and it names
the two commands that produce a guide:

```
error: no compiled IG at /home/you/demo-ig/ig/fsh-generated/resources - run
`d2w fhir generate`, then `make sushi` in the project, and forward again.
```

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

## Data set completeness

DHIS2 keeps a separate record of whether a data set is *finished* for a
period - a `completeDataSetRegistration`, keyed by the same
`(data set, period, organisation unit, attribute option combo)` the values are
filed under. The capture contract already states it, and needs no extension to
do so: `QuestionnaireResponse.status` is `completed` when the reporter finished
the report and `in-progress` when they did not.

| The response says | The values | The completeness |
| --- | --- | --- |
| `completed` | imported | the tuple is registered complete |
| `in-progress` | imported | nothing is registered |

The registration is a **second write, made only after DHIS2 has taken the
values**. A completeness claim about data the instance refused would be a lie,
so a rejected import registers nothing at all. `--no-register-completeness`
turns the second write off for a whole run, and the report says
`not-registered` for every response that would have made one.

The `Data set completeness` row of the summary counts the run, and step six
of the narration says which of three things happened - `5 report(s) would be
registered complete (validate only)` in a dry run, `5 report(s) registered
complete, 0 refused` in an import, and `no aggregate response to register`
when the spool held none. `--details`, or the written report, lists the tuple
each response claimed.

| Outcome | What it means |
| --- | --- |
| `registered` | DHIS2 took the registration; the data set is complete for that tuple |
| `would-register` | a dry run: the tuple a `completed` response would register |
| `not-claimed` | the response reports itself `in-progress` |
| `not-registered` | the run ran under `--no-register-completeness` |
| `refused` | the values imported and DHIS2 refused the registration |

**A refused registration does not un-import the values.** They are imported and
they stay imported; only the claim failed, and the response still counts
`accepted`. Forwarding the same tuple again is the retry - DHIS2 answers a
registration it already holds with `updated`, not a conflict.

A dry run posts nothing here, and says so in its own closing note:

```
note: A dry run writes no values, so there is nothing for a completeness registration to be
about and none is posted. What the run states is the tuple each `completed` response would
register - the data set, period, organisation unit, and attribute option combo its values
ride under. Whether DHIS2 accepts that write is checked by the import, which registers only
after it has taken the values.
```

The written report gives the tuples a section of their own, one row per
claim, because a registration has no UID to look it up by afterwards:

```markdown
## Data set completeness

| Completeness | Data set | Period | Organisation unit | Attribute option combo | Completed on | Why |
| --- | --- | --- | --- | --- | --- | --- |
| registered | TuL8IOPzpHh | 202607 | qO2JLjYrg91 | oawMLLH7OjA |  |  |
| registered | BfMAe6Itzgt | 202607 | lpAPY3QOY2D |  |  |  |
```

An empty attribute option combo column is a data set on the default category
combo - there is one combo and DHIS2 needs no help finding it. `Completed on`
and `Why` fill in only where there is something to say: a date the response
stated, and the reason a registration was refused or never attempted.

The forwarder never writes `/api/dataValueSets`' own `completeDate`, even
though that field registers completeness too. On 2.42 it registers even when
every value in the envelope was refused, and even under `dryRun=true`
(`BUGS.md` 76, 77) - so the claim is made in a call of its own, after the
values are known to have landed.

## The three states a receipt can end in

```
.serve/responses/
  received/    captured, not yet forwarded  - the queue
  forwarded/   DHIS2 accepted it, and <id>.report.json says what it counted
  rejected/    DHIS2 refused it, and <id>.report.json says why
  malformed/   a file that no longer reads as a receipt, and <file>.reason.json says what stopped it
  .drain.lock  held by the drain that is running, if one is
```

`malformed/` is a holding pen rather than a state: nothing in it is a
receipt. A file that will not parse - truncated, hand-edited, half-copied - is
moved there with its reason written beside it, and the run that met it carries
on with everything else. The run names it, and so does `d2w fhir spool`. One
unreadable file costs one receipt, not the drain.

Both drained states carry the report. A rejection needs one to say why it
was refused; an acceptance needs one because "DHIS2 took it" is not the
whole answer either - the import counts are what say how much of it landed,
and an accepted receipt that ignored every value changed nothing in the
instance. The Responses page reads both off the same sidecar. So after the
import above, `forwarded/` holds two files per receipt:

```console
$ ls .serve/responses/forwarded | head -4
0c81a28f79ba4226b8d4d348f2b96de1.json
0c81a28f79ba4226b8d4d348f2b96de1.report.json
130e32d49e734c6badc6dd10161cec31.json
130e32d49e734c6badc6dd10161cec31.report.json
```

Moves are renames within one filesystem, so a receipt is in exactly one
state at every instant. The report is written before the receipt moves, so a
process killed mid-move leaves a report with no receipt - which the next run
overwrites - rather than a drained receipt nothing explains.

**Each receipt is filed the instant DHIS2 answers about it**, inside the
posting loop rather than in a pass at the end. A drain that is killed halfway
- a closed laptop, a lost terminal, a `Ctrl-C` - leaves everything it posted
in `forwarded/` or `rejected/` with the report beside it, and everything it
had not reached untouched in `received/`. There is no window in which DHIS2
holds a payload the spool still calls pending.

## One drain at a time

A drain holds an exclusive lock on `.serve/responses/.drain.lock` for its
whole run, and writes its own process id into the file. A second drain of the
same project fails immediately rather than waiting:

```console
$ d2w fhir forward . --import
error: another drain of this spool is running: process 48122 holds
  /home/anna/demo-ig/.serve/responses/.drain.lock. Wait for it to finish and
  forward again; if no such process is running, remove that file.
```

Failing beats queueing in both directions: an operator who started the second
run by mistake wants to be told, and one who started it deliberately wants the
first run's answer rather than a second run behind it. Two drains over one
spool would translate the same receipts, post both copies, and race each
other's renames.

The lock is an `flock` on an open file descriptor, so the kernel releases it
whether the drain returned, raised, or was killed. `d2w fhir serve` never takes
it - the facade writes into `received/` and reads everywhere, and neither
conflicts with a drain.

## Reading the queue

`d2w fhir spool` answers what is queued, off the project directory alone:

```console
$ d2w fhir spool
  fhir spool
  project                 /home/anna/demo-ig
  not yet sent to DHIS2   4
  accepted by DHIS2       26
  refused by DHIS2        1
  unreadable files        0

note: 1 receipt(s) were refused by DHIS2; fix the instance or the data and
  `d2w fhir requeue` puts them back in the queue
note: --details lists every receipt
```

`--details` adds a row per receipt - the id, its state, the form it answered,
when it arrived, and for a refused one the short reason off the report beside
it. `--json` puts the whole thing on stdout.

No DHIS2 connection and no profile: every fact in the listing is on disk,
which is what makes it answerable while the instance is down - exactly when
somebody will ask.

## Putting a refused receipt back in the queue

A rejection is DHIS2 stating that this payload is wrong, so nothing moves it
back on its own. `d2w fhir requeue` is the operator saying otherwise, once the
instance, the guide, or their mind has changed:

```console
$ d2w fhir requeue 0c81a28f79ba4226b8d4d348f2b96de1
0c81a28f79ba4226b8d4d348f2b96de1 -> .serve/responses/received/0c81a28f79ba4226b8d4d348f2b96de1.json
ok: 1 receipt(s) moved back to received/
note: `d2w fhir forward --import` posts them again
```

`--all-rejected` moves everything DHIS2 refused, which is the usual case after
a fix on the instance. An id that is not in `rejected/` is refused by name, and
refused before anything moves - so a run of five never leaves you working out
which three it got to.

The import report **stays in `rejected/`**. It says what DHIS2 answered the
last time that payload was posted, which is still true of that post and is the
only record of what the receipt was requeued from. The next drain writes a
fresh report wherever the receipt lands.

Like `d2w fhir spool`, this needs no DHIS2 connection: it is a rename inside
the project directory.

## Correcting or withdrawing what you forwarded

The question a DHIS2 person asks next is: somebody typed a number wrong, and
it is in the instance now - what do I do? Read the answer in full at
[Corrections and withdrawals](../../project/fhir-data-lifecycle.md). The short
version, and it is a posture rather than a feature:

| What you want | Where it stands today |
| --- | --- |
| Fix an aggregate value | Capture and forward the same data set, period, and organisation unit again. DHIS2 overwrites the values in place, and it works - but nothing in the run says a correction happened rather than a first entry. |
| Fix a tracker event or a registration | Not available. A second capture is a second receipt, so it derives a new event UID and DHIS2 creates a **duplicate** rather than replacing anything. |
| Withdraw a submission | Not available. There is no fourth spool state, and nothing deletes from DHIS2. |

The capture contract already carries the two lifecycle words this will
eventually be built on, and both currently do something other than what the
word promises: a response whose status is `amended` is collapsed to
`COMPLETED` and forwarded as a brand-new record, and one whose status is
`entered-in-error` is refused by the translator and **filed to `rejected/`**
with a sidecar naming the doctrine. Neither is a way to correct or retract
anything today. The design that turns them into one is in the lifecycle
document, along with why withdrawal is the hard half - DHIS2 permanently burns
a deleted tracker UID.

Filing that one rather than leaving it in the queue is the whole of what
separates a terminal refusal from an ordinary one. Every other refusal has a
fix somewhere - in the guide, in `fhir.toml`, in the data - so the receipt
stays in `received/` and the next run is the retry. `entered-in-error` asks
for a withdrawal, withdrawal is unbuilt, and no change to the guide and no
change to the instance would ever make that response convert; a receipt that
can never succeed is retried by every drain for the rest of the project's life
unless something files it. `d2w fhir requeue` brings it back for an operator
who wants it tried again.

## When the instance stops answering

A 5xx, or a connection that never completes, is the instance failing rather
than a verdict on the payload that met it. The drain stops there. The
receipt that met the failure stays in `received/` along with everything
behind it, whatever the run already posted stays filed, and the report names
what stopped it and how many responses were never sent. Forwarding again
once the instance is healthy is the retry.

The alternative would be worse in both directions: posting the remaining two
hundred payloads into an instance that is falling over, and filing the
receipt that met the 500 under a rejection DHIS2 never made.

## Refusal is not rejection

The two failure modes are different jobs, and the terminal never collapses
them:

| | Refused | Rejected |
| --- | --- | --- |
| Who said no | the translator, before DHIS2 saw it | DHIS2, on the import |
| Where to look | the response, the guide, or `fhir.toml` | the import summary on the outcome |
| Typical cause | a canonical the guide does not publish, a missing `D2Period`, an attribute option combo the form declares and the response does not name | a data element outside the data set, an organisation unit the user cannot write to, a locked period |
| What happens to the file | **stays in `received/`**, unless nothing could ever fix it | moves to `rejected/` with its report |
| How to retry | fix locally, run again - the receipt never left the queue | fix the instance or the data, `d2w fhir requeue`, run again |

A refused response stays put precisely because the retry is natural: nothing
was written, nothing was moved, and the same command is the retry once the
guide or the data is fixed. The one exception is the refusal no fix reaches -
a response reporting itself `entered-in-error`, which asks for a withdrawal
this toolchain does not build - and that one is filed to `rejected/` so it is
not translated again on every drain for ever.

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
| `dataValues[].dataElement` / `.categoryOptionCombo` | the answered item's link id, `<dataElement>.<categoryOptionCombo>` for a disaggregated cell | refused (`unknown-link-id`) |
| `dataValues[].value` | the answer's `value[x]`, per the question's DHIS2 value type | refused, per the reason |

The envelope carries no `completeDate`. Completeness is a second write, and
[Data set completeness](#data-set-completeness) is where it happens.

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

A spool of 29 receipts - one filled in through the capture screens, the rest
a load set posted at the facade - drained against a 2.43.1 instance. The dry
run first:

```console
$ d2w fhir forward
running 7 step(s)
[1/7] spool: 29 pending response(s)
[2/7] guide: 1,419 resource(s), 14 form(s)
[3/7] value types: 84 of 89 question object(s) typed
[4/7] translate: 29 translated, 0 refused
[5/7] post: 29 payload(s) posted (validate only)
[6/7] completeness: 5 report(s) would be registered complete (validate only)
[7/7] spool: 29 spooled, 29 translated, 0 refused, 29 posted, 18 accepted, 1 rejected,
10 unverifiable in a dry run

dry run: DRY RUN - every payload was posted to DHIS2 under its own validate-only mode
(dataValueSets dryRun=true, tracker importMode=VALIDATE). Nothing was written to the
instance and no receipt moved. Re-run with --import to commit.
                                      fhir forward
┌──────────────────────────┬───────────────────────────────────────────────────────────┐
│profile                   │ local_basic (fhir.toml)                                   │
│project                   │ /home/you/demo-ig                                         │
│mode                      │ DRY RUN (validate only)                                   │
│coded answers             │ lenient                                                   │
│spooled                   │ 29                                                        │
│translated                │ 29                                                        │
│refused                   │ 0                                                         │
│posted                    │ 29                                                        │
│accepted                  │ 18                                                        │
│rejected                  │ 1                                                         │
│unverifiable in a dry run │ 10                                                        │
│data set completeness     │ 5 would-register                                          │
└──────────────────────────┴───────────────────────────────────────────────────────────┘
                     rejection reasons (1)
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃Code  ┃ What DHIS2 said                           ┃ Responses┃
┡━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│E1300 │ Generated by ProgramRule (`...`) - `...`. │ 1        │
└──────┴───────────────────────────────────────────┴──────────┘
                             unverifiable in a dry run (1)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃What a dry run cannot check                                                ┃ Responses┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│The enrollment this event answers into is created by a registration        │ 10       │
│validated in the same run. A dry run writes nothing to the instance, so    │          │
│there is no enrollment for DHIS2 to check the event against. An import     │          │
│posts registrations first, and the event is checked against the enrollment │          │
│one created.                                                               │          │
└───────────────────────────────────────────────────────────────────────────┴──────────┘
note: 29 response(s), 47 note(s); full outcomes in
      /home/you/demo-ig/reports/fhir-forward-report.md (--details to print)
error: 1 response(s) rejected by DHIS2; exiting 1 - read the import summary, fix the
       instance or the data, and forward again
note: 10 response(s) this dry run could not check - each is a stage event whose enrollment
      a registration of the same run creates, and only an import creates it
```

Ten of twenty-nine unverifiable is the ordinary shape of a spool holding
tracker stages, not a sign of trouble: the load set registers people and then
records visits for them, and only a committing run has the enrollments to
check the visits against. The same spool, committed:

```console
$ d2w fhir forward --import
running 7 step(s)
[1/7] spool: 29 pending response(s)
[2/7] guide: 1,419 resource(s), 14 form(s)
[3/7] value types: 84 of 89 question object(s) typed
[4/7] translate: 29 translated, 0 refused
[5/7] post: 29 payload(s) posted
[6/7] completeness: 5 report(s) registered complete, 0 refused
[7/7] spool: 29 spooled, 29 translated, 0 refused, 29 posted, 28 accepted, 1 rejected,
0 unverifiable in a dry run
                                      fhir forward
┌──────────────────────────┬───────────────────────────────────────────────────────────┐
│profile                   │ local_basic (fhir.toml)                                   │
│project                   │ /home/you/demo-ig                                         │
│mode                      │ import                                                    │
│coded answers             │ lenient                                                   │
│spooled                   │ 29                                                        │
│translated                │ 29                                                        │
│refused                   │ 0                                                         │
│posted                    │ 29                                                        │
│accepted                  │ 28                                                        │
│rejected                  │ 1                                                         │
│unverifiable in a dry run │ 0                                                         │
│data set completeness     │ 5 registered                                              │
└──────────────────────────┴───────────────────────────────────────────────────────────┘
error: 1 response(s) rejected by DHIS2; exiting 1 - read the import summary, fix the
       instance or the data, and forward again
```

Ten unverifiable became ten accepted, and the one rejection stayed a
rejection - a DHIS2 **program rule** on that instance refusing a value the
synthetic draw produced. That is the whole point of the split: the dry run
proved everything a dry run can prove, and the import answered the rest.

The rollup is what makes a large rejection readable. DHIS2 states a rule
once and then names every object that broke it, so two hundred rejections
are usually three causes; the run groups them by error code plus the message
with its quoted identifiers generalised away, and a response counts once per
distinct cause it met. `--details` replaces the counted hint with one row
per receipt; `--json` puts the whole `ForwardReport` on stdout and nothing
else, import summaries included, so a caller pipes it into `jq` without
filtering the narration out.

The written report opens with the same table and then lists each response
with its own notes. Here is the head of the `--import` run above, and one
entry from each of its two outcome sections:

```markdown
# fhir forward report

- Profile: local_basic (http://localhost:8080)
- Mode: import
- Coded answers: lenient
- Data set completeness: 5 registered
- Forwarded: 2026-08-15T18:08:23+00:00
- Counts: 29 spooled, 29 translated, 0 refused, 29 posted, 28 accepted, 1 rejected, 0 unverifiable in a dry run

## Rejected by DHIS2

- `7944981c0ce84fe19b785f0829fded4e` (http://example.org/fhir/demo/Questionnaire/lxAQ7Zs9VYR) - event - .serve/responses/rejected/7944981c0ce84fe19b785f0829fded4e.json
    - E1300 v2swOcefR0A Generated by ProgramRule (`dahuKlP7jR2`) - `The hemoglobin value cannot be above 99  (vANAXwtLwcT)`.
    - note: wall-clock-derived: the zoned timestamp was read in `UTC` and written as the zone-less wall clock `2026-07-19T07:00:00` DHIS2 stores

## Accepted

- `232da096832942e9b6ab55ab9368a906` (http://example.org/fhir/demo/Questionnaire/TuL8IOPzpHh) - data-value-set - .serve/responses/forwarded/232da096832942e9b6ab55ab9368a906.json
    - Import was successful.
    - note: completeness-claimed: the response reports itself `completed`, so the data set is registered complete for the period
```

The word after the questionnaire canonical is the payload kind - one of
`data-value-set`, `tracked-entity`, `tracker`, `tracker-enrollment`, and
`event` - which is how an operator tells an enrollment of somebody the
instance already holds from a registration that created them.

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
