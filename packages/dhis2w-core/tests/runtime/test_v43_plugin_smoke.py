"""Smoke matrix for the v43 plugin tree — discover + import-time correctness.

Verifies every plugin under `dhis2w_core.v43.plugins.*` registers cleanly
when picked up by `discover_plugins("v43")`. Catches import-time failures
that would otherwise only surface when a v43-stack CLI/MCP user invokes
a specific plugin. Pairs with `test_v41_plugin_smoke.py`.
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


def test_v43_plugin_discovery_returns_full_set() -> None:
    """v43 plugin discovery returns full set."""
    plugins = discover_plugins("v43")
    names = {p.name for p in plugins}
    assert names >= EXPECTED_PLUGINS


def test_v43_every_plugin_conforms_to_protocol() -> None:
    """v43 every plugin conforms to protocol."""
    for plugin in discover_plugins("v43"):
        assert isinstance(plugin, Plugin)
        assert plugin.name
        assert plugin.description
        assert callable(plugin.register_cli)
        assert callable(plugin.register_mcp)


def test_v43_system_plugin_is_v43_bound() -> None:
    """v43 system plugin is v43 bound."""
    plugins = {p.name: p for p in discover_plugins("v43")}
    system = plugins["system"]
    # The plugin's class lives under dhis2w_core.v43.plugins.system, confirming
    # we got the v43 tree (and not v42 by accident).
    assert "v43" in type(system).__module__
