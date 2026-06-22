"""Explorer bundle emitter: writes sharing-data.js and copies the fixed explorer assets.

Mirrors `security_core/report/html.py`: the template, runtime, vendored d3, and logo ship as package
data and are copied verbatim into the run folder beside a per-scan `sharing-data.js`
(`window.__SHARING__`). The data, runtime, and d3 are local, so the explorer works offline; the
template links webfonts from Google with a system-font fallback, matching the HTML report bundle.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from dhis2w_core.security_core.sharing.view import SharingView

# Fixed assets copied verbatim into every run folder. Only sharing-data.js is regenerated per scan.
_ASSET_NAMES = ("sharing-explorer.html", "sharing-runtime.js", "d3.min.js", "dhis2-logo.png")
_ASSET_PACKAGE = "dhis2w_core.security_core.sharing"
_ASSET_DIR = "assets"


class ExplorerRenderer:
    """Renders the interactive sharing explorer as a self-contained, offline multi-file bundle."""

    name = "sharing-explorer"

    def render(self, view: SharingView) -> str:
        """Render the sharing-data.js payload (the window.__SHARING__ assignment)."""
        return view.to_sharing_data_js()

    def emit(self, folder: Path, view: SharingView) -> None:
        """Write sharing-data.js and copy the fixed template, runtime, and vendored d3 into the folder."""
        (folder / "sharing-data.js").write_text(self.render(view), encoding="utf-8")
        assets = files(_ASSET_PACKAGE) / _ASSET_DIR
        for name in _ASSET_NAMES:
            (folder / name).write_bytes((assets / name).read_bytes())
