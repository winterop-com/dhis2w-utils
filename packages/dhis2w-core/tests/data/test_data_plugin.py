"""Unit tests for the data plugin (aggregate + tracker sub-groups)."""

from __future__ import annotations

from dhis2w_core.v42.plugins.data import plugin


def test_plugin_descriptor() -> None:
    """Plugin descriptor."""
    assert plugin.name == "data"
    assert "aggregate" in plugin.description.lower()
    assert "tracker" in plugin.description.lower()
