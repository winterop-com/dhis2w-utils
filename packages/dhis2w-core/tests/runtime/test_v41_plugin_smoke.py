"""Smoke matrix for the v41 plugin tree — discover + import-time correctness.

Verifies every plugin under `dhis2w_core.v41.plugins.*` registers cleanly
when picked up by `discover_plugins("v41")`. Catches import-time failures
that would otherwise only surface when a v41-stack CLI/MCP user invokes
a specific plugin. Pairs with `test_v43_plugin_smoke.py`.
"""

from __future__ import annotations

from dhis2w_core.plugin import Plugin, discover_plugins

EXPECTED_PLUGINS = {
    "analytics",
    "apps",
    "browser",
    "customize",
    "data",  # mounts aggregate + tracker as sub-commands
    "dev",
    "doctor",
    "files",
    "maintenance",
    "messaging",
    "metadata",
    "profile",
    "route",
    "system",
    "user",
    "user-group",
    "user-role",
}


def test_v41_plugin_discovery_returns_full_set() -> None:
    """v41 plugin discovery returns full set."""
    plugins = discover_plugins("v41")
    names = {p.name for p in plugins}
    assert names >= EXPECTED_PLUGINS


def test_v41_every_plugin_conforms_to_protocol() -> None:
    """v41 every plugin conforms to protocol."""
    for plugin in discover_plugins("v41"):
        assert isinstance(plugin, Plugin)
        assert plugin.name
        assert plugin.description
        assert callable(plugin.register_cli)
        assert callable(plugin.register_mcp)


def test_v41_system_plugin_is_v41_bound() -> None:
    """v41 system plugin is v41 bound."""
    plugins = {p.name: p for p in discover_plugins("v41")}
    system = plugins["system"]
    # The plugin's class lives under dhis2w_core.v41.plugins.system, confirming
    # we got the v41 tree (and not v42 by accident).
    assert "v41" in type(system).__module__
