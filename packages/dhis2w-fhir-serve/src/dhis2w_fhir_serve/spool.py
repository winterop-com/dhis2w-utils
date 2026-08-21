"""The response spool: every QuestionnaireResponse the facade received, and which lifecycle state it is in.

The spool is a directory tree under `.serve/responses` - or wherever `[serve] spool_dir` points this
project's, resolved through `dhis2w_fhir.spool.resolve_spool_root` so the forwarder reads the same
answer - with one subdirectory per state:

    `received/`   captured, not yet forwarded - the queue.
    `forwarded/`  translated, posted, and accepted by DHIS2.
    `rejected/`   posted and refused; `<id>.report.json` beside it holds the import report saying why.
    `withdrawn/`  it landed, and `d2w fhir withdraw` retracted it from DHIS2 afterwards;
                  `<id>.report.json` beside it is the record of the delete rather than of an import.

plus one directory that is not a state at all:

    `malformed/`  a holding pen for files that do not read as receipts, each with its reason beside it.

THE DIRECTORY IS THE INDEX, AND IT IS RE-READ ON EVERY CALL. That is the whole reason this module
holds no state. `d2w fhir forward` is a separate process that moves files between those three
directories while the server is running, so an index built at startup is wrong the moment the first
drain finishes: it would keep answering "received" for receipts DHIS2 has already accepted, and a
capture UI reading it would show a queue that never empties. Re-reading costs one `scandir` and one
parse per receipt, which is a rounding error against a facade that serves one project.

ONE BAD FILE COSTS ONE ROW, NOT THE LISTING. A file that will not parse is moved to `malformed/`
with its reason written beside it, and the read carries on with everything else. The loud-not-silent
principle is kept by reporting rather than by refusing: `GET /spool` counts what is in quarantine and
names each file with the error that put it there, which is strictly more than a 500 over the whole
listing ever told anyone. A directory this process cannot read at all is a different failure, and
still raises `UnreadableReceiptError`.

Writes are atomic and durable: a temporary file in the same directory, `fsync`, then a rename, then
an `fsync` of the directory - so a reader never sees a half-written response, a crash leaves the
directory consistent, and a 201 means the receipt survives the machine losing power. The spool
assumes a single *writing* process for `received/`, which is what `d2w fhir serve` is; the forwarder
only moves files that are already whole.

A stored response is the submission as it arrived - a receipt. It is never a live view of DHIS2
data, and reading one back tells you what a client sent, not what DHIS2 now holds. That stays true
after a forward: a forwarded receipt is still readable, because "DHIS2 took this" is a fact about
the receipt rather than a reason to stop serving it.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re
import tempfile
import time
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from dhis2w_fhir.service import ForwardImportOutcome, WithdrawalRecord
from dhis2w_fhir.spool import (
    QUARANTINE_REASON_SUFFIX,
    ForwardRefusalRecord,
    QuarantinedFile,
    read_refusal_record,
    resolve_spool_root,
)
from pydantic import BaseModel, ConfigDict, ValidationError

from dhis2w_fhir_serve.errors import BadSearchError, ServeError
from dhis2w_fhir_serve.log import LOGGER_NAME

#: The spool root a project holds unless `[serve] spool_dir` names another, relative to the project
#: root - regenerable working state, gitignored by the scaffold. A spool the project points somewhere
#: else is the operator's to keep out of version control and to back up.
SPOOL_RELATIVE_PATH = ".serve/responses"

#: Where a receipt waits for the forwarder to drain it.
RECEIVED_RESPONSES_RELATIVE_PATH = f"{SPOOL_RELATIVE_PATH}/received"

#: Where a receipt DHIS2 accepted is moved to, beside the report saying what the import counted.
FORWARDED_RESPONSES_RELATIVE_PATH = f"{SPOOL_RELATIVE_PATH}/forwarded"

#: Where a receipt DHIS2 refused is moved to, beside the report saying why.
REJECTED_RESPONSES_RELATIVE_PATH = f"{SPOOL_RELATIVE_PATH}/rejected"

#: Where a receipt `d2w fhir withdraw` retracted from DHIS2 is moved to, beside the record of the delete.
WITHDRAWN_RESPONSES_RELATIVE_PATH = f"{SPOOL_RELATIVE_PATH}/withdrawn"

#: Where a file that does not read as a receipt is moved to. Not a lifecycle state - a holding pen.
MALFORMED_RESPONSES_RELATIVE_PATH = f"{SPOOL_RELATIVE_PATH}/malformed"

#: What the sibling file carrying a drained receipt's import report is named, after the response id.
#: The forwarder writes one into `forwarded/` and into `rejected/` alike. The listing globs `*.json`,
#: so this suffix is also what keeps a report out of the receipt set, in either directory.
IMPORT_REPORT_SUFFIX = ".report.json"

#: What the sibling file carrying a still-queued receipt's forward refusal is named, after the
#: response id. A committing `d2w fhir forward` writes one into `received/` beside a receipt it
#: refused to translate and left queued, and the move that finally drains the receipt deletes it.
REFUSAL_RECORD_SUFFIX = ".refusal.json"

#: What every interrupted write leaves behind, and the suffix `tempfile.mkstemp` is called with here.
TEMPORARY_FILE_SUFFIX = ".tmp"

#: How old an abandoned temporary file has to be before a sweep deletes it.
ORPHAN_TEMPORARY_FILE_AGE_SECONDS = 3600.0

#: How many receipts one page of a spool read carries when the client names no `_count`.
DEFAULT_SPOOL_PAGE_SIZE = 50

#: The largest page a client is served, however large a `_count` it asks for. The register states its
#: own limit in `[serve.tracked_entities]` because a register page is a request to DHIS2; a spool page
#: is a read of this project's own directory, so the ceiling is this server's rather than the project's.
SPOOL_PAGE_SIZE_LIMIT = 500

#: The search parameter carrying the cursor, and the FHIR-defined one carrying the page size. The same
#: two names the register listing uses, so one client walks either listing the same way.
PAGE_PARAMETER = "page"
COUNT_PARAMETER = "_count"

#: The decoded shape of a spool cursor: how far into the listing the page starts, and the total
#: counted when the walk began.
_CURSOR_PATTERN = re.compile(r"^o(\d+)(?:n(\d+))?$")

#: What a `page` value this server did not mint is answered with - it is a link to follow, not a number.
_UNREADABLE_CURSOR = (
    "`page` is not a page of this listing: its value comes from the `next` or `previous` link of a "
    "result, and is not a number a client composes"
)

logger = logging.getLogger(LOGGER_NAME)


class ResponseLifecycle(StrEnum):
    """Which of the spool's four directories a receipt currently sits in.

    Three of the four are the forwarder's, spelled from the reading side: a receipt is `received`
    until `d2w fhir forward` drains it, and then it is whatever DHIS2 said. A response the translator
    refused stays `received` and the next drain retries it - a committing drain leaves its refusal
    record beside the receipt, which is what `refusal_record` reads - except for the one refusal no
    change to the guide or the data could ever fix, which the forwarder files as `rejected`.

    The fourth is an operator's, and it is the only one a receipt reaches without being posted again:
    `d2w fhir withdraw` deletes from DHIS2 what a forwarded receipt landed and files the receipt under
    `withdrawn/`, with the record of the delete beside it - which is what `withdrawal_record` reads.
    It is terminal, because DHIS2 burns the UID it deletes.

    The same four states as `dhis2w_fhir.spool.SpoolState`, which is the drain's own name for the
    layout. Two enums for one directory tree, because the two packages read it for different reasons
    and neither depends on the other's vocabulary; `tests/test_spool_directory.py` pins them level.

    `malformed/` is not here because nothing in it is a receipt: it is bytes that would not parse
    as one.
    """

    RECEIVED = "received"
    FORWARDED = "forwarded"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


#: The directory name each state is read from, and the order a listing counts them in.
LIFECYCLE_DIRECTORY_NAMES: dict[ResponseLifecycle, str] = {
    ResponseLifecycle.RECEIVED: "received",
    ResponseLifecycle.FORWARDED: "forwarded",
    ResponseLifecycle.REJECTED: "rejected",
    ResponseLifecycle.WITHDRAWN: "withdrawn",
}

#: The directory quarantined files are held in, which is a sibling of the three state directories.
MALFORMED_DIRECTORY_NAME = "malformed"


class UnreadableReceiptError(ServeError):
    """A spool directory cannot be read at all - a permission, a device, a broken mount.

    Not what one unreadable *file* raises: that file is moved to `malformed/`, named in the listing,
    and the read carries on, because a submission the facade silently drops looks to its sender
    exactly like one that never arrived - and so does a listing that 500s over one bad byte.
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
    submitted_by: str | None = None
    """The DHIS2 username the facade validated this submission under, or None when it validated none.

    Set only under `[serve] auth = "dhis2"`, where a caller presents credentials the instance answers
    for and the username DHIS2 gives back is who submitted. Under `none` there is nobody to name, and
    under `token` a static token names nobody either.

    FACADE-SIDE PROVENANCE, AND NOTHING MORE. It says who handed this receipt to this server. It does
    not say who the values reach DHIS2 as: `d2w fhir forward` posts as the forwarding profile, and
    `storedBy` on the instance is DHIS2's own stamp of that profile. The receipt is where "who
    captured this" is answered, and the instance is where "who wrote this" is.
    """

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


class SpoolReading(BaseModel):
    """What one read of the spool found: the receipts it parsed, and the files it moved to `malformed/`."""

    model_config = ConfigDict(frozen=True)

    receipts: tuple[StoredReceipt, ...] = ()
    quarantined: tuple[QuarantinedFile, ...] = ()


class SpoolCursor(BaseModel):
    """Where one page of a spool listing starts, and the total counted when the walk began.

    The total rides the cursor rather than being recounted per page, so a walk states one number
    throughout even though `d2w fhir forward` is moving files between the directories underneath it.
    A page is located by an offset into the newest-first order because that order is a fact about the
    receipts rather than about the filesystem: file names are uuid4 hex and say nothing about time.
    """

    model_config = ConfigDict(frozen=True)

    offset: int = 0
    counted_total: int | None = None
    """How many receipts the listing held when it was first counted; absent on the cursor a client starts from."""

    @classmethod
    def from_token(cls, token: str) -> SpoolCursor:
        """Read one `page` token, refusing anything this server did not mint."""
        try:
            decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode("ascii")
        except (binascii.Error, UnicodeDecodeError, ValueError) as error:
            raise BadSearchError(_UNREADABLE_CURSOR) from error
        match = _CURSOR_PATTERN.match(decoded)
        if match is None:
            raise BadSearchError(_UNREADABLE_CURSOR)
        counted = match.group(2)
        return cls(offset=int(match.group(1)), counted_total=None if counted is None else int(counted))

    def token(self) -> str:
        """This cursor as the `page` parameter carries it."""
        counted = "" if self.counted_total is None else f"n{self.counted_total}"
        return base64.urlsafe_b64encode(f"o{self.offset}{counted}".encode("ascii")).decode().rstrip("=")


class SpoolPage(BaseModel):
    """One page of a spool listing: what is on it, where it sits, and where the pages either side are."""

    model_config = ConfigDict(frozen=True)

    receipts: tuple[StoredReceipt, ...] = ()
    total: int = 0
    """How many receipts the whole listing holds, stated the same on every page of one walk."""

    cursor: SpoolCursor = SpoolCursor()
    next_cursor: SpoolCursor | None = None
    previous_cursor: SpoolCursor | None = None


class ResponseSpool(BaseModel):
    """The receipt tree of one project, read from disk on every call."""

    model_config = ConfigDict(frozen=True)

    directory: Path
    """The spool root - the four state directories, and `malformed/` beside them."""

    @classmethod
    def at(cls, project_root: Path, spool_dir: str = SPOOL_RELATIVE_PATH) -> ResponseSpool:
        """The spool of one project, creating the receiving directory so a first capture has somewhere to land.

        `spool_dir` is `[serve] spool_dir` - relative to the project root unless it is absolute - and
        it is resolved through `dhis2w_fhir.spool.resolve_spool_root`, which is the same resolution
        `d2w fhir forward` reads the key through. The layout under the root is stated in this module
        and in `dhis2w_fhir.spool` alike, for the reason that module gives; where the root is, is not.

        The orphan sweep runs here rather than per write: an abandoned temporary file is what a
        killed process leaves behind, and process start is exactly when there is a new process to
        notice it.
        """
        spool = cls(directory=resolve_spool_root(project_root, spool_dir))
        spool.directory_for(ResponseLifecycle.RECEIVED).mkdir(parents=True, exist_ok=True)
        spool.sweep_orphan_temporary_files()
        return spool

    def directory_for(self, lifecycle: ResponseLifecycle) -> Path:
        """Where receipts in one lifecycle state are read from and written to."""
        return self.directory / LIFECYCLE_DIRECTORY_NAMES[lifecycle]

    @property
    def malformed_directory(self) -> Path:
        """Where a file that does not read as a receipt is held, which is no receipt's lifecycle state."""
        return self.directory / MALFORMED_DIRECTORY_NAME

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
        file would make the id a client was handed at capture time expire on a schedule nothing told
        it. A file that will not parse is quarantined and answers as absent, which is what it now is.
        """
        for lifecycle in ResponseLifecycle:
            path = self.directory_for(lifecycle) / f"{response_id}.json"
            if not path.is_file():
                continue
            try:
                return _read_receipt(path, lifecycle)
            except _MalformedReceiptError as error:
                self._quarantine(path, str(error))
                return None
        return None

    def search(
        self,
        questionnaire: str | None = None,
        form_kind: str | None = None,
        ids: tuple[str, ...] = (),
        lifecycles: tuple[ResponseLifecycle, ...] = (),
    ) -> SpoolReading:
        """Every receipt matching the given filters, newest received first, with what was quarantined."""
        reading = self.read(lifecycles)
        matches = [
            receipt
            for receipt in reading.receipts
            if (questionnaire is None or receipt.questionnaire == questionnaire)
            and (form_kind is None or receipt.form_kind == form_kind)
            and (not ids or receipt.response_id in ids)
        ]
        ordered = sorted(matches, key=lambda receipt: (receipt.received_at, receipt.response_id), reverse=True)
        return SpoolReading(receipts=tuple(ordered), quarantined=reading.quarantined)

    def read(self, lifecycles: tuple[ResponseLifecycle, ...] = ()) -> SpoolReading:
        """Read every receipt in the named states off disk, moving aside whatever will not parse as one.

        The quarantine listing is the whole holding pen rather than what this read moved into it: a
        file that stopped being a receipt an hour ago is exactly as unactioned as one that stopped
        being one just now, and a listing that named only the latter would go quiet about the former.
        """
        selected = lifecycles or tuple(ResponseLifecycle)
        found: list[StoredReceipt] = []
        for lifecycle in selected:
            directory = self.directory_for(lifecycle)
            if not directory.is_dir():
                continue
            for path in _receipt_paths(directory):
                try:
                    found.append(_read_receipt(path, lifecycle))
                except _MalformedReceiptError as error:
                    self._quarantine(path, str(error))
        return SpoolReading(receipts=tuple(found), quarantined=self.malformed())

    def receipts(self, lifecycles: tuple[ResponseLifecycle, ...] = ()) -> tuple[StoredReceipt, ...]:
        """Read every receipt in the named states off disk, in file-name order per state."""
        return self.read(lifecycles).receipts

    def malformed(self) -> tuple[QuarantinedFile, ...]:
        """Every file in the holding pen, each named with the error that put it there."""
        directory = self.malformed_directory
        if not directory.is_dir():
            return ()
        return tuple(
            _quarantine_record(path)
            for path in sorted(_scan(directory))
            if not path.name.endswith(QUARANTINE_REASON_SUFFIX)
        )

    def import_report(self, response_id: str, lifecycle: ResponseLifecycle) -> ForwardImportOutcome | None:
        """What DHIS2 said about one drained receipt, read off the report the forwarder left beside it.

        Either drained state answers: `rejected/` holds why the payload was refused and `forwarded/`
        holds what the import counted. A receipt still in `received/` has no report because nothing
        has been asked about it yet, and answers None like any receipt whose report is not there. A
        withdrawn receipt is read through `withdrawal_record`, because the file beside it answers a
        different question - what DHIS2 did when it was asked to let the object go.

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

    def withdrawal_record(self, response_id: str) -> WithdrawalRecord | None:
        """What DHIS2 answered when `d2w fhir withdraw` asked it to take one receipt's event back.

        The sidecar of a withdrawn receipt is not an import report: it names the event that was
        deleted, the instant the delete was posted, and what the instance keeps afterwards - which is
        a hidden copy rather than nothing. The import report that said what the receipt landed stays
        in `forwarded/`, so the two answers to the two questions are two files.

        Only a `withdrawn` receipt has one. A record that will not parse answers None, for the reason
        `import_report` gives.
        """
        path = self.directory_for(ResponseLifecycle.WITHDRAWN) / f"{response_id}{IMPORT_REPORT_SUFFIX}"
        if not path.is_file():
            return None
        try:
            return WithdrawalRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            logger.warning("%s is not a readable withdrawal record; the receipt is listed without one", path)
            return None

    def refusal_record(self, response_id: str) -> ForwardRefusalRecord | None:
        """The refusal the last committing drain left beside one still-queued receipt.

        Only a `received` receipt can have one - the move that drains a receipt deletes the marker -
        and a receipt no committing drain has refused answers None, exactly like one no drain has
        seen. A record that will not parse also answers None, for the reason `import_report` gives.
        """
        return read_refusal_record(self.directory_for(ResponseLifecycle.RECEIVED), response_id)

    def count(self) -> int:
        """How many receipts the spool holds, across every lifecycle state."""
        return len(self.receipts())

    def count_by_lifecycle(self) -> dict[ResponseLifecycle, int]:
        """How many receipts sit in each state, which is the one number a queue is read by."""
        counts = dict.fromkeys(ResponseLifecycle, 0)
        for receipt in self.receipts():
            counts[receipt.lifecycle] += 1
        return counts

    def sweep_orphan_temporary_files(
        self, *, older_than_seconds: float = ORPHAN_TEMPORARY_FILE_AGE_SECONDS
    ) -> tuple[str, ...]:
        """Delete the temporary files an interrupted write left behind, and answer with what was deleted.

        THE AGE GUARD IS THE WHOLE OF THE SAFETY. A temporary file being written this instant is
        indistinguishable from one a killed process abandoned - same name shape, same directory - so
        the only thing separating them is how long ago the file was touched. A young one is left
        alone even though it is probably nothing, because deleting the file a running capture is
        mid-write into would turn a durable write into a lost one.
        """
        swept: list[str] = []
        cutoff = time.time() - older_than_seconds
        directories = [
            self.directory,
            *(self.directory_for(lifecycle) for lifecycle in ResponseLifecycle),
            self.malformed_directory,
        ]
        for directory in directories:
            if not directory.is_dir():
                continue
            for path in sorted(_scan(directory)):
                if not path.name.endswith(TEMPORARY_FILE_SUFFIX):
                    continue
                try:
                    if path.stat().st_mtime > cutoff:
                        continue
                    path.unlink()
                except OSError:
                    continue
                swept.append(path.name)
        return tuple(swept)

    def _quarantine(self, path: Path, reason: str) -> QuarantinedFile:
        """Move one unreadable file into the holding pen, its reason written down beside it first."""
        logger.warning("%s does not read as a receipt (%s); moved to %s", path, reason, self.malformed_directory)
        record = QuarantinedFile(file_name=path.name, reason=reason)
        directory = self.malformed_directory
        directory.mkdir(parents=True, exist_ok=True)
        _write_atomically(directory / f"{path.name}{QUARANTINE_REASON_SUFFIX}", record.model_dump_json(indent=2) + "\n")
        try:
            os.replace(path, directory / path.name)
            _fsync_directory(directory)
        except OSError as error:
            return QuarantinedFile(file_name=path.name, reason=f"{reason}; the file could not be moved aside ({error})")
        return record


def page_of(receipts: tuple[StoredReceipt, ...], cursor: SpoolCursor, count: int) -> SpoolPage:
    """Slice one page out of an ordered listing, and name the pages either side of it.

    The total is whatever the first page of a walk counted, carried forward on every link it hands
    out - so a client paging through a spool the forwarder is draining underneath it reads one
    number rather than a different one per page. An offset past the end is an empty page rather than
    a refusal: a link minted before the spool was drained has become a page with nothing on it.
    """
    total = cursor.counted_total if cursor.counted_total is not None else len(receipts)
    offset = min(cursor.offset, len(receipts))
    reached = SpoolCursor(offset=offset, counted_total=total)
    page = receipts[offset : offset + count]
    following = offset + len(page)
    return SpoolPage(
        receipts=page,
        total=total,
        cursor=reached,
        next_cursor=SpoolCursor(offset=following, counted_total=total) if following < len(receipts) else None,
        previous_cursor=SpoolCursor(offset=max(offset - count, 0), counted_total=total) if offset > 0 else None,
    )


def requested_page_size(stated: str | None) -> int:
    """How many receipts one page carries: what the client asked for, bounded by what this server serves.

    A `_count` above the limit is served the limit rather than refused - R4 says a server may return
    fewer resources than were asked for - while a `_count` that is not a positive number is a
    malformed query rather than an ambitious one, and is refused as such.
    """
    if stated is None:
        return DEFAULT_SPOOL_PAGE_SIZE
    try:
        count = int(stated)
    except ValueError as error:
        raise BadSearchError(f"`{COUNT_PARAMETER}` was given `{stated}`, which is not a number of rows") from error
    if count < 1:
        raise BadSearchError(f"`{COUNT_PARAMETER}` was given `{stated}`: a page carries at least one row")
    return min(count, SPOOL_PAGE_SIZE_LIMIT)


def requested_cursor(stated: str | None) -> SpoolCursor:
    """Which page was asked for - the first one when the request names none."""
    return SpoolCursor() if stated is None else SpoolCursor.from_token(stated)


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


class _MalformedReceiptError(Exception):
    """One file that does not read as a receipt, carrying the sentence the quarantine record holds."""


def _receipt_paths(directory: Path) -> list[Path]:
    """Every receipt file of one state directory, in file-name order, with the sidecars left out."""
    return sorted(
        path
        for path in _scan(directory)
        if path.suffix == ".json"
        and not path.name.endswith(IMPORT_REPORT_SUFFIX)
        and not path.name.endswith(REFUSAL_RECORD_SUFFIX)
    )


def _scan(directory: Path) -> list[Path]:
    """Every file of one directory, turning a directory this process cannot read into a named refusal."""
    try:
        return [path for path in directory.iterdir() if path.is_file()]
    except OSError as error:
        raise UnreadableReceiptError(f"{directory}: the spool directory cannot be read ({error})") from error


def _quarantine_record(path: Path) -> QuarantinedFile:
    """One quarantined file as a listing states it, reading the reason written beside it when it moved."""
    reason_path = path.with_name(f"{path.name}{QUARANTINE_REASON_SUFFIX}")
    if reason_path.is_file():
        try:
            return QuarantinedFile.model_validate_json(reason_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            return QuarantinedFile(file_name=path.name, reason="not readable as a receipt")
    return QuarantinedFile(file_name=path.name, reason="not readable as a receipt")


def _write_atomically(destination: Path, payload: str) -> None:
    """Write one file through a temporary sibling and a rename, so a reader never sees it half-written.

    The bytes reach the device before the rename and the rename reaches it before this returns -
    `fsync` on the file, then `fsync` on the directory that now names it - so the 201 a capture is
    answered with is a statement about a receipt that survives the machine losing power rather than
    about one that reached the page cache.
    """
    descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        _fsync_directory(destination.parent)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _fsync_directory(directory: Path) -> None:
    """Flush one directory's own entries, which is what makes a rename durable rather than merely done."""
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    except OSError:
        # A filesystem that will not fsync a directory handle - some network mounts do not - has
        # nothing further to offer here, and the file's own fsync has already run.
        pass
    finally:
        os.close(descriptor)


def _read_receipt(path: Path, lifecycle: ResponseLifecycle) -> StoredReceipt:
    """Parse one spooled file into a receipt, naming whichever way it is not one."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise UnreadableReceiptError(f"{path}: the file cannot be read ({error})") from error
    except json.JSONDecodeError as error:
        raise _MalformedReceiptError(f"not readable as JSON ({error})") from error
    try:
        envelope = StoredResponseEnvelope.model_validate(raw)
    except ValidationError as error:
        raise _MalformedReceiptError(f"not a stored response envelope ({error})") from error
    return StoredReceipt(**envelope.model_dump(), lifecycle=lifecycle)
