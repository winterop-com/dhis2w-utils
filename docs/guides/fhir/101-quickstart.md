# Quickstart: six commands to a served IG

**Who this is for:** anyone who wants a generated, compiled Implementation
Guide in a browser before reading anything longer.

**Before you start:** `uv` and Docker installed; network access to a DHIS2
instance (the commands below use the public play server) - and ten minutes of
reading FHIR terms in [FHIR for DHIS2 people](101-fhir-concepts.md) if words
like CodeSystem are new.

**You will be able to:**

- scaffold a dockerized IG project with a pinned toolchain
- validate and generate IG source from a live DHIS2 instance
- compile the guide and open it in a browser

Command output below was captured on a real run against
`https://play.im.dhis2.org/dev-2-42`; your paths, counts, and timings will
differ. Play server instance names rotate - if the URL 404s, pick a current
instance from [play.im.dhis2.org](https://play.im.dhis2.org/), or run a
[local DHIS2](../../local-setup.md) and point the profile at
`http://localhost:8080`.

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

The `...` hides a summary table naming the absolute project directory.

## 2. Install the project's own toolchain

The scaffolded `pyproject.toml` declares d2w, and `uv sync` writes `.venv`
plus the `uv.lock` that pins it.

```console
$ uv sync
Using CPython 3.13.14
Creating virtual environment at: .venv
Resolved 97 packages in 298ms
Installed 91 packages in 155ms
 + aiofile==3.12.3
 + aiosqlite==0.22.1
 + annotated-doc==0.0.5
...
 + uvicorn==0.52.1
 + watchfiles==1.2.0
 + websockets==17.0.1
```

The `...` hides the rest of the 91 installed packages.

## 3. Point it at a DHIS2 instance

Secrets are never command-line flags - the password comes from the
`DHIS2_PASSWORD` environment variable (or an interactive prompt). `--local`
keeps the profile beside the project in `.dhis2/profiles.toml`;
`--default` makes it the one `make validate` and `make generate` pick up.
Alternatively set `profile` in `fhir.toml` - `d2w fhir init --profile demo`
seeds it while scaffolding.

```console
$ DHIS2_PASSWORD=district uv run d2w profile add demo --auth basic --username admin \
    --url https://play.im.dhis2.org/dev-2-42 --local --default
profile 'demo' saved to /home/you/my-ig/.dhis2/profiles.toml
```

## 4. Check the instance's codes before generating anything

```console
$ make validate
uv run d2w fhir validate
running 5 step(s)
[1/5] connecting: https://play.im.dhis2.org/dev-2-42
[2/5] selection: 26 data sets, 14 programs, 21 stages, 980 data elements, 171
option sets, 22 categories, 1,332 organisation units
[3/5] instance sweep: 60 collections, 4,631 objects
[4/5] option sets: 171 read
[5/5] findings: 451 finding(s)
...
                                 fhir validate
┌───────────────────┬──────────────────────────────────────────────────────────┐
│profile            │ demo (project-toml)                                      │
│resource types     │ 60                                                       │
│objects swept      │ 4631                                                     │
│option sets        │ 171                                                      │
│options            │ 15209                                                    │
│attributes         │ 11                                                       │
│errors             │ 0                                                        │
│warnings           │ 67                                                       │
│infos              │ 384                                                      │
│selection findings │ 0 errors, 67 warnings, 288 infos                         │
│code coverage      │ 26/2565 (selection objects whose code can serve as an    │
│                   │ identity stem)                                           │
│code source        │ id                                                       │
└───────────────────┴──────────────────────────────────────────────────────────┘
```

The `...` hides the `wrote reports/fhir-validate-report.{md,csv,pdf}` lines,
and a findings-by-category table follows the summary. Zero errors means every
finding is advisory for the default configuration -
[Validate the instance](201-validate.md#read-severity-as-build-impact) explains the grades.

## 5. Generate the IG source

```console
$ make generate
uv run d2w fhir generate
running 8 step(s)
[1/8] instance metadata: 61 questionnaire target(s), 171 option set(s), 22
categories, 1,332 organisation unit(s)
[2/8] foundation: 16 written, 0 unchanged
[3/8] option sets: 513 written, 0 unchanged
[4/8] categories: 66 written, 0 unchanged
[5/8] questionnaires: 112 written, 0 unchanged, 7 notes
[6/8] examples: 61 written, 0 unchanged, 8 notes
[7/8] organisation units: 2667 written, 0 unchanged
[8/8] pages: 67 written, 0 unchanged, 7 notes
full pipeline: 3,502 file(s) written across 7 target(s)
...
```

The `...` hides a per-target table naming each output directory and a pointer
to `reports/fhir-generate-notes.md`.

## 6. Compile it

`make setup` builds the docker image once - SUSHI, the IG publisher, and Java
all live in it, so neither is installed on your machine.

```console
$ make setup
docker build -t fhir-ig .
#0 building with "desktop-linux" instance using docker driver
...
#8 naming to docker.io/library/fhir-ig:latest done
#8 DONE 0.1s
```

`make build` runs the full IG publisher, which compiles the FSH with its own
SUSHI on the way. The first build is the slow one; see
[Build and publish the guide](201-build-and-publish.md#keep-the-caches-warm) for the caches that make every later
build cheaper.

```console
$ make build
docker run --rm -v $(pwd)/ig:/home/publisher/ig -v fhir-ig-cache:/home/publisher/.fhir \
		fhir-ig \
		java -Xmx4g -jar /home/publisher/.ig-publisher/publisher.jar ig.ini -ig . -tx http://tx.fhir.org
...
Sushi: info  Preprocessed 145 documents with 19 aliases.
Sushi: info  Imported 30 definitions and 152 instances.
...
Sushi: ========================= SUSHI RESULTS ===========================
Sushi: |  -------------------------------------------------------------  |
Sushi: | |    Profiles   |  Extensions  |   Logicals   |   Resources   | |
Sushi: | |-------------------------------------------------------------| |
Sushi: | |       6       |      12      |      0       |       0       | |
Sushi: |  -------------------------------------------------------------  |
Sushi: |  -------------------------------------------------------------  |
Sushi: | |      ValueSets     |    CodeSystems    |     Instances      | |
Sushi: | |-------------------------------------------------------------| |
Sushi: | |         6          |         6         |        152         | |
Sushi: |  -------------------------------------------------------------  |
Sushi: |                                                                 |
Sushi: ===================================================================
Sushi: | O-fish-ally error free!                0 Errors      0 Warnings |
Sushi: ===================================================================
...
Generating Narratives
...
```

The first `...` hides publisher start-up, the later ones the long tail: after
SUSHI compiles the FSH, the publisher spends most of the run generating
narratives and validating every resource against the terminology server -
tens of minutes on a first build with cold caches, and far less once they are
warm.

Open the generated site:

```console
$ open ig/output/index.html
```

Every make target drives `d2w` through `uv run`, so `make validate` and
`make generate` are `uv run d2w fhir validate` / `uv run d2w fhir generate`
against the pinned build - spell either form, they do the same thing.
`make clean` removes build output; `make clean-all` also drops the caches.

To point a FHIR client at the guide instead of publishing it,
[`d2w fhir serve`](201-serve.md) runs the compiled project as a
read-and-capture endpoint, and [`d2w fhir forward`](201-forward.md) posts what
that endpoint captured back into DHIS2, closing the loop.

Next: [Set up an IG project](201-set-up-a-project.md)
