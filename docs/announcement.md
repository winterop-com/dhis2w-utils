# Introducing dhis2w: a typed Python toolkit for DHIS2

Most people who automate DHIS2 from Python reach for an HTTP wrapper, make a call, and get a dictionary back. That works, and the official DHIS2 Python client does it cleanly. But once you're maintaining real integrations — across multiple instances, multiple DHIS2 majors, and increasingly alongside AI agents — you start wanting more than raw JSON.

That's what `dhis2w` is for. It's a Python toolkit for DHIS2, built around one idea: a single typed core that drives every surface you might need.

## Typed from the wire up

Every response is a Pydantic model generated from DHIS2's own OpenAPI spec. Your editor autocompletes field names, and a type checker flags a mistyped key before the code ever runs. You stop cross-referencing the API docs to remember whether it's `displayName` or `display_name`.

```python
from dhis2w_client import BasicAuth, Dhis2Client

async with Dhis2Client(base_url="...", auth=BasicAuth("admin", "district")) as client:
    me = await client.system.me()
    print(me.username)   # typed, autocompleted, checked
```

## One core, four surfaces

The same typed client backs a Python library, a `dhis2` CLI with eighteen command domains, an MCP server, and Playwright browser automation. Each DHIS2 domain has one `service.py` shared between the CLI and MCP, so the two surfaces never drift apart.

```bash
dhis2 system info
dhis2 metadata list dataElements --fields id,name
dhis2 doctor          # ~100 health + integrity checks against a live instance
```

## Built for AI agents

The MCP server exposes around 304 typed tools — one per CLI command — so any MCP host like Claude or Cursor can operate a DHIS2 instance directly, with typed inputs and outputs. Point an agent at your instance and it can read metadata, run analytics, or check system health without you wiring up a single endpoint.

## Version-aware across v41, v42, v43

`dhis2w` detects the DHIS2 major on connect and binds the matching hand-written tree, with the wire-shape differences between versions folded into the library. The same code runs against all three, and `dhis2 --version` tells you exactly which tree booted and why.

## Real auth, real multi-instance

Basic, PAT, and OAuth2/OIDC with PKCE, behind a pluggable provider protocol. A profile system (`.dhis2/profiles.toml`) lets you keep several instances configured side by side and switch between them by name.

## Where it fits

If you want the smallest possible dependency and raw JSON for a quick notebook pull, the official DHIS2 Python client is a great fit. If you want types, a CLI, agent tooling, and v41-v43 coverage in one place, that's what `dhis2w` adds.

It's third-party, unaffiliated with DHIS2, and pre-1.0 — the surface is still moving. Try it:

```bash
uv tool install dhis2w-cli
dhis2 --help
```

Source, docs, and runnable examples: https://github.com/winterop-com/dhis2w-utils
