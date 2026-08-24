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
| `--force` | Overwrite scaffold files that already exist. |
| `--refresh` | Bring an existing project's scaffold up to date - see below. Rejects `--force`. |

Every seeding flag is offline: values are written to `fhir.toml` as given and
never checked against an instance. `init` writes a minimal `fhir.toml` holding
just the IG identity, plus `fhir.toml.example` documenting every option with
its default - copy what you need across; anything you omit keeps its default.

!!! tip "Eight worked starting points"
    [`examples/fhir/igs/`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/igs/README.md)
    holds eight complete project trees built exactly this way against the
    seeded local instance, one per feature story - the smallest possible
    guide, a disaggregated aggregate one, an event program, a tracker
    program, a strict-terminology one, an organisation-unit registry, a
    facility publishing every capture kind at once, and one whose generate
    is refused by design. Each carries a README stating the `d2w fhir init`
    command it was scaffolded with, the `fhir.toml` lines added by hand, and
    what the compiled guide shows. Copying the one nearest your instance is
    usually faster than starting from the flags above.

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
- **`[tool.uv.sources]` sources all three packages from one commit** of the
  dhis2w-utils repository on `main`, and the lock pins the concrete commit.
  A CLI paired with a plugin from a different build is not a combination
  anyone tests. Delete the entries once you prefer PyPI releases, and they
  resolve from there instead.

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
