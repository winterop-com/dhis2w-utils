# Quickstart: from nothing to a served IG

**Who this is for:** anyone who wants a generated, compiled Implementation
Guide in a browser before reading anything longer.

**Before you start:** `uv` and Docker installed; network access to a DHIS2
instance - and ten minutes of reading FHIR terms in
[FHIR for DHIS2 people](101-fhir-concepts.md) if words like CodeSystem are new.

**You will be able to:**

- scaffold a dockerized IG project with a pinned toolchain
- validate and generate IG source from a live DHIS2 instance
- compile the guide, open it in a browser, and serve it as a FHIR endpoint

Seven steps. The first five take seconds each; the sixth is where the wall clock
goes - budget tens of minutes for the first compile.

Command output below was captured on a real run against a local DHIS2 2.43.1
carrying the Sierra Leone demo database. Your paths, counts, and timings will
differ, and long absolute paths are shortened to `/home/you/my-ig`. To run it
against the public play server instead, use a URL from
[play.im.dhis2.org](https://play.im.dhis2.org/) in step 3 - the instance names
rotate, so pick a current one. To run a DHIS2 locally, see
[the local setup page](../../local-setup.md).

If you want one command that tells you whether an instance can carry this whole
chain before you invest in it, run [`d2w fhir doctor`](201-doctor.md) first - it
does every step below in a throwaway workspace and reports what breaks.

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
`--default` makes it the one `make validate` and `make generate` pick up.
Alternatively set `profile` in `fhir.toml` - `d2w fhir init --profile demo`
seeds it while scaffolding.

```console
$ DHIS2_PASSWORD=district uv run d2w profile add demo --auth basic --username admin \
    --url http://localhost:8080 --local --default
profile 'demo' saved to /home/you/my-ig/.dhis2/profiles.toml
```

## 4. Check the instance's codes before generating anything

```console
$ make validate
uv run d2w fhir validate
running 5 step(s)
[1/5] connecting: http://localhost:8080
[2/5] selection: 2 data sets, 6 programs, 5 stages, 70 data elements, 13 option sets, 5 categories, 1,332 organisation units
[3/5] instance sweep: 40 collections, 1,634 objects
[4/5] option sets: 13 read
[5/5] findings: 41 finding(s)
...
                                 fhir validate
┌───────────────────┬──────────────────────────────────────────────────────────┐
│profile            │ demo (project-toml)                                      │
│resource types     │ 40                                                       │
│objects swept      │ 1634                                                     │
│option sets        │ 13                                                       │
│options            │ 52                                                       │
│attributes         │ 4                                                        │
│errors             │ 0                                                        │
│warnings           │ 8                                                        │
│infos              │ 33                                                       │
│selection findings │ 0 errors, 8 warnings, 20 infos                           │
│code coverage      │ 1/1433 (selection objects whose code can serve as an     │
│                   │ identity stem)                                           │
│code source        │ id                                                       │
└───────────────────┴──────────────────────────────────────────────────────────┘
               findings by category (5)
┏━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃Severity ┃ Scope     ┃ Category              ┃ Count┃
┡━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│warning  │ selection │ template-hostile-name │ 8    │
│info     │ selection │ spaced-code           │ 20   │
│info     │ instance  │ invalid-code          │ 1    │
│info     │ instance  │ missing-code          │ 1    │
│info     │ instance  │ template-hostile-name │ 11   │
└─────────┴───────────┴───────────────────────┴──────┘
ok: passed: 8 selection warning(s), 20 selection info(s), 13 instance finding(s)
```

That run took four seconds. The `...` hides the
`wrote /home/you/my-ig/reports/fhir-validate-report.{md,csv,pdf}` lines, and the
full findings are in that Markdown report.

Zero errors means nothing blocks generation, but do not read the warnings as
cosmetic - read the report before you build. On this instance the eight
`template-hostile-name` warnings are the ones that matter, and step 6 shows one of
them ending a seventeen-minute publisher run.
[Validate the instance](201-validate.md#read-severity-as-build-impact) explains the
grades.

## 5. Generate the IG source

```console
$ make generate
uv run d2w fhir generate
running 8 step(s)
[1/8] instance metadata: 14 questionnaire target(s), 13 option set(s), 5 categories, 1,332 organisation unit(s)
[2/8] foundation: 23 written, 0 unchanged
[3/8] option sets: 39 written, 0 unchanged
[4/8] categories: 15 written, 0 unchanged
[5/8] questionnaires: 28 written, 0 unchanged, 1 note
[6/8] examples: 14 written, 0 unchanged, 2 notes
[7/8] organisation units: 2667 written, 0 unchanged
[8/8] pages: 20 written, 0 unchanged, 1 note
full pipeline: 2,806 file(s) written across 7 target(s)
...
note: 4 note(s) across 3 target(s); full list in /home/you/my-ig/reports/fhir-generate-notes.md (--details to print)
```

Also four seconds, against an instance this size. The `...` hides a per-target
table naming each output directory. Note the shape of it: two data sets and six
programs produced fourteen forms, while 1,332 organisation units produced 2,667
files - the registry is almost always the bulk of an IG, because every unit
emits both an `Organization` and a `Location`.

## 6. Compile it

`make setup` builds the docker image once - SUSHI, the IG publisher, and Java
all live in it, so none of them is installed on your machine.

```console
$ make setup
docker build -t fhir-ig .
...
#8 naming to docker.io/library/fhir-ig:latest done
#8 DONE 0.1s
```

`make build` runs the full IG publisher, which compiles the FSH with its own
SUSHI on the way. This is the slow step, and the first run is the slowest; see
[Build and publish the guide](201-build-and-publish.md#keep-the-caches-warm)
for the caches that make every later build cheaper.

```console
$ make build
docker run --rm -v $(pwd)/ig:/home/publisher/ig -v fhir-ig-cache:/home/publisher/.fhir \
		fhir-ig \
		java -Xmx4g -jar /home/publisher/.ig-publisher/publisher.jar ig.ini -ig . -tx http://tx.fhir.org
...
Sushi: ========================= SUSHI RESULTS ===========================
Sushi: |  -------------------------------------------------------------  |
Sushi: | |    Profiles   |  Extensions  |   Logicals   |   Resources   | |
Sushi: | |-------------------------------------------------------------| |
Sushi: | |       7       |      19      |      1       |       0       | |
Sushi: |  -------------------------------------------------------------  |
Sushi: |  -------------------------------------------------------------  |
Sushi: | |      ValueSets     |    CodeSystems    |     Instances      | |
Sushi: | |-------------------------------------------------------------| |
Sushi: | |         7          |         7         |         60         | |
Sushi: |  -------------------------------------------------------------  |
Sushi: |                                                                 |
Sushi: ===================================================================
Sushi: | Ac-clam-ations!                        0 Errors      0 Warnings |
Sushi: ===================================================================
...
Generating Narratives                              (00:34.062)
Run Template                                       (08:19.109)
Generate HTML Outputs                              (10:36.070)
Jekyll: done in 34.278 seconds.                    (16:15.377)
Checking Output HTML                               (16:23.794)
```

The `...` hide publisher start-up and the long tail. Expect tens of minutes on a
first build with cold caches, and far less once they are warm; the registry is what
makes it long, which is why [`max_level`](301-what-goes-in.md) is the dial worth
knowing about.

Those counts are worth a second look, because they show the split the generator
makes. SUSHI compiled 7 profiles, 19 extensions, 1 logical model, and only 7
CodeSystems - the shared ones. The option-set and category terminology and all 2,664
registry resources are not in that table at all: they are written as pre-built FHIR
JSON and loaded verbatim, which is what keeps SUSHI's part of the run to twelve
seconds. The other sixteen minutes are the publisher: narratives, the template, a
rendered page per artifact, and Jekyll over the result.

### When a DHIS2 name is hostile to the template

This run did not finish cleanly, and the reason is worth knowing before you meet it:

```console
Publishing Content Failed: Unable to process page output/en/CodeSystem-d2-os-OsFhirEscS1-cs.html
Caused by: org.hl7.fhir.exceptions.FHIRFormatError: Unable to read attribute '49' value on <5>
make: *** [build] Error 1
```

The option set behind that page is named `Age (<5 - 49) & over`. The publisher
injects that name into the HTML it generates without escaping the `<`, then fails
re-parsing its own output - it reads `<5 - 49)` as a tag. `make build` exits non-zero
after about seventeen minutes.

`make validate` predicted it exactly, back in step 4:

```
warning | selection | template-hostile-name | Age (<5 - 49) & over (OsFhirEscS1)
  name contains '<' which the IG publisher template injects into HTML unescaped
```

So read `template-hostile-name` as build-breaking, not cosmetic, and rename the
offending objects in DHIS2 before building. Angle brackets are common in real DHIS2
metadata - `<1y`, `< 5y`, `>5 & over` are ordinary category option and data element
names - so this is worth checking on any instance.

The site itself was still written: the failure comes at the final output check, after
Jekyll has rendered everything, so `ig/output/` holds a complete browsable guide even
on this run. [Troubleshooting](201-troubleshooting.md) covers the other ways a
publisher run ends badly.

Open the generated site:

```console
$ open ig/output/index.html
```

Every make target drives `d2w` through `uv run`, so `make validate` and
`make generate` are `uv run d2w fhir validate` / `uv run d2w fhir generate`
against the pinned build - spell either form, they do the same thing.
`make clean` removes build output; `make clean-all` also drops the caches.

## 7. Serve it as a FHIR endpoint

Publishing the site is one way to hand the guide over. The other is to run it
as a live FHIR endpoint a client can call:

```console
$ make serve
uv run d2w fhir serve
starting /home/you/my-ig on http://127.0.0.1:8091 as a FHIR endpoint (ctrl-c to stop)
INFO dhis2w_fhir_serve loaded the compiled IG at /home/you/my-ig: 2830 resources across 14 types, 0 stored responses
```

It binds loopback, because the facade has no authentication - reaching it from
another host is a deliberate act. Now any FHIR client can read what you
published:

```console
$ curl -s localhost:8091/Questionnaire/BfMAe6Itzgt | jq .title
"Child Health"
```

Three things beyond reading are worth knowing exist:

- **`make serve-live`** skips the compile entirely and builds the store straight
  off the DHIS2 instance at startup, which is the fastest way to look at what
  your metadata would publish as. [Serve the guide](201-serve.md) covers both
  modes.
- **`make serve-ui`** adds a [browser capture UI](201-capture-ui.md) at `/`, so
  a person can fill one of these forms in and submit it. It needs a serve
  installed from a wheel, which ships the built front end.
- **The register.** A running serve also answers `GET /Patient` with the
  instance's tracked entities, published as whatever resource type your project
  maps each tracked entity type to.

What a client captures lands in a local spool, and
[`d2w fhir forward`](201-forward.md) drains it back into DHIS2 - dry run by
default - which closes the loop from published contract to data in the
instance.

Next: [Set up an IG project](201-set-up-a-project.md)
