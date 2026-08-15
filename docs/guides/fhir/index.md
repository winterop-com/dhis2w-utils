# The `d2w fhir` series

`d2w fhir` turns a DHIS2 instance's metadata into a FHIR Implementation Guide
source tree: a [SUSHI](https://fshschool.org/docs/sushi/) project whose FSH
(FHIR Shorthand) definitions and pre-built registry JSON are generated from the
DHIS2 API and published as FHIR resources by the IG publisher. One plugin
covers the whole loop: `init` scaffolds a dockerized project, `validate`
grades the instance's codes by build impact, `generate` writes the IG source,
the scaffolded `make build` compiles the browsable guide, `serve` runs the
compiled project as a read-and-capture FHIR endpoint, and `forward` posts what
that endpoint captured back into DHIS2. `doctor` runs that whole chain against
one instance and reports what the instance breaks.

The series is graded: **101** pages explain and demonstrate, **201** pages
operate a project day to day, **301** pages configure `fhir.toml`, and **401**
pages integrate against and extend what the project publishes. Every page
states who it is for; start where your question lives.

Every term either side of the boundary - DHIS2's and FHIR's - has an entry in
the [Glossary](glossary.md). Read it first if a word in any page below is
carrying more meaning than you can place, and keep it open beside the page you
are working through.

## Where to start

Find the sentence that describes your situation. Each row is a reading order,
not a menu - the pages build on each other left to right.

| Your situation | Read, in this order |
| --- | --- |
| **You run a DHIS2 instance and want its forms available as FHIR** | [What `d2w fhir` is and why](101-what-and-why.md), [Quickstart](101-quickstart.md), then the 201 pages from [Check an instance with doctor](201-doctor.md) onward |
| **You are deciding whether your ministry should publish a guide at all** | [What `d2w fhir` is and why](101-what-and-why.md), then the project-level design records: the [FHIR roadmap and review guide](../../project/fhir-roadmap.md), the [DHIS2 fidelity audit](../../project/fhir-dhis2-fidelity.md), and the [harmonization design](../../project/fhir-harmonization.md) |
| **You integrate a system against a guide someone else published** | [Glossary](glossary.md), [FHIR for DHIS2 people](101-fhir-concepts.md), then the 401 pages from [The capture contract](401-capture-contract.md) |
| **You configure what the guide contains** | [Quickstart](101-quickstart.md), [Validate the instance](201-validate.md), then the 301 pages from [The settings file](301-fhir-toml.md) |
| **You operate a project that already exists** | [Check an instance with doctor](201-doctor.md), then the 201 pages in order |
| **You are new to FHIR entirely** | [Glossary](glossary.md), [FHIR for DHIS2 people](101-fhir-concepts.md), [What `d2w fhir` is and why](101-what-and-why.md) |

## 101 - Understand

- [Glossary](glossary.md) - every DHIS2 term and what the toolkit does with it,
  every FHIR and toolkit term and what it is in DHIS2 terms. A dictionary, read
  by lookup.
- [What `d2w fhir` is and why](101-what-and-why.md) - why a ministry publishes
  an IG, what the verbs produce, what it costs. No commands.
- [FHIR for DHIS2 people](101-fhir-concepts.md) - the FHIR model itself,
  explained in DHIS2 terms and at length. Where the glossary gives you a
  sentence, this gives you the reasoning.
- [Quickstart: six commands to a served IG](101-quickstart.md) - scaffold,
  validate, generate, and compile a guide from the play server.

## 201 - Operate a project

- [Check an instance with doctor](201-doctor.md) - the whole chain against one
  instance, in one command, with one verdict. Run this first.
- [Set up an IG project](201-set-up-a-project.md) - the scaffold, the pinned
  toolchain, profiles, and `--refresh`.
- [Validate the instance](201-validate.md) - the findings, what severity
  means, and the report files.
- [Generate the IG source](201-generate.md) - the generate targets and what
  each one writes.
- [Build and publish the guide](201-build-and-publish.md) - SUSHI, the IG
  publisher, build time, and the two caches.
- [Serve the guide](201-serve.md) - the read-and-capture facade, and what a
  live run serves that a compiled run does not.
- [Capture in the browser](201-capture-ui.md) - the form filler a served
  project offers.
- [Forward captures into DHIS2](201-forward.md) - draining the serve spool
  into DHIS2, dry run first.
- [Troubleshooting](201-troubleshooting.md) - publisher exits, heap sizing,
  and the errors worth recognising.

## 301 - Configure fhir.toml

- [The settings file: fhir.toml](301-fhir-toml.md) - where the file lives, how
  it is read, and the map of its tables.
- [Who the guide is](301-identity.md) - `profile` and the `[ig]` table: id,
  canonical, publisher.
- [What goes in](301-what-goes-in.md) - the selection tables: data sets,
  programs, option sets, categories, organisation units.
- [How things are generated](301-generation.md) - `[generate]` and
  `[generate.naming]`: the identity stem, concept codes, and the canonical
  token registry.
- [Serving it](301-serving.md) - the `[serve]` table: host, port, spool,
  capture behaviour, and the register of tracked entities.

## 401 - Integrate and extend

- [The capture contract](401-capture-contract.md) - the response profiles a
  submission must meet.
- [Consume the FHIR API](401-consume-the-fhir-api.md) - reads, searches, and the
  operations a client drives.
- [Identifiers and the D2 extensions](401-identifiers-and-extensions.md) -
  where the DHIS2 identity of every artifact lives.
- [Terminology and ConceptMaps](401-terminology-and-conceptmaps.md) - the
  emitted terminology and the route back to DHIS2.
- [Custom subject types](401-custom-subject-types.md) - tracked entity types
  that are not people.
- [Regeneration and hand-authoring](401-regeneration-and-hand-authoring.md) - what a generate run owns,
  and where hand-authored content is safe.

## Reference

- [CLI reference](../../cli-reference.md) - every `d2w fhir` command and flag.
- [`dhis2w_fhir` API reference](../../api/fhir.md) - the importable surface.
- [`dhis2w_fhir_serve` API reference](../../api/fhir-serve.md) - the facade
  package.
- [FHIR plugin architecture](../../architecture/fhir-plugin.md) - how the
  packages are laid out and why.

## The design record

The reasoning behind the shapes these pages describe lives under Project,
not here. Read them when you want the *why* rather than the *how*:

- [FHIR roadmap and review guide](../../project/fhir-roadmap.md) - what exists,
  the settled and open decisions, the review dimensions.
- [FHIR conversion layer](../../project/fhir-conversion.md) - how data crosses
  the boundary in both directions.
- [Corrections and withdrawals](../../project/fhir-data-lifecycle.md) - how a
  submitted value is corrected or retracted.
- [DHIS2 fidelity audit](../../project/fhir-dhis2-fidelity.md) - every concept
  that makes DHIS2 distinctively DHIS2, and whether the guide carries it.
- [FHIR harmonization](../../project/fhir-harmonization.md) - how several
  country guides relate.
- [FHIR enrollment resource](../../project/fhir-enrollment-resource.md) - why
  the read side models an enrollment as it does.
