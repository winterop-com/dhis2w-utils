"""Rung four of the facade ladder: everything the durable rung has, plus the four things it lacked.

`examples/fhir/client/complex_facade.py` receives, spools, and drains - but it takes aggregate
reports only, translates under whatever dial the context was built with, says nothing about a value
an earlier receipt already sent, and states its own surface nowhere. This rung closes all four:

- **Tracker routing.** A translated payload goes to the endpoint its shape names: an aggregate
  envelope to `/api/dataValueSets`, a person, an enrollment, or an event to `/api/tracker` under the
  key that payload rides. The demo captures an event of a program without registration.
- **The coded-answer dial.** `strict` or `lenient` is application configuration here, resolved at
  startup and stamped onto the translation context - the same dial `[serve] strict_codes` sets for a
  served facade and `d2w fhir forward` inherits.
- **Overwrite naming.** Before a drain posts an aggregate payload it reads what this spool has
  already landed, and names every value a forwarded receipt sent before. DHIS2 cannot answer that
  question - it counts a replacement exactly like a first write - so the spool answers it.
- **A `/metadata` that is honest about being small.** It lists the forms this facade accepts and the
  two routes it answers on. It is **not** a FHIR CapabilityStatement, and it does not pretend to be.

**The moral of the ladder.** Read the four additions above and notice what they have in common:
every one is a piece of `d2w fhir serve` and `d2w fhir forward`, rebuilt smaller. At this rung the
question is no longer "what else do I need to write" but "why am I writing it": the served facade
brings the capability statement, the published guide, the register, the capture screens, the requeue
path, and a drain that is a separate process from the server - and it is one command. **At this
rung, run `d2w fhir serve`.**

The guide is [Build your own facade](../../../docs/fhir/401-build-your-own-facade.md); what a valid
response is, is [the capture contract](../../../docs/fhir/401-capture-contract.md).

Usage:
    uv run python examples/fhir/client/advanced_facade.py

Requires a DHIS2 profile (`d2w profile list`). The demo imports two data values and one event for
real and deletes them again at the end, so the instance is left exactly as it was found.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from _fixture import aggregate_form_id, conversion_context, event_form_id, form_canonical
from _runner import run_example
from dhis2w_client import Dhis2ApiError, Dhis2Client, Dhis2ClientError, Profile
from dhis2w_client.generated.v42.oas import ImportSummary, TrackerImportReport
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import resolve
from dhis2w_fhir import (
    CodedAnswerMode,
    ConversionContext,
    ConversionResult,
    ForwardedCellIndex,
    ForwardedSubmission,
    ForwardImportIssue,
    ForwardImportOutcome,
    ForwardImportRecord,
    SpoolLayout,
    aggregate_cells,
    build_forwarded_cell_index,
    translate_response,
)
from dhis2w_fhir import spool as spool_queue
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)
from dhis2w_fhir.spool import ForwardRefusalRecord, RefusalReason
from dhis2w_fhir_serve import spool as spool_writer
from dhis2w_fhir_serve.spool import ResponseLifecycle
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

#: What the demo reports: a facility both the data set and the program are assigned to, a period
#: nothing else reports on, and two cells. The far-future period keeps the demo's own values the
#: only ones there, so deleting them at the end takes nothing else with them.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"
REPORTED_PERIOD_ISO = "209902"
REPORTED_NUMBERS = {"s46m5MS0hxu.Prlt0C1RF0s": 12, "s46m5MS0hxu.psbwp3CQEhs": 8}

#: The same two cells, reported again with different numbers. This is what the drain names as values
#: an earlier receipt already sent - the resubmission an operator wants to see before it lands.
CORRECTED_NUMBERS = {"s46m5MS0hxu.Prlt0C1RF0s": 15, "s46m5MS0hxu.psbwp3CQEhs": 7}

#: The supervision visit the demo captures on the tracker route: when it happened, and one answer.
EVENT_OCCURRED_AT = "2026-01-19T10:30:00"
EVENT_ANSWERS = {"s46m5MS0hxu": 21}

#: How long the drain waits between passes, and how the demo polls a receipt it is holding an id for.
DRAIN_INTERVAL_SECONDS = 0.5
POLL_INTERVAL_SECONDS = 0.25
POLL_ATTEMPTS = 240

#: From here up the instance is failing rather than answering, so the receipt waits for the next pass.
SERVER_ERROR_STATUS = 500

logger = logging.getLogger("facade")


class FacadeSettings(BaseModel):
    """Everything the facade resolves once at startup: the instance, the receipts, and the dial."""

    model_config = ConfigDict(frozen=True)

    profile_name: str
    profile: Profile
    project_root: Path
    """The directory the spool tree sits under. A deployment names the project the receipts belong to."""

    coded_answers: CodedAnswerMode = CodedAnswerMode.LENIENT
    """How exactly a coded answer has to name its concept - the dial `[serve] strict_codes` sets."""

    @classmethod
    def resolved(cls, *, project_root: Path, coded_answers: CodedAnswerMode) -> FacadeSettings:
        """Read the DHIS2 profile this process runs against: `DHIS2_PROFILE`, or the configured default."""
        resolved = resolve()
        return cls(
            profile_name=resolved.name,
            profile=resolved.profile,
            project_root=project_root,
            coded_answers=coded_answers,
        )

    @property
    def layout(self) -> SpoolLayout:
        """Where the receipts sit: `[serve] spool_dir` against the project root, `.serve/responses` by default."""
        return SpoolLayout.resolve(self.project_root)


class FacadeRuntime(BaseModel):
    """What the process holds for its whole life: the context, one client, and the spool it writes to."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    context: ConversionContext
    spool: spool_writer.ResponseSpool
    client: Dhis2Client | None = None
    """None only outside the lifespan - before startup finished, and after shutdown began."""


class CaptureReceipt(BaseModel):
    """What a capture is answered with: the id it is readable under, and the state it starts in."""

    model_config = ConfigDict(frozen=True)

    receipt: str
    state: ResponseLifecycle
    received_at: str


class ReceiptReport(BaseModel):
    """Where one capture stands: its state, and whatever the drain wrote down beside it."""

    model_config = ConfigDict(frozen=True)

    receipt: str
    state: ResponseLifecycle
    questionnaire: str
    received_at: str
    imported: ForwardImportOutcome | None = None
    refusal: ForwardRefusalRecord | None = None


class ServedForm(BaseModel):
    """One form this facade accepts, as its own small `/metadata` states it."""

    model_config = ConfigDict(frozen=True)

    questionnaire: str
    form_kind: str
    dhis2_object: str | None = None
    """The data set, program, program stage, or tracked entity type the form captures into."""

    questions: int


class FacadeMetadata(BaseModel):
    """What this facade accepts and where - honest, small, and not a FHIR CapabilityStatement.

    A CapabilityStatement is a claim about a FHIR server: which resources it serves, which searches
    answer, which interactions exist. This facade serves no FHIR resource and answers no search, so
    publishing one would be a claim it cannot keep. What a client of *this* surface needs is the two
    routes and the list of forms, and that is exactly what this says. `d2w fhir serve` answers the
    real `/metadata`, because it really is a FHIR server.
    """

    model_config = ConfigDict(frozen=True)

    capture_route: str = "POST /QuestionnaireResponse"
    receipt_route: str = "GET /receipts/{id}"
    coded_answers: CodedAnswerMode
    forms: tuple[ServedForm, ...] = ()


def build_facade(settings: FacadeSettings, context: ConversionContext) -> FastAPI:
    """Three routes - capture, receipt, metadata - plus the drain that empties the queue into DHIS2."""
    # The dial is stamped onto the context here, so every translation this process runs - at the
    # door and in the drain alike - reads coded answers the way the settings say.
    dialled = context.model_copy(update={"coded_answer_mode": settings.coded_answers})
    runtime = FacadeRuntime(context=dialled, spool=spool_writer.ResponseSpool.at(settings.project_root))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Open the client, start the drain, and stop the drain before the client closes under it."""
        logger.info("starting against %s (profile %s)", settings.profile.base_url, settings.profile_name)
        async with open_client(settings.profile) as client:
            runtime.client = client
            drain = asyncio.create_task(drain_forever(runtime, settings))
            logger.info("ready, %s coded answers, receipts under %s", settings.coded_answers, settings.layout.root)
            try:
                yield
            finally:
                drain.cancel()
                with suppress(asyncio.CancelledError):
                    await drain
                runtime.client = None
        logger.info("stopped")

    app = FastAPI(title="DHIS2 FHIR capture", lifespan=lifespan)

    @app.post("/QuestionnaireResponse")
    async def capture(response: QuestionnaireResponse) -> JSONResponse:
        """Translate one capture, write the receipt down, and answer with its id before DHIS2 is asked."""
        # Translating at the door is validation, not the send: a response the translator will not
        # read is refused now, while there is a client on the other end of the request to tell.
        result = translate_response(response, runtime.context)
        if result.is_refused:
            refusals = [refusal.model_dump(mode="json", exclude_none=True) for refusal in result.refusals]
            return JSONResponse(status_code=422, content={"refusals": refusals})
        form = runtime.context.form_for(response.questionnaire)
        receipt_id = spool_writer.new_response_id()
        envelope = spool_writer.StoredResponseEnvelope(
            response_id=receipt_id,
            received_at=spool_writer.current_instant(),
            form_kind=form.form_kind if form is not None else "",
            questionnaire=response.questionnaire or "",
            # The receipt is the submission as it arrived, stamped with the id it now answers under.
            response=response.model_copy(update={"id": receipt_id}).model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
        )
        runtime.spool.save(envelope)
        logger.info("received %s, answering the %s form", receipt_id, envelope.form_kind)
        accepted = CaptureReceipt(
            receipt=receipt_id, state=ResponseLifecycle.RECEIVED, received_at=envelope.received_at
        )
        return JSONResponse(
            status_code=201,
            content=accepted.model_dump(mode="json"),
            headers={"Location": f"/receipts/{receipt_id}"},
        )

    @app.get("/receipts/{receipt_id}")
    async def receipt(receipt_id: str) -> JSONResponse:
        """Where one capture stands, by the id it was handed - readable in every state, forever."""
        stored = runtime.spool.get(receipt_id)
        if stored is None:
            return JSONResponse(status_code=404, content={"detail": f"no receipt `{receipt_id}` in this spool"})
        report = ReceiptReport(
            receipt=stored.response_id,
            state=stored.lifecycle,
            questionnaire=stored.questionnaire,
            received_at=stored.received_at,
            imported=runtime.spool.import_report(receipt_id, stored.lifecycle),
            refusal=runtime.spool.refusal_record(receipt_id),
        )
        return JSONResponse(content=report.model_dump(mode="json", exclude_none=True))

    @app.get("/metadata")
    async def metadata() -> JSONResponse:
        """Which forms this facade accepts and where to send them - the whole of its published surface."""
        forms = tuple(
            ServedForm(
                questionnaire=canonical,
                form_kind=form.form_kind,
                dhis2_object=form.data_set_uid
                or form.program_stage_uid
                or form.program_uid
                or form.tracked_entity_type_uid,
                questions=len(form.questions),
            )
            for canonical, form in sorted(runtime.context.forms.items())
        )
        published = FacadeMetadata(coded_answers=settings.coded_answers, forms=forms)
        return JSONResponse(content=published.model_dump(mode="json", exclude_none=True))

    return app


async def drain_forever(runtime: FacadeRuntime, settings: FacadeSettings) -> None:
    """Drain the queue for as long as the process lives, and keep the queue when the instance is down."""
    while True:
        try:
            await drain_once(runtime, settings)
        except (Dhis2ClientError, httpx.HTTPError) as error:
            # Nothing is lost and nothing is filed: every receipt this pass did not reach is still
            # in `received/`, which is exactly what the next pass reads.
            logger.warning("DHIS2 did not answer (%s); the queue keeps its receipts and the next pass retries", error)
        await asyncio.sleep(DRAIN_INTERVAL_SECONDS)


async def drain_once(runtime: FacadeRuntime, settings: FacadeSettings) -> None:
    """One pass over the queue: post each waiting receipt, and file it under what DHIS2 answered."""
    client = runtime.client
    if client is None:
        return
    # The same lock `d2w fhir forward` takes: two drains over one spool would post every receipt
    # twice and race each other's renames, and this facade's own drain is one of the two.
    with spool_queue.drain_lock(settings.layout):
        queued = spool_queue.read_received_responses(settings.layout).responses
        if not queued:
            return
        # What this spool has already landed in DHIS2, read once per pass off the sidecars in
        # `forwarded/`. A pass carrying no aggregate payload never reads it.
        index = build_forwarded_cell_index(settings.layout)
        for spooled in queued:
            result = translate_response(spooled.response, runtime.context)
            if result.is_refused:
                # A guide can move between the capture and the drain, so a receipt that translated
                # at the door can stop translating. The receipt stays queued - the fix is in the
                # guide or in the data - and the refusal is written beside it as the queue's history.
                spool_queue.record_refusal(spooled, _refusal_record(result))
                logger.warning("still queued, %s: %s", spooled.response_id, result.refusals[0].reason)
                continue
            _name_overwrites(index, result, spooled.response_id)
            record = await post_payload(client, result, received_at=spooled.received_at)
            if record.is_rejected:
                spool_queue.move_to_rejected(spooled, record)
                logger.warning("rejected %s: %s", spooled.response_id, record.issues[0].line if record.issues else "")
                continue
            spool_queue.move_to_forwarded(spooled, record)
            index.record(
                record.cells, ForwardedSubmission(response_id=spooled.response_id, received_at=spooled.received_at)
            )
            logger.info("forwarded %s: %s", spooled.response_id, record.counts_line)


def _name_overwrites(index: ForwardedCellIndex, result: ConversionResult, response_id: str) -> None:
    """Say which values this payload sends that a forwarded receipt already sent, before it is sent.

    DHIS2 replaces such a value in place and counts the write exactly as it counts a first entry, so
    no import summary can separate the two. The spool's own record can, and this is where it says
    so: nothing is refused over it - the run reports, and the operator decides.
    """
    if result.data_value_set is None:
        return
    for overwritten in index.already_sent(aggregate_cells(result.data_value_set)):
        logger.warning("%s replaces a value already sent: %s", response_id, overwritten.line)


async def post_payload(client: Dhis2Client, result: ConversionResult, *, received_at: str) -> ForwardImportRecord:
    """Post one translated payload to the endpoint its own shape names, and project DHIS2's answer.

    An aggregate envelope is an `/api/dataValueSets` body whole; a person, an enrollment, and an
    event each ride one key of an `/api/tracker` one. `target_kind` alone cannot decide it - a
    registration produces a tracked entity for a person DHIS2 does not hold yet and an enrollment
    alone for one it does - so the branch is on which field the translation actually filled.
    """
    payload = result.payload
    assert payload is not None  # a translated result carries a payload; only a refused one does not
    wire = payload.model_dump(by_alias=True, exclude_none=True, mode="json")
    if result.data_value_set is not None:
        answer = await _post(client, "/api/dataValueSets", wire, {})
        return _aggregate_record(answer, result, received_at)
    params = {"importStrategy": "CREATE", "async": "false"}
    if result.tracked_entity is not None:
        body: dict[str, Any] = {"trackedEntities": [wire]}
    elif result.enrollment is not None:
        body = {"enrollments": [wire]}
    else:
        body = {"events": [wire]}
    return _tracker_record(await _post(client, "/api/tracker", body, params), result, received_at)


async def _post(client: Dhis2Client, path: str, body: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    """POST one payload and answer with DHIS2's own report, whether it took the payload or refused it."""
    try:
        return await client.post_raw(path, body, params=params)
    except Dhis2ApiError as error:
        # A refused import carries the endpoint's own report, and that is a verdict to file. A 5xx
        # is the instance failing rather than answering, so it raises and the receipt stays queued.
        if error.status_code >= SERVER_ERROR_STATUS or not isinstance(error.body, dict):
            raise
        return error.body


def _aggregate_record(answer: dict[str, Any], result: ConversionResult, received_at: str) -> ForwardImportRecord:
    """Project an `/api/dataValueSets` answer into the sidecar filed beside the receipt."""
    summary = ImportSummary.model_validate(answer.get("response") or answer)
    counts = summary.importCount
    envelope = result.data_value_set
    return ForwardImportRecord(
        status=summary.status.value if summary.status is not None else None,
        message=summary.description,
        created=(counts.imported or 0) if counts is not None else 0,
        updated=(counts.updated or 0) if counts is not None else 0,
        ignored=(counts.ignored or 0) if counts is not None else 0,
        issues=tuple(
            ForwardImportIssue(error_code=conflict.errorCode, subject=conflict.object, message=conflict.value)
            for conflict in summary.conflicts or ()
        ),
        target_kind=result.target_kind,
        received_at=received_at,
        # The identity of every value this payload landed on, never the numbers: it is what lets the
        # next drain say which values an earlier receipt already sent.
        cells=aggregate_cells(envelope) if envelope is not None else (),
    )


def _tracker_record(answer: dict[str, Any], result: ConversionResult, received_at: str) -> ForwardImportRecord:
    """Project an `/api/tracker` answer into the sidecar filed beside the receipt."""
    report = TrackerImportReport.model_validate(answer.get("response") or answer)
    stats = report.stats
    validation = report.validationReport
    return ForwardImportRecord(
        status=report.status.value if report.status is not None else None,
        message=report.message,
        created=(stats.created or 0) if stats is not None else 0,
        updated=(stats.updated or 0) if stats is not None else 0,
        ignored=(stats.ignored or 0) if stats is not None else 0,
        issues=tuple(
            ForwardImportIssue(error_code=error.errorCode, subject=error.uid, message=error.message)
            for error in (validation.errorReports if validation is not None else None) or ()
        ),
        target_kind=result.target_kind,
        received_at=received_at,
    )


def _refusal_record(result: ConversionResult) -> ForwardRefusalRecord:
    """The marker a drain leaves beside a queued receipt it would not translate."""
    return ForwardRefusalRecord(
        refused_at=spool_writer.current_instant(),
        reasons=tuple(
            RefusalReason(category=refusal.category, element=refusal.element, reason=refusal.reason)
            for refusal in result.refusals
        ),
    )


def aggregate_capture(context: ConversionContext, canonical: str, numbers: dict[str, int]) -> QuestionnaireResponse:
    """One small aggregate report: the form it answers, the period, the place, and two numbers."""
    period = [Extension(url="iso", valueString=REPORTED_PERIOD_ISO), Extension(url="type", valueCode="Monthly")]
    return QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        extension=[
            Extension(url=context.naming.form_type_url, valueCode="aggregate"),
            Extension(url=context.naming.period_url, extension=period),
        ],
        subject=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
        item=[
            QuestionnaireResponseItem(linkId=link_id, answer=[QuestionnaireResponseAnswer(valueInteger=value)])
            for link_id, value in numbers.items()
        ],
    )


def event_capture(context: ConversionContext, canonical: str) -> QuestionnaireResponse:
    """One supervision visit: a program without registration, so a date and a place and no person."""
    return QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        # `authored` is the event's occurrence, not a document timestamp - see build_event_response.py.
        authored=EVENT_OCCURRED_AT,
        extension=[Extension(url=context.naming.form_type_url, valueCode="event")],
        subject=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
        item=[
            QuestionnaireResponseItem(linkId=link_id, answer=[QuestionnaireResponseAnswer(valueInteger=value)])
            for link_id, value in EVENT_ANSWERS.items()
        ],
    )


async def post_capture(caller: httpx.AsyncClient, response: QuestionnaireResponse, label: str) -> ReceiptReport:
    """Post one capture, then poll its receipt until a drain has filed it - what a client with an id does."""
    answer = await caller.post(
        "/QuestionnaireResponse", json=response.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    accepted = CaptureReceipt.model_validate(answer.json())
    print(f"POST /QuestionnaireResponse, {label} -> {answer.status_code} {accepted.receipt} ({accepted.state})")
    for _ in range(POLL_ATTEMPTS):
        report = ReceiptReport.model_validate((await caller.get(f"/receipts/{accepted.receipt}")).json())
        if report.state is not ResponseLifecycle.RECEIVED:
            imported = report.imported
            counts = imported.counts_line if imported is not None else "no report"
            print(f"  drained to {report.state}: {counts}")
            return report
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"receipt {accepted.receipt} was still queued after {POLL_ATTEMPTS} polls")


async def remove_from_dhis2(
    settings: FacadeSettings, context: ConversionContext, *, event_receipt_id: str | None
) -> None:
    """Delete what this run imported, so the demo leaves the instance exactly as it found it.

    One delete covers both aggregate receipts: they report the same two cells, and a delete names
    the cells rather than the numbers. The event is deleted by its DHIS2 UID, which is derived from
    the receipt id the facade stamped on the capture - see
    `examples/fhir/client/derive_receipt_event_uid.py` - so the capture is translated again under
    that id to learn the UID back.
    """
    aggregate = translate_response(
        aggregate_capture(context, form_canonical(aggregate_form_id()), REPORTED_NUMBERS), context
    )
    async with open_client(settings.profile) as client:
        if aggregate.data_value_set is not None:
            body = aggregate.data_value_set.model_dump(by_alias=True, exclude_none=True, mode="json")
            await client.post_raw("/api/dataValueSets", body, params={"importStrategy": "DELETE"})
        if event_receipt_id is None:
            return
        stamped = event_capture(context, form_canonical(event_form_id())).model_copy(update={"id": event_receipt_id})
        event = translate_response(stamped, context)
        if event.event is not None:
            await client.post_raw(
                "/api/tracker",
                {"events": [{"event": event.event.event}]},
                params={"importStrategy": "DELETE", "async": "false"},
            )


async def main() -> None:
    """Capture an aggregate report, a correction of it, and an event - and read the surface back."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    context = conversion_context()
    # A scratch spool, because this demo's receipts are the demo's. A deployment points the facade
    # at the directory its receipts belong to: `d2w fhir serve` writes `.serve/responses` inside the
    # project, and `[serve] spool_dir` moves the tree to a volume the operator backs up.
    project_root = Path(tempfile.mkdtemp(prefix="d2w-facade-spool-"))
    settings = FacadeSettings.resolved(project_root=project_root, coded_answers=CodedAnswerMode.STRICT)
    app = build_facade(settings, context)
    aggregate_canonical = form_canonical(aggregate_form_id())
    event_receipt_id: str | None = None
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://facade") as caller,
        ):
            published = FacadeMetadata.model_validate((await caller.get("/metadata")).json())
            print(f"GET /metadata: {published.capture_route}, {published.coded_answers} coded answers")
            for served in published.forms:
                print(f"  {served.form_kind:14} {served.dhis2_object or '-':12} {served.questions:3} question(s)")
            print()

            await post_capture(
                caller, aggregate_capture(context, aggregate_canonical, REPORTED_NUMBERS), "an aggregate report"
            )
            # The same two cells again. The drain reads `forwarded/` before it posts, so it names
            # both values as ones the first receipt already sent - and posts them anyway.
            await post_capture(
                caller, aggregate_capture(context, aggregate_canonical, CORRECTED_NUMBERS), "a correction of it"
            )
            event = await post_capture(caller, event_capture(context, form_canonical(event_form_id())), "an event")
            event_receipt_id = event.receipt
    finally:
        await remove_from_dhis2(settings, context, event_receipt_id=event_receipt_id)
        shutil.rmtree(project_root, ignore_errors=True)
        print("cleaned up: the imported values and the event are deleted, and the scratch spool is gone")


if __name__ == "__main__":
    run_example(main)
