# Set up an IG project

You have a DHIS2 instance. It holds data sets, programs, option sets,
category combinations, and an organisation-unit hierarchy, and someone
outside DHIS2 now needs to read forms out of it and send data back. This page
makes the directory that does that: one command writes a project that reads
your instance's metadata and turns it into a published package other systems
can consume. The package is a FHIR Implementation Guide; nothing on this page
asks you to know what that means.

**Who this is for:** the DHIS2 implementer standing that project up for the
first time, and the operator bringing an existing one up to the current
toolchain.

**Before you start:** `uv` installed, a `d2w` you can run (`uv tool install
dhis2w-cli` gives you one anywhere), and a DHIS2 instance you can reach.
Docker is not needed until you compile - see
[Build and publish the guide](201-build-and-publish.md).

**You will be able to:**

- scaffold a complete, reproducible IG project with one command
- install the project's pinned toolchain and know why the pin exists
- point the project at the right DHIS2 instance, without credentials on disk
- bring an older project up to the current d2w without losing your edits

## Scaffold the project

`d2w fhir init` writes the whole project: config, SUSHI skeleton, a
`pyproject.toml` that pins the toolchain, a Makefile, and a Dockerfile.

```console
$ d2w fhir init demo-ig --id dhis2.fhir.demo \
    --canonical http://example.org/fhir/demo \
    --publisher "Demo Organisation" --profile local_basic
                                   fhir init
┌──────────┬──────────────────────────┐
│directory │ /home/you/demo-ig        │
│created   │ 13                       │
│skipped   │ 0                        │
└──────────┴──────────────────────────┘
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
next: run `d2w fhir generate` (profile `local_basic`)
```

The flags that matter, all optional:

| Flag | What it seeds |
| --- | --- |
| `--id` | IG package id (default `dhis2.fhir.example`). |
| `--canonical` | Canonical base URL, no trailing slash. |
| `--name`, `--title` | SUSHI name and IG title, derived from `--id` when omitted. |
| `--publisher` | Publisher name. |
| `--publisher-url` | Publisher home page. Omit it unless you have a real site: the IG publisher links it from every generated page, and pointing it at the canonical yields one broken link per page. |
| `--status` | `draft` (default) or `active`; drives the sushi-config status and the status and experimental flag on every generated definitional resource. |
| `--profile` | Seeds the `profile` key of `fhir.toml`, so `d2w fhir generate` reads that instance without a flag. |
| `--sushi-timeout` | Seconds the IG publisher gives its internal SUSHI run (default 1800), written to `ig/fsh.ini`. |
| `--max-level` | Deepest organisation-unit level to generate, seeding `[generate.organisation_units]` `max_level`. Rejected below 1. |
| `--data-set`, `--event-program`, `--tracker-program` | UIDs to seed the `[generate.*]` `include_ids` selection tables with (each repeatable). |
| `--template` | Pre-populate the project from a guide already generated against a real DHIS2 instance - see [Start from a template](#start-from-a-template). |
| `--list-templates` | Name every template this install can scaffold from, one line each, and exit. |
| `--force` | Overwrite scaffold files that already exist. |
| `--refresh` | Bring an existing project's scaffold up to date - see below. Rejects `--force`. |

Every seeding flag is offline: values are written to `fhir.toml` as given and
never checked against an instance. `init` writes a minimal `fhir.toml` holding
the IG identity and one standing choice - `hostile_names = "substitute"`, since
almost every instance names an age band with a `<` the IG publisher cannot
survive ([what it does](301-generation.md#hostile_names)) - plus
`fhir.toml.example` documenting every option with its default; copy what you
need across, and anything you omit keeps its default.

## Start from a template

Everything above scaffolds an empty project: the skeleton is there, and the
guide inside it arrives when `d2w fhir generate` reads your instance. A
template skips that wait. `--template` lays down a guide someone already
generated against a real DHIS2 instance, so the project compiles and serves
without reaching an instance at all.

```console
$ d2w fhir init --list-templates
                              fhir init --template (9)
┌────────────────────────┬──────────┬────────────────────────────────────────────┐
│template                │ ships in │ publishes                                  │
├────────────────────────┼──────────┼────────────────────────────────────────────┤
│aggregate-minimal       │ bundled  │ The smallest complete guide: the forms,    │
│                        │          │ one district, no category axes.            │
│event-program           │ bundled  │ A program without registration: one        │
│                        │          │ Questionnaire, one occurrence date, no     │
│                        │          │ enrollment.                                │
│patient-summary         │ bundled  │ An International Patient Summary at        │
│                        │          │ $summary: who a person is, and which       │
│                        │          │ recorded values are doses.                 │
│aggregate-disaggregated │ checkout │ Disaggregated aggregate example guide      │
│facility-mixed          │ checkout │ Mixed facility example guide               │
│refused-names           │ checkout │ Refused names example guide                │
│registry-district       │ checkout │ District registry example guide            │
│terminology-strict      │ checkout │ Strict terminology example guide           │
│tracker-registration    │ checkout │ Tracker registration example guide         │
└────────────────────────┴──────────┴────────────────────────────────────────────┘
note: a bundled template rides the installed package; a checkout one is read from
examples/fhir/igs/ of the dhis2w-utils repository and exists only in a clone of it
```

The listing comes off the template manifest, so it names what this install
actually holds rather than what some page once said it held. A bundled
template's line is written for it; a checkout one's is its guide's own title.

**Bundled or checkout.** A bundled template rides the installed package and
works anywhere `d2w` does. A checkout one is read from
[`examples/fhir/igs/`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/igs/README.md)
of the dhis2w-utils repository, which no wheel carries, so it scaffolds only
from a clone. Three of the nine ride the wheel; asking an installed package for
one of the other six is refused by saying where it lives:

```console
$ d2w fhir init demo --template facility-mixed
error: template `facility-mixed` belongs to the example catalog, which ships in the
dhis2w-utils repository rather than in an installed package. This install carries
aggregate-minimal, event-program, patient-summary. Run `d2w fhir init` from a clone
of the repository to scaffold from `facility-mixed`.
```

**What a template supplies, and what your flags supply.** The template is the
default and the flag wins:

| Value | Without a flag | With a flag |
| --- | --- | --- |
| `--id`, `--canonical` | The template's own. | Yours. |
| `--name`, `--title` | The template's own, but only while you keep its `--id`; name a different `--id` and they derive from yours as usual. | Yours. |
| `--publisher`, `--status`, `--publisher-url` | The scaffold's defaults, never the template's - a project you scaffold is published by you. | Yours. |
| `--profile` | Absent, exactly as an ordinary `init`. A template serves without an instance, so nothing needs one until you generate. | Yours. |
| The `[generate]` and `[ips]` selection | The template's, appended to the scaffolded `fhir.toml`. | Refused - see below. |

**`--canonical` reaches the whole tree.** A pre-built resource states its
canonical in full - `Questionnaire.url`, `CodeSystem.url`, every `valueSet`
reference - 409 of them in the smallest template. Scaffolding rewrites every
one from the template's address to yours, so a project with a canonical of its
own publishes nothing under the template's name.

**A template refuses a selection of its own.** `--data-set`,
`--event-program`, `--tracker-program`, and `--max-level` are rejected beside
`--template`: the template ships the tree its own selection produced, and
writing a different selection into `fhir.toml` would state one thing in the
configuration and another in the files beside it. Scaffold first, then edit
`fhir.toml` and run `d2w fhir generate` against an instance that holds what you
named.

**Your scaffold files stay yours.** Three of the files `init` writes live under
`ig/input/` - `fsh/aliases.fsh`, `pagecontent/index.md`, and
`ignoreWarnings.txt`. A template payload never lands on one of them, so
[`--refresh`](#refresh-an-older-projects-scaffold) still maintains exactly the
files it wrote.

To take a template somewhere real, point the project at your own instance and
regenerate: set `profile`, edit the selection to UIDs that instance holds, and
run `d2w fhir generate`. That rewrites `ig/input/` from your metadata, and the
template's content is gone - which is the intent. Until then it is a working
guide you can read, compile, and serve.

## Install the pinned toolchain

The scaffolded project is a `uv` project. Its `pyproject.toml` declares
`dhis2w-cli`, `dhis2w-fhir`, and `dhis2w-fhir-serve` - the CLI, the
generator, and the server `d2w fhir serve` runs on:

```console
$ cd demo-ig
$ uv sync
Resolved 97 packages in 4ms
Checked 91 packages in 11ms
```

(The first run also downloads and installs the packages; later runs just
check.) Three facts make the project reproducible:

- **`uv.lock` is committed.** The FSH a project publishes is a function of
  the d2w build that wrote it, so the lock is what makes a regenerate
  reproducible on any machine. The scaffolded `.gitignore` covers `.venv/`
  and deliberately does not cover `uv.lock`.
- **`.python-version` pins the interpreter** (`3.13`, matching
  `requires-python`). An older project gains it via `d2w fhir init --refresh`.
- **The three packages resolve from PyPI as one release.** Each package's own
  dependency floors hold the CLI, the generator, and the server to the same
  version, and the lock pins the exact one - a CLI paired with a plugin from a
  different build is not a combination anyone tests. The published wheels are
  also what ships the capture UI. To track the repository's `main` branch
  instead of releases, add a `[tool.uv.sources]` git entry per package; the
  scaffolded `pyproject.toml` shows the shape.

Every scaffolded make target drives `d2w` through `uv run`, so `make
validate` and `make generate` are `uv run d2w fhir validate` / `uv run d2w
fhir generate` against the pinned build - spell either form, they do the
same thing:

```console
$ make help
help         Show available targets
setup        Build the SUSHI + IG publisher docker image
upgrade      Rebuild the image from scratch, pulling the latest SUSHI + IG publisher
generate     Regenerate FSH from DHIS2 metadata
update       Update the project to the current d2w: move the toolchain pin, sync, refresh the scaffold-managed files
validate     Check the DHIS2 instance's codes/names for FHIR-safety (writes md/csv/pdf; exit 1 on errors)
check        Scan the artifacts on disk for what aborts the IG publisher (offline, seconds, exit 1 on findings)
cache-init   Ensure the shared package-cache volume is writable by the publisher user
sushi        Compile FSH to FHIR resources
build        Run the full IG publisher
serve        Serve the compiled IG as a FHIR endpoint, with the capture UI at / (run generate + sushi first)
serve-live   Serve straight from the DHIS2 instance, with the capture UI at / - no compile needed
forward      Dry-run the capture spool against DHIS2 - validate only, nothing written, nothing moved
forward-import Import the capture spool into DHIS2 and file every receipt by what it became
clean        Remove build output (keeps ig/input-cache, the terminology cache the next build reuses)
clean-all    Also remove the terminology cache and the FHIR package cache volume
refresh      Wipe build output, pull latest tooling, regenerate, revalidate, rebuild (keeps the caches)
```

Move the pin when you want the newer toolchain, not by accident:

```bash
uv lock --upgrade
uv sync
```

Then regenerate and rebuild against the new pin. `make refresh` is the one
target worth using over the raw commands, because it is a chain no single
command replaces: it drops both caches, rebuilds the docker image from
scratch, then runs `d2w fhir generate`, `d2w fhir validate`, and the
publisher in order - tolerating validate's exit 1 so a full rebuild still
produces fresh reports, and skipping SUSHI because the publisher runs its
own.

```bash
make refresh
```

## Point it at a DHIS2 instance

Generation reads its config from the nearest `fhir.toml`, discovered by
walking up from the working directory - the same idiom as
`.dhis2/profiles.toml`. The profile it connects with resolves in this order,
first match wins:

| Order | Source |
| --- | --- |
| 1 | the global `-p` / `--profile` option on the `d2w` command |
| 2 | the `DHIS2_PROFILE` environment variable |
| 3 | the `profile` key in `fhir.toml` |
| 4 | the default profile from your `profiles.toml` |

Write step 3 while scaffolding with `d2w fhir init --profile <name>`, or set
the key by hand later - both land in the same place. If you have no profile
yet, create one:

```console
$ DHIS2_PASSWORD=district uv run d2w profile add local_basic --auth basic --username admin \
    --url http://localhost:8080 --local --default
profile 'local_basic' saved to /home/you/demo-ig/.dhis2/profiles.toml
```

`--local` writes it into the project's own `.dhis2/profiles.toml`, so the
project carries its instance with it. A name that also exists in your global
store is not an error - the run says which one wins:

```text
warning: a profile named 'local_basic' also exists in the global scope; the project-scoped
one will override it when you're in this directory.
```

Secrets are never command-line flags - the password comes from the
`DHIS2_PASSWORD` environment variable (or an interactive prompt when it is
unset).

Credentials never live in `fhir.toml`. It is committed project config: it
names a profile, and the profile store holds the secret.

`d2w fhir validate` needs no `fhir.toml` at all - it targets an instance,
not a project, so it runs anywhere. See
[Validate the instance](201-validate.md) for what changes inside a project.

## Refresh an older project's scaffold

The scaffold grows: a `path-resource` glob lands in `ig/sushi-config.yaml`,
an entry lands in `.gitignore`, a menu entry lands beside the others - and a
project scaffolded before that carries none of them. `--refresh` re-renders
the scaffold for an existing project and writes what it safely can:

```console
$ d2w fhir init . --refresh
                              fhir init --refresh
┌────────────────────┬──────────────────────────┐
│directory           │ /home/you/demo-ig        │
│created             │ 0                        │
│refreshed           │ 0                        │
│unchanged           │ 12                       │
│with your additions │ 0                        │
│diverged (kept)     │ 0                        │
└────────────────────┴──────────────────────────┘
  unchanged fhir.toml.example
  unchanged ig/sushi-config.yaml
  unchanged ig/ig.ini
  unchanged ig/fsh.ini
  unchanged ig/input/fsh/aliases.fsh
  unchanged ig/input/pagecontent/index.md
  unchanged ig/input/ignoreWarnings.txt
  unchanged pyproject.toml
  unchanged .python-version
  unchanged Makefile
  unchanged Dockerfile
  unchanged .gitignore
note: fhir.toml is yours - a refresh never writes it
```

The rule is one sentence: **a file is rewritten only when the current
scaffold render reproduces every line already on disk, in order.** So a
refresh can only add what the scaffold gained, and no line you wrote is ever
dropped. Every file gets one of five outcomes, all of them printed:

| Outcome | Meaning |
| --- | --- |
| `created` | A scaffold file the project did not have. Written. |
| `refreshed` | The render carries every line on disk plus more. Rewritten. |
| `unchanged` | Already byte-identical to the current scaffold. |
| `with your additions` | Carries every line the current scaffold renders, plus lines of your own. Nothing to add, so nothing is written. |
| `diverged (kept)` | Holds lines the current scaffold does not write - your edits, or scaffold lines that have since changed; a line-preserving refresh cannot tell which. Your version stays, reported as `kept <path> (holds lines the current scaffold does not write)`. To take the scaffold's version, delete the file and refresh again. |

`fhir.toml` is never written - it is your configuration, and a refresh skips
it outright. The IG identity comes off the project itself: `[ig]` and the
selection tables from `fhir.toml`, the SUSHI timeout from `ig/fsh.ini`, and
the publisher URL plus copyright year from `ig/sushi-config.yaml`.

!!! warning "A scaffold line you deliberately deleted comes back"
    Deleting a line leaves every remaining line still present in the render,
    in order - which is exactly the shape a refresh rewrites. To keep a
    scaffold line out, change it into something the scaffold would not
    produce - comment it out, or edit it - rather than removing it. To go
    the other way and take the scaffold's version of a kept file, delete the
    file and refresh again; it comes back as `created`.

`--refresh` and `--force` are mutually exclusive, and the run stops if you
pass both: `--force` rewrites every scaffold file including the ones you
edited, `--refresh` rewrites only what it can rewrite without losing an
edit. They are opposite answers to the same question.

Three verbs share a word, so keep them apart: `init --refresh` touches the
scaffold and never the generated output; the scaffolded `make refresh`
rebuilds the IG from the instance; and the one-command way to bring an older
project up to the current d2w is `make update` - it moves the toolchain pin
(`uv lock --upgrade`), syncs, and runs `init --refresh`, pin first, so the
refresh runs on the d2w it just installed.

Why this exists is concrete: a project scaffolded before `path-resource`
covered a predefined-resource sub-folder keeps a `sushi-config.yaml` without
that glob. SUSHI loads the pre-built JSON regardless, so `make sushi` stays
green - but the IG Publisher does not recurse, and silently drops those
resources from the published guide. A refresh adds the glob.

Next: [Validate the instance](201-validate.md)
