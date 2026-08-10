# FHIR IG generation with `d2w fhir`

`d2w fhir` turns a DHIS2 instance's metadata into a FHIR Implementation Guide:
a SUSHI project generated from the DHIS2 API, compiled and published by the IG
publisher, served as a read-and-capture FHIR endpoint, and forwarded back into
DHIS2. The documentation is a graded series - 101 understand, 201 operate a
project, 301 configure `fhir.toml`, 401 integrate and extend - and the
[series index](fhir/index.md) is its front door, with an "I am a..." router.

The full page map:

| Topic | Page |
| --- | --- |
| Why publish an IG, what the verbs produce, what it costs | [What `d2w fhir` is and why](fhir/101-what-and-why.md) |
| Every FHIR term, explained in DHIS2 terms | [FHIR for DHIS2 people](fhir/101-fhir-concepts.md) |
| Quickstart: six commands to a served IG | [Quickstart](fhir/101-quickstart.md) |
| Scaffold, pinned toolchain, profiles, `--refresh` | [Set up an IG project](fhir/201-set-up-a-project.md) |
| FHIR-safety findings, severity as build impact, reports | [Validate the instance](fhir/201-validate.md) |
| The generate targets and what each writes | [Generate the IG source](fhir/201-generate.md) |
| The Makefile, build knobs, registry scale, the two caches | [Build and publish the guide](fhir/201-build-and-publish.md) |
| The read-and-capture facade and its two modes | [Serve the guide](fhir/201-serve.md) |
| The browser form filler | [Capture in the browser](fhir/201-capture-ui.md) |
| Draining the serve spool into DHIS2 | [Forward captures into DHIS2](fhir/201-forward.md) |
| Publisher exits, heap sizing, literal refusals | [Troubleshooting](fhir/201-troubleshooting.md) |
| Where `fhir.toml` lives and the map of its tables | [The settings file](fhir/301-fhir-toml.md) |
| `profile` and `[ig]`: id, canonical, publisher | [Who the guide is](fhir/301-identity.md) |
| The selection tables: data sets, programs, org units | [What goes in](fhir/301-what-goes-in.md) |
| `[generate]`, `[generate.naming]`, the token registry | [How things are generated](fhir/301-generation.md) |
| The `[serve]` section | [Serving it](fhir/301-serving.md) |
| The response profiles a submission must meet | [The capture contract](fhir/401-capture-contract.md) |
| Reads, searches, `$translate`, `$generate` | [Consume the FHIR API](fhir/401-consume-the-fhir-api.md) |
| Identifier families, `D2Period`, `D2AttributeValue` | [Identifiers and the D2 extensions](fhir/401-identifiers-and-extensions.md) |
| Option-set and category terminology, ConceptMaps | [Terminology and ConceptMaps](fhir/401-terminology-and-conceptmaps.md) |
| Tracked entity types that are not people | [Custom subject types](fhir/401-custom-subject-types.md) |
| What a generate run owns; where your files are safe | [Regeneration and hand-authoring](fhir/401-regeneration-and-hand-authoring.md) |

Reference pages: the [CLI reference](../cli-reference.md), the
[`dhis2w_fhir`](../api/fhir.md) and [`dhis2w_fhir_serve`](../api/fhir-serve.md)
API pages, and the [FHIR plugin architecture](../architecture/fhir-plugin.md).
