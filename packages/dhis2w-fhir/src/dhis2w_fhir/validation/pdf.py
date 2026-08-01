"""PDF rendering of the FHIR-safety validation report: cover page, clickable contents, one section per type.

Typography is Noto Sans with Noto Sans Lao as a fallback, both shipped beside this module under
`fonts/` with their OFL licence, so DHIS2 names in Lao script render instead of dropping to
boxes. The fonts are the only reason this module carries binary assets.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF
from fpdf.enums import TableCellFillMode, TextEmphasis
from fpdf.fonts import FontFace
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.validation.schemas import FhirValidationReport, SeverityBreakdown, ValidationFinding

if TYPE_CHECKING:
    from fpdf.outline import OutlineSection

__all__ = ["render_validation_pdf"]

_FONT_DIRECTORY = Path(__file__).parent / "fonts"
_FONT_FAMILY = "NotoSans"
_FALLBACK_FAMILY = "NotoSansLao"

_INK = (17, 17, 17)
_MUTED = (110, 110, 110)
_HEADER_FILL = (238, 238, 238)

#: Severity cell tints: red for errors, amber for warnings, grey for infos.
_SEVERITY_FILLS = {
    "error": (250, 214, 214),
    "warning": (252, 234, 199),
    "info": (231, 231, 231),
}

#: Relative widths of the five finding columns (Severity, Category, Object, Code, Detail).
_FINDING_COLUMN_WIDTHS = (16, 24, 44, 22, 84)

#: Every body cell names its font explicitly so the table renderer re-selects it per cell.
_BODY_FACE = FontFace(family=_FONT_FAMILY)


class _TypeSection(BaseModel):
    """One resource type's findings, in report order, with the breakdown the contents and heading print."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    breakdown: SeverityBreakdown
    findings: list[ValidationFinding]


def _code_cell(code: str | None) -> str:
    """Render the code column: a missing code as `-`, a code that is the empty string as `(empty)`."""
    if code is None:
        return "-"
    return code or "(empty)"


def render_validation_pdf(report: FhirValidationReport, target: str, generated_at: datetime) -> bytes:
    """Render the validation report as a PDF: cover page, clickable contents, one section per resource type."""
    sections = _sections(report)
    document = _ValidationPdf(target=target, sections=sections)
    document.set_auto_page_break(auto=True, margin=18)
    document.add_page()
    document.render_cover(report, generated_at)
    document.add_page()
    document.insert_toc_placeholder(document.render_table_of_contents, pages=_contents_pages(sections))
    # The placeholder's trailing page break leaves the cursor on a fresh page: the first section
    # takes it, so neither a full report nor an empty one carries a blank page.
    if sections:
        for index, section in enumerate(sections):
            document.render_section(section, start_new_page=index > 0)
    else:
        document.render_no_findings()
    return bytes(document.output())


def _contents_pages(sections: list[_TypeSection]) -> int:
    """Pages to reserve for the table of contents - about 30 rows fit on one."""
    return max(1, (len(sections) + 29) // 30)


def _sections(report: FhirValidationReport) -> list[_TypeSection]:
    """Bucket findings by resource type, sorted by type, each with its severity breakdown."""
    resource_types = sorted({finding.resource_type for finding in report.findings})
    sections: list[_TypeSection] = []
    for resource_type in resource_types:
        findings = [finding for finding in report.findings if finding.resource_type == resource_type]
        sections.append(
            _TypeSection(
                resource_type=resource_type,
                breakdown=SeverityBreakdown.of(findings),
                findings=findings,
            )
        )
    return sections


class _ValidationPdf(FPDF):
    """The validation-report document: Noto Sans typography, a running footer, and per-type sections."""

    def __init__(self, target: str, sections: list[_TypeSection]) -> None:
        """Set up an A4 document with the Noto Sans family and its Lao fallback registered."""
        super().__init__(orientation="P", unit="mm", format="A4")
        self.target = target
        self.sections = sections
        self.set_margins(12, 14, 12)
        self.add_font(_FONT_FAMILY, "", _FONT_DIRECTORY / "NotoSans-Regular.ttf")
        self.add_font(_FONT_FAMILY, "B", _FONT_DIRECTORY / "NotoSans-Bold.ttf")
        self.add_font(_FALLBACK_FAMILY, "", _FONT_DIRECTORY / "NotoSansLao-Regular.ttf")
        self.set_fallback_fonts([_FALLBACK_FAMILY])
        self.set_font(_FONT_FAMILY, "", 9)
        self.set_text_color(*_INK)

    def set_font(self, family: str | None = None, style: str | TextEmphasis = "", size: float = 0) -> None:
        """Select a font, always re-selecting it in full.

        fpdf2 switches `current_font` to a fallback font when it meets a glyph the selected font
        lacks, but leaves `font_family` pointing at the original. Its `set_font` then short-circuits
        on the unchanged family/style/size and the fallback stays active for every later run - so
        one Lao name would render the rest of the document in the Lao font. Clearing `font_family`
        first defeats that short-circuit.
        """
        resolved_family = family or self.font_family
        self.font_family = ""
        super().set_font(resolved_family, style, size)

    def footer(self) -> None:
        """Draw the running footer: the page counter on the left, the validated target on the right."""
        self.set_y(-14)
        self.set_font(_FONT_FAMILY, "", 7)
        self.set_text_color(*_MUTED)
        half = (self.w - self.l_margin - self.r_margin) / 2
        self.cell(half, 5, f"page {self.page_no()} of {{nb}}", align="L")
        self.cell(half, 5, self.target, align="R")
        self.set_text_color(*_INK)

    def render_cover(self, report: FhirValidationReport, generated_at: datetime) -> None:
        """Draw the title block and the instance-wide summary counts."""
        self.set_font(_FONT_FAMILY, "B", 20)
        self.multi_cell(0, 10, "FHIR-safety validation report", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_font(_FONT_FAMILY, "", 10)
        self.set_text_color(*_MUTED)
        self.multi_cell(0, 5.5, f"Target: {self.target}", new_x="LMARGIN", new_y="NEXT")
        self.multi_cell(
            0, 5.5, f"Generated: {generated_at.isoformat(timespec='seconds')}", new_x="LMARGIN", new_y="NEXT"
        )
        self.set_text_color(*_INK)
        self.ln(6)
        self.set_font(_FONT_FAMILY, "B", 12)
        self.multi_cell(0, 7, "Summary", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        self.set_font(_FONT_FAMILY, "", 9)
        rows = [
            ("Resource types swept", str(report.resource_type_count)),
            ("Objects swept", str(report.object_count)),
            ("Option sets (deep pass)", str(report.option_set_count)),
            ("Options (deep pass)", str(report.option_count)),
            ("Errors", str(report.error_count)),
            ("Warnings", str(report.warning_count)),
            ("Infos", str(report.info_count)),
        ]
        heading = FontFace(emphasis="BOLD", fill_color=_HEADER_FILL)
        with self.table(
            col_widths=(60, 20),
            width=80,
            text_align=("LEFT", "RIGHT"),
            headings_style=heading,
            borders_layout="SINGLE_TOP_LINE",
            cell_fill_mode=TableCellFillMode.NONE,
        ) as table:
            header = table.row()
            header.cell("Measure")
            header.cell("Count")
            for label, value in rows:
                row = table.row()
                row.cell(label, style=_BODY_FACE)
                row.cell(value, style=_BODY_FACE)

    def render_table_of_contents(self, pdf: FPDF, outline: list[OutlineSection]) -> None:
        """Render the clickable contents: one row per resource type with its finding breakdown."""
        pdf.set_xy(pdf.l_margin, pdf.t_margin)
        pdf.set_font(_FONT_FAMILY, "B", 14)
        pdf.multi_cell(0, 9, "Contents", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font(_FONT_FAMILY, "", 9)
        for entry in outline:
            section = self._section_for(entry.name)
            link = pdf.add_link(page=entry.page_number)
            pdf.set_text_color(20, 60, 140)
            pdf.cell(60, 6, entry.name, link=link)
            pdf.set_text_color(*_MUTED)
            pdf.cell(90, 6, section.breakdown.line if section is not None else "", link=link)
            pdf.set_text_color(*_INK)
            pdf.cell(0, 6, str(entry.page_number), align="R", new_x="LMARGIN", new_y="NEXT", link=link)
        if not outline:
            pdf.set_text_color(*_MUTED)
            pdf.multi_cell(0, 6, "No findings - every code is FHIR-safe.", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_INK)

    def render_no_findings(self) -> None:
        """State the clean result on its own page when the instance produced no findings at all."""
        self.set_font(_FONT_FAMILY, "B", 14)
        self.multi_cell(0, 9, "Findings", new_x="LMARGIN", new_y="NEXT")
        self.set_font(_FONT_FAMILY, "", 9)
        self.set_text_color(*_MUTED)
        self.multi_cell(0, 6, "No findings - every code is FHIR-safe.", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_INK)

    def render_section(self, section: _TypeSection, *, start_new_page: bool) -> None:
        """Open a bookmarked section for one resource type on its own page, then draw its findings table."""
        if start_new_page:
            self.add_page()
        self.start_section(section.resource_type)
        self.set_font(_FONT_FAMILY, "B", 14)
        self.multi_cell(0, 9, section.resource_type, new_x="LMARGIN", new_y="NEXT")
        self.set_font(_FONT_FAMILY, "", 9)
        self.set_text_color(*_MUTED)
        self.multi_cell(0, 5.5, section.breakdown.line, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_INK)
        self.ln(3)
        self.set_font(_FONT_FAMILY, "", 7.5)
        heading = FontFace(emphasis="BOLD", fill_color=_HEADER_FILL)
        with self.table(
            col_widths=_FINDING_COLUMN_WIDTHS,
            headings_style=heading,
            line_height=4.5,
            borders_layout="HORIZONTAL_LINES",
            cell_fill_mode=TableCellFillMode.NONE,
        ) as table:
            header = table.row()
            for label in ("Severity", "Category", "Object", "Code", "Detail"):
                header.cell(label)
            for finding in section.findings:
                row = table.row()
                row.cell(
                    finding.severity,
                    style=FontFace(family=_FONT_FAMILY, fill_color=_SEVERITY_FILLS[finding.severity]),
                )
                row.cell(finding.category, style=_BODY_FACE)
                row.cell(f"{finding.name} ({finding.uid})", style=_BODY_FACE)
                row.cell(_code_cell(finding.code), style=_BODY_FACE)
                row.cell(finding.message, style=_BODY_FACE)

    def _section_for(self, resource_type: str) -> _TypeSection | None:
        """Find the section belonging to one contents entry."""
        for section in self.sections:
            if section.resource_type == resource_type:
                return section
        return None
