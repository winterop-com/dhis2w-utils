# dhis2w-cli

Typer console script `d2w` for working with DHIS2 instances from the shell. Discovers plugins from `dhis2w-core` — sixteen top-level domains covering metadata, data, analytics, tracker, users, routes, files, messaging, apps, doctor, and developer tools.

## Install

```bash
# Drops `d2w` on $PATH
uv tool install dhis2w-cli

# With Playwright UI automation (browser screenshots, OIDC login, PAT minting)
uv tool install 'dhis2w-cli[browser]'
playwright install chromium    # one-time, after the install above

# Update later
uv tool upgrade dhis2w-cli
```

Or run on demand without installing:

```bash
uvx --from dhis2w-cli d2w --help
```

## Configure

The CLI reads a profile from `.dhis2/profiles.toml` (project) or `~/.config/dhis2/profiles.toml` (user). One-shot bootstrap:

```bash
d2w profile bootstrap mywork
```

Or set env vars and skip the profile system entirely:

```bash
export DHIS2_URL=https://dhis2.example.org
export DHIS2_PAT=d2p_...
d2w system info
```

## Surface

```
d2w analytics    DHIS2 analytics queries.
d2w apps         DHIS2 apps — /api/apps + /api/appHub.
d2w browser      Playwright UI automation (only with [browser] extra).
d2w data         DHIS2 data values (aggregate + tracker).
d2w dev          Developer/operator tools.
d2w doctor       Probe a DHIS2 instance for known gotchas + requirements.
d2w fhir         FHIR IG generation (SUSHI/FSH) from DHIS2 metadata.
d2w files        Manage DHIS2 documents + file resources.
d2w maintenance  DHIS2 maintenance (tasks, cache, integrity, cleanup, refresh).
d2w messaging    DHIS2 internal messaging.
d2w metadata     DHIS2 metadata inspection.
d2w profile      Manage DHIS2 profiles.
d2w route        DHIS2 integration routes.
d2w system       DHIS2 system info.
d2w user         DHIS2 user administration.
d2w user-group   DHIS2 user-group administration.
d2w user-role    DHIS2 user-role administration.
```

`d2w --help` for the full tree; `d2w <group> --help` for each.

## Documentation

Full CLI reference: https://winterop-com.github.io/dhis2w-utils/cli-reference/.

`dhis2w-cli` is one member of the [`dhis2w-utils`](https://github.com/winterop-com/dhis2w-utils) workspace. The MCP server (`dhis2w-mcp`) exposes the same plugin surface as MCP tools.
