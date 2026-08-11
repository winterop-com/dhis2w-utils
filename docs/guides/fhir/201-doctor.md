# Check an instance with doctor

**Who this is for:** anyone about to point the FHIR toolchain at a DHIS2
instance they have not used before - a new country profile, a fresh
deployment, an upgrade they want to re-clear.

**Before you start:** a DHIS2 profile that resolves
([Profiles](../../architecture/profiles.md)). Nothing else. Doctor scaffolds
its own project, in its own throwaway directory, and cleans up after itself.

**You will be able to:**

- get a one-command verdict on whether this instance works with the toolchain
- read the phase table and tell a broken instance from a noisy one
- explain what the oracle phase proves, and in which direction

```bash
d2w -p laos fhir doctor           # the whole chain, one verdict
d2w -p laos fhir doctor --live    # and let the instance judge the output
```

## When to run it

Run doctor the first time you meet an instance, and again whenever the
instance changes under you.

- **A handover.** Someone gives you a URL and a token. Doctor tells you, in
  about a minute, whether `generate`, `serve`, `capture`, and `forward` all
  work against it - before you invest a day in a project directory.
- **An upgrade.** The instance moved from 2.41 to 2.42. Doctor's connect
  phase states the version and which plugin tree bound to it, and the rest
  of the run says whether anything downstream noticed.
- **A metadata change.** A country renamed half its facilities. Run
  `--live` and the oracle says whether what the toolchain would serve still
  derives from what the instance now holds.
- **A bug report.** "Forwarding fails on our instance." A doctor run is the
  smallest complete reproduction, and its markdown report is the attachment.

Doctor is **not** a build. It never publishes anything, it never writes to
the instance - the forward phase runs in validate-only mode - and its
workspace is deleted when the run ends unless you name one.

## The verdict

A run ends on one line:

```
verdict: BROKEN: 6 pass, 2 warn, 1 fail, 0 skipped, 0 blocked; forward failed
```

Exit code 1 follows a **fail** and nothing else. Warnings and skips exit 0,
because a warning is something to read and a skip is something this machine
could not offer.

| Outcome | What it means |
| --- | --- |
| `pass` | The phase ran and found nothing worth acting on. |
| `warn` | The phase ran and found something that degrades the result without breaking it. |
| `fail` | The phase ran and found something broken. The run exits 1. |
| `skipped` | The phase did not run, because this machine or this invocation does not offer what it needs. The reason is stated. |
| `blocked` | The phase did not run, because an earlier phase did not produce its input. The reason names it. |

A failure does not stop the run. Only a phase that structurally depends on
a missing input is blocked - no store means no capture - so one broken
thing does not hide the six working ones behind it.

## The nine phases

**connect** opens a client against the profile, detects the instance's
version from `/api/system/info`, and states which of the `v41` / `v42` /
`v43` plugin trees bound to it. Bad credentials or an unreachable host fail
here as one line, and everything after is blocked: there is nothing to
check against.

**scaffold** writes a throwaway project. By default it picks a small
representative probe - the first data set by name, the first
`WITHOUT_REGISTRATION` program, the first `WITH_REGISTRATION` program - and
then chooses the slice of the organisation-unit hierarchy those forms are
actually assigned to, because DHIS2 refuses a response naming a unit a form
is not assigned to and a probe that ignored that would be grading its own
arithmetic. A form assigned nowhere inside that slice is dropped from the
selection with the reason stated. `--all-targets` scaffolds empty selection
tables instead, which means every data set, every program, and every level.

**generate** runs the full pipeline against the instance - the same
`d2w fhir generate` a project runs - and keeps every note it raised. Notes
are warnings: an unmatched selection entry, a question no synthetic answer
fits, a reference that leaves the selection.

**compile** runs a real FSH compiler over the emitted source: `sushi` on
PATH, or the `fhir-ig` docker image the scaffold's `make setup` builds.
Doctor never builds that image - pulling a JVM and a node toolchain is not
a decision a conformance check gets to make on your machine - so a machine
with neither is reported `skipped` with that reason. A compile is evidence,
not a gate doctor may demand of every machine.

**validate** is `d2w fhir validate` folded in: the instance's codes graded
for FHIR-safety, with the scope-aware severity rollup. An error on the
configured build path fails the phase; hygiene elsewhere in the instance is
a warning.

**serve** builds the served store **in process** - no port is bound, no
subprocess starts. When the compile ran, the store is the compiled guide.
When it did not, the live builders produce the same documents and doctor
writes them where a compiler would have, so the phases after it read one
tree either way. The phase then counts resources per type and says whether
the read-set a capture client needs is present.

**capture** asks the served endpoint to fill in each published form
(`$generate`) and posts each answer straight back at it
(`POST /QuestionnaireResponse`), holding it to the invariant the operation
exists for: **what this server generates, this server accepts, 201**. A
form the server cannot generate against is a warning; an endpoint refusing
its own output is a failure. Registration forms are captured before their
stages, because a stage response answers against the enrollment a spooled
registration minted.

**forward** drains that corpus at the real instance in validate-only mode -
nothing is written, nothing moves. Rejections roll up by cause, so two
hundred responses breaking one rule read as one row. A clean instance shows
**0 rejected**. Responses a dry run cannot check - a stage event whose
enrollment this very run would have created - are counted separately and
are not held against the instance.

**oracle** is the phase doctor exists for, and it runs on `--live`.

## The oracle, explained

Every other phase asks: *does the toolchain run?* The oracle asks a harder
question: *does what the toolchain would serve still say what the instance
says?*

It works one family at a time - organisation units, option sets, data sets,
programs. For each, it takes the resources the store holds, reads the DHIS2
UID each one names, and asks the instance for those objects back. Two
things can go wrong, and both are findings:

- **A resource names an object the instance does not hold.** Something was
  deleted, or renamed out from under the guide.
- **A resource disagrees with the object it derives from.** The instance
  says the facility is called "Bo District" and the served `Organization`
  says "Bo".

For the second check it takes a sample - five per family by default,
`--samples N` to change it - drawn with a fixed seed, so two runs against
one unchanged instance judge the same objects and a mismatch reproduces by
re-running the command.

**The instance is the authority, always.** The DHIS2 object is the fact and
the served resource is the claim about it; a mismatch is never the
instance's mistake. That direction is the whole point. Anyone can write a
test that says the toolchain agrees with itself. The oracle says whether it
agrees with the country's own data, today, and it names the field path -
`name`, `title`, `identifier[1].value` - where it stopped agreeing.

## Reading a real run

```
┃Phase    ┃ Outcome ┃ Seconds ┃ What it found                                  ┃
│connect  │ pass    │ 1.2     │ https://play.im.dhis2.org/dev-2-42 is DHIS2    │
│         │         │         │ 2.42.6-SNAPSHOT, bound to the v42 tree         │
│generate │ warn    │ 2.8     │ 839 file(s) across 7 target(s), 2 note(s)      │
│compile  │ pass    │ 18.0    │ docker fhir-ig sushi compiled 71 resource(s)   │
│serve    │ pass    │ 0.3     │ 867 resource(s) from the compiled guide        │
│capture  │ pass    │ 0.1     │ 5 form(s), 5 generated, 5 accepted as 201      │
│forward  │ fail    │ 2.1     │ 5 spooled, 5 translated, 0 refused, 5 posted,  │
│         │         │         │ 2 accepted, 1 rejected, 2 unverifiable         │
│oracle   │ pass    │ 0.9     │ organisation units: 108 resource(s) over 107   │
│         │         │         │ DHIS2 object(s), 107 resolved, 5 deep-compared │
```

Read the phase table first and the findings second. The table says which
leg of the chain broke; the findings say what to do about it. Here the
chain is sound end to end and one response was rejected by a DHIS2 program
rule on the instance - a fact about that instance's configuration, which is
exactly what a handover needs to surface before anyone builds on it.

## Options

| Flag | What it does |
| --- | --- |
| `--workspace <dir>` | Run in a named directory and keep it. The report is written into it. |
| `--keep` | Keep the temporary workspace instead of removing it. |
| `--all-targets` | Scaffold empty selection tables: every data set, every program, every level. |
| `--live` | Run the oracle phase. |
| `--samples N` | How many resources per family the oracle deep-compares (default 5). |
| `--json` | Emit the typed report on stdout; the narration stays on stderr. |
| `--no-progress` | Do not narrate each phase as it completes. |

The instance comes from the root flag, exactly as it does for
`d2w fhir serve`:

```bash
d2w -p laos fhir doctor
DHIS2_PROFILE=laos d2w fhir doctor
```

There is no local `--profile`. One instance per run, named the same way
everywhere.

## The written report

Every run writes `reports/fhir-doctor-report.md` - into the workspace when
you named one, into the working directory otherwise. It carries the phase
table, every finding with its field path, and the header a handover needs:
which profile, which instance, which DHIS2 version, and when.

That file is the artifact. Attach it to the handover.

## What doctor is not

- It is **not** a build. It never runs the IG publisher and it publishes
  nothing.
- It is **not** a write. The forward phase runs validate-only; no data
  reaches the instance.
- It is **not** exhaustive. The default probe is three forms and one
  subtree, chosen to be representative rather than complete. Use
  `--all-targets` when you want the whole instance, and expect it to take
  correspondingly longer.
- It has **no MCP tool**. A run writes a project tree, shells out to a
  compiler, and posts a corpus through a server it started - a write-heavy
  orchestration with no read-only shape a tool could honestly advertise.

## Where to go next

- [Set up a project](201-set-up-a-project.md) - once doctor says the
  instance works, this is the real project.
- [Validate an instance](201-validate.md) - the codes phase on its own,
  with the full md / csv / pdf reports.
- [Forward captured responses](201-forward.md) - what the forward phase is
  a dry run of.
- [Troubleshooting](201-troubleshooting.md) - the failure modes doctor
  names, one by one.
