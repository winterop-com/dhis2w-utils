# dhis2w-fhir

FHIR Implementation Guide generation from DHIS2 metadata.

- `d2w fhir init` scaffolds a dockerized SUSHI IG project with a committed `fhir.toml`.
- `d2w fhir generate foundation|option-sets|questionnaires|examples|org-units|pages|all` emits FSH: the DHIS2 identifier systems (aliases + NamingSystems) plus the D2Period and D2FormType extensions, option sets as CodeSystem/ValueSet pairs carrying both DHIS2 identifiers, data sets and event programs as Questionnaire instances with their data-element and category-option-combo support terminology, example QuestionnaireResponses answering those forms (synthetic by default, or fetched from the instance), organisation units as Organization/Location instances with partOf hierarchy, and the narrative site pages the IG publisher renders.
- `d2w fhir validate` checks a DHIS2 instance's codes and names for FHIR-safety (R4).

The `foundation` target also emits the capture contract a third party builds against without reading DHIS2: the `D2AggregateResponse` and `D2EventResponse` QuestionnaireResponse profiles, one per form kind, each pinning the context a capture client has to carry, and the `D2CaptureServer` CapabilityStatement stating the interactions a server accepting those responses supports.

The package registers itself through the `dhis2.plugins` entry-point group, so installing it next to `dhis2w-cli` / `dhis2w-mcp` adds the `d2w fhir` commands and the read-only `fhir_validate` MCP tool. Naming of generated artifacts is configurable via `[generate.naming]` in `fhir.toml`.

Roadmap: org unit group / group set classifications as additional Organization.type codings (tokens OUG / OUGS), categories / category options as CodeSystem/ValueSet pairs, and tracker programs as Patient + EpisodeOfCare alongside their per-stage forms.
