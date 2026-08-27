"""`GET /facade/spool` - the receipt tree with its lifecycle, for the capture UI's Responses page.

WHY THIS IS NOT FHIR, STATED ONCE SO NOBODY HAS TO RE-DERIVE IT.

Almost everything this facade answers has a FHIR spelling, and where one exists it is used - the
receipts themselves are `GET /QuestionnaireResponse`, and that search covers all three lifecycle
states, so a client that only speaks FHIR still sees every receipt. What that search cannot carry
is the receipt *envelope*: when the facade accepted the submission, which DHIS2 form kind it was
validated as, what the server had to warn about, which of the spool's four directories the file
now sits in, and - for a rejection - the DHIS2 import report `d2w fhir forward` left beside it.

None of those are elements of a QuestionnaireResponse. Two of them could be forced into `meta`
(`lastUpdated` for the receipt instant, a `tag` for the lifecycle), and a DHIS2 `ImportSummary`
could be bent into an `OperationOutcome`, but that would spread one record across a FHIR resource,
a tag system this IG does not publish, and a second operation - and the DHIS2 import counts would
still have nowhere honest to go. A facade-owned record with no FHIR analogue is better served as
what it is. So this is a plain typed JSON endpoint, `application/json`, and its shape is Pydantic
models rather than a Bundle.

AND SO IT LIVES UNDER `/facade`, which is where every answer of that kind lives. The base URL is
FHIR's and its contract is the CapabilityStatement; this facade's own API is a different contract at
a different address, published as OpenAPI at `/facade/openapi.json`. Two APIs, two documents, one
process. `dhis2w_fhir_serve.routes` states the mounting and `docs/fhir/design/endpoint-naming.md`
states the rule a new endpoint is placed by.

Every read re-reads the directory. `d2w fhir forward` moves files while this server runs, so a
listing built from anything else is stale by design; see `dhis2w_fhir_serve.spool`.

THE LISTING IS PAGED, with the same two parameters the register listing uses: `_count` for how many
rows a page carries and `page` for an opaque cursor a client only ever gets from a `next` or
`previous` link. `total` is the whole listing on every page of one walk, and the per-state counts are
the whole spool rather than the page - a queue depth that changed with the page you were looking at
would be no queue depth at all.
"""

from __future__ import annotations

from typing import Annotated

from dhis2w_fhir.r4 import Extension, QuestionnaireResponse, QuestionnaireResponseItem
from dhis2w_fhir.service import ForwardImportOutcome, WithdrawalRecord
from dhis2w_fhir.spool import ForwardRefusalRecord, QuarantinedFile
from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from dhis2w_fhir_serve.capture.naming import PERIOD_ISO_SUB_EXTENSION, PERIOD_TYPE_SUB_EXTENSION, CaptureNaming
from dhis2w_fhir_serve.routes.capture import capture_state
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.spool import (
    COUNT_PARAMETER,
    PAGE_PARAMETER,
    ResponseLifecycle,
    ResponseSpool,
    SpoolCursor,
    StoredReceipt,
    page_of,
    requested_cursor,
    requested_page_size,
)

#: Where the listing is served from, under the facade API's mount.
SPOOL_PATH = "/spool"

#: What this operation is grouped under in the facade API's document.
SPOOL_TAG = "Receipts"

#: The prefix a Location reference carries before the DHIS2 organisation-unit uid.
LOCATION_REFERENCE_PREFIX = "Location/"

router = APIRouter()


class SpoolRejectionIssue(BaseModel):
    """One row DHIS2 named as a reason it would not take the payload."""

    model_config = ConfigDict(frozen=True)

    error_code: str | None = None
    subject: str | None = None
    message: str | None = None


class SpoolRejection(BaseModel):
    """What DHIS2 said about one refused receipt, projected out of the report the forwarder stored.

    A projection rather than the report itself: `ForwardImportOutcome` carries the endpoint's whole
    generated document alongside its rollup, and a listing that shipped those would send a
    `TrackerImportReport` per rejected row to a browser that renders four fields of it.
    """

    model_config = ConfigDict(frozen=True)

    status: str | None = None
    message: str | None = None
    created: int = 0
    updated: int = 0
    ignored: int = 0
    issues: tuple[SpoolRejectionIssue, ...] = ()

    @classmethod
    def from_outcome(cls, outcome: ForwardImportOutcome) -> SpoolRejection:
        """Reduce one stored import report to the rollup a rejected row shows."""
        return cls(
            status=outcome.status,
            message=outcome.message,
            created=outcome.created,
            updated=outcome.updated,
            ignored=outcome.ignored,
            issues=tuple(
                SpoolRejectionIssue(error_code=issue.error_code, subject=issue.subject, message=issue.message)
                for issue in outcome.issues
            ),
        )


class SpoolImport(BaseModel):
    """What DHIS2 counted when it took one receipt, projected out of the report the forwarder stored.

    The counts without the issue rows a rejection carries, because an import DHIS2 accepted named no
    rows against the payload - `created`, `updated`, `ignored` and `deleted` are the whole of what it
    said. They are what answers "the receipt is forwarded, but did any of it land": an import that
    ignored every value is an accepted receipt that changed nothing in the instance.
    """

    model_config = ConfigDict(frozen=True)

    status: str | None = None
    message: str | None = None
    created: int = 0
    updated: int = 0
    ignored: int = 0
    deleted: int = 0

    @classmethod
    def from_outcome(cls, outcome: ForwardImportOutcome) -> SpoolImport:
        """Reduce one stored import report to the counts an accepted row shows."""
        return cls(
            status=outcome.status,
            message=outcome.message,
            created=outcome.created,
            updated=outcome.updated,
            ignored=outcome.ignored,
            deleted=outcome.deleted,
        )


class SpoolRefusal(BaseModel):
    """What the last committing drain said when it refused to translate one still-queued receipt.

    The receipt stays `received` and the next drain retries it, so this is the queue's own history
    rather than a DHIS2 answer: when the drain looked, how many drains have refused the receipt so
    far, and why. Projected out of the refusal record the forwarder stored beside the receipt.
    """

    model_config = ConfigDict(frozen=True)

    refused_at: str
    attempt_count: int = 1
    reasons: tuple[SpoolRejectionIssue, ...] = ()

    @classmethod
    def from_record(cls, record: ForwardRefusalRecord) -> SpoolRefusal:
        """Reduce one stored refusal record to the rollup a still-queued row shows."""
        return cls(
            refused_at=record.refused_at,
            attempt_count=record.attempt_count,
            reasons=tuple(
                SpoolRejectionIssue(error_code=reason.category, subject=reason.element, message=reason.reason)
                for reason in record.reasons
            ),
        )


class SpoolWithdrawal(BaseModel):
    """What DHIS2 answered when it was asked to take one receipt's event back, and what it keeps afterwards.

    Projected out of the withdrawal record `d2w fhir withdraw` stored beside the receipt. The note is
    the record's own sentence rather than a phrasing invented here: DHIS2 soft-deletes, so the row
    stays in the instance carrying its value and is gone from every ordinary read, and a listing that
    said "deleted" would be claiming more than the toolkit can stand behind.
    """

    model_config = ConfigDict(frozen=True)

    withdrawn_at: str
    """The instant the withdrawal was posted, as a FHIR `instant` (UTC)."""

    event_uid: str
    """The DHIS2 event the withdrawal named, derived from the receipt's own logical id."""

    note: str
    """What remains in the instance, in the record's own words."""

    status: str | None = None
    deleted: int = 0
    """How many objects DHIS2 counted as deleted when it took the retraction."""

    @classmethod
    def from_record(cls, record: WithdrawalRecord) -> SpoolWithdrawal:
        """Reduce one stored withdrawal record to what a withdrawn row shows."""
        return cls(
            withdrawn_at=record.withdrawn_at,
            event_uid=record.event_uid,
            note=record.note,
            status=record.status,
            deleted=record.deleted,
        )


class SpoolResponseSummary(BaseModel):
    """One receipt as a listing row: when it arrived, what it answers, where it is, and what DHIS2 said."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    received_at: str
    lifecycle: ResponseLifecycle
    form_kind: str
    questionnaire: str
    """The canonical of the Questionnaire the submission answered."""

    questionnaire_id: str | None = None
    """The last segment of that canonical - the id the form is served under, for joining to a title."""

    submitted_by: str | None = None
    """The DHIS2 username the facade validated this submission under, or None when it validated none."""

    status: str | None = None
    authored: str | None = None
    answer_count: int = 0
    warnings: tuple[str, ...] = ()
    period: str | None = None
    """The ISO period an aggregate submission reports for."""

    period_type: str | None = None
    organisation_unit: str | None = None
    """The DHIS2 organisation-unit uid the capture happened at."""

    tracked_entity: str | None = None
    tracker_enrollment: str | None = None
    rejection: SpoolRejection | None = None
    """Why DHIS2 refused this receipt, on a rejected row that has a readable report beside it."""

    imported: SpoolImport | None = None
    """What DHIS2 counted for this receipt, on a forwarded row that has a readable report beside it."""

    refusal: SpoolRefusal | None = None
    """The last committing drain's refusal, on a received row that has a record beside it."""

    withdrawal: SpoolWithdrawal | None = None
    """What DHIS2 answered the retraction, on a withdrawn row that has a readable record beside it."""


class SpoolCounts(BaseModel):
    """How many receipts sit in each lifecycle state - the queue depth, and what became of the rest."""

    model_config = ConfigDict(frozen=True)

    received: int = 0
    forwarded: int = 0
    rejected: int = 0
    withdrawn: int = 0
    """Receipts DHIS2 took and `d2w fhir withdraw` retracted afterwards. Terminal: nothing leaves this state."""

    malformed: int = 0
    """Files in the holding pen. Not receipts and not a lifecycle state - bytes that would not parse as one."""


class SpoolListing(BaseModel):
    """One page of this project's receipts, newest first, with the whole listing's counts beside them.

    `total` is the whole searchset rather than the page, and it is the same number on every page of
    one walk. `next` and `previous` are the links a client follows; the page token is this server's
    business and is not a number a client composes.
    """

    model_config = ConfigDict(frozen=True)

    total: int
    counts: SpoolCounts
    responses: tuple[SpoolResponseSummary, ...]
    malformed: tuple[QuarantinedFile, ...] = ()
    """Every file the spool moved aside because it does not read as a receipt, with what stopped it."""

    self_url: str = ""
    """This page, as a client may ask for it again and be handed the same page."""

    previous_url: str | None = None
    next_url: str | None = None


@router.get(
    SPOOL_PATH,
    tags=[SPOOL_TAG],
    summary="List the stored receipts",
    description=(
        "One page of this project's receipts, newest first, each with the lifecycle state its file "
        "is currently in and whatever DHIS2 said about it. The spool directory is re-read on every "
        "call, so a `d2w fhir forward` run in another process shows up on the next request with "
        "nothing restarted.\n\n"
        "`total` is the whole listing on every page of one walk, and the per-state counts are the "
        "whole spool rather than the page - a queue depth that changed with the page you were "
        "looking at would be no queue depth at all. Walk the pages by following `next_url`; the page "
        "token is this server's to mint and not a number to compose."
    ),
    response_description="One page of receipts, the whole spool's counts, and the links either side of the page.",
)
async def read_spool(
    request: Request,
    count_parameter: Annotated[
        str | None,
        Query(
            alias=COUNT_PARAMETER,
            description="How many receipts this page carries. Out-of-range values are clamped.",
        ),
    ] = None,
    page_parameter: Annotated[
        str | None,
        Query(alias=PAGE_PARAMETER, description="An opaque cursor, taken from a previous page's `next_url`."),
    ] = None,
) -> SpoolListing:
    """Answer one page of the receipts, re-reading the spool directory as it does.

    The read runs off the event loop. Every fact in a listing comes from `stat`ing and parsing files,
    which is blocking work, and a facade doing it inline would stall every other request it is
    serving - including the capture that is trying to write into the same directory.

    Both parameters are read as text rather than as numbers on purpose: an unreadable `_count` is a
    client asking for a page size this server does not offer, and it is answered with the default
    page rather than with a 422 about a listing that has one.
    """
    context = serve_context(request)
    naming = capture_state(request).naming
    count = requested_page_size(count_parameter)
    cursor = requested_cursor(page_parameter)
    reading = await run_in_threadpool(context.spool.search)
    counts = SpoolCounts(
        received=sum(1 for receipt in reading.receipts if receipt.lifecycle is ResponseLifecycle.RECEIVED),
        forwarded=sum(1 for receipt in reading.receipts if receipt.lifecycle is ResponseLifecycle.FORWARDED),
        rejected=sum(1 for receipt in reading.receipts if receipt.lifecycle is ResponseLifecycle.REJECTED),
        withdrawn=sum(1 for receipt in reading.receipts if receipt.lifecycle is ResponseLifecycle.WITHDRAWN),
        malformed=len(reading.quarantined),
    )
    page = page_of(reading.receipts, cursor, count)
    responses = await run_in_threadpool(_summaries, context.spool, page.receipts, naming)
    return SpoolListing(
        total=page.total,
        counts=counts,
        responses=responses,
        malformed=reading.quarantined,
        self_url=_page_url(request, page.cursor, count),
        previous_url=None if page.previous_cursor is None else _page_url(request, page.previous_cursor, count),
        next_url=None if page.next_cursor is None else _page_url(request, page.next_cursor, count),
    )


def _page_url(request: Request, cursor: SpoolCursor, count: int) -> str:
    """One page of the listing as a client may ask for it again and be given the same page."""
    return str(request.url.include_query_params(**{COUNT_PARAMETER: count, PAGE_PARAMETER: cursor.token()}))


def _summaries(
    spool: ResponseSpool, receipts: tuple[StoredReceipt, ...], naming: CaptureNaming
) -> tuple[SpoolResponseSummary, ...]:
    """Project one page of receipts into listing rows, reading the sidecar beside each receipt that has one.

    Only the page pays for this. Deriving a row parses the stored resource and reads a sidecar off
    disk, which is the expensive half of the listing, so a spool of ten thousand receipts costs a
    page of it rather than all of it.

    Which sidecar is read follows from the state, because the three sidecars answer three questions:
    a drained receipt has an import report, a queued one may have a drain's refusal, and a withdrawn
    one has the record of the delete. Reading a state's own file is also what keeps a withdrawal
    record from being parsed as the import report it is not.
    """
    rows: list[SpoolResponseSummary] = []
    for receipt in receipts:
        drained = receipt.lifecycle in (ResponseLifecycle.FORWARDED, ResponseLifecycle.REJECTED)
        withdrawn = receipt.lifecycle is ResponseLifecycle.WITHDRAWN
        rows.append(
            _summary(
                receipt,
                naming,
                spool.import_report(receipt.response_id, receipt.lifecycle) if drained else None,
                spool.refusal_record(receipt.response_id) if receipt.lifecycle is ResponseLifecycle.RECEIVED else None,
                spool.withdrawal_record(receipt.response_id) if withdrawn else None,
            )
        )
    return tuple(rows)


def _summary(
    receipt: StoredReceipt,
    naming: CaptureNaming,
    report: ForwardImportOutcome | None,
    refusal: ForwardRefusalRecord | None = None,
    withdrawal: WithdrawalRecord | None = None,
) -> SpoolResponseSummary:
    """Build one listing row, deriving the capture context out of the stored resource where it reads.

    The stored report reads as a rejection or as an import by which state the receipt is in, rather
    than by what the document says: a report is written beside a receipt at the moment it is moved,
    so the directory it is in is the forwarder's own statement of which answer it was.
    """
    rejected = receipt.lifecycle is ResponseLifecycle.REJECTED
    forwarded = receipt.lifecycle is ResponseLifecycle.FORWARDED
    row = SpoolResponseSummary(
        response_id=receipt.response_id,
        received_at=receipt.received_at,
        lifecycle=receipt.lifecycle,
        form_kind=receipt.form_kind,
        questionnaire=receipt.questionnaire,
        submitted_by=receipt.submitted_by,
        questionnaire_id=_last_segment(receipt.questionnaire),
        warnings=receipt.warnings,
        rejection=SpoolRejection.from_outcome(report) if report is not None and rejected else None,
        imported=SpoolImport.from_outcome(report) if report is not None and forwarded else None,
        refusal=SpoolRefusal.from_record(refusal) if refusal is not None else None,
        withdrawal=SpoolWithdrawal.from_record(withdrawal) if withdrawal is not None else None,
    )
    response = _parsed(receipt)
    if response is None:
        # A receipt the r4 models cannot read is still a receipt: the row states what the envelope
        # recorded and leaves the derived context empty, rather than failing the whole listing.
        return row
    period, period_type = _period(response, naming)
    return row.model_copy(
        update={
            "status": response.status,
            "authored": response.authored,
            "answer_count": _answer_count(response),
            "period": period,
            "period_type": period_type,
            "organisation_unit": _organisation_unit(response, naming),
            "tracked_entity": _identifier_value(response, naming.tracked_entity_system),
            "tracker_enrollment": _enrollment(response, naming),
        }
    )


def _parsed(receipt: StoredReceipt) -> QuestionnaireResponse | None:
    """The stored resource as a model, or None when it is not one these models read."""
    try:
        return QuestionnaireResponse.model_validate(receipt.response)
    except ValidationError:
        return None


def _answer_count(response: QuestionnaireResponse) -> int:
    """How many answers the submission carries, counting through groups.

    Answers rather than items: a group holds no value, and a repeating question holds several, so
    the number a person wants beside a receipt is how many values DHIS2 would receive from it.
    """
    return _count_answers(response.item)


def _count_answers(items: list[QuestionnaireResponseItem] | None) -> int:
    """Every answer in one item tree, counting through groups and through nested answer items."""
    total = 0
    for item in items or []:
        for answer in item.answer or []:
            total += 1
            total += _count_answers(answer.item)
        total += _count_answers(item.item)
    return total


def _period(response: QuestionnaireResponse, naming: CaptureNaming) -> tuple[str | None, str | None]:
    """The ISO period and period type an aggregate submission reports for, from the D2Period extension."""
    period = _extension(response.extension, naming.period_url)
    if period is None:
        return None, None
    iso = _extension(period.extension, PERIOD_ISO_SUB_EXTENSION)
    period_type = _extension(period.extension, PERIOD_TYPE_SUB_EXTENSION)
    return (iso.valueString if iso else None), (period_type.valueCode if period_type else None)


def _organisation_unit(response: QuestionnaireResponse, naming: CaptureNaming) -> str | None:
    """Where the capture happened: a tracker event's own extension, or the Location subject of the rest."""
    extension = _extension(response.extension, naming.organisation_unit_url)
    reference = extension.valueReference.reference if extension and extension.valueReference else None
    if reference is None and response.subject is not None:
        reference = response.subject.reference
    if reference is None or not reference.startswith(LOCATION_REFERENCE_PREFIX):
        return None
    return reference.removeprefix(LOCATION_REFERENCE_PREFIX) or None


def _enrollment(response: QuestionnaireResponse, naming: CaptureNaming) -> str | None:
    """The enrollment uid a tracker event was captured against."""
    extension = _extension(response.extension, naming.tracker_enrollment_url)
    if extension is None or extension.valueIdentifier is None:
        return None
    return extension.valueIdentifier.value


def _identifier_value(response: QuestionnaireResponse, system: str) -> str | None:
    """The subject's business identifier under one system - how a tracker response names its entity."""
    identifier = response.subject.identifier if response.subject else None
    if identifier is None or identifier.system != system:
        return None
    return identifier.value


def _extension(extensions: list[Extension] | None, url: str) -> Extension | None:
    """The first extension under one url, or None."""
    return next((extension for extension in extensions or [] if extension.url == url), None)


def _last_segment(url: str) -> str | None:
    """The id a canonical url ends in, for joining a receipt to the form it answered."""
    segment = url.rsplit("/", 1)[-1]
    return segment or None
