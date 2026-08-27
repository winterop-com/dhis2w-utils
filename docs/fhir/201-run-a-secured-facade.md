# Run a secured facade on a real instance

**Who this is for:** whoever is responsible for the facade being up, reachable
by the right callers, and landing what it captures in DHIS2.

**Before you start:** `uv` and Docker installed, a DHIS2 URL, and an account on
it. The account needs read access for everything here except step 10, which
writes.

**You will be able to:**

- take one DHIS2 instance from nothing to a facade other machines can call
- state who each step hands over to, and what success looks like
- decide the facade's posture towards a caller deliberately rather than by default

This page is the order, not the depth. Every step is one command, one sentence
about what success looks like, and the page that owns it - go there when a step
needs more than a command. The [Quickstart](101-quickstart.md) is the same road
run fast on one machine, and stops at a served endpoint; this one carries on
through securing it and draining it.

Steps 1 to 5 are quick. Step 6 is the only expensive one, and steps 7 onward do
not wait for it.

## Step 1: check the instance survives the trip

Before investing a day in an instance, find out what it breaks. `doctor` runs
connect, scaffold, generate, compile, validate, serve, capture and forward in a
throwaway directory it deletes afterwards, and writes nothing to DHIS2.

```console
$ d2w -p ministry fhir doctor
```

**Success:** one verdict, and a phase table naming anything that failed.

**Depth:** [Check an instance with doctor](201-doctor.md).

## Step 2: scaffold the project

The project is a git repository you keep. One command writes `fhir.toml`, the
SUSHI skeleton, a `pyproject.toml` pinning the toolchain, a Makefile and a
Dockerfile.

```console
$ d2w fhir init ministry-ig --id org.ministry.dhis2 \
    --canonical https://ministry.example.org/fhir --publisher "Ministry of Health"
$ cd ministry-ig && uv sync
```

**Success:** thirteen files created, and `uv.lock` recording the pin. Commit it -
it is what makes a regenerate reproducible on another machine.

**Depth:** [Set up an IG project](201-set-up-a-project.md).

## Step 3: point it at the DHIS2 instance

Secrets are never flags. `--local` keeps the profile beside the project in
`.dhis2/profiles.toml` rather than in your home directory, which is what you
want for a project a colleague will also run.

```console
$ DHIS2_PASSWORD=... uv run d2w profile add ministry --auth basic --username reporter \
    --url https://dhis2.example.org --local --default
```

**Success:** the profile path echoed back, and `uv run d2w fhir validate`
connecting in step 4.

**Depth:** [Point it at a DHIS2 instance](201-set-up-a-project.md#point-it-at-a-dhis2-instance),
and [Connect to DHIS2](../guides/connecting-to-dhis2.md) for the other auth kinds.

## Step 4: grade the metadata

This is the guardrail. It reads every code and name the selection holds and
grades each finding by what it costs the publish, so a name carrying `<` is
caught in seconds rather than killing a compile in its final output check.

```console
$ uv run d2w fhir validate
```

**Success:** zero errors. A non-zero exit is the command working - errors are the
gate step 5 applies, not advice. Fix the names in DHIS2, publish them rewritten
with `hostile_names = "substitute"`, or keep them out of the selection.

**Depth:** [Validate the instance](201-validate.md), and
[`hostile_names`](301-generation.md#hostile_names) for the choice between those
last two roads.

## Step 5: write the IG source

One pass over the instance writes the whole guide's source: FSH for the forms,
profiles, extensions and terminology, and pre-built FHIR JSON for the
organisation unit registry.

```console
$ uv run d2w fhir generate
```

**Success:** a per-target file count. Expect the registry to be most of it - every
organisation unit emits both an `Organization` and a `Location`.

An absent `[generate.*]` table means everything of that kind, so decide the
selection here rather than discovering it at build size.

**Depth:** [Generate the IG source](201-generate.md), and
[What goes in](301-what-goes-in.md) for the selection tables.

## Step 6: compile the guide

This is the publish step and the slow one - the HL7 IG publisher renders a page
per resource out of the docker image the scaffold defines. **It is optional for
serving:** `d2w fhir serve --live` needs nothing compiled, and the compiled
posture needs only the SUSHI compile. Run it when you want the browsable
website to hand over.

```console
$ docker build -t fhir-ig .
$ make build
```

**Success:** `ig/output/index.html` opens and every artifact has a page. The
publisher's own QA counts on the last line are not the build's exit status.

**Depth:** [Build and publish the guide](201-build-and-publish.md), and
[Troubleshooting](201-troubleshooting.md) when it exits non-zero.

## Step 7: serve it

```console
$ uv run d2w fhir serve --port 8091
```

**Success:** a startup line naming the resource count, and
`curl -s localhost:8091/metadata` answering a `CapabilityStatement`. State the
port explicitly: it defaults to 8080, which is where a local DHIS2 usually
listens.

`--live` builds the store off the instance at startup instead of off the
compiled guide - the fastest way to see what your metadata publishes as, and the
mode the `dhis2` posture in step 8 requires.

**Depth:** [Serve the guide](201-serve.md), and [Serving it](301-serving.md) for
the `[serve]` table.

## Step 8: say who may call it

**Do not skip this before the facade leaves your machine.** A project whose
`fhir.toml` names no `auth` key binds loopback and refuses to start anywhere
else, so the server will not quietly become reachable - but on loopback it
serves every caller that reaches it, because the unwritten posture is `none`.
There are four postures, and the choice is one line somebody writes down.
`none` written out is the fourth: the deliberate sentence that this facade
serves everybody, which is what the refusal above is asking for.

```console
$ export D2W_FHIR_SERVE_TOKENS='a-long-random-value,another-for-the-second-client'
$ uv run d2w fhir serve --auth token --host 0.0.0.0 --port 8091
```

- **`token`** is a shared bearer secret, read from `D2W_FHIR_SERVE_TOKENS` and
  never from `fhir.toml`.
- **`dhis2`** authenticates callers as themselves against your instance, and
  reads the register as them - `d2w fhir serve --live --auth dhis2`.
- **`jwt`** accepts tokens from an identity provider the ministry already runs,
  configured under `[serve.jwt]`.

`--auth-scope` decides how much is behind the credential: `write` gates
submissions only, `all` gates everything but `/metadata`.

**Success:** `GET /facade/whoami` names the caller, and an uncredentialed
`POST /QuestionnaireResponse` is refused.

**Depth:** [Secure the facade](201-secure.md).

## Step 9: put the capture screens on it

`--ui` serves a form filler at `/` that renders the published forms, picks the
organisation unit and reporting period, and shows every receipt's state. It
needs a serve installed from a wheel, which ships the built front end.

```console
$ uv run d2w fhir serve --auth token --ui
```

**Success:** the Overview at `/` listing the forms this guide publishes.

**Depth:** [Capture in the browser](201-capture-ui.md).

Whether captures arrive through those screens or through
`POST /QuestionnaireResponse` from another system, they land in the same spool
and meet the same profiles - [The capture contract](401-capture-contract.md)
states what a submission must carry.

## Step 10: drain the spool into DHIS2

This is the only step that writes to your instance. Dry run is the default and
validates the whole queue without writing a byte - even then the payloads go
through DHIS2's own validate-only mode, so the instance's rules decide.

```console
$ uv run d2w fhir forward
$ uv run d2w fhir forward --import
```

**Success:** every receipt moved out of `received` - into `forwarded` where DHIS2
accepted it, or `rejected` where DHIS2 refused it, with the reason named. One
drain runs at a time; there is no daemon mode, so a scheduler invokes this.

**Depth:** [Forward captures into DHIS2](201-forward.md).

## Step 11: keep it running

The facade is now doing its job. Four commands are the day-to-day:

- `d2w fhir spool` reads the queue - what is waiting, what DHIS2 refused, and
  why - with no DHIS2 connection and no profile.
- `d2w fhir requeue <id>` puts a refused receipt back in the queue after you
  have fixed what refused it.
- `d2w fhir withdraw <id>` retracts from DHIS2 something a drain already landed.
- `d2w fhir init --refresh` brings the project's scaffold-managed files up to
  date without touching a line you wrote, so a toolchain move is a reviewable
  diff.

When the instance's metadata changes, re-run steps 4 and 5, review the diff, and
republish. Generated files are replaced and hand-authored files beside them are
never touched - [Regeneration and hand-authoring](401-regeneration-and-hand-authoring.md)
draws that line.

**Depth:** [Forward captures into DHIS2](201-forward.md) for the spool commands,
and [Troubleshooting](201-troubleshooting.md) for the errors worth recognising.

Next: [Consume the FHIR API](401-consume-the-fhir-api.md) - what a client can now
ask this facade for.
