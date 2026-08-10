# The `d2w fhir` series

`d2w fhir` turns a DHIS2 instance's metadata into a FHIR Implementation Guide
source tree: a [SUSHI](https://fshschool.org/docs/sushi/) project whose FSH
(FHIR Shorthand) definitions and pre-built registry JSON are generated from the
DHIS2 API and published as FHIR resources by the IG publisher. One plugin
covers the whole loop: `init` scaffolds a dockerized project, `validate`
grades the instance's codes by build impact, `generate` writes the IG source,
the scaffolded `make build` compiles the browsable guide, `serve` runs the
compiled project as a read-and-capture FHIR endpoint, and `forward` posts what
that endpoint captured back into DHIS2.

The series is graded: **101** pages explain and demonstrate, **201** pages
operate a project day to day, **301** pages configure `fhir.toml`, and **401**
pages integrate against and extend what the project publishes. Every page
states who it is for; start where your question lives.

## I am a...

| I am a... | Start at | Then |
| --- | --- | --- |
| **DHIS2 implementer** deciding whether to publish an IG | [What `d2w fhir` is and why](101-what-and-why.md) | [FHIR for DHIS2 people](101-fhir-concepts.md), [Quickstart](101-quickstart.md) |
| **M&E configurer** shaping what the guide contains | [Quickstart](101-quickstart.md) | The 301 pages on `fhir.toml`, [Validate the instance](201-validate.md) |
| **Integration developer** building against the published guide | [FHIR for DHIS2 people](101-fhir-concepts.md) | The 401 pages, starting at [The capture contract](401-capture-contract.md) |
| **Operator** running generate, build, serve, and forward | [Quickstart](101-quickstart.md) | The 201 pages, starting at [Set up an IG project](201-set-up-a-project.md) |

## 101 - Understand

- [What `d2w fhir` is and why](101-what-and-why.md) - why a ministry publishes
  an IG, what the verbs produce, what it costs. No commands.
- [FHIR for DHIS2 people](101-fhir-concepts.md) - every FHIR term this series
  uses, explained in DHIS2 terms.
- [Quickstart: six commands to a served IG](101-quickstart.md) - scaffold,
  validate, generate, and compile a guide from the play server.

## 201 - Operate a project

- [Set up an IG project](201-set-up-a-project.md) - the scaffold, the pinned
  toolchain, profiles, and `--refresh`.
- [Validate the instance](201-validate.md) - the findings, what severity
  means, and the report files.
- [Generate the IG source](201-generate.md) - the generate targets and what
  each one writes.
- [Build and publish the guide](201-build-and-publish.md) - SUSHI, the IG
  publisher, build time, and the two caches.
- [Serve the guide](201-serve.md) - the read-and-capture facade and its two
  modes.
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
- [Serving it](301-serving.md) - the `[serve]` table: host, port, spool, and
  capture behaviour.

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
