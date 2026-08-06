"""Validation schemas: the sweep projections plus the finding and report shapes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class MetadataItemIn(BaseModel):
    """The metadata-object projection from the instance-wide `/api/metadata?fields=id,name,code` sweep."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str | None = None
    code: str | None = None


class MetadataCollectionIn(BaseModel):
    """The metadata-collection projection (e.g. dataElements) from the instance-wide sweep."""

    model_config = ConfigDict(frozen=True)

    resource: str
    items: list[MetadataItemIn] = Field(default_factory=list)


class ValidationFinding(BaseModel):
    """One FHIR-safety finding about a DHIS2 metadata object."""

    model_config = ConfigDict(frozen=True)

    severity: Literal["error", "warning", "info"]
    category: str
    resource_type: str
    uid: str
    name: str
    code: str | None = None
    message: str


def pluralize(count: int, noun: str) -> str:
    """Render a count with its noun, singular at exactly one (`1 error`, `0 errors`)."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


class SeverityBreakdown(BaseModel):
    """One group's finding counts, rendered as the single line both the Markdown and PDF reports print."""

    model_config = ConfigDict(frozen=True)

    total: int
    errors: int
    warnings: int
    infos: int

    @classmethod
    def of(cls, findings: list[ValidationFinding]) -> SeverityBreakdown:
        """Count the severities across one group of findings."""
        return cls(
            total=len(findings),
            errors=sum(1 for finding in findings if finding.severity == "error"),
            warnings=sum(1 for finding in findings if finding.severity == "warning"),
            infos=sum(1 for finding in findings if finding.severity == "info"),
        )

    @property
    def line(self) -> str:
        """The counts as one line, e.g. `12 findings - 3 errors, 4 warnings, 5 infos`."""
        return (
            f"{pluralize(self.total, 'finding')} - {pluralize(self.errors, 'error')}, "
            f"{pluralize(self.warnings, 'warning')}, {pluralize(self.infos, 'info')}"
        )


class FhirValidationReport(BaseModel):
    """Outcome of `d2w fhir validate` - FHIR-safety of a DHIS2 instance's codes."""

    option_set_count: int = 0
    option_count: int = 0
    attribute_count: int = 0
    resource_type_count: int = 0
    object_count: int = 0
    findings: list[ValidationFinding] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_count(self) -> int:
        """Number of error findings."""
        return sum(1 for finding in self.findings if finding.severity == "error")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warning_count(self) -> int:
        """Number of warning findings."""
        return sum(1 for finding in self.findings if finding.severity == "warning")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def info_count(self) -> int:
        """Number of info findings."""
        return sum(1 for finding in self.findings if finding.severity == "info")
