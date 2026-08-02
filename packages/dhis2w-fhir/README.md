# dhis2w-fhir

FHIR Implementation Guide generation from DHIS2 metadata.

- `d2w fhir init` scaffolds a dockerized SUSHI IG project with a committed `fhir.toml`.
- `d2w fhir generate foundation|option-sets|questionnaires|org-units|all` emits FSH: the DHIS2 identifier systems (aliases + NamingSystems) plus the D2Period and D2FormType extensions, option sets as CodeSystem/ValueSet pairs carrying both DHIS2 identifiers, data sets and event programs as Questionnaire instances with their data-element and category-option-combo support terminology, organisation units as Organization/Location instances with partOf hierarchy.
- `d2w fhir validate` checks a DHIS2 instance's codes and names for FHIR-safety (R4).

The package registers itself through the `dhis2.plugins` entry-point group, so installing it next to `dhis2w-cli` / `dhis2w-mcp` adds the `d2w fhir` commands and the read-only `fhir_validate` MCP tool. Naming of generated artifacts is configurable via `[generate.naming]` in `fhir.toml`.

Roadmap: org unit group / group set classifications as additional Organization.type codings (tokens OUG / OUGS), categories / category options as CodeSystem/ValueSet pairs, tracker programs as Patient + EpisodeOfCare alongside their per-stage forms, and the captured data as QuestionnaireResponse.
