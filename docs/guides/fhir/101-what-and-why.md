# What `d2w fhir` is and why

**Who this is for:** DHIS2 implementers and programme managers deciding whether
to publish a FHIR Implementation Guide from a DHIS2 instance - before anyone
installs anything.

**Before you start:** nothing to install; this page has no commands.

**You will be able to:**

- say why a ministry publishes an Implementation Guide at all
- name what each `d2w fhir` verb produces and how the pieces fit
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

## What the verbs produce

`d2w fhir` is one CLI plugin with a small set of verbs. Each one produces a
concrete thing:

| Verb | Produces |
| --- | --- |
| `init` | A complete, dockerized SUSHI project: `fhir.toml`, `sushi-config.yaml`, a `pyproject.toml` pinning the d2w toolchain, a Makefile, a Dockerfile. `--refresh` brings an existing project's scaffold-managed files up to date. |
| `validate` | A FHIR-safety report on the instance's codes - Markdown, CSV, and PDF - with every finding graded by build impact on your configured IG. |
| `generate` | The IG source: FSH for forms, profiles, extensions, and terminology; pre-built FHIR JSON for the organisation-unit registry, option-set and category terminology, and ConceptMaps. Re-running converges - generated files are replaced, hand-authored files beside them are never touched. |
| `serve` | A running FHIR facade over the compiled IG: read and search every published artifact, answer `$translate` over the ConceptMaps, accept `QuestionnaireResponse` captures, and offer a browser capture UI. |
| `forward` | DHIS2 imports built from captured responses: the serve spool drained, translated, and posted back into the instance - dry run first. |

Compiling the source into the browsable guide is the scaffolded project's
`make build`, which runs SUSHI and the HL7 IG Publisher inside the Docker image
`make setup` builds once. Nothing needs installing beyond `uv` and Docker.

Together the verbs cover the whole loop: describe the instance (an IG a
partner can build against), capture against it (a FHIR endpoint that accepts
submissions), and land the data back in DHIS2 (the forwarder). You can stop at
any point on that line - plenty of projects only ever publish the guide.

## What it costs

- **Tooling:** `uv` and Docker on one machine. SUSHI, the IG publisher, and
  Java all live in the docker image; nothing else is installed on the host.
- **Time:** generating IG source from a national-scale instance takes minutes.
  The first `make build` is the slow one - the publisher downloads its
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
