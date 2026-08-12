"""The response spool: every QuestionnaireResponse the facade received, and which lifecycle state it is in.

The spool is a directory tree under `.serve/responses`, one subdirectory per state:

    `received/`   captured, not yet forwarded - the queue.
    `forwarded/`  translated, posted, and accepted by DHIS2.
    `rejected/`   posted and refused; `<id>.report.json` beside it holds the import report saying why.

THE DIRECTORY IS THE INDEX, AND IT IS RE-READ ON EVERY CALL. That is the whole reason this module
holds no state. `d2w fhir forward` is a separate process that moves files between those three
directories while the server is running, so an index built at startup is wrong the moment the first
drain finishes: it would keep answering "received" for receipts DHIS2 has already accepted, and a
capture UI reading it would show a queue that never empties. Re-reading costs one `scandir` and one
parse per receipt, which is a rounding error against a facade that serves one project.

Writes are atomic (a temporary file in the same directory, then a rename), so a reader never sees a
half-written response and a crash leaves the directory consistent. The spool assumes a single
*writing* process for `received/`, which is what `d2w fhir serve` is; the forwarder only moves files
that are already whole.

A stored response is the submission as it arrived - a receipt. It is never a live view of DHIS2
data, and reading one back tells you what a client sent, not what DHIS2 now holds. That stays true
after a forward: a forwarded receipt is still readable, because "DHIS2 took this" is a fact about
the receipt rather than a reason to stop serving it.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from dhis2w_fhir.service import ForwardImportOutcome
from pydantic import BaseModel, ConfigDict, ValidationError

from dhis2w_fhir_serve.errors import ServeError
from dhis2w_fhir_serve.log import LOGGER_NAME

#: The spool root relative to the project root - regenerable working state, gitignored by the scaffold.
SPOOL_RELATIVE_PATH = ".serve/responses"

#: Where a receipt waits for the forwarder to drain it.
RECEIVED_RESPONSES_RELATIVE_PATH = f"{SPOOL_RELATIVE_PATH}/received"

#: Where a receipt DHIS2 accepted is moved to, beside the report saying what the import counted.
FORWARDED_RESPONSES_RELATIVE_PATH = f"{SPOOL_RELATIVE_PATH}/forwarded"

#: Where a receipt DHIS2 refused is moved to, beside the report saying why.
REJECTED_RESPONSES_RELATIVE_PATH = f"{SPOOL_RELATIVE_PATH}/rejected"

#: What the sibling file carrying a drained receipt's import report is named, after the response id.
#: The forwarder writes one into `forwarded/` and into `rejected/` alike. The listing globs `*.json`,
#: so this suffix is also what keeps a report out of the receipt set, in either directory.
IMPORT_REPORT_SUFFIX = ".report.json"

logger = logging.getLogger(LOGGER_NAME)


class ResponseLifecycle(StrEnum):
    """Which of the spool's three directories a receipt currently sits in.

    The states are the forwarder's, spelled from the reading side: a receipt is `received` until
    `d2w fhir forward` drains it, and then it is whatever DHIS2 said. A response the translator
    refused never moves, so it stays `received` and the next drain retries it - which is why there
    is no fourth state here even though a forward run reports one.
    """

    RECEIVED = "received"
    FORWARDED = "forwarded"
    REJECTED = "rejected"


#: The directory name each state is read from, and the order a listing counts them in.
LIFECYCLE_DIRECTORY_NAMES: dict[ResponseLifecycle, str] = {
    ResponseLifecycle.RECEIVED: "received",
    ResponseLifecycle.FORWARDED: "forwarded",
    ResponseLifecycle.REJECTED: "rejected",
}


class UnreadableReceiptError(ServeError):
    """A file in the spool directory cannot be read as the receipt the facade wrote.

    Loud rather than skipped, and named: a submission the facade silently drops looks to its sender
    exactly like one that never arrived.
    """

    status_code = 500
    issue_code = "exception"


class StoredResponseEnvelope(BaseModel):
    """One received QuestionnaireResponse plus the receipt metadata the facade recorded around it."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    received_at: str
    """The instant the facade accepted the response, as a FHIR `instant` (UTC, `Z`-suffixed)."""

    form_kind: str
    questionnaire: str
    warnings: tuple[str, ...] = ()
    response: dict[str, Any]
    """The QuestionnaireResponse as received, stamped with its `id` - the same escape hatch `StoreEntry.body` documents.

    The facade's contract is byte-faithful: a receipt has to read back as what the client sent, so the
    resource is held verbatim rather than round-tripped through a model that would drop the extensions
    and answer types this repo has no schema for. The dict leaves the spool only as an HTTP response body.
    """


class StoredReceipt(StoredResponseEnvelope):
    """One receipt as the spool answers it: the envelope on disk, plus which state its file sits in.

    The lifecycle is not in the envelope because it is not written into it - it is which directory
    the file is in, which is what makes a forward run a rename with no bookkeeping at all.
    """

    lifecycle: ResponseLifecycle


class ResponseSpool(BaseModel):
    """The receipt tree of one project, read from disk on every call."""

    model_config = ConfigDict(frozen=True)

    directory: Path
    """The spool root - the directory holding `received/`, `forwarded/`, and `rejected/`."""

    @classmethod
    def at(cls, project_root: Path) -> ResponseSpool:
        """The spool of one project, creating the receiving directory so a first capture has somewhere to land."""
        spool = cls(directory=project_root / SPOOL_RELATIVE_PATH)
        spool.directory_for(ResponseLifecycle.RECEIVED).mkdir(parents=True, exist_ok=True)
        return spool

    def directory_for(self, lifecycle: ResponseLifecycle) -> Path:
        """Where receipts in one lifecycle state are read from and written to."""
        return self.directory / LIFECYCLE_DIRECTORY_NAMES[lifecycle]

    def save(self, envelope: StoredResponseEnvelope) -> None:
        """Write the envelope atomically into the receiving directory, which is where a capture lands."""
        directory = self.directory_for(ResponseLifecycle.RECEIVED)
        directory.mkdir(parents=True, exist_ok=True)
        # The envelope's own fields and nothing else: a `StoredReceipt` handed back here would
        # otherwise write its lifecycle into the file, where it would immediately disagree with
        # the directory the file is in.
        payload = envelope.model_dump_json(indent=2, include=set(StoredResponseEnvelope.model_fields)) + "\n"
        _write_atomically(directory / f"{envelope.response_id}.json", payload)

    def get(self, response_id: str) -> StoredReceipt | None:
        """The receipt a `GET /QuestionnaireResponse/{id}` read resolves to, in whichever state it now sits.

        A forwarded receipt still reads back. Serving 404 the moment `d2w fhir forward` renamed the
        file would make the id a client was handed at capture time expire on a schedule nothing told it.
        """
        for lifecycle in ResponseLifecycle:
            path = self.directory_for(lifecycle) / f"{response_id}.json"
            if path.is_file():
                return _read_receipt(path, lifecycle)
        return None

    def search(
        self,
        questionnaire: str | None = None,
        form_kind: str | None = None,
        ids: tuple[str, ...] = (),
        lifecycles: tuple[ResponseLifecycle, ...] = (),
    ) -> tuple[StoredReceipt, ...]:
        """Every receipt matching the given filters, newest received first."""
        matches = [
            receipt
            for receipt in self.receipts(lifecycles)
            if (questionnaire is None or receipt.questionnaire == questionnaire)
            and (form_kind is None or receipt.form_kind == form_kind)
            and (not ids or receipt.response_id in ids)
        ]
        return tuple(sorted(matches, key=lambda receipt: (receipt.received_at, receipt.response_id), reverse=True))

    def receipts(self, lifecycles: tuple[ResponseLifecycle, ...] = ()) -> tuple[StoredReceipt, ...]:
        """Read every receipt in the named states off disk, in file-name order per state."""
        selected = lifecycles or tuple(ResponseLifecycle)
        found: list[StoredReceipt] = []
        for lifecycle in selected:
            directory = self.directory_for(lifecycle)
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                if path.name.endswith(IMPORT_REPORT_SUFFIX):
                    continue
                found.append(_read_receipt(path, lifecycle))
        return tuple(found)

    def import_report(self, response_id: str, lifecycle: ResponseLifecycle) -> ForwardImportOutcome | None:
        """What DHIS2 said about one drained receipt, read off the report the forwarder left beside it.

        Either drained state answers: `rejected/` holds why the payload was refused and `forwarded/`
        holds what the import counted. A receipt still in `received/` has no report because nothing
        has been asked about it yet, and answers None like any receipt whose report is not there.

        A report that will not parse answers None rather than raising: it is the diagnostic that got
        corrupted, not the receipt that got lost, so a listing still names the receipt and simply
        says nothing about what DHIS2 made of it.
        """
        path = self.directory_for(lifecycle) / f"{response_id}{IMPORT_REPORT_SUFFIX}"
        if not path.is_file():
            return None
        try:
            return ForwardImportOutcome.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            logger.warning("%s is not a readable import report; the receipt is listed without one", path)
            return None

    def count(self) -> int:
        """How many receipts the spool holds, across every lifecycle state."""
        return len(self.receipts())

    def count_by_lifecycle(self) -> dict[ResponseLifecycle, int]:
        """How many receipts sit in each state, which is the one number a queue is read by."""
        counts = dict.fromkeys(ResponseLifecycle, 0)
        for receipt in self.receipts():
            counts[receipt.lifecycle] += 1
        return counts


def new_response_id() -> str:
    """Mint a receipt id: a uuid4 hex, which is 32 characters of `[a-f0-9]` and so a valid FHIR id.

    Deliberately not a DHIS2 UID (`dhis2w_client.v42.uids.generate_uid`). A receipt is a resource the
    facade owns, not a DHIS2 object, and an 11-character DHIS2-shaped id would read as one. The hex
    form drops the dashes a uuid string carries so the id is safe in a path segment and a file name.
    """
    return uuid.uuid4().hex


def current_instant() -> str:
    """The current UTC time as a FHIR `instant` (`Z`-suffixed, second precision)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _read_receipt(path: Path, lifecycle: ResponseLifecycle) -> StoredReceipt:
    """Parse one spooled file into a receipt, failing loudly and naming the file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise UnreadableReceiptError(f"{path}: not readable as JSON ({error})") from error
    try:
        envelope = StoredResponseEnvelope.model_validate(raw)
    except ValidationError as error:
        raise UnreadableReceiptError(f"{path}: not a stored response envelope ({error})") from error
    return StoredReceipt(**envelope.model_dump(), lifecycle=lifecycle)
