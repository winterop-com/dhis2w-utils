# dhis2w-fhir

FHIR Implementation Guide generation from DHIS2 metadata.

- `d2w fhir init` scaffolds a dockerized SUSHI IG project with a committed `fhir.toml`.
- `d2w fhir generate option-sets|org-units|all` emits FSH: option sets as CodeSystem/ValueSet pairs carrying both DHIS2 identifiers, organisation units as Organization/Location instances with partOf hierarchy.
- `d2w fhir validate` checks a DHIS2 instance's codes and names for FHIR-safety (R4).

The package registers itself through the `dhis2.plugins` entry-point group, so installing it next to `dhis2w-cli` / `dhis2w-mcp` adds the `d2w fhir` commands and the `fhir_*` MCP tools. Naming of generated artifacts is configurable via `[generate.naming]` in `fhir.toml`.

Roadmap: org unit group / group set classifications as additional Organization.type codings, categories / category options as CodeSystem/ValueSet pairs, Questionnaire generation from programs, translation designations.
