# dhis2-plugin-hello — external plugin example

Minimal standalone package showing how an external Python package adds a
`d2w <command>` + an MCP tool **without touching this repo**. Everything
works through `importlib.metadata.entry_points(group="dhis2.plugins")` —
dhis2w-core's loader walks that group at startup and mounts whatever it
finds.

## Layout

```
examples/plugin-external/
├── pyproject.toml              # [project.entry-points."dhis2.plugins"]
│                                  hello = "dhis2_plugin_hello:plugin"
├── README.md
└── src/
    └── dhis2_plugin_hello/
        ├── __init__.py         # exports `plugin = _HelloPlugin()`
        ├── service.py          # pure library code (uses open_client / profiles)
        ├── cli.py              # Typer sub-app, mounted as `d2w hello`
        └── mcp.py              # FastMCP tool `hello_say`
```

Same layout every first-party plugin uses (`packages/dhis2w-core/src/dhis2w_core/plugins/*/`).
The only extra step external plugins need is the entry-point line in
`pyproject.toml` — first-party plugins get picked up by a built-in
package scan instead.

## Install + use

```bash
# From the repo root:
uv add --editable examples/plugin-external/

# Verify it registered:
d2w --help | grep hello
#   hello        External plugin example.

d2w hello say
#   Hello, admin admin!

d2w hello say --greeting "Hei"
#   Hei, admin admin!

# Uninstall when done:
uv remove dhis2-plugin-hello
```

MCP equivalent:

```python
from fastmcp import Client
from dhis2w_mcp.server import build_server

async with Client(build_server()) as client:
    result = await client.call_tool("hello_say", {"greeting": "Hei"})
    print(result.structured_content)  # {"data": "Hei, admin admin!"}
```

## What to copy for your own plugin

1. Replace `dhis2_plugin_hello` with your package name everywhere (dir +
   entry-point + imports).
2. Change the entry-point key (`hello = "..."`) to your plugin's surface
   name — this is what appears in `d2w --help`.
3. Add whatever DHIS2 calls your plugin needs in `service.py`, expose
   them via `cli.py` + `mcp.py`, keep the plugin descriptor in
   `__init__.py`.

That's it. The CLI-vs-MCP parity is voluntary (a plugin that only
registers a CLI sub-app won't show up in MCP and vice versa).
