"""`GET /spool` - the receipt tree with its lifecycle, for the capture UI's Responses page.

WHY THIS IS NOT FHIR, STATED ONCE SO NOBODY HAS TO RE-DERIVE IT.

Almost everything this facade answers has a FHIR spelling, and where one exists it is used - the
receipts themselves are `GET /QuestionnaireResponse`, and that search covers all three lifecycle
states, so a client that only speaks FHIR still sees every receipt. What that search cannot carry
is the receipt *envelope*: when the facade accepted the submission, which DHIS2 form kind it was
validated as, what the server had to warn about, which of the spool's three directories the file
now sits in, and - for a rejection - the DHIS2 import report `d2w fhir forward` left beside it.

None of those are elements of a QuestionnaireResponse. Two of them could be forced into `meta`
(`lastUpdated` for the receipt instant, a `tag` for the lifecycle), and a DHIS2 `ImportSummary`
could be bent into an `OperationOutcome`, but that would spread one record across a FHIR resource,
a tag system this IG does not publish, and a second operation - and the DHIS2 import counts would
still have nowhere honest to go. A facade-owned record with no FHIR analogue is better served as
what it is. So this is a plain typed JSON endpoint, `application/json`, and its shape is Pydantic
models rather than a Bundle.

The path is a single lowercase segment, exactly like `/metadata`. FHIR resource types are
PascalCase, so `/spool` can never shadow one, and the router mounts with the other fixed paths -
ahead of `/{resource_type}`, which would otherwise claim it and answer "this server does not serve
the resource type `spool`".

Every read re-reads the directory. `d2w fhir forward` moves files while this server runs, so a
listing built from anything else is stale by design; see `dhis2w_fhir_serve.spool`.
"""

from __future__ import annotations

from dhis2w_fhir.r4 import Extension, QuestionnaireResponse, QuestionnaireResponseItem
from dhis2w_fhir.service import ForwardImportOutcome
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.requests import Request

from dhis2w_fhir_serve.capture.naming import PERIOD_ISO_SUB_EXTENSION, PERIOD_TYPE_SUB_EXTENSION, CaptureNaming
from dhis2w_fhir_serve.routes.capture import capture_state
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.spool import ResponseLifecycle, StoredReceipt

#: Where the listing is served from. One lowercase segment, so no FHIR resource type can collide.
SPOOL_PATH = "/spool"

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


class SpoolCounts(BaseModel):
    """How many receipts sit in each lifecycle state - the queue depth, and what became of the rest."""

    model_config = ConfigDict(frozen=True)

    received: int = 0
    forwarded: int = 0
    rejected: int = 0


class SpoolListing(BaseModel):
    """Every receipt this project holds, newest first, with the per-state counts beside them."""

    model_config = ConfigDict(frozen=True)

    total: int
    counts: SpoolCounts
    responses: tuple[SpoolResponseSummary, ...]


@router.get(SPOOL_PATH)
async def read_spool(request: Request) -> SpoolListing:
    """List every stored receipt with its lifecycle state, re-reading the spool directory as it answers."""
    context = serve_context(request)
    naming = capture_state(request).naming
    receipts = context.spool.search()
    counts = SpoolCounts(
        received=sum(1 for receipt in receipts if receipt.lifecycle is ResponseLifecycle.RECEIVED),
        forwarded=sum(1 for receipt in receipts if receipt.lifecycle is ResponseLifecycle.FORWARDED),
        rejected=sum(1 for receipt in receipts if receipt.lifecycle is ResponseLifecycle.REJECTED),
    )
    responses = tuple(
        _summary(
            receipt,
            naming,
            context.spool.rejection(receipt.response_id) if receipt.lifecycle is ResponseLifecycle.REJECTED else None,
        )
        for receipt in receipts
    )
    return SpoolListing(total=len(responses), counts=counts, responses=responses)


def _summary(
    receipt: StoredReceipt, naming: CaptureNaming, rejection: ForwardImportOutcome | None
) -> SpoolResponseSummary:
    """Build one listing row, deriving the capture context out of the stored resource where it reads."""
    row = SpoolResponseSummary(
        response_id=receipt.response_id,
        received_at=receipt.received_at,
        lifecycle=receipt.lifecycle,
        form_kind=receipt.form_kind,
        questionnaire=receipt.questionnaire,
        questionnaire_id=_last_segment(receipt.questionnaire),
        warnings=receipt.warnings,
        rejection=SpoolRejection.from_outcome(rejection) if rejection is not None else None,
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
