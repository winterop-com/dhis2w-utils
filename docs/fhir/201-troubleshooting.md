# Troubleshooting

Something refused. This page is the index: every literal message a `d2w fhir`
command or a build prints, what caused it, and what to do. Most of the causes
turn out to be facts about your DHIS2 instance rather than faults in the
tooling - a code with a `<` in it, an organisation unit a form is not
assigned to, a program rule doing its job - so the fix is usually in DHIS2,
and the message says which object.

**Who this is for:** the operator holding an error message. Find the literal
text below, read the cause, apply the fix.

**Before you start:** nothing - this page is the index you grep when
something refuses.

**You will be able to:** match the exact error text a `d2w fhir` command or
a build printed to its cause and its fix.

Every refusal a `d2w fhir` command makes is an `error:` message on stderr
with exit 1 - one per thing that is wrong, and no traceback. The exception
is a `fhir.toml` value the settings document rejects outright, which comes
out as the technical printout
[the settings file page reads for you](301-fhir-toml.md#editing-safely).
Publisher and SUSHI failures come out of the docker runs that drive them
instead, in Java's voice; those are the second half of this page.

## Project and configuration

| Symptom (literal text) | Cause | Fix |
| --- | --- | --- |
| `error: no fhir.toml found in this directory or any parent. Run` `` `d2w fhir init [DIRECTORY]` `` `to scaffold a FHIR IG project first.` | A command that needs a project (`generate`, `serve`, `forward`) ran outside one. | `cd` into the project, or scaffold one. `validate` is the exception - it runs anywhere. |
| `no fhir.toml in <dir> - there is no project to refresh. Run` `` `d2w fhir init <dir>` `` `to scaffold one.` | `init --refresh` pointed at a directory that is not a project. | Point it at the project root - the directory holding `fhir.toml`. |
| `error: fhir.toml: unknown key '<key>' in [<section>]`, sometimes followed by `did you mean '<name>'?` | `fhir.toml` names an option the settings document does not declare - usually a typo (`max_lvl` for `max_level`). One line per unknown key. | Use the suggested spelling, or copy the option line out of `fhir.toml.example`. [The settings file](301-fhir-toml.md) lists every option. |
| `error: no profile named '<name>' (available: ...). Run` `` `d2w profile list` `` `to see all profiles.` followed by a `hint:` block naming the same two commands | The resolved profile does not exist in any `profiles.toml`. | `d2w profile list`, then fix the `-p` flag, `DHIS2_PROFILE`, or the `profile` key in `fhir.toml`; `d2w profile add <name> ...` creates one. |
| `warning: a profile named '<name>' also exists in the global scope; the project-scoped one will override it when you're in this directory.` | Not an error. `d2w profile add --local` wrote a project-scoped profile whose name is also in your global store. | Nothing, if the override is what you wanted. Rename one of the two if it is not. |
| `Font MPDFAA+NotoSans is missing the following glyphs: ...` during `d2w fhir validate` | Not a finding about your instance. The PDF writer met a character the bundled font has no drawing for, in a DHIS2 name or code it was rendering. | Nothing - the `.md` and `.csv` reports carry the character regardless. |
| `--refresh and --force are mutually exclusive: --force rewrites every scaffold file including the ones you edited, --refresh rewrites only what it can rewrite without losing your edits` | Both flags on one `init` run. | Pick one: `--refresh` preserves edits, `--force` overwrites everything. |
| `--refresh takes the project's identity and generation tables from its own fhir.toml, so <flags> would be ignored: drop the flag, or edit fhir.toml and refresh` | Identity flags (`--id`, `--canonical`, ...) passed together with `--refresh`. | Edit `fhir.toml`, then refresh without the flags. |
| `--max-level must be 1 or greater` | `d2w fhir init --max-level 0` (or negative) - it would silently produce an empty registry. | Pass a level of 1 or more, or drop the flag. |
| `Invalid value: unknown format(s): <x> (choose from md, csv, pdf)` | Typo in `validate --format`. | Use a comma list of `md`, `csv`, `pdf`. |
| `at least one format is required (choose from md, csv, pdf)` | `validate --format` given an empty list. | Name at least one format, or drop the flag for all three. |

## Validate and generate refusals

`error: N error(s) found; exiting 1 (--no-fail to suppress)` is validate
doing its job: the instance carries build-aborting codes or names, listed
individually above the line. Fix them in DHIS2, or `--no-fail` if the run
must pass anyway. [Validate the instance](201-validate.md) explains the
grading.

**Generate refuses what validate marks as build-aborting.** The whole run,
not the one object - skipping it would publish a broken guide quietly
instead of failing loudly:

```text
error: optionSets 'Bednet distribution' (csRsm0D7guY) has code
'ENTO - IRS < 6 Months', which carries '<'. A DHIS2 code becomes an
identifier value, which the IG publisher writes into a table cell unescaped
and then strict-parses, so the publisher aborts with "Unable to Parse HTML -
node 'td' has unexpected content" in its last pass, once every resource has
already been rendered. Change the code in DHIS2, then run `d2w fhir
validate` for the full report.
```

Cause: an in-scope code on an identifier surface carries `<`. Fix: change
the code in DHIS2. Only `<` refuses; `>` and `&` stay warnings.

A name refuses the same way, through its own message: a DHIS2 name stays
byte-true on the emitted resource's title, which the publisher writes into
pages it strict-parses after writing. The refusal names the object - or the
option, whose name lands in page tables - and ends with the same
instruction: change the name in DHIS2, then run `d2w fhir validate` for the
full report.

**The same refusal, read off the files a build publishes:**

```text
error: 3 build-aborting artifact(s) found; exiting 1 before the publisher runs
(--no-fail to suppress)
```

Cause: `d2w fhir check-artifacts` found a `<` in the artifacts on disk. That
is a different question from the two above, which read the instance and the
selection - a build publishes whatever `ig/fsh-generated/` and `ig/input/`
hold, so output from before the gate existed, output from an older toolchain
pin, and hand-authored FSH all reach the publisher without passing it. Fix:
what each finding's own line says - regenerate after narrowing the selection
for a generated file, edit the file for a hand-authored one. [The build
refuses before it begins](201-build-and-publish.md#the-build-refuses-before-it-begins)
covers the scan.

**A code-sourced naming run refuses on unusable stems:**

```text
error: [generate.naming] source = "code" needs a usable, unique code on
every selected option set; 3 cannot serve as identity stems: <name> (<uid>)
<defect>; ... Fix the codes in DHIS2, or use source = "code-or-id" while
migrating; `d2w fhir validate` names every offender.
```

Cause: `[generate.naming] source = "code"` met a selected object with a
missing, unusable, or colliding code. Fix: what the message says - the
validate report names every offender as `code-stem-refusal`.

**A program UID listed under the wrong selection table fails by name:**

```text
error: program '<name>' (<uid>) has programType WITH_REGISTRATION; a tracker
program is selected under [generate.tracker_programs], which emits one
Questionnaire per stage
```

```text
error: program '<name>' (<uid>) has programType WITHOUT_REGISTRATION; a
WITHOUT_REGISTRATION program is selected under [generate.event_programs]
```

Cause: `[generate.event_programs]` selects `WITHOUT_REGISTRATION` programs
and `[generate.tracker_programs]` selects `WITH_REGISTRATION` ones; you
named a UID in the wrong table. Fix: move the UID. (With empty tables the
sweep routes each program by its live type and never refuses.)

## SUSHI and IG publisher failures

| Symptom (literal text) | Cause | Fix |
| --- | --- | --- |
| `Sushi timeout exceeded: 1800 seconds` then `Process exited with an error: 143 (Exit value: 143)` | The publisher's internal SUSHI run overran the `ig/fsh.ini` timeout. | Raise it: `d2w fhir init --sushi-timeout <seconds>` (or edit `[FSH] timeout` in `ig/fsh.ini`). |
| `Exception in thread "main" java.lang.OutOfMemoryError: Java heap space` mid-validation, a Java stack trace, partial phases logged | The guide does not fit the publisher's JVM heap - a national-scale guide (8,000-plus publishable files) needs more than the default `4g`. | `make build JAVA_HEAP=8g`. Keep the docker VM at heap + ~2 GB or the fix trades this failure for an exit-137 kill in the write phases: on one 16 GB VM, `8g` completes a national guide where `4g` dies here and `10g` is OOM-killed at Jekyll. |
| The publisher exits `137` with `ig/output` empty afterwards | `128 + 9` - SIGKILL from the kernel's OOM killer during the peak-memory phases. | Give the docker VM more memory (heap + ~2G), or drop the publisher's `-Xmx` (`-Xmx2g`, or `make build JAVA_HEAP=2g`) to fit the box. Confirm with `docker inspect <container> --format '{{.State.OOMKilled}}'`. |
| `Publishing Content Failed: Process exited with an error: 4 (Exit value: 4)` | Not an exit code - SUSHI exits with the number of errors it counted, and the publisher reports it and stops. | Read the `Sushi: error` lines above it, not the number. |
| `Failed to register resource at path: .../input/resources/...` | One predefined resource failed to load - malformed JSON *or* a failed read; a file written shortly before the container read it can come back truncated across a Docker bind mount. | Re-run first. A transient read registers cleanly the second time; a genuinely malformed resource fails every time on the same files. Cross-check `Loaded virtual package sushi-local#LOCAL with N resources` against the file count under `ig/input/resources/`. |
| `Unable to process page .../CodeSystem-....html` with `Caused by: org.hl7.fhir.exceptions.FHIRFormatError: Unable to Parse HTML - node 'td' has unexpected content` | A DHIS2 code carrying `<` reached an identifier table cell - the publisher's final pass, so the whole build was spent first. | Change the code in DHIS2. `d2w fhir check-artifacts` finds it in the file on disk before a build starts, and `d2w fhir validate` reports the same object as `template-hostile-code` from the instance side. |
| `Unable to Parse HTML - node 'h2' has unexpected content` | A DHIS2 *name* carrying `<` in a change-history heading - a malformed page, not an aborted build. | Change the name in DHIS2; validate reports it as `template-hostile-name`. |
| `The html source has duplicate anchor Ids: <code-system-id>-<code>` in the QA output, often under an `Internal error in location` line | Two distinct DHIS2 codes differ only in whitespace (`Pre eclampsia` beside `Preeclampsia`), and the publisher's anchor slug strips it, so both concept rows get one anchor id. | Cosmetic - the build completes and the page renders both rows. The codes are the instance's own and a `content: complete` CodeSystem must state both, so nothing is merged on this side. BUGS.md 107 carries the upstream repro. |
| `Publishing Content Failed: Unable to process page <Resource>.html`, with `Caused by: org.hl7.fhir.exceptions.FHIRFormatError: Unable to Parse HTML - ... last text = '<the text before the bracket>'` and `AIProcessor.produceMDForResource` in the stack | A DHIS2 *name* carrying `<` reached a rendered page. This is the expensive one: the name survives every earlier pass, Checking Output HTML included, and kills only the publisher's final AI-markdown pass - hours in, once every resource has already been rendered, and the message names a page rather than the object. Run `d2w fhir check-artifacts`: it reads the same files the publisher does, names the file, the resource, and the element in seconds, and it is what `make build` runs first, so a refreshed project (`d2w fhir init --refresh`) never reaches this failure again. `d2w fhir validate` names the same objects from the instance side, and `d2w fhir generate` refuses the run up front. Rename the object in DHIS2; where you cannot - upstream demo metadata, a name a ministry actually uses - leave it out of the selection. [`examples/fhir/igs/refused-names`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/igs/refused-names/README.md) is the worked exhibit. |
| `Duplicate definition of ...` | The same identity reached SUSHI twice - once compiled from FSH, once as a predefined resource; generated FSH left behind by an older plugin layout. | Run `d2w fhir generate`; it sweeps the superseded FSH and the report's deleted count is the confirmation. |
| One error per organisation unit with geometry during an offline build (`TX_SERVER=n/a`): `` The value provided ('application/geo+json') was not found in the value set 'MimeType' ... (error message = Cannot invoke "...TerminologyClientContext.getAddress()" because "tc" is null) `` | The GeoJSON boundary attachment states its media type, R4 invariant `att-1` requires it wherever the attachment carries data, and that field binds to the IETF BCP 13 media types - a value set only a terminology server can answer. Offline there is no server, and the publisher reports the null terminology client as the reason. The build completes; the errors are the whole cost. | Build online and they go away. Offline is still worth having: on a district registry it is a 51-second build, and dropping the media type to silence these would trade them for one `att-1` violation per unit on **every** build, online ones included. |
| A build that sits at `Generating Narratives` far longer than the resource count explains | Not slow - idle. Every ConceptMap row is validated against the system its target code sits in, and a DHIS2 identifier namespace declared only as a NamingSystem answers nothing, so the publisher asks the terminology server about each row in turn and is told UNKNOWN_CODESYSTEM each time. Measured on one district-scale guide: 4,779 terminology requests, 57 percent of them byte-identical repeats, and the narrative phase alone at 438 seconds. | Regenerate with a current `d2w fhir generate`. It publishes each of those namespaces as a `content: complete` CodeSystem beside the maps, which drops the same guide to 5 terminology requests and 1.5 seconds of narratives. `content: not-present` does not work - the publisher reads it as "the codes are elsewhere" and asks anyway. |
| A build whose `Generate Native Outputs` phase runs for minutes on macOS | Not the publisher - the mount. Docker reaches a host directory over a network-style filesystem, and that phase writes tens of thousands of small files one at a time. Measured on one guide: 341 seconds through the mount, 21 seconds on the container's own disk. | Nothing to do on a refreshed project: `make build` streams the project into the container, builds there, and streams `output/`, `fsh-generated/` and `input-cache/` back. `d2w fhir init --refresh` brings an older Makefile up to date. `make build-bind` is the old behaviour if you want to watch `output/` fill as it is written. |

## Serve refusals

The facade itself is [Serve the IG](201-serve.md); these are the ways it
refuses to start.

| Symptom (literal text) | Cause | Fix |
| --- | --- | --- |
| `error: no compiled IG at ig/fsh-generated/resources - run` `` `d2w fhir generate` ``, `then` `` `make sushi` `` `in the project, and serve again.` | The default mode serves what SUSHI wrote, and this project has never been compiled. | What the message says - or `d2w fhir serve --live` to serve straight from the instance, no compile needed. |
| `error: port 8391 on 127.0.0.1 is already in use (usually the local DHIS2 instance; set [serve] port in fhir.toml or pass --port)` | Something else holds the address - typically a local DHIS2 stack on 8080. | Set `[serve] port` in `fhir.toml`, or `--port`. |
| **No** refusal, and `d2w fhir serve` starts on a port your local DHIS2 already answers on | The probe binds an IPv4 socket and the other listener holds the port on IPv6 only. Docker Desktop on macOS publishing `8080` is exactly that (`TCP *:8080 (LISTEN)`, IPv6), so serve starts beside DHIS2 and then answers some of the `localhost:8080` requests meant for it. | Choose the port in `[serve]` rather than relying on the probe. `lsof -nP -iTCP:<port> -sTCP:LISTEN` shows who really holds it. |
| `` `d2w fhir serve` `` `needs the dhis2w-fhir-serve package. Install it with` `` `uv add dhis2w-fhir-serve` `` `or` `` `pip install 'dhis2w-cli[serve]'` `` | The serve package is an extra, and this environment does not have it. A scaffolded project declares it, so `uv sync` there is enough. | Install it either way the message names. |
| `` error: `--ui` needs a built frontend at .../dhis2w_fhir_serve/static, and there is none. Build it with `make build-frontend` (an installed wheel ships it already). `` | Running `--ui` from a source checkout that never built the frontend bundle. | `make build-frontend` in the checkout; installed wheels ship the bundle. |

## Forward outcomes

`d2w fhir forward` ([Forward captures into DHIS2](201-forward.md)) is a dry
run by default - nothing is written, nothing moves. Its closing lines are
outcomes, not crashes:

| Symptom (literal text) | Cause | Fix |
| --- | --- | --- |
| `error: no compiled IG at <dir>/ig/fsh-generated/resources - run` `` `d2w fhir generate` ``, `then` `` `make sushi` `` `in the project, and forward again.` | Translation reads the compiled artifacts, there are none, and this project states `[forward] live = false` so no stand-in is built off the instance. | Generate and compile, then forward again - or drop `live = false` and let the drain build the guide off the instance. |
| `error: N response(s) rejected by DHIS2` where the rollup names `E1300 Generated by ProgramRule (...)` | A DHIS2 **program rule** on the instance refused a value. Synthetic corpora hit this often: a load set draws values inside a data element's own value type, and a program rule can forbid a subset of that range. | Read the rule the message names in the instance's Maintenance app. This is a fact about that instance's configuration, and a load set is not the data to relax a rule for. |
| `note: the spool is empty -` `` `d2w fhir serve` `` `is what fills it` | Nothing has been captured; `.serve/responses/received/` holds no receipts. | Run the facade, capture something (or post a load set), then forward. |
| `error: N response(s) rejected by DHIS2; exiting 1 - read the import summary, fix the instance or the data, and forward again` | DHIS2's import refused the payloads; each receipt moved to `rejected/` beside its import report. Common codes: `E1029` (unit outside the form's assignment), `E8023` (missing attribute option combo), `E1064` (duplicate unique attribute value). | Read `reports/fhir-forward-report.md` and the per-receipt reports; fix, then forward again. |
| `note: N response(s) this dry run could not check - each is a stage event whose enrollment a registration of the same run creates, and only an import creates it` | A dry run writes nothing, so the enrollment a registration mints is not there when the stage event naming it is validated; DHIS2 answers that event `E1313` plus the `E1079` program mismatch it asserts against the absent enrollment. Counted unverifiable, not rejected, and the run still exits 0. | Nothing to fix - `--import` posts registrations first and the pair does not arise. A stage event whose enrollment no registration of the run mints is a rejection instead, and says so. |
| `note: N response(s) sent M value(s) an earlier submission had already sent ...`, or on a dry run `note: N response(s) carry M value(s) an earlier submission has already sent ...` | Not an error. A receipt this project already forwarded had sent the same aggregate values - same data element, category option combo, period, organisation unit, and attribute option combo - and DHIS2 replaces such a value in place while counting the write exactly as it counts a first entry. | Nothing, if the second submission is the correction you meant. If it is not, read the earlier submission at `.serve/responses/forwarded/<id>.json` and capture the form again with the value you want. [Values a previous submission already sent](201-forward.md#values-a-previous-submission-already-sent) explains the reading. |
| `note: N response(s) were not sent: each carries M value(s) in all that a receipt this spool has already forwarded sent, and` `` `[forward] overwrites` `` `is` `` `refuse` `` ... | Not an error, and not a failure of the responses. This project states `[forward] overwrites = "refuse"`, so a form carrying a figure an earlier submission already sent is refused whole and left in the queue with the covered figures written down beside it. | Read them, then decide: `d2w fhir forward --import --overwrites allow` sends them and names every figure replaced, or leave them queued and correct the earlier submission instead. [Overwrites](201-forward.md#overwrites) carries the posture in full. |
| `note: N receipt(s) DHIS2 has already accepted record no values, so this run cannot say whether they sent any of these values first` | A receipt in `forwarded/` has an import report naming no values, which every receipt a drain files does record. Something other than a drain put it there - a hand-copied file, an edited report. | Restore the report the drain wrote, or accept that those receipts are invisible to the reading above. Nothing else in the run is affected. |
| `note: N response(s) refused by the translator - they stay in the spool, so fixing the guide or the data and forwarding again is the retry` | The translator could not build a payload it stands behind; the receipts stayed in `received/`. | Fix the guide or the data; forwarding again is the retry. |
| `note: <file> does not read as a receipt and was moved to .serve/responses/malformed/: ...` | A spool file is not a stored response envelope - hand-edited, truncated, or foreign. The run moved it aside and carried on with everything else, so one bad file costs one receipt rather than the drain. | Read `.serve/responses/malformed/<file>.reason.json`, then restore the receipt from wherever it came from, or delete it. `d2w fhir spool --details` lists the whole holding pen. |
| `error: another drain of this spool is running: process N holds .serve/responses/.drain.lock ...` | A second `d2w fhir forward` started while one was already draining this project. Two drains would post every payload twice and race each other's renames, so the second one fails rather than waits. | Wait for the running drain and forward again. If no such process exists - a machine that lost power mid-drain - delete the named lockfile. |
| `note: <id>: <path> was gone when the drain went to file it ...` | Something moved a receipt's file between the read that listed it and the rename that would have filed it. DHIS2 had already answered about the payload, and that answer is in the report. | Nothing to fix in the run - it graded the receipt rather than throwing the drain away. Check whether a second operator or a hand-run `mv` is working in the same spool. |
| A receipt reporting itself `entered-in-error` sits in `rejected/` with a report naming no DHIS2 error | Withdrawal is a deletion and this toolchain imports, so that response can never convert - no change to the guide and no change to the instance would help. It is filed rather than retried by every drain. See [Corrections and withdrawals](design/data-lifecycle.md). | Nothing, usually. `d2w fhir requeue <id>` puts it back in the queue if you want it tried again. |
| DHIS2 refuses a load-set re-import with `E1002` and `E1080` | A load-set corpus mints the DHIS2 identities it names, so it imports once - those UIDs now exist. | `d2w fhir generate load-set --salt <anything>` mints a fresh corpus; the same salt reproduces the same corpus. |
| DHIS2 refuses a receipt you moved back out of `forwarded/` and forwarded again, naming a UID it already holds | The receipt already imported. An event's UID is derived from the receipt's own logical id and every payload is posted as a create, so a second forward of one receipt names the objects the first one made. | This is the refusal working - the visit is already in DHIS2. Look the named UID up rather than forwarding again; the receipt belongs in `forwarded/`. |

Next: [the series index](index.md)
