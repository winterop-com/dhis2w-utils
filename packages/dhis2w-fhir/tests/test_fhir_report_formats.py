"""Unit tests for the Markdown, CSV, and PDF renderings of the FHIR-safety validation report."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from dhis2w_fhir.validation.pdf import _code_cell, render_validation_pdf
from dhis2w_fhir.validation.report import (
    CSV_HEADER,
    display_code,
    render_validation_csv,
    render_validation_markdown,
)
from dhis2w_fhir.validation.schemas import FhirValidationReport, SeverityBreakdown, ValidationFinding

_GENERATED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

#: A Lao organisation-unit name - the script the bundled fallback font exists for.
_LAO_NAME = "ບ້ານ ນາໄຮ່"


def _finding(severity: str, resource_type: str, name: str, code: str | None = "X") -> ValidationFinding:
    """Build one finding for the renderers."""
    return ValidationFinding(
        severity=severity,  # type: ignore[arg-type]
        category="invalid-code",
        resource_type=resource_type,
        uid="Uid1aaaaaaa",
        name=name,
        code=code,
        message="code is not a valid FHIR code: code has leading whitespace",
    )


def _report() -> FhirValidationReport:
    """A multi-finding report spanning three resource types and all three severities."""
    return FhirValidationReport(
        option_set_count=3,
        option_count=9,
        resource_type_count=4,
        object_count=120,
        findings=[
            _finding("error", "options", "Male [in Sex]"),
            _finding("warning", "dataElements", "ANC 1st visit"),
            _finding("info", "organisationUnits", _LAO_NAME),
            _finding("error", "organisationUnits", 'Quoted "name", piped | too', code=None),
        ],
    )


def test_csv_header_and_rows() -> None:
    """The CSV carries the header row plus one row per finding, in report order."""
    rows = list(csv.reader(io.StringIO(render_validation_csv(_report()))))
    assert tuple(rows[0]) == CSV_HEADER
    assert len(rows) == 5
    assert rows[1] == [
        "error",
        "invalid-code",
        "options",
        "Uid1aaaaaaa",
        "Male [in Sex]",
        "X",
        "code is not a valid FHIR code: code has leading whitespace",
    ]


def test_csv_quotes_only_where_needed() -> None:
    """QUOTE_MINIMAL leaves plain values bare and quotes the ones carrying commas or quotes."""
    text = render_validation_csv(_report())
    assert "severity,category,resource_type,uid,name,code,message\r\n" in text
    assert '"Quoted ""name"", piped | too"' in text


def test_csv_renders_a_missing_code_as_empty() -> None:
    """A finding without a code leaves the code column empty rather than writing None."""
    rows = list(csv.reader(io.StringIO(render_validation_csv(_report()))))
    assert rows[4][5] == ""


def test_csv_of_a_clean_report_is_the_header_alone() -> None:
    """A report with no findings still produces a valid, header-only CSV."""
    assert render_validation_csv(FhirValidationReport()) == ",".join(CSV_HEADER) + "\r\n"


def test_pdf_is_a_pdf_of_reasonable_size() -> None:
    """A multi-finding report renders a real PDF carrying its embedded fonts."""
    payload = render_validation_pdf(_report(), "probe (https://dhis2.example)", _GENERATED_AT)
    assert payload.startswith(b"%PDF")
    assert len(payload) > 20_000


def test_pdf_renders_lao_script_names() -> None:
    """A Lao name renders through the bundled Noto Sans Lao fallback instead of dropping glyphs."""
    lao_only = FhirValidationReport(findings=[_finding("error", "organisationUnits", _LAO_NAME)])
    payload = render_validation_pdf(lao_only, "probe", _GENERATED_AT)
    assert payload.startswith(b"%PDF")
    assert b"NotoSansLao" in payload


def test_pdf_of_a_clean_report() -> None:
    """A report with zero findings still renders: cover, contents, and the clean result."""
    payload = render_validation_pdf(FhirValidationReport(), "probe", _GENERATED_AT)
    assert payload.startswith(b"%PDF")


def test_markdown_escapes_a_newline_inside_a_code() -> None:
    """A DHIS2 code carrying a literal newline (play 2.42 has them) prints its escape on one row."""
    report = FhirValidationReport(findings=[_finding("error", "categoryOptions", "Blue", code="BLUE\nBLUE")])
    markdown = render_validation_markdown(report, "probe", _GENERATED_AT)
    table_rows = [line for line in markdown.splitlines() if line.startswith("| error |")]
    assert len(table_rows) == 1
    assert "`BLUE\\nBLUE`" in table_rows[0]
    assert "BLUE\nBLUE" not in markdown


def test_csv_keeps_the_raw_code_a_report_displays_escaped() -> None:
    """The CSV is for machines: the code column carries the raw value, newline and all."""
    report = FhirValidationReport(findings=[_finding("error", "categoryOptions", "Blue", code="BLUE\nBLUE")])
    rows = list(csv.reader(io.StringIO(render_validation_csv(report))))
    assert rows[1][5] == "BLUE\nBLUE"


def test_pdf_renders_a_code_carrying_a_newline() -> None:
    """The same code renders through the PDF table without breaking the run."""
    report = FhirValidationReport(findings=[_finding("error", "categoryOptions", "Blue", code="BLUE\nBLUE")])
    assert render_validation_pdf(report, "probe", _GENERATED_AT).startswith(b"%PDF")


def test_display_code_makes_the_invisible_visible() -> None:
    """Control characters print as their escape and edge spaces are quoted onto the page."""
    assert display_code(None) == "-"
    assert display_code("") == "(empty)"
    assert display_code("ANC-01") == "ANC-01"
    assert display_code("BLUE\nBLUE") == "BLUE\\nBLUE"
    assert display_code("BLUE\r\nBLUE") == "BLUE\\r\\nBLUE"
    assert display_code("tab\there") == "tab\\there"
    assert display_code(" M ") == '" M "'
    assert display_code(" M") == '" M"'


def test_markdown_quotes_a_code_with_edge_spaces() -> None:
    """A code padded with spaces renders quoted, so the padding is on the page."""
    report = FhirValidationReport(findings=[_finding("error", "options", "Male [in Sex]", code=" M ")])
    markdown = render_validation_markdown(report, "probe", _GENERATED_AT)
    assert '`" M "`' in markdown


def test_markdown_flattens_newlines_inside_a_name() -> None:
    """The same flattening applies to the object column, which carries the DHIS2 name."""
    report = FhirValidationReport(findings=[_finding("error", "categoryOptions", "Two\r\nLines")])
    markdown = render_validation_markdown(report, "probe", _GENERATED_AT)
    assert "| Two Lines (Uid1aaaaaaa) |" in markdown


def test_markdown_carries_the_timestamp_and_per_section_breakdown() -> None:
    """The Markdown report states when it was generated and breaks each section down by severity."""
    markdown = render_validation_markdown(_report(), "probe", _GENERATED_AT)
    assert "Generated: 2026-08-01T12:00:00+00:00" in markdown
    assert "2 findings - 1 error, 0 warnings, 1 info" in markdown


def test_severity_breakdown_is_singular_at_one() -> None:
    """Every counted noun reads `1 error`, never `1 errors`."""
    single = SeverityBreakdown(total=1, errors=1, warnings=1, infos=1)
    assert single.line == "1 finding - 1 error, 1 warning, 1 info"
    plural = SeverityBreakdown(total=0, errors=0, warnings=2, infos=2)
    assert plural.line == "0 findings - 0 errors, 2 warnings, 2 infos"


def test_pdf_renders_an_empty_code_distinctly() -> None:
    """An empty-string code is a finding about an empty code, not about a missing one."""
    assert _code_cell("") == "(empty)"
    assert _code_cell(None) == "-"
    assert _code_cell("X") == "X"
    report = FhirValidationReport(findings=[_finding("error", "dataElements", "Blank", code="")])
    assert render_validation_pdf(report, "probe", _GENERATED_AT).startswith(b"%PDF")
