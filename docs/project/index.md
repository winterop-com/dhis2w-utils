---
title: Project
---

# Project

The living record of the toolkit: what it does today, what changed, what is
planned, and the upstream quirks worked around along the way. These pages are
the meta layer around the surface docs (Client, CLI, MCP) and the architecture
reference.

<div class="grid cards" markdown>

- **Feature catalog**

    ---

    Every user-visible capability across the published packages and the three
    version trees, grouped by surface.

    [Browse the catalog](features.md)

- **Changelog**

- **Roadmap**

    ---

    Current state, gaps surfaced during use, the near-term slate, and the
    strategic options under consideration.

    [See the roadmap](../roadmap.md)

- **FHIR roadmap + review guide**

    ---

    The `dhis2w-fhir` plan in one place: what exists, the settled and open
    decisions, four review dimensions, and the build measurements.

    [Open the FHIR guide](fhir-roadmap.md)

- **FHIR conversion layer**

    ---

    How data crosses between DHIS2 and FHIR in both directions, and where the
    mapping definition lives.

    [Read the conversion plan](fhir-conversion.md)

- **Corrections and withdrawals**

    ---

    How a submitter corrects a value that already reached DHIS2, how a
    submission is retracted, and why withdrawal is terminal.

    [Read the lifecycle design](fhir-data-lifecycle.md)

- **DHIS2 fidelity audit**

    ---

    Every concept that makes DHIS2 distinctively DHIS2, with a verdict: carried,
    worth carrying with a named carrier, or deliberately not with the reason.

    [Read the fidelity audit](fhir-dhis2-fidelity.md)

- **FHIR harmonization**

    ---

    How N country guides relate: terminology alignment, a master guide, and
    indicator comparability, with the prerequisites each tier waits on.

    [Read the harmonization design](fhir-harmonization.md)

- **Upstream DHIS2 quirks**

    ---

    The catalogue of upstream DHIS2 bugs and surprises, each with a `curl` repro
    and the workaround applied in this repo.

    [Review the quirks](upstream-quirks.md)

- **Decisions and lessons**

    ---

    The maintainer-facing decisions log and lessons learned during development.

    [Decisions](../decisions.md) | [Lessons](../lessons.md)

</div>

## How these pages stay current

- **Feature catalog** is hand-maintained; the auto-generated
  [CLI reference](../cli-reference.md) and [MCP reference](../mcp-reference.md)
  are the source of truth when a count drifts.
- **Upstream quirks** and the **planning** pages render their repository-root
  source files (`BUGS.md`, the migration plan) directly, so editing the root
  file updates the site on the next build.
- **Roadmap** describes what is next, never what shipped; finished items are
  deleted from it rather than rewritten into history.
