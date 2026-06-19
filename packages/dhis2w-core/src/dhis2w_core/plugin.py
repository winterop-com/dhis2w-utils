"""Plugin Protocol + discovery for dhis2w-core.

Plugins are self-contained capability folders under
`dhis2w_core.v{41,42,43}.plugins.*`. Each plugin module exports a
module-level `plugin` attribute conforming to the `Plugin` Protocol.
External packages may register additional plugins via
`importlib.metadata.entry_points(group="dhis2.plugins")`.
"""

from __future__ import annotations

import importlib
import pkgutil
from importlib.metadata import entry_points
from typing import Any, Protocol, runtime_checkable

DEFAULT_VERSION_KEY = "v42"


def resolve_startup_version() -> str:
    """Pick the plugin-tree version key from the active profile (best-effort).

    Resolution chain (first match wins):

    1. `profile.version` from the active profile (set via
       `d2w profile add NAME ... --version v43` or hand-edited in
       `profiles.toml`). A pin here wins over `DHIS2_VERSION`.
    2. `DHIS2_VERSION` env var, mapped `41` / `42` / `43` -> `v41` / `v42` / `v43`.
       Applies only when the active profile has no `version` pin — it lets
       `make verify-examples DHIS2_VERSION=41` target the v41 tree against an
       unpinned profile without hand-editing it.
    3. `DEFAULT_VERSION_KEY` (`"v42"`) — the canonical baseline.

    Falls back to `DEFAULT_VERSION_KEY` on any resolution failure (no profile
    configured, corrupt TOML, etc.) so the CLI / MCP bootstrap never crashes —
    the wire client auto-detects regardless.
    """
    import os  # noqa: PLC0415 — scoped to startup discovery, avoids import-time cycles

    try:
        from dhis2w_core.profile import resolve

        resolved = resolve()
    except Exception:  # noqa: BLE001 — startup discovery must not raise
        resolved = None
    if resolved is not None and resolved.profile.version is not None:
        return resolved.profile.version.value
    env_version = os.environ.get("DHIS2_VERSION", "").strip()
    if env_version in {"41", "42", "43"}:
        return f"v{env_version}"
    if env_version in {"v41", "v42", "v43"}:
        return env_version
    return DEFAULT_VERSION_KEY


@runtime_checkable
class Plugin(Protocol):
    """Dual-surface plugin descriptor registered with the CLI and/or MCP."""

    name: str
    description: str

    def register_cli(self, app: Any) -> None:
        """Mount this plugin's Typer sub-app on the root CLI."""
        ...

    def register_mcp(self, mcp: Any) -> None:
        """Register this plugin's tools on the FastMCP server."""
        ...


def discover_plugins(version_key: str = "v42") -> list[Plugin]:
    """Discover built-in and entry-point plugins for the given major version.

    `version_key` picks which `dhis2w_core.v{N}.plugins.*` tree to walk —
    `"v41"`, `"v42"` (default), or `"v43"`. CLI / MCP bootstraps resolve
    this from the active profile and fall back to `"v42"` when nothing is
    set. Entry-point plugins are version-agnostic.
    """
    plugins: list[Plugin] = []
    plugins.extend(_discover_builtins(version_key))
    plugins.extend(_discover_external())
    return plugins


def _discover_builtins(version_key: str) -> list[Plugin]:
    try:
        package = importlib.import_module(f"dhis2w_core.{version_key}.plugins")
    except ImportError:
        return []
    found: list[Plugin] = []
    for _, name, _is_pkg in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"dhis2w_core.{version_key}.plugins.{name}")
        plugin = getattr(module, "plugin", None)
        if plugin is not None and isinstance(plugin, Plugin):
            found.append(plugin)
    return found


def _discover_external() -> list[Plugin]:
    found: list[Plugin] = []
    for entry in entry_points(group="dhis2.plugins"):
        try:
            plugin = entry.load()
        except ImportError:
            continue
        if isinstance(plugin, Plugin):
            found.append(plugin)
    return found
