"""Unit tests for the CSV and PDF renderings of the FHIR-safety validation report."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from dhis2w_fhir.validation.pdf import render_validation_pdf
from dhis2w_fhir.validation.report import CSV_HEADER, render_validation_csv
from dhis2w_fhir.validation.schemas import FhirValidationReport, ValidationFinding

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
        message="code is not a valid FHIR code (whitespace at the edges or doubled inside)",
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
        "code is not a valid FHIR code (whitespace at the edges or doubled inside)",
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
