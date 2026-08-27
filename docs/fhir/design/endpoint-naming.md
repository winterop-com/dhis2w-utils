# Endpoint naming on a FHIR base URL

The facade runs two APIs in one process, at two addresses. The base URL is
FHIR's: it owns the resource-type paths (`/Patient`, `/Questionnaire`, and every
type a future release mints), `/metadata`, and the `$`-operation space, and its
contract is the CapabilityStatement. Everything the facade answers about
*itself* - the receipts it holds, the settings it was started with, who it
decided the caller is, the evaluator, the vocabularies, the register listings -
is a different API mounted at `/facade`, with its own OpenAPI document at
`/facade/openapi.json`. This note states why the surface is split that way, the
one family that is at the root and is not FHIR, and the rules a new endpoint is
placed by.

## The three families

- **FHIR space, at the base URL** - resource types, `/metadata`, and the
  declared operations (`$generate`, `$translate`, `$summary`, `$evaluate`). FHIR
  decides these spellings; there is no naming choice to make. `/metadata` is the
  contract, and a conformant client needs nothing else to use this surface.
- **The facade's own API, under `/facade`** - `/facade/whoami`,
  `/facade/spool`, `/facade/uiconfig`, `/facade/evaluate`,
  `/facade/metadata-health`, `/facade/terminology/lookup`,
  `/facade/terminology/validate-code`, and the two tracked entity listings.
  Plain `application/json` about the process rather than resources out of it,
  consumed by the capture UI and by operators. It is served as an application of
  its own, so it has a contract of its own: `/facade/openapi.json` describes
  every operation in it, typed from the same Pydantic models the handlers
  answer with, and `/facade/docs` renders that document as a page.
- **CDS Hooks, at the base URL** - `/cds-services` and `/cds-services/{id}`.
  Plain JSON, and not this facade's own API: CDS Hooks fixes discovery at
  `{base}/cds-services` exactly as FHIR fixes `{base}/metadata`, so an EHR
  configured with this server's base URL asks for that path and no other. A
  specification's path is not an implementation's to move.

## The rules, as practiced

1. A capability a FHIR client should reach is a **`$`-operation at the base
   URL**, declared in the CapabilityStatement through an OperationDefinition the
   server itself hosts. `$evaluate` beside `/facade/evaluate` is the worked
   example: the operation spelling serves the ecosystem, the plain-JSON spelling
   under the mount serves the UI, and one implementation answers both. The root
   has exactly one evaluation spelling, and it is the FHIR one.
2. An endpoint that answers about the **process** rather than about resources
   goes **under `/facade`**, whatever else is true of it. The tracked entity
   record is the case that proves the rule: it answers a FHIR `Bundle` under
   `application/fhir+json`, and it is under the mount anyway, because FHIR
   declares no interaction at `/{type}/{uid}/events` and the address is this
   facade's own invention.
3. A facade-own endpoint is a **flat hyphenated noun** naming what it answers,
   never a verb ceremony (`metadata-health`, not `check-metadata`).
4. A **prefix inside the mount** is introduced only when a family exists - two
   or more paths about one subject - and never speculatively. `terminology/*`
   earned its prefix; `whoami` did not.
5. A new path at the **base URL** needs a specification that fixes it there.
   FHIR's own space and CDS Hooks' discovery are the two that qualify today. A
   name invented here does not, and does not need to be checked against the R4
   resource-type list or against later releases' minted names, because it is not
   at the root to collide with them.

## What the split settles

Every flat name at the root used to be a bet that FHIR would never mint a
resource type with that spelling, and none of those names were discoverable by a
conformant client - `CapabilityStatement.rest` has no vocabulary for them. The
mount ends both problems at once. `/facade` is one lowercase segment, the only
one this facade invents at the root, and everything inside it is described by a
document written for exactly that purpose. `/metadata` describes FHIR;
`/facade/openapi.json` describes the controls; neither has to carry the other.
