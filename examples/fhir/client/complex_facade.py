"""Level three of the facade ladder: the capture survives the instance being unreachable.

The two levels below answer a capture with what DHIS2 said about it, which means the sender is the
only place the submission exists until DHIS2 has taken it. This level inverts that. A capture is
written to disk first - atomically, fsynced, under an id the client is handed - and answered `201`
**before DHIS2 is asked anything at all**. A background task drains the queue afterwards, and a
capture that arrives while the instance is down simply waits for the pass that finds it up.

The spool is not reimplemented here. It is the same tree `d2w fhir serve` writes and `d2w fhir
forward` drains, through the same published primitives:

- `dhis2w_fhir_serve.spool.ResponseSpool` is the write side: `save` lands a receipt through a
  temporary sibling, an `fsync`, a rename, and an `fsync` of the directory - which is the whole
  reason a `201` from this facade is a promise rather than a hope.
- `dhis2w_fhir.spool` is the drain side: `read_received_responses` reads the queue,
  `move_to_forwarded` / `move_to_rejected` file each receipt beside DHIS2's own report, and
  `record_refusal` leaves the queue's history beside a receipt the translator stopped reading.

**The trade:** this level posts aggregate reports and no tracker payload, holds no dial on coded
answers, names no value an earlier receipt already sent, and states its surface nowhere - a client
is told the two routes out of band. That is `examples/fhir/client/advanced_facade.py`, which is also
the level where the honest answer becomes `d2w fhir serve`.

Note what has already happened here: half the imports are the served facade's own. Writing receipts
durably is not a thing worth having a second version of, so this level uses the one that exists.

The guide is [Build your own facade](../../../docs/fhir/401-build-your-own-facade.md); what a valid
response is, is [the capture contract](../../../docs/fhir/401-capture-contract.md).

Usage:
    uv run python examples/fhir/client/complex_facade.py

Requires a DHIS2 profile (`d2w profile list`). The demo imports two values for real and deletes them
again at the end, so the instance is left exactly as it was found.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from _fixture import aggregate_form_id, conversion_context, form_canonical
from _runner import run_example
from dhis2w_client import Dhis2ApiError, Dhis2Client, Dhis2ClientError, Profile
from dhis2w_client.generated.v42.oas import ImportSummary
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import resolve
from dhis2w_fhir import (
    ConversionContext,
    ConversionResult,
    ForwardImportIssue,
    ForwardImportOutcome,
    ForwardImportRecord,
    SpoolLayout,
    aggregate_cells,
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

#: What the demo reports: a facility Child Health is assigned to, a period nothing else reports on,
#: and two cells. The far-future period is what makes the demo's own values the only ones there, so
#: deleting them at the end takes nothing else with them.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"
REPORTED_PERIOD_ISO = "209901"
REPORTED_NUMBERS = {"s46m5MS0hxu.Prlt0C1RF0s": 12, "s46m5MS0hxu.psbwp3CQEhs": 8}

#: How long the drain waits between passes over the queue.
DRAIN_INTERVAL_SECONDS = 0.5

#: How often the demo asks its receipt where it stands, and how many times before it gives up.
POLL_INTERVAL_SECONDS = 0.25
POLL_ATTEMPTS = 240

#: From here up the instance is failing rather than answering, so the receipt waits for the next pass.
SERVER_ERROR_STATUS = 500

logger = logging.getLogger("facade")


class FacadeSettings(BaseModel):
    """Everything the facade resolves once at startup: the instance it posts to, and where receipts live."""

    model_config = ConfigDict(frozen=True)

    profile_name: str
    profile: Profile
    project_root: Path
    """The directory the spool tree sits under. A deployment names the project the receipts belong to."""

    @classmethod
    def resolved(cls, *, project_root: Path) -> FacadeSettings:
        """Read the DHIS2 profile this process runs against: `DHIS2_PROFILE`, or the configured default."""
        resolved = resolve()
        return cls(profile_name=resolved.name, profile=resolved.profile, project_root=project_root)

    @property
    def layout(self) -> SpoolLayout:
        """Where the receipts sit: `[serve] spool_dir` against the project root, `.serve/responses` by default.

        The one thing the writing side and the draining side have to agree on to the character, which
        is why both resolve it through `SpoolLayout` rather than composing the path themselves.
        """
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
    """What DHIS2 answered, once a drain has asked it. Absent while the receipt is still queued."""

    refusal: ForwardRefusalRecord | None = None
    """Why the last drain would not translate this queued receipt, when one would not."""


def build_facade(settings: FacadeSettings, context: ConversionContext) -> FastAPI:
    """Two routes - capture and receipt - plus the background task that drains the queue into DHIS2."""
    runtime = FacadeRuntime(context=context, spool=spool_writer.ResponseSpool.at(settings.project_root))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Open the client, start the drain, and stop the drain before the client closes under it."""
        logger.info("starting against %s (profile %s)", settings.profile.base_url, settings.profile_name)
        async with open_client(settings.profile) as client:
            runtime.client = client
            drain = asyncio.create_task(drain_forever(runtime, settings))
            logger.info("ready, receipts under %s", settings.layout.root)
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
        if result.data_value_set is None:
            # This level posts aggregate reports and routes nothing else, so it says so at the door
            # rather than writing down a receipt it will never drain.
            return JSONResponse(
                status_code=422,
                content={
                    "detail": (
                        "this facade takes aggregate reports; the tracker routing is "
                        "examples/fhir/client/advanced_facade.py, and `d2w fhir serve` takes all five form kinds"
                    )
                },
            )
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
        logger.info("received %s answering %s", receipt_id, envelope.questionnaire)
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
    # The same lock `d2w fhir forward` takes. Two drains over one spool would post every receipt
    # twice and race each other's renames, and this facade's own drain is one of the two.
    with spool_queue.drain_lock(settings.layout):
        for spooled in spool_queue.read_received_responses(settings.layout).responses:
            result = translate_response(spooled.response, runtime.context)
            if result.is_refused:
                # A guide can move between the capture and the drain, so a receipt that translated
                # at the door can stop translating. The receipt stays queued - the fix is in the
                # guide or in the data - and the refusal is written beside it as the queue's history.
                spool_queue.record_refusal(spooled, _refusal_record(result))
                logger.warning("still queued, %s: %s", spooled.response_id, result.refusals[0].reason)
                continue
            record = await post_data_value_set(client, result, received_at=spooled.received_at)
            if record.is_rejected:
                spool_queue.move_to_rejected(spooled, record)
                logger.warning("rejected %s: %s", spooled.response_id, record.issues[0].line if record.issues else "")
            else:
                spool_queue.move_to_forwarded(spooled, record)
                logger.info("forwarded %s: %s", spooled.response_id, record.counts_line)


async def post_data_value_set(
    client: Dhis2Client, result: ConversionResult, *, received_at: str
) -> ForwardImportRecord:
    """Post one aggregate envelope and project DHIS2's answer into the sidecar filed beside the receipt."""
    envelope = result.data_value_set
    assert envelope is not None  # the caller routes every other payload kind before it gets here
    body = envelope.model_dump(by_alias=True, exclude_none=True, mode="json")
    try:
        answer = await client.post_raw("/api/dataValueSets", body)
    except Dhis2ApiError as error:
        # A refused import carries the endpoint's own report, and that is a verdict to file. A 5xx
        # is the instance failing rather than answering, so it raises and the receipt stays queued.
        if error.status_code >= SERVER_ERROR_STATUS or not isinstance(error.body, dict):
            raise
        answer = error.body
    summary = ImportSummary.model_validate(answer.get("response") or answer)
    counts = summary.importCount
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
        # The identity of every value this payload landed on, never the numbers. It is what lets a
        # later drain say which values an earlier receipt already sent - the next level's story.
        cells=aggregate_cells(envelope),
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


def aggregate_capture(context: ConversionContext, canonical: str) -> QuestionnaireResponse:
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
            for link_id, value in REPORTED_NUMBERS.items()
        ],
    )


async def wait_for_drain(caller: httpx.AsyncClient, receipt_id: str) -> ReceiptReport:
    """Poll one receipt until a drain has filed it, which is what a client holding an id does."""
    for _ in range(POLL_ATTEMPTS):
        answer = await caller.get(f"/receipts/{receipt_id}")
        report = ReceiptReport.model_validate(answer.json())
        if report.state is not ResponseLifecycle.RECEIVED:
            return report
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"receipt {receipt_id} was still queued after {POLL_ATTEMPTS} polls")


async def remove_imported_values(settings: FacadeSettings, context: ConversionContext) -> None:
    """Delete what this run imported, so the demo leaves the instance exactly as it found it."""
    result = translate_response(aggregate_capture(context, form_canonical(aggregate_form_id())), context)
    envelope = result.data_value_set
    if envelope is None:
        return
    body = envelope.model_dump(by_alias=True, exclude_none=True, mode="json")
    async with open_client(settings.profile) as client:
        await client.post_raw("/api/dataValueSets", body, params={"importStrategy": "DELETE"})


async def main() -> None:
    """Post one capture, watch it travel from received to forwarded, and read its journey back."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    context = conversion_context()
    # A scratch spool, because this demo's receipts are the demo's. A deployment points the facade
    # at the directory its receipts belong to: `d2w fhir serve` writes `.serve/responses` inside the
    # project, and `[serve] spool_dir` moves the tree to a volume the operator backs up.
    project_root = Path(tempfile.mkdtemp(prefix="d2w-facade-spool-"))
    settings = FacadeSettings.resolved(project_root=project_root)
    app = build_facade(settings, context)
    capture = aggregate_capture(context, form_canonical(aggregate_form_id()))
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://facade") as caller,
        ):
            answer = await caller.post(
                "/QuestionnaireResponse", json=capture.model_dump(mode="json", by_alias=True, exclude_none=True)
            )
            accepted = CaptureReceipt.model_validate(answer.json())
            print(f"POST /QuestionnaireResponse -> {answer.status_code}, receipt {accepted.receipt}")
            print(f"  answered {accepted.state} at {accepted.received_at}, before DHIS2 was asked anything")
            print(f"  the receipt is on disk under {settings.layout.root}")
            report = await wait_for_drain(caller, accepted.receipt)
            print(f"GET /receipts/{accepted.receipt} -> {report.state}")
            if report.imported is not None:
                print(f"  DHIS2 answered {report.imported.status}: {report.imported.counts_line}")
            for issue in report.imported.issues if report.imported is not None else ():
                print(f"  [{issue.error_code}] {issue.message}")
    finally:
        await remove_imported_values(settings, context)
        shutil.rmtree(project_root, ignore_errors=True)
        print(f"cleaned up: the {len(REPORTED_NUMBERS)} imported value(s) are deleted and the scratch spool is gone")


if __name__ == "__main__":
    run_example(main)
