# The `d2w fhir` series

`d2w fhir` turns a DHIS2 instance's metadata into a FHIR Implementation Guide
source tree: a [SUSHI](https://fshschool.org/docs/sushi/) project whose FSH
(FHIR Shorthand) definitions and pre-built registry JSON are generated from the
DHIS2 API and published as FHIR resources by the IG publisher. One plugin
covers the whole loop: `init` scaffolds a dockerized project, `validate`
grades the instance's codes by build impact, `generate` writes the IG source,
the IG publisher compiles the browsable guide, `serve` runs the
compiled project as a read-and-capture FHIR endpoint, and `forward` posts what
that endpoint captured back into DHIS2. `doctor` runs that whole chain against
one instance and reports what the instance breaks.

Most projects need three things, in this order: a facade running, that facade
pointed at a DHIS2 instance, and that facade accepting captures in the format
the guide publishes. [Introduction](100-introduction.md) is those three steps on
one page, with the command that does each and the link that owns it - read it
first if you are new here. Everything else in this series is depth behind one of
those steps, or one of the capabilities that sit beyond them.

The series is graded 100 to 501: the **100** page is the front door, **101**
pages explain and demonstrate, **201** pages operate a project day to day,
**301** pages configure `fhir.toml`, **401** pages integrate against and extend
what the project publishes, and **501** pages teach the expression languages
that compute over FHIR data. Every page states who it is for; start where your
question lives.

Every term either side of the boundary - DHIS2's and FHIR's - has an entry in
the [Glossary](glossary.md). Read it first if a word in any page below is
carrying more meaning than you can place, and keep it open beside the page you
are working through.

## Where to start

Find the sentence that describes your situation. Each row is a reading order,
not a menu - the pages build on each other left to right.

| Your situation | Read, in this order |
| --- | --- |
| **You are new here and want the shape of it** | [Introduction](100-introduction.md), then whichever step you need depth on |
| **You run a DHIS2 instance and want its forms available as FHIR** | [Introduction](100-introduction.md), [What `d2w fhir` is and why](101-what-and-why.md), [Quickstart](101-quickstart.md), then the 201 pages from [Check an instance with doctor](201-doctor.md) onward |
| **You have to get a facade up on a real instance, reachable and forwarding** | [Run a secured facade on a real instance](201-run-a-secured-facade.md), following each step's link where you need the depth |
| **You are deciding whether your ministry should publish a guide at all** | [What `d2w fhir` is and why](101-what-and-why.md), then the project-level design records: the [FHIR roadmap and review guide](design/roadmap.md), the [DHIS2 fidelity audit](design/dhis2-fidelity.md), and the [harmonization design](design/harmonization.md) |
| **You integrate a system against a guide someone else published** | [Glossary](glossary.md), [FHIR for DHIS2 people](101-fhir-concepts.md), then the 401 pages from [The capture contract](401-capture-contract.md) |
| **You configure what the guide contains** | [Quickstart](101-quickstart.md), [Validate the instance](201-validate.md), then the 301 pages from [The settings file](301-fhir-toml.md) |
| **You operate a project that already exists** | [Check an instance with doctor](201-doctor.md), then the 201 pages in order |
| **You are new to FHIR entirely** | [Glossary](glossary.md), [FHIR for DHIS2 people](101-fhir-concepts.md), [What `d2w fhir` is and why](101-what-and-why.md) |
| **You want to compute over FHIR data - expressions, logic, quality measures** | [FHIRPath](501-fhirpath.md), [CQL](501-cql.md), [Quality measures](501-measures.md), then [The FHIR version binding](501-version-binding.md) |

## Start here

- [Introduction](100-introduction.md) - what a `d2w fhir` facade is, the three
  steps that get you one, and the command that does each. The page to read
  before any other.

## 101 - Understand

- [Glossary](glossary.md) - every DHIS2 term and what the toolkit does with it,
  every FHIR and toolkit term and what it is in DHIS2 terms. A dictionary, read
  by lookup.
- [What `d2w fhir` is and why](101-what-and-why.md) - why a ministry publishes
  an IG, what the verbs produce, what it costs. No commands.
- [FHIR for DHIS2 people](101-fhir-concepts.md) - the FHIR model itself,
  explained in DHIS2 terms and at length. Where the glossary gives you a
  sentence, this gives you the reasoning.
- [Quickstart: from nothing to a served IG](101-quickstart.md) - scaffold,
  validate, generate, compile, and serve a guide from a DHIS2 instance.

## 201 - Operate a project

- [Run a secured facade on a real instance](201-run-a-secured-facade.md) - the
  eleven steps from nothing to a facade other machines call and a spool draining
  into DHIS2, each one command deep, handing over to the pages below.
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
- [Secure the facade](201-secure.md) - security is opt-in: the loopback-only
  default, and the token, DHIS2, and JWT postures with their scopes.
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
- [Embed the facade](401-embed-the-facade.md) - the facade as a library: no
  server, no port, no UI, and the projection as the local storage layer.
- [Build your own facade](401-build-your-own-facade.md) - the four-level ladder
  from one route of FastAPI to the point where `d2w fhir serve` is the answer.
- [Identifiers and the D2 extensions](401-identifiers-and-extensions.md) -
  where the DHIS2 identity of every artifact lives.
- [Terminology and ConceptMaps](401-terminology-and-conceptmaps.md) - the
  emitted terminology and the route back to DHIS2.
- [Custom subject types](401-custom-subject-types.md) - tracked entity types
  that are not people.
- [Regeneration and hand-authoring](401-regeneration-and-hand-authoring.md) - what a generate run owns,
  and where hand-authored content is safe.

## 501 - Evaluate

The expression languages that compute over FHIR data, in the
`dhis2w-fhir-engine` package. Written for someone who knows DHIS2 and has never
seen an expression language, and needing no DHIS2 instance, no server, and no
generated project - every page runs against data you paste in. The exception is
held to the end of each language page: a closing section that runs the same
logic against a served project or a seeded instance, and says so.

- [FHIRPath](501-fhirpath.md) - the smaller language: paths, filters, and
  functions over one resource or one Bundle, and why every expression answers
  with a collection.
- [CQL](501-cql.md) - the bigger language: a named, versioned library, what its
  header binds, how a retrieve reaches data, how a ValueSet scopes one, and how
  an interval bounds a reporting period.
- [Quality measures](501-measures.md) - the populations, the scoring rules, the
  `MeasureReport` that comes out, and the DHIS2 payoff: indicators published as
  computable measures.
- [The FHIR version binding](501-version-binding.md) - what is
  FHIR-version-neutral, what is R4-bound, and what an R5 sibling would provide.

## Reference

- [Runnable examples](https://github.com/winterop-com/dhis2w-utils/tree/main/examples/fhir) -
  `examples/fhir/`, the whole surface as scripts you can run: `cli/` for the
  commands each 201 page describes, `client/` for the Python library path
  (generate a guide, consume a facade, drain a spool), and `engine/` for the
  expression languages the 501 pages teach. One copy, runs on v41, v42 and v43
  alike.
- [Feature catalog: FHIR IG Toolchain](../project/features.md#fhir-ig-toolchain) -
  every capability of the toolchain in one inventory, surface by surface.
- [CLI reference](../cli-reference.md) - every `d2w fhir` command and flag.
- [`dhis2w_fhir` API reference](api-dhis2w-fhir.md) - the importable surface.
- [`dhis2w_fhir_serve` API reference](api-dhis2w-fhir-serve.md) - the facade
  package.
- [`dhis2w_fhir_engine` API reference](api-dhis2w-fhir-engine.md) - the
  evaluation engine: FHIRPath, CQL, ELM, and quality measures.
- [FHIR plugin architecture](architecture.md) - how the
  packages are laid out and why.

## The design record

The reasoning behind the shapes these pages describe lives under Project,
not here. Read them when you want the *why* rather than the *how*:

- [FHIR roadmap and review guide](design/roadmap.md) - what exists,
  the settled and open decisions, the review dimensions.
- [FHIR conversion layer](design/conversion.md) - how data crosses
  the boundary in both directions.
- [Corrections and withdrawals](design/data-lifecycle.md) - how a
  submitted value is corrected or retracted.
- [DHIS2 fidelity audit](design/dhis2-fidelity.md) - every concept
  that makes DHIS2 distinctively DHIS2, and whether the guide carries it.
- [FHIR harmonization](design/harmonization.md) - how several
  country guides relate.
- [The IPS document](design/ips.md) - what an International
  Patient Summary requires, which sections a DHIS2 tracker instance could
  feed, and the prototype that makes the reserved decisions concrete
  (`examples/fhir/client/ips_document.py`).
- [FHIR enrollment resource](design/enrollment-resource.md) - why
  the read side models an enrollment as it does.
- [The library surface](design/library.md) - what the FHIR toolchain is
  apart from its commands: what is importable today, the composition contract
  the served facade is missing, and the sequence that closes the gap.
- [The materialized projection](design/projection.md) - what it takes to serve
  FHIR from a synced backend rather than a live proxy: the measured limits of the
  live model on population evaluation and multilingual person search, the sync
  doctrine, and the backends that could hold it.
