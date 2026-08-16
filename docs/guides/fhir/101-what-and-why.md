# What `d2w fhir` is and why

**Who this is for:** DHIS2 implementers and programme managers deciding whether
to publish a FHIR Implementation Guide from a DHIS2 instance - before anyone
installs anything.

**Before you start:** nothing to install; this page has no commands.

**You will be able to:**

- say why a ministry publishes an Implementation Guide at all
- name what each `d2w fhir` verb produces and how the pieces fit
- say what the toolchain does not do, and what runs where
- state what adopting the toolchain costs in tooling, time, and upkeep

## Why a ministry publishes an IG

A DHIS2 instance is a system; an Implementation Guide is a **contract**. The
instance holds your data sets, programs, option sets, and organisation units,
and answers API calls for whoever has credentials. The IG is the published,
versioned document that says - in the vocabulary the rest of digital health
speaks - what those structures are, what a submission against them must look
like, and which codes mean what. A third party can read it, validate against
it, and build to it **without access to your DHIS2 metadata API, your
credentials, or your team's time**.

That matters the moment anything outside DHIS2 wants in or out: a national
health information exchange, a lab system pushing results, a mobile app
capturing in the field, a regional reporting pipeline, or a donor who asks
"where is your FHIR interface?". FHIR is the answer those systems expect, and
an IG is how FHIR interfaces are specified. Hand-writing one from DHIS2
metadata is months of transcription that starts rotting the day it is
finished. `d2w fhir` generates it from the instance instead, so the guide is a
build product: when the metadata changes, you regenerate, diff, and republish.

## What your instance turns into

Nothing here asks you to model anything again. The generator reads the metadata you
already maintain and republishes it under FHIR's names:

- your **data sets and program stages** become forms a FHIR client can render
- your **option sets and categories** become published vocabularies, so an outside
  system can resolve a code instead of guessing at it
- your **organisation unit hierarchy** becomes a registry that a partner can point at
- your **data elements and tracked entity attributes** become the coded questions
  those forms ask

[FHIR for DHIS2 people](101-fhir-concepts.md) names each FHIR term through its DHIS2
counterpart and carries the full table of what becomes what.

## What the verbs produce

`d2w fhir` is one CLI plugin with a small set of verbs. Each one produces a
concrete thing:

| Verb | Produces |
| --- | --- |
| `doctor` | One verdict on whether this instance can carry the whole chain. It runs connect, scaffold, generate, compile, validate, serve, capture, forward, and an oracle phase in a throwaway workspace, and reports what your instance breaks. Run it before anything else - see [Check an instance with doctor](201-doctor.md). |
| `init` | A complete, dockerized SUSHI project: `fhir.toml`, `sushi-config.yaml`, a `pyproject.toml` pinning the d2w toolchain, a Makefile, a Dockerfile. `--refresh` brings an existing project's scaffold-managed files up to date. |
| `validate` | A FHIR-safety report on the instance's codes - Markdown, CSV, and PDF - with every finding graded by build impact on your configured IG. |
| `generate` | The IG source: FSH for forms, profiles, extensions, and terminology; pre-built FHIR JSON for the organisation-unit registry, option-set and category terminology, and ConceptMaps. Re-running converges - generated files are replaced, hand-authored files beside them are never touched. |
| `serve` | A running FHIR facade over the compiled IG: read and search every published artifact, answer `$translate` over the ConceptMaps, serve the instance's tracked entities as a register, accept `QuestionnaireResponse` captures, and - with `--ui` - offer a [browser capture UI](201-capture-ui.md) that fills those forms in. |
| `forward` | DHIS2 imports built from captured responses: the serve spool drained, translated, and posted back into the instance. Dry run is the default, and `--import` commits. |

Compiling the source into the browsable guide is one `docker run` of the HL7
IG Publisher, which compiles the FSH with its own SUSHI on the way, out of an
image you build once. Nothing needs installing beyond `uv` and Docker.

Together the verbs cover the whole loop: describe the instance (an IG a
partner can build against), capture against it (a FHIR endpoint that accepts
submissions), and land the data back in DHIS2 (the forwarder). You can stop at
any point on that line - plenty of projects only ever publish the guide.

## What runs where

Nothing in this toolchain is installed into DHIS2. There is no DHIS2 app to deploy,
no jar to drop on the server, and no change to your instance's configuration.

| Piece | Where it runs | What it does to DHIS2 |
| --- | --- | --- |
| `d2w fhir generate` / `validate` / `doctor` | Your machine, or a CI runner | Reads metadata over the DHIS2 API. Writes nothing. |
| The IG build (SUSHI, the HL7 IG Publisher) | Docker, on that same machine | Never talks to DHIS2 at all - it compiles files on disk. |
| The published guide | Any static web host | Nothing. It is HTML and JSON; it needs no DHIS2 connection and no credentials. |
| `d2w fhir serve` | A process you run, loopback by default | Reads, in `--live` mode, to build its store at startup. Captures are held in a local spool, not sent onward. |
| `d2w fhir forward` | Your machine | The only verb that writes. Dry run is the default, and even then payloads go through the DHIS2 endpoint's own validate-only mode, so the instance's rules decide. |

The credentials come from a `d2w` profile, so the account you point at decides what
the toolchain may see. A read-only account is enough for everything except `forward`.

## What it does not do

Worth being blunt, because the FHIR word invites assumptions:

- **It is not a live FHIR API in front of DHIS2.** `d2w fhir serve` answers from a
  store built at startup - off the compiled guide, or off a snapshot of the instance
  with `--live`. It is not a proxy that translates each request through to DHIS2, and
  a change made in DHIS2 after startup is not visible until it is restarted.
- **It does not replace DHIS2 data entry.** The capture UI exists so a form can be
  filled against the published contract and forwarded in; the DHIS2 apps remain how
  routine entry is done.
- **It does not move analytics.** Indicators, predictors, dashboards, and the
  analytics tables are outside what the guide describes. It publishes the shape of
  your data collection, not your reporting.
- **It does not sync.** There is no continuous replication in either direction.
  `generate` is a build step you re-run; `forward` is a drain you invoke.
- **It does not fix your metadata.** `validate` and `doctor` will show you codes that
  are missing, duplicated, or not FHIR-safe. Fixing them is work in the instance.
- **It publishes no patient data by default.** The generated guide contains metadata
  and example responses, not real records. The tracked-entity register is something a
  running serve offers from your instance, not something the published guide carries.

## What it costs

- **Tooling:** `uv` and Docker on one machine. SUSHI, the IG publisher, and
  Java all live in the docker image; nothing else is installed on the host.
- **Time:** generating IG source from a national-scale instance takes minutes.
  The first publisher run is the slow one - it downloads its
  packages and renders a page per artifact - and two caches make every later
  build much cheaper. A registry of a few thousand organisation units is the
  main driver of build time and site size.
- **Upkeep:** the project is a git repository. You commit the configuration
  and any hand-authored FSH, regenerate when metadata changes, and review the
  diff. The scaffold pins the d2w toolchain in `uv.lock`, so a regenerate is
  reproducible until you deliberately move the pin.
- **Data hygiene, not data entry:** `validate` will surface DHIS2 codes that
  are missing, duplicated, or not FHIR-safe. Fixing those in the instance is
  work the IG did not create - it only made it visible - and the guide builds
  with documented fall-backs while you do.

The plugin is version-neutral: the wire client auto-detects the DHIS2 major on
connect, so one package serves v41, v42, and v43.

Next: [FHIR for DHIS2 people](101-fhir-concepts.md) - the ten-minute
vocabulary tour.
