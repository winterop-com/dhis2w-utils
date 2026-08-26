# Quickstart: from nothing to a served IG

**Who this is for:** anyone who wants a generated, compiled Implementation
Guide in a browser before reading anything longer.

**Before you start:** `uv` and Docker installed; network access to a DHIS2
instance - and a detour through
[FHIR for DHIS2 people](101-fhir-concepts.md) if words like CodeSystem are new.
New to this entirely? [Introduction](100-introduction.md) is the three steps
on one page before you run anything.

**You will be able to:**

- scaffold a dockerized IG project with a pinned toolchain
- validate and generate IG source from a live DHIS2 instance
- compile the guide, open it in a browser, and serve it as a FHIR endpoint

Seven steps. The first five are quick; the sixth is where the wall clock goes -
the first compile is much the longest thing on this page.

**Know what costs what before you start.** Step 6 - the full IG publisher build -
is the *publish* step: it renders the guide's website, a page per resource, and
the organisation-unit registry is almost always most of those pages
(`[generate.organisation_units] max_level` and `root` are the dials). Serving
never needs it: `d2w fhir serve --live` needs nothing compiled at all and shows
you a working endpoint straight after step 5, and the compiled posture of
`serve` needs only the SUSHI compile (`make sushi`), not the build.
Run step 6 when you want the website in a browser; skip to step 7 when you want
the endpoint.

Command output below was captured on a real run against a local DHIS2 2.43.1
carrying the Sierra Leone demo database, which also holds a handful of
deliberately template-hostile names - step 4 is where they surface. Your paths
and counts will differ, and long absolute paths are shortened to
`/home/you/my-ig`. To run it against the public play server instead, use a URL
from [play.im.dhis2.org](https://play.im.dhis2.org/) in step 3 - the instance names
rotate, so pick a current one. To run a DHIS2 locally, see
[the local setup page](../local-setup.md).

If you want one command that tells you whether an instance can carry this whole
chain before you invest in it, run [`d2w fhir doctor`](201-doctor.md) first - it
does every step below in a throwaway workspace and reports what breaks.

## The fastest working facade

The seven steps below build a guide from *your* instance, and steps 3 to 5 are
the ones that need one. If what you want first is to see the thing working -
the forms, the endpoint, the data-entry screens - start from a template
instead. `--template` scaffolds a project pre-populated with a guide already
generated against a real DHIS2 instance, so there is nothing to point at and
nothing to wait for:

```console
$ d2w fhir init demo --template patient-summary
...
│created                │ 13              │
│template               │ patient-summary │
│template files         │ 269             │
...
  laid down 269 files from template `patient-summary` under ig/input/
note: the guide under ig/input/ was generated against a DHIS2 instance already - none is needed to serve it
next: cd demo && make sushi, then `d2w fhir serve . --ui`
$ cd demo && make setup && make sushi
...
| You're making waves now!               0 Errors      0 Warnings |
$ d2w fhir serve . --ui
```

Docker for the compile, and that is the whole dependency list. The endpoint
answers `/metadata` as a FHIR server, the guide it serves holds six
Questionnaires and 83 Locations, and the capture screens are at `/`.

`d2w fhir init --list-templates` names the rest;
[Start from a template](201-set-up-a-project.md#start-from-a-template)
documents what a template supplies and what your own flags override. When you
are ready to publish your own instance's metadata instead, come back to step 1.

## 1. Scaffold a project

Any `d2w` runs this one command - `uv tool install dhis2w-cli` if you have
none yet.

```console
$ d2w fhir init my-ig --id org.example.dhis2 --canonical https://example.org/fhir --publisher "Example Org"
...
  created fhir.toml
  created fhir.toml.example
  created ig/sushi-config.yaml
  created ig/ig.ini
  created ig/fsh.ini
  created ig/input/fsh/aliases.fsh
  created ig/input/pagecontent/index.md
  created ig/input/ignoreWarnings.txt
  created pyproject.toml
  created .python-version
  created Makefile
  created Dockerfile
  created .gitignore
next: set `profile` in fhir.toml, then run `d2w fhir generate`
$ cd my-ig
```

The `...` hides a summary table naming the absolute project directory and
counting what was created - thirteen files, none skipped.

## 2. Install the project's own toolchain

The scaffolded `pyproject.toml` declares the d2w packages and pins them at one
commit, so the plugin and its core are never mismatched builds. `uv sync`
writes `.venv` plus the `uv.lock` that records the pin.

```console
$ uv sync
Using CPython 3.13.14
Creating virtual environment at: .venv
   Updating https://github.com/winterop-com/dhis2w-utils (main)
    Updated https://github.com/winterop-com/dhis2w-utils (0f30586)
Resolved 97 packages in 16.24s
   Building dhis2w-cli @ git+https://github.com/winterop-com/dhis2w-utils@0f30586
   Building dhis2w-fhir @ git+https://github.com/winterop-com/dhis2w-utils@0f30586
...
Prepared 6 packages in 1.14s
Installed 91 packages in 195ms
 + aiofile==3.12.3
...
```

The `...` hide the rest of the six built packages and the 91 installed ones.
Commit `uv.lock`: it is what makes a regenerate reproducible on another
machine.

## 3. Point it at a DHIS2 instance

Secrets are never command-line flags - the password comes from the
`DHIS2_PASSWORD` environment variable (or an interactive prompt). `--local`
keeps the profile beside the project in `.dhis2/profiles.toml`;
`--default` makes it the one `d2w fhir validate` and `d2w fhir generate` pick up.
Alternatively set `profile` in `fhir.toml` - `d2w fhir init --profile demo`
seeds it while scaffolding.

```console
$ DHIS2_PASSWORD=district uv run d2w profile add demo --auth basic --username admin \
    --url http://localhost:8080 --local --default
profile 'demo' saved to /home/you/my-ig/.dhis2/profiles.toml
```

## 4. Check the instance's codes before generating anything

`uv run` drives the toolchain the last step pinned, so the check runs against
the versions `uv.lock` records rather than whatever `d2w` is on your PATH.

The scaffold wrote `hostile_names = "substitute"` into `fhir.toml`, under which
a DHIS2 name carrying `<` is rewritten for publication and nothing stops. This
walkthrough shows the gate instead, so change that one line to
`hostile_names = "refuse"` before running the check. Both roads are real and
[`hostile_names`](301-generation.md#hostile_names) is where to choose between
them; validate grades under whichever one the file states.

```console
$ uv run d2w fhir validate
running 5 step(s)
[1/5] connecting: http://localhost:8080
[2/5] selection: 2 data sets, 4 programs, 3 stages, 70 data elements, 12 option sets, 5 categories, 1,332 organisation units
[3/5] instance sweep: 40 collections, 1,618 objects
[4/5] option sets: 12 read
[5/5] findings: 41 finding(s)
...
                                fhir validate
┌───────────────────┬────────────────────────────────────────────────────────┐
│profile            │ demo (project-toml)                                    │
│resource types     │ 40                                                     │
│objects swept      │ 1618                                                   │
│option sets        │ 12                                                     │
│options            │ 48                                                     │
│attributes         │ 4                                                      │
│errors             │ 6                                                      │
│warnings           │ 7                                                      │
│infos              │ 28                                                     │
│selection findings │ 6 errors, 7 warnings, 20 infos                         │
│code coverage      │ 1/1428 (selection objects whose code can serve as an   │
│                   │ identity stem)                                         │
│code source        │ id                                                     │
│hostile names      │ refuse - every name is published exactly as DHIS2       │
│                   │ states it                                              │
└───────────────────┴────────────────────────────────────────────────────────┘
               findings by category (6)
┏━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃Severity ┃ Scope     ┃ Category              ┃ Count┃
┡━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│error    │ selection │ template-hostile-name │ 6    │
│warning  │ selection │ invalid-code          │ 1    │
│warning  │ selection │ template-hostile-name │ 6    │
│info     │ selection │ spaced-code           │ 20   │
│info     │ instance  │ missing-code          │ 1    │
│info     │ instance  │ template-hostile-name │ 7    │
└─────────┴───────────┴───────────────────────┴──────┘
                                 findings (6)
[one row per error - the object, its code, and the character it carries]
error: 6 error(s) found; exiting 1 (--no-fail to suppress)
```

Validation is one of the quick steps. The `...` hides the
`wrote /home/you/my-ig/reports/fhir-validate-report.{md,csv,pdf}` lines, and the
full findings are in that Markdown report.

**It exited 1, and that is the command working.** Six selected objects carry a
`<` in their name: the category `Age (<5 >5) & sex`, the category options `<1y`
and `<5`, the data element `Vitamin A given to < 5y`, the option set
`Age (<5 - 49) & over`, and the option `<5` inside it. A DHIS2 name stays
byte-true on the `title` of the resource it becomes - escaping it would make the
guide disagree with the instance about what the object is called - and the IG
publisher writes those titles into pages it strict-parses after writing. A `<`
opens a tag there, and the publisher dies on the page it just wrote.

The error grade means one specific thing here: **`d2w fhir generate` refuses a
selection holding any of them**, before it writes a file. These errors are not
advice, they are the gate the next step applies, so validate and generate cannot
disagree about what is publishable. The refusal costs seconds; the same names
reaching the publisher cost a whole build, because it fails in its final output
check, once every resource has already been rendered.

The seven warnings are softer, and a build survives them. Six are the same
character class one grade down - the category options `>1y` and `>5 & over`, the
option `>5 & under 50`, and three organisation units carrying `&`
(`EM&BEE Maternity Home Clinic`, `Leprosy & TB Hospital`, and
`UMC Mitchener Memorial Maternity & Health Centre`). `>` and `&` cost a
malformed page rather than a dead one. The seventh is a different fault: the
category option `Outreach` carries a line break inside its code.

The twenty-eight infos are cosmetic beside those - twenty selected codes with
spaces in them, and eight findings about objects the instance holds but this
project does not select. [Validate the
instance](201-validate.md#read-severity-as-build-impact) explains every grade.

Three honest ways forward, and all of them are real:

- **Fix the names in DHIS2** and run validate again. On your own instance this
  is the one to take: rename the six so no name carries a `<`, and clear the
  `>` and `&` warnings while you are in there.
- **Publish them rewritten.** Put `hostile_names = "substitute"` back and the
  guide publishes `Vitamin A given to under 5y` while DHIS2 keeps the name it
  holds. Validate then grades those six informational and the build survives
  them - [`hostile_names`](301-generation.md#hostile_names) is the whole story.
- **Keep them out of the selection.** A guide publishes what its `fhir.toml`
  names, and nothing obliges it to name everything. Step 5 takes this road,
  because the demo database is not yours to rename.

## 5. Narrow the selection, then generate the IG source

An absent `[generate.*]` table means *everything of that kind*, which is how the
six objects step 4 graded as errors got into the selection. Name the vocabularies
and the form instead, and the offenders are simply not in the guide. Add this to
`fhir.toml` - `d2w fhir init --refresh` never rewrites the file, so hand edits
survive:

```toml
[generate.data_sets]
include_ids = ["TuL8IOPzpHh"]     # EPI Stock - Child Health owns the hostile data element

[generate.option_sets]
include_ids = ["OsVaccType1"]     # naming any keeps Age (<5 - 49) & over out

[generate.categories]
include_ids = ["GLevLNI9wkl"]     # the DHIS2 built-in `default` category alone
```

The organisation units stay unnarrowed, so the registry is still the whole
country. The vocabularies the selected forms bind come along regardless of what
the table names - that is why the run below reports eleven option sets against
one id - and what naming any at all does is stop the *unbound* ones being swept
in, which is where `Age (<5 - 49) & over` was coming from.
`uv run d2w fhir validate` now reports 0 errors and 3 warnings, the three `&`
facility names, and generation is no longer refused:

```console
$ uv run d2w fhir generate
running 8 step(s)
[1/8] instance metadata: 9 questionnaire target(s), 11 option set(s), 1 category, 1,332 organisation unit(s)
[2/8] foundation: 24 written, 0 unchanged
[3/8] option sets: 33 written, 0 unchanged, 1 note
[4/8] categories: 3 written, 0 unchanged
[5/8] questionnaires: 21 written, 0 unchanged, 1 note
[6/8] examples: 9 written, 0 unchanged, 1 note
[7/8] organisation units: 2667 written, 0 unchanged, 1 note
[8/8] pages: 15 written, 0 unchanged, 1 note
full pipeline: 2,772 file(s) written across 7 target(s)
...
note: 4 note(s) across 4 target(s); full list in /home/you/my-ig/reports/fhir-generate-notes.md (--details to print)
```

One of the quick steps. The `...` hides a per-target table naming each output
directory. Note the shape of it: one data set and four programs produced nine
forms, while 1,332 organisation units produced 2,667 files - the registry is
almost always the bulk of an IG, because every unit emits both an `Organization`
and a `Location`.

## 6. Compile it

This is the publish step, and the slow one - the publisher renders a page per
resource, so a big registry sets its wall clock. Nothing in step 7 waits for
it: `serve --live` needs no compile at all, and the compiled `serve` posture
needs only `make sushi`. Come back here when you want the website.

The scaffolded `Dockerfile` carries SUSHI, the IG publisher, and Java, so none
of them is installed on your machine. Build that image once:

```console
$ docker build -t fhir-ig .
...
#8 naming to docker.io/library/fhir-ig:latest done
```

The publisher caches downloaded FHIR packages in a named docker volume, and a
freshly created volume is root-owned - the publisher runs as a non-root user and
cannot write to it. Chown it once, before the first build:

```console
$ docker run --rm -u root -v fhir-ig-cache:/home/publisher/.fhir --entrypoint sh fhir-ig \
    -c "mkdir -p /home/publisher/.fhir/packages && chown -R 1001:1001 /home/publisher/.fhir"
```

Now run the publisher over `ig/`. It compiles the FSH with its own SUSHI on the
way, so this single command is the whole compile. This is the slow step, and the
first run is the slowest; see
[Build and publish the guide](201-build-and-publish.md#keep-the-caches-warm)
for the caches that make every later build cheaper.

```console
$ docker run --rm -v $(pwd)/ig:/home/publisher/ig -v fhir-ig-cache:/home/publisher/.fhir \
		fhir-ig \
		java -Xmx4g -jar /home/publisher/.ig-publisher/publisher.jar ig.ini -ig . -tx http://tx.fhir.org
...
Sushi: ========================= SUSHI RESULTS ===========================
Sushi: |  -------------------------------------------------------------  |
Sushi: | |    Profiles   |  Extensions  |   Logicals   |   Resources   | |
Sushi: | |-------------------------------------------------------------| |
Sushi: | |       7       |      20      |      1       |       0       | |
Sushi: |  -------------------------------------------------------------  |
Sushi: |  -------------------------------------------------------------  |
Sushi: | |      ValueSets     |    CodeSystems    |     Instances      | |
Sushi: | |-------------------------------------------------------------| |
Sushi: | |         8          |         8         |         50         | |
Sushi: |  -------------------------------------------------------------  |
Sushi: |                                                                 |
Sushi: ===================================================================
Sushi: | You are dolphinitely doing great!      0 Errors      0 Warnings |
Sushi: ===================================================================
...
Generating Narratives
Run Template
Generate HTML Outputs
Checking Output HTML
Errors: 11, Warnings: 1413, Info: 1426, Broken Links: 0
```

The `...` hide publisher start-up and the long tail. A first build with cold
caches is much the most expensive thing in the chain and gets far cheaper once
they are warm, and the registry is what makes it long - which is why
[`max_level`](301-what-goes-in.md) is the dial worth knowing about.

The SUSHI counts are worth a second look, because they show the split the
generator makes. SUSHI compiled 7 profiles, 20 extensions, 1 logical model, and
only 8 CodeSystems - the shared ones. All 2,664 registry resources are not in that
table at all: they are written as pre-built FHIR JSON and loaded verbatim, which is
what keeps SUSHI's part of the run to a small slice of it. Nearly all the rest is
the publisher: narratives, the template, a rendered page per artifact, and Jekyll
over the result.

The last line of the transcript is the publisher's own QA pass over the site it
wrote, and not the build's exit status - this run exited 0 with `ig/output/`
complete and browsable. Those counts are what the publisher makes of the guide's
content, mostly terminology conventions a generated IG does not follow;
[Troubleshooting](201-troubleshooting.md) covers reading them.

### Why the hostile names were worth catching in step 4

The build above reached its end because step 5 kept the six objects step 4 named
out of the selection. Had any of them stayed in, there would have been no build to
reach: `d2w fhir generate` refuses before writing a file, naming the object and
the character it carries.

```
error | selection | template-hostile-name | optionSets | Age (<5 - 49) & over (OsFhirEscS1)
  name Age (<5 - 49) & over contains '<' which the IG publisher template injects
  into HTML unescaped, so `make build` fails: the publisher strict-parses the page
  it just wrote and cannot read it back; change the name in DHIS2
```

That is the whole argument for the gate sitting where it does. The alternative is
not a warning, it is this build failing in its final output check - after every one
of those 2,664 registry resources has been rendered - on a page the publisher wrote
itself and then could not read back. Read `template-hostile-name` as build-breaking
rather than cosmetic. Angle brackets are ordinary in real DHIS2 metadata (`<1y`,
`< 5y`, `>5 & over` are all real names on this instance), so this is worth checking
on any instance before you invest a build in it. The
[`refused-names`](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/fhir/igs/refused-names)
example is a project that keeps one in on purpose, so you can watch the refusal.

Open the generated site:

```console
$ open ig/output/index.html
```

The scaffold's Makefile wraps every command on this page, and that is the only
mention it gets here: `make validate` and `make generate` are the `uv run d2w`
lines above verbatim, while `make build` adds the cache chown and a `JAVA_HEAP`
knob to the publisher invocation. [Set up an IG
project](201-set-up-a-project.md) documents the targets.

## 7. Serve it as a FHIR endpoint

Publishing the site is one way to hand the guide over. The other is to run it
as a live FHIR endpoint a client can call:

```console
$ uv run d2w fhir serve --port 8091
starting /home/you/my-ig on http://127.0.0.1:8091 as a FHIR endpoint (ctrl-c to stop)
INFO dhis2w_fhir_serve loaded the compiled IG at /home/you/my-ig: 2803 resources across 14 types, 0 stored responses
```

It binds loopback, and by default it asks nobody who they are - so reaching it
from another host is a deliberate act, and one this server refuses until
[`[serve] auth`](301-serving.md#auth) says who it serves. The port is worth
stating on this instance:
`[serve] port` defaults to 8080, which is where the DHIS2 you just read from is
listening. Now any FHIR client can read what you published:

```console
$ curl -s localhost:8091/Questionnaire/TuL8IOPzpHh | jq .title
"EPI Stock"
```

Three things beyond reading are worth knowing exist:

- **`d2w fhir serve --live`** skips the compile entirely and builds the store
  straight off the DHIS2 instance at startup, which is the fastest way to look at
  what your metadata would publish as. [Serve the guide](201-serve.md) covers
  both modes.
- **`d2w fhir serve --ui`** adds a [browser capture UI](201-capture-ui.md) at `/`, so
  a person can fill one of these forms in and submit it. It needs a serve
  installed from a wheel, which ships the built front end.
- **The register.** A running serve also answers `GET /Patient` with the
  instance's tracked entities, published as whatever resource type your project
  maps each tracked entity type to.

What a client captures lands in a local spool, and
[`d2w fhir forward`](201-forward.md) drains it back into DHIS2 - dry run by
default - which closes the loop from published contract to data in the
instance.

Next: [Set up an IG project](201-set-up-a-project.md), or
[Run a secured facade](201-run-a-secured-facade.md) for the same road carried
through securing and forwarding.
