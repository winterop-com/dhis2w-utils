"""The capture spool the forwarder drains: where a received response is read from, and where it moves next.

`d2w fhir serve` writes every accepted `QuestionnaireResponse` to `.serve/responses/received/<id>.json`
as a receipt envelope, and `ls` on that directory is the pending count. This module is the read side of
the same convention plus the three states a drained response can end in:

    `received/`   captured, not yet forwarded - the queue.
    `forwarded/`  translated, posted, and accepted by DHIS2.
    `rejected/`   translated and posted, and DHIS2 refused it; `<id>.report.json` beside it says why.

A conversion-refused response never moves. The fix for it is in the IG or in the data, so leaving it in
`received/` makes the next `d2w fhir forward` a retry with no bookkeeping at all.

The layout is duplicated rather than imported: `dhis2w-fhir` is a dependency of `dhis2w-fhir-serve`, so
the arrow only points one way and the forwarder reads the files directly under the same conventions.
Moves are `os.replace` within one filesystem, so a response is in exactly one state at every instant.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from dhis2w_fhir.r4 import QuestionnaireResponse

__all__ = [
    "FORWARDED_RESPONSES_RELATIVE_PATH",
    "RECEIVED_RESPONSES_RELATIVE_PATH",
    "REJECTED_RESPONSES_RELATIVE_PATH",
    "REJECTION_REPORT_SUFFIX",
    "SpoolReadError",
    "SpooledResponse",
    "move_to_forwarded",
    "move_to_rejected",
    "read_received_responses",
]

#: Where `d2w fhir serve` writes a receipt, relative to the project root.
RECEIVED_RESPONSES_RELATIVE_PATH = ".serve/responses/received"

#: Where a response DHIS2 accepted is moved to, relative to the project root.
FORWARDED_RESPONSES_RELATIVE_PATH = ".serve/responses/forwarded"

#: Where a response DHIS2 refused is moved to, relative to the project root.
REJECTED_RESPONSES_RELATIVE_PATH = ".serve/responses/rejected"

#: What the sibling file carrying a rejection's import report is named, after the response id.
REJECTION_REPORT_SUFFIX = ".report.json"


class SpoolReadError(LookupError):
    """Raised when a spooled file cannot be read as the receipt the facade wrote."""


class SpooledResponse(BaseModel):
    """One receipt off the spool: the response to translate, plus where its file currently sits."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    received_at: str
    form_kind: str
    questionnaire: str
    project_root: Path
    path: Path
    """The file this receipt was read from, which is what the lifecycle moves."""

    response: QuestionnaireResponse
    """The captured response as a model, parsed from the verbatim resource the receipt carries."""


def read_received_responses(project_root: Path) -> tuple[SpooledResponse, ...]:
    """Read every pending receipt of one project, in file-name order so a drain is reproducible.

    An absent spool directory is not an error - it is a project nothing has been captured into yet -
    and answers with no receipts at all. A file that is in the directory and cannot be read as a
    receipt is a `SpoolReadError` naming it: a submission the forwarder silently skipped would look
    to its sender exactly like one that was never captured.
    """
    directory = project_root / RECEIVED_RESPONSES_RELATIVE_PATH
    if not directory.is_dir():
        return ()
    return tuple(_read_receipt(path, project_root) for path in sorted(directory.glob("*.json")))


def move_to_forwarded(spooled: SpooledResponse) -> Path:
    """Move one accepted receipt out of the queue, and answer with where it now lives."""
    return _move(spooled, FORWARDED_RESPONSES_RELATIVE_PATH)


def move_to_rejected(spooled: SpooledResponse, report: BaseModel) -> Path:
    """Write one rejection's report beside where the receipt is going, then move the receipt there.

    The report lands first, so a process that dies mid-move leaves a report with no receipt - a
    stale file the next run overwrites - rather than a rejected receipt nothing explains.
    """
    directory = spooled.project_root / REJECTED_RESPONSES_RELATIVE_PATH
    directory.mkdir(parents=True, exist_ok=True)
    _write_atomically(
        directory / f"{spooled.response_id}{REJECTION_REPORT_SUFFIX}",
        report.model_dump_json(indent=2, exclude_none=True) + "\n",
    )
    return _move(spooled, REJECTED_RESPONSES_RELATIVE_PATH)


def _move(spooled: SpooledResponse, relative_directory: str) -> Path:
    """Rename one receipt into another spool state, creating the destination directory if it is new."""
    directory = spooled.project_root / relative_directory
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / spooled.path.name
    os.replace(spooled.path, destination)
    return destination


def _write_atomically(destination: Path, payload: str) -> None:
    """Write one file through a temporary sibling and a rename, so a reader never sees it half-written."""
    descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _read_receipt(path: Path, project_root: Path) -> SpooledResponse:
    """Parse one spooled file into the receipt the forwarder drains, failing loudly and naming the file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SpoolReadError(f"{path}: not readable as JSON ({error})") from error
    if not isinstance(raw, dict):
        raise SpoolReadError(f"{path}: expected a JSON object holding a stored response envelope")
    resource = raw.get("response")
    if not isinstance(resource, dict):
        raise SpoolReadError(f"{path}: the envelope carries no `response` resource")
    try:
        response = QuestionnaireResponse.model_validate(resource)
    except ValidationError as error:
        raise SpoolReadError(
            f"{path}: the captured resource is not a QuestionnaireResponse this package reads ({error})"
        ) from error
    return SpooledResponse(
        response_id=str(raw.get("response_id") or response.id or path.stem),
        received_at=str(raw.get("received_at") or ""),
        form_kind=str(raw.get("form_kind") or ""),
        questionnaire=str(raw.get("questionnaire") or response.questionnaire or ""),
        project_root=project_root,
        path=path,
        response=response,
    )
