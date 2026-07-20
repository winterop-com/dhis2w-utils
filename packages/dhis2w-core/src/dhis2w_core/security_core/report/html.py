"""HTML report renderer: emits the data-driven report bundle (template, runtime, logo, data)."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from dhis2w_core.security_core.report.model import AuditReport
from dhis2w_core.security_core.report.view import build_report_view

# Fixed assets copied verbatim into every run folder. The template and runtime read all content
# from report-data.js at view time, so only report-data.js is regenerated per scan.
_ASSET_NAMES = ("report.dc.html", "support.js", "dhis2-logo.png")
_ASSET_PACKAGE = "dhis2w_core.security_core.report"
_ASSET_DIR = "assets"


class HtmlRenderer:
    """Renders the audit report as a multi-file HTML bundle opened via report.dc.html."""

    name = "html"
    suffix = "dc.html"

    def render(self, report: AuditReport) -> str:
        """Render the report-data.js payload (the window.__REPORT__ assignment)."""
        return build_report_view(report).to_report_data_js()

    def emit(self, folder: Path, report: AuditReport) -> None:
        """Write report-data.js and copy the fixed template, runtime, and logo into the folder."""
        (folder / "report-data.js").write_text(self.render(report), encoding="utf-8")
        assets = files(_ASSET_PACKAGE) / _ASSET_DIR
        for name in _ASSET_NAMES:
            (folder / name).write_bytes((assets / name).read_bytes())
