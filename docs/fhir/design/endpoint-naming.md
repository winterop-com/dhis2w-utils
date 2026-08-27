# Endpoint naming on a FHIR base URL

The facade answers at one base URL, and that URL is not neutral ground: FHIR owns
the resource-type paths (`/Patient`, `/Questionnaire`, and every type a future
release mints), `/metadata`, and the `$`-operation space. Everything else the
facade serves shares that root. This note states the convention the surface
follows, the tension in it, and the decision parked at 2.0.0.

## The surface today

Three kinds of path answer at the base URL:

- **FHIR space** - resource types, `/metadata`, and the declared operations
  (`$generate`, `$translate`, `$summary`, `$evaluate`). FHIR decides these
  spellings; there is no naming choice to make.
- **The facade's own plain-JSON endpoints** - `/whoami`, `/spool`, `/uiconfig`,
  `/evaluate`, `/metadata-health`. Flat, lowercase, hyphenated nouns. These
  answer plain `application/json` about the facade itself and are consumed by
  the capture UI and by operators, not by FHIR clients.
- **Grouped families** - `/terminology/lookup` and `/terminology/validate-code`;
  `/tracked-entities/{uid}/enrollments` and `/tracked-entities/{uid}/events`.
  A prefix appears only once two or more paths share a subject.

## The rules, as practiced

1. A capability a FHIR client should reach is a **`$`-operation**, declared in
   the CapabilityStatement through an OperationDefinition the server itself
   hosts. `$evaluate` beside `/evaluate` is the worked example: the plain-JSON
   spelling serves the UI, the operation spelling serves the ecosystem, and one
   implementation answers both.
2. A facade-own endpoint is a **flat hyphenated noun** naming what it answers,
   never a verb ceremony (`/metadata-health`, not `/check-metadata`).
3. A **prefix** is introduced only when a family exists - two or more paths
   about one subject - and never speculatively. `/terminology/*` earned its
   prefix; `/whoami` did not.
4. A new flat name is checked against the R4 resource-type list **and** against
   the names later releases have already minted, before it ships.

## The tension

Every flat name at the root is a bet that FHIR never mints a resource type with
that spelling, and none of the flat endpoints are discoverable by a conformant
client - `CapabilityStatement.rest` has no vocabulary for them. Two of them sit
uncomfortably already: `/metadata-health` is one hyphen away from FHIR's own
`/metadata`, and `/evaluate` predates its `$evaluate` twin rather than deriving
from it.

## Parked at 2.0.0

Whether the plain-JSON family moves under one reserved prefix (a single
non-resource segment the UI and operators use, leaving the root to FHIR) is a
breaking rename, and 2.0.0 is the stated horizon for breaks of that kind. The
decision is deliberately not taken here; what this note fixes is the rule for
every endpoint added **until** then - follow the four rules above, and prefer
the `$`-operation route whenever the consumer could be a FHIR client rather
than this facade's own screens.
