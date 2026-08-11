# Troubleshooting

**Who this is for:** the operator holding an error message. Find the literal
text below, read the cause, apply the fix.

**Before you start:** nothing - this page is the index you grep when
something refuses.

**You will be able to:** match the exact error text a `d2w fhir` command or
a build printed to its cause and its fix.

Every refusal a `d2w fhir` command makes is a one-line `error:` message on
stderr with exit 1 - never a traceback. Publisher and SUSHI failures come
out of `make sushi` / `make build` instead, in Java's voice; those are the
second half of this page.

## Project and configuration

| Symptom (literal text) | Cause | Fix |
| --- | --- | --- |
| `error: no fhir.toml found in this directory or any parent. Run` `` `d2w fhir init [DIRECTORY]` `` `to scaffold a FHIR IG project first.` | A command that needs a project (`generate`, `serve`, `forward`) ran outside one. | `cd` into the project, or scaffold one. `validate` is the exception - it runs anywhere. |
| `no fhir.toml in <dir> - there is no project to refresh. Run` `` `d2w fhir init <dir>` `` `to scaffold one.` | `init --refresh` pointed at a directory that is not a project. | Point it at the project root - the directory holding `fhir.toml`. |
| `error: no profile named '<name>' (available: ...). Run` `` `d2w profile list` `` `to see all profiles.` | The resolved profile does not exist in any `profiles.toml`. | `d2w profile list`, then fix the `-p` flag, `DHIS2_PROFILE`, or the `profile` key in `fhir.toml`; `d2w profile add <name> ...` creates one. |
| `--refresh and --force are mutually exclusive: --force rewrites every scaffold file including the ones you edited, --refresh rewrites only what it can rewrite without losing your edits` | Both flags on one `init` run. | Pick one: `--refresh` preserves edits, `--force` overwrites everything. |
| `--refresh takes the project's identity and generation tables from its own fhir.toml, so <flags> would be ignored: drop the flag, or edit fhir.toml and refresh` | Identity flags (`--id`, `--canonical`, ...) passed together with `--refresh`. | Edit `fhir.toml`, then refresh without the flags. |
| `--max-level must be 1 or greater` | `d2w fhir init --max-level 0` (or negative) - it would silently produce an empty registry. | Pass a level of 1 or more, or drop the flag. |
| `Invalid value: unknown format(s): <x> (choose from md, csv, pdf)` | Typo in `validate --format`. | Use a comma list of `md`, `csv`, `pdf`. |
| `at least one format is required (choose from md, csv, pdf)` | `validate --format` given an empty list. | Name at least one format, or drop the flag for all three. |

## Validate and generate refusals

`error: N error(s) found; exiting 1 (--no-fail to suppress)` is validate
doing its job: the instance carries build-aborting codes, listed
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
and then strict-parses, so `make build` aborts with "Unable to Parse HTML -
node 'td' has unexpected content" in its last pass, once every resource has
already been rendered. Change the code in DHIS2, then run `d2w fhir
validate` for the full report.
```

Cause: an in-scope code on an identifier surface carries `<`. Fix: change
the code in DHIS2. Only `<` refuses; `>` and `&` stay warnings.

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
| `make: *** [build] Error 137` with `ig/output` empty afterwards | `128 + 9` - SIGKILL from the kernel's OOM killer during the peak-memory phases. | Give the docker VM more memory (heap + ~2G), or `make build JAVA_HEAP=2g` to fit the box. Confirm with `docker inspect <container> --format '{{.State.OOMKilled}}'`. |
| `Publishing Content Failed: Process exited with an error: 4 (Exit value: 4)` | Not an exit code - SUSHI exits with the number of errors it counted, and the publisher reports it and stops. | Read the `Sushi: error` lines above it, not the number. |
| `Failed to register resource at path: .../input/resources/...` | One predefined resource failed to load - malformed JSON *or* a failed read; a file written shortly before the container read it can come back truncated across a Docker bind mount. | Re-run first. A transient read registers cleanly the second time; a genuinely malformed resource fails every time on the same files. Cross-check `Loaded virtual package sushi-local#LOCAL with N resources` against the file count under `ig/input/resources/`. |
| `Unable to process page .../CodeSystem-....html` with `Caused by: org.hl7.fhir.exceptions.FHIRFormatError: Unable to Parse HTML - node 'td' has unexpected content` | A DHIS2 code carrying `<` reached an identifier table cell - the publisher's final pass, so the whole build was spent first. | Change the code in DHIS2. `d2w fhir validate` reports the same object as `template-hostile-code` in seconds. |
| `Unable to Parse HTML - node 'h2' has unexpected content` | A DHIS2 *name* carrying `<` in a change-history heading - a malformed page, not an aborted build. | Change the name in DHIS2; validate reports it as `template-hostile-name`. |
| `Duplicate definition of ...` | The same identity reached SUSHI twice - once compiled from FSH, once as a predefined resource; generated FSH left behind by an older plugin layout. | Run `d2w fhir generate`; it sweeps the superseded FSH and the report's deleted count is the confirmation. |
| `NullPointerException` during an offline build (`TX_SERVER=n/a`) | Current publisher versions need a terminology server for some required bindings - the `Attachment.contentType` binding on the GeoJSON boundary extension among them, so an org-unit IG will not build offline. | Build online, or use `n/a` only when your content has no such bindings. |

## Serve refusals

The facade itself is [Serve the IG](201-serve.md); these are the ways it
refuses to start.

| Symptom (literal text) | Cause | Fix |
| --- | --- | --- |
| `error: no compiled IG at ig/fsh-generated/resources - run` `` `d2w fhir generate` ``, `then` `` `make sushi` `` `in the project, and serve again.` | The default mode serves what SUSHI wrote, and this project has never been compiled. | What the message says - or `d2w fhir serve --live` to serve straight from the instance, no compile needed. |
| `error: port 8080 on 127.0.0.1 is already in use (usually the local DHIS2 instance; set [serve] port in fhir.toml or pass --port)` | Something else holds the address - typically a local DHIS2 stack on 8080. | Set `[serve] port` in `fhir.toml`, or `--port`. |
| `` `d2w fhir serve` `` `needs the dhis2w-fhir-serve package. Install it with` `` `uv add dhis2w-fhir-serve` `` `or` `` `pip install 'dhis2w-cli[serve]'` `` | The serve package is an extra, and this environment does not have it. A scaffolded project declares it, so `uv sync` there is enough. | Install it either way the message names. |
| `` error: `--ui` needs a built frontend at .../dhis2w_fhir_serve/static, and there is none. Build it with `make build-frontend` (an installed wheel ships it already). `` | Running `--ui` from a source checkout that never built the frontend bundle. | `make build-frontend` in the checkout; installed wheels ship the bundle. |

## Forward outcomes

`d2w fhir forward` ([Forward captures into DHIS2](201-forward.md)) is a dry
run by default - nothing is written, nothing moves. Its closing lines are
outcomes, not crashes:

| Symptom (literal text) | Cause | Fix |
| --- | --- | --- |
| `no compiled IG at <dir> - run` `` `d2w fhir generate` ``, `then` `` `make sushi` `` `in the project, and forward again.` | Translation reads the compiled artifacts, and there are none. | Generate and compile, then forward again. |
| `note: the spool is empty -` `` `d2w fhir serve` `` `is what fills it` | Nothing has been captured; `.serve/responses/received/` holds no receipts. | Run the facade, capture something (or post a load set), then forward. |
| `error: N response(s) rejected by DHIS2 - read the import summary, fix the instance or the data, and forward again` | DHIS2's import refused the payloads; each receipt moved to `rejected/` beside its import report. Common codes: `E1029` (unit outside the form's assignment), `E8023` (missing attribute option combo), `E1064` (duplicate unique attribute value). | Read `reports/fhir-forward-report.md` and the per-receipt reports; fix, then forward again. |
| `note: N response(s) refused by the translator - they stay in the spool, so fixing the guide or the data and forwarding again is the retry` | The translator could not build a payload it stands behind; the receipts stayed in `received/`. | Fix the guide or the data; forwarding again is the retry. |
| `<path>: not readable as JSON (...)` / `<path>: the envelope carries no` `` `response` `` `resource` / `<path>: the captured resource is not a QuestionnaireResponse this package reads (...)` | A spool file is not a stored response envelope - hand-edited, truncated, or foreign. | Remove or restore the named file; the spool is `.serve/responses/`. |
| DHIS2 refuses a load-set re-import with `E1002` and `E1080` | A load-set corpus mints the DHIS2 identities it names, so it imports once - those UIDs now exist. | `d2w fhir generate load-set --salt <anything>` mints a fresh corpus; the same salt reproduces the same corpus. |

Next: [the series index](index.md)
