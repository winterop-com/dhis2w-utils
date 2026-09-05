"""The capture spool the forwarder drains: where a received response is read from, and where it moves next.

`d2w fhir serve` writes every accepted `QuestionnaireResponse` to `<spool root>/received/<id>.json` as a
receipt envelope - the root being `.serve/responses` inside the project unless `[serve] spool_dir` names
another - and `ls` on that directory is the pending count. This module is the read side of the same
convention plus the four states a receipt can end in:

    `received/`   captured, not yet forwarded - the queue.
    `forwarded/`  translated, posted, and accepted by DHIS2.
    `rejected/`   translated and posted, and DHIS2 refused it.
    `withdrawn/`  it landed, and `d2w fhir withdraw` retracted it from DHIS2 afterwards.

Three of those states carry an `<id>.report.json` sidecar holding what DHIS2 answered. A rejection needs
one to say why it was refused; an acceptance needs one because "DHIS2 took it" is not the whole answer
either - the import counts are what say how much of it landed, and a receipt filed with nothing beside
it leaves that unanswerable from the spool alone.

`withdrawn/` is the one state a receipt reaches without being posted again. Its report is what DHIS2
answered the delete, and the report of the import that landed it stays behind in `forwarded/`: that
document is still true of that import, and the two answer different questions. Withdrawal is terminal
by DHIS2's rule rather than by ours - the UID a tracker delete burns is refused under every import
strategy afterwards - so nothing moves a receipt back out of `withdrawn/`.

A fourth directory, `malformed/`, is a holding pen rather than a state: a file that does not read as a
receipt is moved there with its reason beside it, and the read that found it carries on. One unreadable
byte on disk must not cost the other two hundred receipts their drain, and a file skipped without being
named is a submission that has silently disappeared - so the policy is move it, name it, and continue.
A directory that cannot be read at all is a different failure and is still raised.

A conversion-refused response never moves, unless what refused it can never be fixed: `entered-in-error`
is a withdrawal, which this toolchain does not build, so that one is filed to `rejected/` rather than
retried by every drain forever. Every other refusal has a fix in the guide or in the data, so leaving it
in `received/` makes the next `d2w fhir forward` a retry with no bookkeeping at all. What a committing
drain does leave behind is an `<id>.refusal.json` beside the receipt - when the drain saw it, how many
drains have refused it, and why - so a listing can tell a receipt drains keep refusing from one no drain
has touched. The same sidecar carries the other refusal a drain makes and leaves queued: a response
whose aggregate values a forwarded receipt already sent, under `[forward] overwrites = "refuse"`. The
marker is about the queue, so the move that finally drains the receipt deletes it: the import report
supersedes it.

The layout is duplicated rather than imported: `dhis2w-fhir` is a dependency of `dhis2w-fhir-serve`, so
the arrow only points one way and the forwarder reads the files directly under the same conventions.
Moves are `os.replace` within one filesystem, so a response is in exactly one state at every instant.

WHERE the tree sits is the one thing both sides share code for. `[serve] spool_dir` moves it, and the
server that writes a receipt and the drain that files it have to land on the same directory to the
character - so `resolve_spool_root` here is what both of them resolve the key through, and the
duplicated names above are the layout *under* that root rather than a second answer to where it is.

One drain at a time. A `.drain.lock` in the spool root carries an exclusive `flock` for the length of
a run and the draining process id inside it, because two drains over one spool would post the same
receipt twice and race each other's renames.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, ValidationError

from dhis2w_fhir.r4 import QuestionnaireResponse

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = [
    "DRAIN_LOCK_FILE_NAME",
    "FORWARDED_RESPONSES_RELATIVE_PATH",
    "IMPORT_REPORT_SUFFIX",
    "MALFORMED_RESPONSES_RELATIVE_PATH",
    "ORPHAN_TEMPORARY_FILE_AGE_SECONDS",
    "QUARANTINE_REASON_SUFFIX",
    "RECEIVED_RESPONSES_RELATIVE_PATH",
    "REFUSAL_RECORD_SUFFIX",
    "REJECTED_RESPONSES_RELATIVE_PATH",
    "SPOOL_RELATIVE_PATH",
    "WITHDRAWN_RESPONSES_RELATIVE_PATH",
    "ForwardRefusalRecord",
    "QuarantinedFile",
    "RefusalReason",
    "SpoolContents",
    "SpoolLayout",
    "SpoolLockedError",
    "SpoolReadError",
    "SpoolReading",
    "SpoolState",
    "SpooledReceipt",
    "SpooledResponse",
    "drain_lock",
    "malformed_files",
    "move_to_forwarded",
    "move_to_received",
    "move_to_rejected",
    "move_to_withdrawn",
    "read_import_reports",
    "read_receipt",
    "read_received_responses",
    "read_refusal_record",
    "read_spooled_receipts",
    "record_refusal",
    "resolve_spool_root",
    "sweep_orphan_temporary_files",
    "write_import_report",
]

#: The spool root a project holds unless `[serve] spool_dir` names another, relative to the project
#: root. The six constants below spell that default layout out; a project that moved its spool has
#: the same directory names under the root `SpoolLayout` resolved for it.
SPOOL_RELATIVE_PATH = ".serve/responses"

#: Where `d2w fhir serve` writes a receipt by default, relative to the project root.
RECEIVED_RESPONSES_RELATIVE_PATH = ".serve/responses/received"

#: Where a response DHIS2 accepted is moved to by default, relative to the project root.
FORWARDED_RESPONSES_RELATIVE_PATH = ".serve/responses/forwarded"

#: Where a response DHIS2 refused is moved to by default, relative to the project root.
REJECTED_RESPONSES_RELATIVE_PATH = ".serve/responses/rejected"

#: Where a receipt `d2w fhir withdraw` retracted from DHIS2 is moved to by default, relative to the
#: project root.
WITHDRAWN_RESPONSES_RELATIVE_PATH = ".serve/responses/withdrawn"

#: Where a file that does not read as a receipt is moved to by default, relative to the project root.
#: Not a state a receipt is in - a holding pen for bytes nothing can act on until a person looks at them.
MALFORMED_RESPONSES_RELATIVE_PATH = ".serve/responses/malformed"

#: What the sibling file carrying a drained receipt's import report is named, after the response id.
#: The same suffix in `forwarded/` and in `rejected/`, because it is the same document either way -
#: what DHIS2 answered - and a reader that had to know the state to know the filename would be one
#: more convention for no gain.
IMPORT_REPORT_SUFFIX = ".report.json"

#: What the sibling file carrying a still-queued receipt's translator refusal is named, after the
#: response id. Written only by a committing drain, only in `received/`, and deleted by the move
#: that finally drains the receipt - it records the queue's own history, which an import report
#: supersedes. A dry run writes none, exactly as it moves nothing.
REFUSAL_RECORD_SUFFIX = ".refusal.json"

#: What the sibling file carrying a quarantined file's reason is named, after the file itself. The
#: reason is only known at the moment the file is moved aside, so it is written down there and then;
#: every later listing reads it back rather than re-deriving a parse failure it no longer has.
QUARANTINE_REASON_SUFFIX = ".reason.json"

#: The lockfile one drain holds for its whole run, inside the spool root.
DRAIN_LOCK_FILE_NAME = ".drain.lock"

#: What every interrupted write leaves behind, and the suffix `tempfile.mkstemp` is called with here.
TEMPORARY_FILE_SUFFIX = ".tmp"

#: How old an abandoned temporary file has to be before a sweep deletes it.
ORPHAN_TEMPORARY_FILE_AGE_SECONDS = 3600.0


class SpoolReadError(LookupError):
    """Raised when a spool directory cannot be read at all - a permission, a device, a broken mount.

    Not what an unreadable *file* raises: one bad file is quarantined and named, because losing a
    whole drain to it would be the larger failure. This is the directory itself refusing.
    """


class SpoolLockedError(LookupError):
    """Raised when another drain of the same spool holds the lock, naming the process that holds it."""


class SpoolState(StrEnum):
    """Which of the spool's four directories a receipt currently sits in.

    Three of the four are the drain's: a receipt is captured, and DHIS2 either takes the payload or
    refuses it. The fourth is an operator's, and it is the only one that is reached without posting
    the receipt again - `d2w fhir withdraw` retracts from DHIS2 what a forwarded receipt landed, and
    files the receipt here to say the submission stands withdrawn rather than unsent.
    """

    RECEIVED = "received"
    FORWARDED = "forwarded"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


#: The directory each state's receipts sit in, under whatever root the project points the spool at.
SPOOL_STATE_DIRECTORY_NAMES: dict[SpoolState, str] = {
    SpoolState.RECEIVED: "received",
    SpoolState.FORWARDED: "forwarded",
    SpoolState.REJECTED: "rejected",
    SpoolState.WITHDRAWN: "withdrawn",
}

#: What the holding pen is called, which is a sibling of the three state directories.
MALFORMED_DIRECTORY_NAME = "malformed"


def resolve_spool_root(project_root: Path, spool_dir: str = SPOOL_RELATIVE_PATH) -> Path:
    """Where one project's spool root sits: the stated directory, against the project unless absolute.

    The single answer both the server and the forwarder resolve `[serve] spool_dir` through. A
    relative path is the ordinary case and keeps the tree inside the project the receipts belong to;
    an absolute one is taken as written, which is how a spool lands on a volume the operator chose -
    and everything outside the project (version control, backups) is theirs to arrange from there.
    """
    stated = Path(spool_dir.strip())
    return stated if stated.is_absolute() else project_root / stated


class SpoolLayout(BaseModel):
    """One project's spool on disk: the project it belongs to, and the root its receipts live under.

    Carried rather than recomputed, because every move in a drain is a rename between two
    directories of this layout and a second opinion about where the root is would file a receipt
    where nothing looks for it. `project_root` rides along because a report names a spool file
    relative to the project, which stays true of a root outside it - the path is simply absolute there.
    """

    model_config = ConfigDict(frozen=True)

    project_root: Path
    root: Path

    @classmethod
    def resolve(cls, project_root: Path, spool_dir: str = SPOOL_RELATIVE_PATH) -> SpoolLayout:
        """The layout one project's `[serve] spool_dir` names, defaulting to the tree inside the project."""
        return cls(project_root=project_root, root=resolve_spool_root(project_root, spool_dir))

    def directory_for(self, state: SpoolState) -> Path:
        """Where receipts in one state are read from and moved to."""
        return self.root / SPOOL_STATE_DIRECTORY_NAMES[state]

    @property
    def malformed_directory(self) -> Path:
        """The holding pen for files that do not read as receipts, which is no receipt's state."""
        return self.root / MALFORMED_DIRECTORY_NAME

    @property
    def lock_path(self) -> Path:
        """The lockfile one drain holds for its whole run."""
        return self.root / DRAIN_LOCK_FILE_NAME


class QuarantinedFile(BaseModel):
    """One file moved to `malformed/` because it does not read as a receipt, and what stopped it."""

    model_config = ConfigDict(frozen=True)

    file_name: str
    """The name the file had in the state directory, kept unchanged by the move."""

    reason: str


class SpooledResponse(BaseModel):
    """One receipt off the spool: the response to translate, plus where its file currently sits."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    received_at: str
    form_kind: str
    questionnaire: str
    submitted_by: str | None = None
    """The DHIS2 username the facade validated the submission under, or None when it validated none.

    Facade-side provenance. It says who handed this receipt to `d2w fhir serve`, and says nothing
    about the identity the values reach DHIS2 under - a drain posts as the forwarding profile, and
    `storedBy` on the instance is DHIS2's own stamp of that profile.
    """

    layout: SpoolLayout
    """The spool this receipt came off, which is the one that files it - see `SpoolLayout`."""

    path: Path
    """The file this receipt was read from, which is what the lifecycle moves."""

    @property
    def project_root(self) -> Path:
        """The project this receipt belongs to, which is what a report names its path relative to."""
        return self.layout.project_root

    response: QuestionnaireResponse
    """The captured response as a model, parsed from the verbatim resource the receipt carries."""


class SpoolReading(BaseModel):
    """What one read of `received/` found: the receipts to drain, and the files it moved aside."""

    model_config = ConfigDict(frozen=True)

    responses: tuple[SpooledResponse, ...] = ()
    quarantined: tuple[QuarantinedFile, ...] = ()


class RefusalReason(BaseModel):
    """One reason a drain refused a spooled response, as the refusal record states it."""

    model_config = ConfigDict(frozen=True)

    category: str
    element: str | None = None
    reason: str


class ForwardRefusalRecord(BaseModel):
    """What the last committing drain wrote beside a receipt it refused to send.

    The receipt itself never moves and is never rewritten - see the module docstring - so this
    sidecar is the whole of the drain's mark on the queue: when it last looked, how many drains
    have refused the receipt, and why. Deleted by the move that finally drains the receipt.
    """

    model_config = ConfigDict(frozen=True)

    refused_at: str
    """The instant the last committing drain refused the receipt, as a FHIR `instant` (UTC)."""

    attempt_count: int = 1
    """How many committing drains have refused this receipt so far."""

    reasons: tuple[RefusalReason, ...] = ()

    @property
    def line(self) -> str:
        """The record as the one line a listing row shows: the first reason, or the bare fact."""
        if self.reasons:
            return self.reasons[0].reason
        return "a forward run refused this response"


class SpooledReceipt(BaseModel):
    """One receipt's envelope as a listing reads it, without translating the resource it carries.

    A listing answers where a receipt is and what it answers, and neither question needs the
    QuestionnaireResponse parsed - so a receipt whose resource this package's models cannot read is
    still a row rather than a hole.
    """

    model_config = ConfigDict(frozen=True)

    response_id: str
    received_at: str
    form_kind: str
    questionnaire: str
    submitted_by: str | None = None
    """The DHIS2 username the facade validated this submission under, or None when it validated none."""

    state: SpoolState
    path: Path

    refusal: ForwardRefusalRecord | None = None
    """The last committing drain's refusal of this still-queued receipt, when one is on disk."""


class SpoolContents(BaseModel):
    """Every receipt one project's spool holds, in each state, plus what is sitting in quarantine."""

    model_config = ConfigDict(frozen=True)

    receipts: tuple[SpooledReceipt, ...] = ()
    quarantined: tuple[QuarantinedFile, ...] = ()

    def in_state(self, state: SpoolState) -> tuple[SpooledReceipt, ...]:
        """Every receipt sitting in one state, in arrival order with the receipt id as the tiebreaker."""
        return tuple(receipt for receipt in self.receipts if receipt.state is state)


def read_received_responses(layout: SpoolLayout) -> SpoolReading:
    """Read every pending receipt of one project, in arrival order with the receipt id as the tiebreaker.

    A receipt id is a random hex string, so a directory listing orders on nothing a submission means.
    `received_at` is what a drain has to act on: DHIS2 replaces an aggregate value in place, so the
    instance ends up holding whichever submission was posted last, and posting the older one last
    would leave it holding the older number. Two receipts stamped the same instant order on their
    ids, which is arbitrary but the same on every run, so a drain stays reproducible.

    An absent spool directory is not an error - it is a project nothing has been captured into yet -
    and answers with no receipts at all. A file that will not read as a receipt is moved to
    `malformed/` with its reason beside it and named in the reading: a drain that aborted on it
    would lose every other receipt's turn to one file, and one that skipped it silently would make a
    submission disappear.
    """
    directory = layout.directory_for(SpoolState.RECEIVED)
    if not directory.is_dir():
        return SpoolReading()
    responses: list[SpooledResponse] = []
    quarantined: list[QuarantinedFile] = []
    for path in _receipt_paths(directory):
        try:
            responses.append(_read_receipt(path, layout))
        except _MalformedReceiptError as error:
            quarantined.append(_quarantine(path, layout, str(error)))
    responses.sort(key=lambda response: (response.received_at, response.response_id))
    return SpoolReading(responses=tuple(responses), quarantined=tuple(quarantined))


def read_receipt(layout: SpoolLayout, state: SpoolState, response_id: str) -> SpooledResponse:
    """Read one named receipt out of one state, resource and all, refusing by name when it is not there.

    What `d2w fhir withdraw` reads. A drain reads a whole directory because it acts on the queue; a
    withdrawal acts on one receipt an operator named, so it opens that file and nothing else - and a
    file that is not there, or will not read as a receipt, is a refusal rather than a quarantine,
    because the operator is standing in front of the answer.
    """
    path = layout.directory_for(state) / f"{response_id}.json"
    if not path.is_file():
        raise SpoolReadError(f"`{response_id}` is not a {state.value} receipt of {layout.project_root}")
    try:
        return _read_receipt(path, layout)
    except _MalformedReceiptError as error:
        raise SpoolReadError(f"{path}: {error}") from error


def read_spooled_receipts(layout: SpoolLayout) -> SpoolContents:
    """Read the envelope of every receipt in every state, quarantining whatever will not read as one.

    What `d2w fhir spool` lists. It touches no DHIS2 and parses no payload: a receipt is named by its
    envelope, which is the whole of what a queue listing states.

    Each state is listed in arrival order with the receipt id as the tiebreaker, which is the order
    `read_received_responses` drains in - so what a listing shows as next in the queue is what the
    next drain posts first.
    """
    receipts: list[SpooledReceipt] = []
    quarantined: list[QuarantinedFile] = []
    for state in SpoolState:
        directory = layout.directory_for(state)
        if not directory.is_dir():
            continue
        for path in _receipt_paths(directory):
            try:
                receipt = _read_envelope(path, state)
            except _MalformedReceiptError as error:
                quarantined.append(_quarantine(path, layout, str(error)))
                continue
            if state is SpoolState.RECEIVED:
                receipt = receipt.model_copy(update={"refusal": read_refusal_record(directory, receipt.response_id)})
            receipts.append(receipt)
    receipts.sort(key=lambda receipt: (receipt.received_at, receipt.response_id))
    return SpoolContents(receipts=tuple(receipts), quarantined=malformed_files(layout))


def malformed_files(layout: SpoolLayout) -> tuple[QuarantinedFile, ...]:
    """Every file sitting in `malformed/`, each with the reason written beside it when it was moved."""
    directory = layout.malformed_directory
    if not directory.is_dir():
        return ()
    return tuple(
        _quarantine_record(path)
        for path in sorted(_scan(directory))
        if not path.name.endswith(QUARANTINE_REASON_SUFFIX)
    )


def record_refusal(spooled: SpooledResponse, record: ForwardRefusalRecord) -> Path:
    """Write one still-queued receipt's refusal record beside it, durably, and answer with where it sits.

    The receipt itself is never rewritten; the record is a sibling file the next listing reads and
    the move that finally drains the receipt deletes. Written atomically and fsynced the way a
    receipt is, because a marker that vanishes with the power is a drain that never happened.
    """
    destination = spooled.path.with_name(f"{spooled.response_id}{REFUSAL_RECORD_SUFFIX}")
    _write_atomically(destination, record.model_dump_json(indent=2, exclude_none=True) + "\n")
    return destination


def read_refusal_record(directory: Path, response_id: str) -> ForwardRefusalRecord | None:
    """The refusal record beside one queued receipt, or None when no committing drain has refused it.

    A record that will not parse answers None rather than raising: it is the marker that got
    corrupted, not the receipt that got lost, so a listing still names the receipt and simply says
    nothing about the drain that refused it.
    """
    path = directory / f"{response_id}{REFUSAL_RECORD_SUFFIX}"
    if not path.is_file():
        return None
    try:
        return ForwardRefusalRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None


def move_to_forwarded(spooled: SpooledResponse, report: BaseModel) -> Path:
    """Write one acceptance's import report beside where the receipt is going, then move the receipt there."""
    return _file_beside_report(spooled, report, SpoolState.FORWARDED)


def write_import_report(layout: SpoolLayout, state: SpoolState, response_id: str, report: BaseModel) -> Path:
    """Write the import report beside one already-filed receipt, replacing whatever is there.

    What a drain uses to say something further about a receipt it has already moved - the answer to
    a completeness registration posted after the values landed. The receipt itself is never
    rewritten, and the write is atomic, so a reader either sees the previous report or this one.
    """
    directory = layout.directory_for(state)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{response_id}{IMPORT_REPORT_SUFFIX}"
    _write_atomically(destination, report.model_dump_json(indent=2, exclude_none=True) + "\n")
    return destination


def read_import_reports(layout: SpoolLayout, state: SpoolState) -> tuple[tuple[str, str], ...]:
    """Every import report of one state, as the receipt id it belongs to and the JSON text it holds.

    The text rather than a model: the shape a report carries is the service's business, and this
    module writes the file without reading what is in it. A file that will not read at all is left
    out rather than raised, exactly as an unreadable sidecar is elsewhere - one file must not cost a
    drain its answer about the rest.
    """
    directory = layout.directory_for(state)
    if not directory.is_dir():
        return ()
    reports: list[tuple[str, str]] = []
    for path in sorted(_scan(directory)):
        if not path.name.endswith(IMPORT_REPORT_SUFFIX):
            continue
        try:
            reports.append((path.name.removesuffix(IMPORT_REPORT_SUFFIX), path.read_text(encoding="utf-8")))
        except OSError:
            continue
    return tuple(reports)


def move_to_rejected(spooled: SpooledResponse, report: BaseModel) -> Path:
    """Write one rejection's import report beside where the receipt is going, then move the receipt there."""
    return _file_beside_report(spooled, report, SpoolState.REJECTED)


def move_to_withdrawn(spooled: SpooledResponse, report: BaseModel) -> Path:
    """Write what DHIS2 answered the delete beside `withdrawn/`, then move the forwarded receipt in after it.

    THE FORWARD'S OWN IMPORT REPORT STAYS IN `forwarded/`. It states what DHIS2 did with the payload
    when it took it, which is still true of that import and is the only record of what was landed;
    the document written here states what DHIS2 did when it was asked to take it back. Two answers
    to two questions, and neither is rewritten - the receipt itself never was.
    """
    return _file_beside_report(spooled, report, SpoolState.WITHDRAWN)


def move_to_received(layout: SpoolLayout, response_id: str) -> Path:
    """Move one rejected receipt back into the queue, and answer with where it now sits.

    THE SIDECAR STAYS IN `rejected/`. The report states what DHIS2 answered the last time this
    payload was posted, which is still true of that post and is the only record of what the receipt
    was requeued from; carrying it into `received/` would put a drained receipt's answer beside a
    receipt nothing has yet asked about. The next drain writes a fresh report wherever the receipt
    lands - overwriting the stale one in place when the answer is the same, and leaving it behind as
    history when the receipt is accepted this time.

    ANY REFUSAL RECORD IN `received/` GOES. This is the one way a receipt enters the queue from
    another state, and a marker under its name there can only be a leftover - a drain killed between
    the rename that filed the receipt and the unlink that cleared its marker. The receipt is entering
    the queue with no drain having refused it, so nothing beside it may say one did.
    """
    source = layout.directory_for(SpoolState.REJECTED) / f"{response_id}.json"
    if not source.is_file():
        raise SpoolReadError(f"`{response_id}` is not a rejected receipt of {layout.project_root}")
    directory = layout.directory_for(SpoolState.RECEIVED)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / source.name
    os.replace(source, destination)
    marker = directory / f"{response_id}{REFUSAL_RECORD_SUFFIX}"
    marker.unlink(missing_ok=True)
    _fsync_directory(directory)
    _fsync_directory(source.parent)
    return destination


@contextmanager
def drain_lock(layout: SpoolLayout) -> Generator[Path]:
    """Hold the spool's exclusive drain lock for one run, refusing at once when another run holds it.

    Two drains over one spool would translate the same receipts, post both copies, and race each
    other's renames - so the second one fails rather than waits: an operator who started it by
    mistake wants to be told, and one who started it deliberately wants the first run's answer
    rather than a queue behind it. The lockfile carries the holding process id so the refusal names
    what to look for, and the lock is an `flock` on an open descriptor, so the kernel releases it
    whether the drain returned, raised, or was killed.
    """
    layout.root.mkdir(parents=True, exist_ok=True)
    path = layout.lock_path
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise SpoolLockedError(_locked_message(path)) from error
        os.ftruncate(descriptor, 0)
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.fsync(descriptor)
        yield path
    finally:
        os.close(descriptor)


def sweep_orphan_temporary_files(
    layout: SpoolLayout, *, older_than_seconds: float = ORPHAN_TEMPORARY_FILE_AGE_SECONDS
) -> tuple[str, ...]:
    """Delete the temporary files an interrupted write left behind, and answer with what was deleted.

    THE AGE GUARD IS THE WHOLE OF THE SAFETY. A temporary file being written this instant is
    indistinguishable from one a killed process abandoned - same name shape, same directory - and the
    only thing the directory can say about the difference is how long ago the file was touched. So a
    young one is left alone even though it is probably nothing, because deleting the file a running
    capture is mid-write into would turn a durable write into a lost one.
    """
    swept: list[str] = []
    cutoff = time.time() - older_than_seconds
    directories = [
        layout.root,
        *(layout.directory_for(state) for state in SpoolState),
        layout.malformed_directory,
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


class _MalformedReceiptError(Exception):
    """One file that does not read as a receipt, carrying the sentence the quarantine record holds."""


def _receipt_paths(directory: Path) -> list[Path]:
    """Every receipt file of one state directory, with the sidecars left out.

    File-name order is a stable reading of the directory and nothing more; a caller that acts on the
    receipts orders them on `received_at` once they are parsed.
    """
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
        raise SpoolReadError(f"{directory}: the spool directory cannot be read ({error})") from error


def _quarantine(path: Path, layout: SpoolLayout, reason: str) -> QuarantinedFile:
    """Move one unreadable file to `malformed/`, its reason written down beside it first.

    The reason lands first for the same reason an import report does: a process that dies mid-move
    leaves a reason with no file - a stale note the next quarantine overwrites - rather than a file
    in the holding pen that nothing explains.
    """
    record = QuarantinedFile(file_name=path.name, reason=reason)
    directory = layout.malformed_directory
    directory.mkdir(parents=True, exist_ok=True)
    _write_atomically(directory / f"{path.name}{QUARANTINE_REASON_SUFFIX}", record.model_dump_json(indent=2) + "\n")
    try:
        os.replace(path, directory / path.name)
        _fsync_directory(directory)
    except OSError as error:
        return QuarantinedFile(file_name=path.name, reason=f"{reason}; the file could not be moved aside ({error})")
    return record


def _quarantine_record(path: Path) -> QuarantinedFile:
    """One quarantined file as a listing states it, reading the reason written beside it when it moved."""
    reason_path = path.with_name(f"{path.name}{QUARANTINE_REASON_SUFFIX}")
    if reason_path.is_file():
        try:
            return QuarantinedFile.model_validate_json(reason_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            return QuarantinedFile(file_name=path.name, reason="not readable as a receipt")
    return QuarantinedFile(file_name=path.name, reason="not readable as a receipt")


def _locked_message(path: Path) -> str:
    """Name the drain that holds the lock, in the terms the operator has to act on."""
    holder = _lock_holder(path)
    held_by = f"process {holder}" if holder is not None else "another process"
    return (
        f"another drain of this spool is running: {held_by} holds {path}. Wait for it to finish and "
        "forward again; if no such process is running, remove that file."
    )


def _lock_holder(path: Path) -> int | None:
    """The process id the holding drain wrote into the lockfile, or None when it wrote nothing readable."""
    try:
        stated = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(stated) if stated.isdigit() else None


def _file_beside_report(spooled: SpooledResponse, report: BaseModel, state: SpoolState) -> Path:
    """Land one receipt's import report in its destination, then move the receipt in after it.

    The report lands first, so a process that dies mid-move leaves a report with no receipt - a
    stale file the next run overwrites - rather than a drained receipt nothing explains. A refusal
    record an earlier drain left beside the receipt goes with the move: it recorded the queue, the
    receipt is leaving the queue, and the import report is now the answer about it.
    """
    directory = spooled.layout.directory_for(state)
    directory.mkdir(parents=True, exist_ok=True)
    _write_atomically(
        directory / f"{spooled.response_id}{IMPORT_REPORT_SUFFIX}",
        report.model_dump_json(indent=2, exclude_none=True) + "\n",
    )
    destination = _move(spooled, state)
    marker = spooled.path.with_name(f"{spooled.response_id}{REFUSAL_RECORD_SUFFIX}")
    if marker.is_file():
        marker.unlink(missing_ok=True)
        _fsync_directory(marker.parent)
    return destination


def _move(spooled: SpooledResponse, state: SpoolState) -> Path:
    """Rename one receipt into another spool state, creating the destination directory if it is new."""
    directory = spooled.layout.directory_for(state)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / spooled.path.name
    os.replace(spooled.path, destination)
    _fsync_directory(directory)
    _fsync_directory(spooled.path.parent)
    return destination


def _write_atomically(destination: Path, payload: str) -> None:
    """Write one file through a temporary sibling and a rename, so a reader never sees it half-written.

    The bytes reach the device before the rename and the rename reaches it before this returns -
    `fsync` on the file, then `fsync` on the directory that now names it - so what a caller
    acknowledges afterwards is a file that survives the machine losing power rather than one that
    reached the page cache.
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


def _read_receipt(path: Path, layout: SpoolLayout) -> SpooledResponse:
    """Parse one spooled file into the receipt the forwarder drains, naming what it stumbled on."""
    raw = _read_envelope_body(path)
    resource = raw.get("response")
    if not isinstance(resource, dict):
        raise _MalformedReceiptError("the envelope carries no `response` resource")
    try:
        response = QuestionnaireResponse.model_validate(resource)
    except ValidationError as error:
        raise _MalformedReceiptError(
            f"the captured resource is not a QuestionnaireResponse this package reads ({error})"
        ) from error
    return SpooledResponse(
        response_id=str(raw.get("response_id") or response.id or path.stem),
        received_at=str(raw.get("received_at") or ""),
        form_kind=str(raw.get("form_kind") or ""),
        questionnaire=str(raw.get("questionnaire") or response.questionnaire or ""),
        submitted_by=_submitted_by(raw),
        layout=layout,
        path=path,
        response=response,
    )


def _read_envelope(path: Path, state: SpoolState) -> SpooledReceipt:
    """Parse one spooled file into the row a listing states, without reading the resource it carries."""
    raw = _read_envelope_body(path)
    response_id = raw.get("response_id")
    if not isinstance(response_id, str) or not response_id:
        raise _MalformedReceiptError("the envelope names no `response_id`")
    return SpooledReceipt(
        response_id=response_id,
        received_at=str(raw.get("received_at") or ""),
        form_kind=str(raw.get("form_kind") or ""),
        questionnaire=str(raw.get("questionnaire") or ""),
        submitted_by=_submitted_by(raw),
        state=state,
        path=path,
    )


def _submitted_by(raw: dict[str, object]) -> str | None:
    """The username on one receipt envelope, or None when it carries none or carries something else."""
    stated = raw.get("submitted_by")
    return stated if isinstance(stated, str) and stated != "" else None


def _read_envelope_body(path: Path) -> dict[str, object]:
    """One receipt file as the JSON object it has to be, naming whichever way it is not one.

    The dict never leaves this module: both readers above wrap it in their own model before
    answering, which is what keeps the wire shape at the boundary it arrived on.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SpoolReadError(f"{path}: the file cannot be read ({error})") from error
    except json.JSONDecodeError as error:
        raise _MalformedReceiptError(f"not readable as JSON ({error})") from error
    if not isinstance(raw, dict):
        raise _MalformedReceiptError("expected a JSON object holding a stored response envelope")
    return raw
