"""What the capture path says back: one issue vocabulary, and the two OperationOutcomes it builds.

A capture answers with an OperationOutcome whether it succeeded or not, because a response the
server accepted with warnings is the interesting case: the submission is stored, and the client
still has to be told what the server could not check or had to interpret. Rejections and
acceptances therefore share one issue type, and differ only in the severity they carry.

The issue codes are R4's own (`OperationOutcome.issue.code`), narrowed to the ones a capture can
raise. They are wider than the read path's vocabulary in `errors.py` on purpose: a read either
finds a resource or does not, while a capture fails against a profile, a terminology, or a
questionnaire's own item tree, and R4 names those failures separately.
"""

from __future__ import annotations

from typing import Literal

from dhis2w_fhir.r4 import OperationOutcome, OperationOutcomeIssue
from pydantic import BaseModel, ConfigDict

CaptureIssueSeverity = Literal["error", "warning", "information"]
"""The `OperationOutcome.issue.severity` values a capture reports."""

CaptureIssueCode = Literal[
    "invalid",
    "structure",
    "required",
    "value",
    "invariant",
    "code-invalid",
    "multiple-matches",
    "not-found",
    "not-supported",
    "business-rule",
    "informational",
]
"""The `OperationOutcome.issue.code` values a capture reports."""

#: What the information issue on an accepted capture states about what was stored.
RECEIPT_NOTE = "a stored response is the submission as received - a receipt, not a live view of DHIS2 data"


class CaptureIssue(BaseModel):
    """One thing the capture path found: where it is, what it is, and how badly it went."""

    model_config = ConfigDict(frozen=True)

    severity: CaptureIssueSeverity
    code: CaptureIssueCode
    expression: str | None = None
    diagnostics: str | None = None

    def is_error(self) -> bool:
        """Whether this issue rejects the submission rather than annotating it."""
        return self.severity == "error"


class CaptureRejection(Exception):
    """A submission the facade refused, carrying the status it answers with and every issue found."""

    def __init__(self, http_status: int, issues: tuple[CaptureIssue, ...]) -> None:
        super().__init__(f"capture rejected with {http_status}: {len(issues)} issue(s)")
        self.http_status = http_status
        self.issues = issues


def rejection_outcome(issues: tuple[CaptureIssue, ...]) -> OperationOutcome:
    """The body a refused capture answers with: every issue the failing phase found, in the order found."""
    return OperationOutcome(issue=[_issue(issue) for issue in issues])


def success_outcome(response_id: str, warnings: tuple[CaptureIssue, ...]) -> OperationOutcome:
    """The body an accepted capture answers with: what was stored, then whatever the server had to note."""
    stored = OperationOutcomeIssue(
        severity="information",
        code="informational",
        diagnostics=f"stored response {response_id}; {RECEIPT_NOTE}",
    )
    return OperationOutcome(issue=[stored, *(_issue(warning) for warning in warnings)])


def _issue(issue: CaptureIssue) -> OperationOutcomeIssue:
    """Carry one capture issue onto the R4 element it is reported as."""
    return OperationOutcomeIssue(
        severity=issue.severity,
        code=issue.code,
        diagnostics=issue.diagnostics,
        expression=[issue.expression] if issue.expression else None,
    )
