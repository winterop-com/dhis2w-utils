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

    Every user-visible capability across all six packages and three version
    trees, grouped by surface.

    [Browse the catalog](features.md)

- **Changelog**

    ---

    Release-by-release history, newest first. Rendered from the repository-root
    `CHANGELOG.md`.

    [Read the changelog](changelog.md)

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
- **Changelog**, **upstream quirks**, and the **planning** pages render their
  repository-root source files (`CHANGELOG.md`, `BUGS.md`, the migration plan)
  directly, so editing the root file updates the site on the next build.
- **Roadmap** describes what is next, never what shipped; finished items are
  deleted from it rather than rewritten into history.
