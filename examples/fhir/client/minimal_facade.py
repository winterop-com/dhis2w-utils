"""The fifty-line FHIR facade: receive a QuestionnaireResponse, translate it, post it to DHIS2.

`d2w fhir serve` is the complete facade - capability statement, published guide, a live register, a
durable spool, and `d2w fhir forward` draining it. Most integrations want none of that: they have a
FastAPI application already, and somewhere to put a failure already. What they need is the one thing
they cannot write themselves - a captured `QuestionnaireResponse` as the DHIS2 import payload it
means. That is `translate_response`, and `build_facade` below is the whole recipe around it.

What this gives up, all of it deliberately:

| The served facade has | This does not |
| --- | --- |
| durable receipts - every submission stored and readable by id | nothing is written down; the verdict is the answer |
| a retryable spool - a capture waits out an unreachable DHIS2 | an unreachable instance is the caller's to retry |
| a refused queue - a rejected receipt kept, and requeued | a refusal is a 422 body, and then it is gone |
| capability discovery - `/metadata` states the surface | one route at one address, agreed out of band |
| the register - `Patient` search off the live instance | your own application answers who a person is |
| the strict/lenient dial on coded answers | whatever `ConversionContext` the process was handed |
| overwrite naming - a drain names values already sent | each capture is posted with no memory of the last |

**When each fits.** Take the served facade when the submitting side is somebody else's client, when a
refused capture must survive until a person fixes it, and when the receipts are the record. Take this
recipe when the submitting side is yours and the facade is one route in an application that exists.

The guide is [Build your own facade](../../../docs/fhir/401-build-your-own-facade.md); what a valid
response is, is [the capture contract](../../../docs/fhir/401-capture-contract.md).

Usage:
    uv run python examples/fhir/client/minimal_facade.py

Requires a DHIS2 profile (`d2w profile list`). The fixture builds the translation context on first run.
"""

from __future__ import annotations

import json

import httpx
from _fixture import aggregate_form_id, conversion_context, form_canonical
from _runner import run_example
from dhis2w_client import Dhis2ApiError, Profile
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import ConversionContext, translate_response
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)
from fastapi import FastAPI
from fastapi.responses import JSONResponse

#: What the demo reports: a facility Child Health is assigned to, a monthly period, two cells.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"
REPORTED_PERIOD = [Extension(url="iso", valueString="202601"), Extension(url="type", valueCode="Monthly")]
REPORTED_NUMBERS = {"s46m5MS0hxu.Prlt0C1RF0s": 12, "s46m5MS0hxu.psbwp3CQEhs": 8}


def build_facade(context: ConversionContext, profile: Profile, *, dry_run: bool = False) -> FastAPI:
    """One route: receive a capture, translate it, post it to DHIS2, hand back the verdict."""
    app = FastAPI(title="DHIS2 FHIR capture")

    @app.post("/QuestionnaireResponse")
    async def capture(response: QuestionnaireResponse) -> JSONResponse:
        """Translate one captured response and answer with what DHIS2 said about it."""
        # FastAPI parsed the body against the R4 model already, and every model is closed - so an
        # unknown key is its own 422 before this runs.
        result = translate_response(response, context)
        if result.is_refused:
            # A refusal is about the response alone, so the instance is never asked about it.
            refusals = [refusal.model_dump(mode="json", exclude_none=True) for refusal in result.refusals]
            return JSONResponse(status_code=422, content={"refusals": refusals})
        payload = result.payload
        assert payload is not None  # a translated result carries a payload; only a refused one does not

        # Which endpoint the payload goes to is the payload's own shape: an aggregate envelope is an
        # `/api/dataValueSets` body whole, and each tracker payload rides one key of an `/api/tracker` one.
        wire = payload.model_dump(by_alias=True, exclude_none=True, mode="json")
        if result.data_value_set is not None:
            path, params = "/api/dataValueSets", {"dryRun": "true"} if dry_run else {}
            body = wire
        else:
            path, params = "/api/tracker", {"importStrategy": "CREATE", "async": "false"}
            if dry_run:
                params["importMode"] = "VALIDATE"
            if result.tracked_entity is not None:
                body = {"trackedEntities": [wire]}
            elif result.enrollment is not None:
                body = {"enrollments": [wire]}
            else:
                body = {"events": [wire]}

        # One client per request. `open_client` reads `/api/system/info` to bind the version tree, so a
        # facade capturing continuously holds one open for the process - the same call, in a lifespan.
        async with open_client(profile) as client:
            try:
                verdict = await client.post_raw(path, body, params=params)
            except Dhis2ApiError as error:
                # A refused import is a 409 carrying DHIS2's own report - a verdict to pass on, not
                # a fault. Anything carrying no report is about the run, and is raised.
                if not isinstance(error.body, dict):
                    raise
                return JSONResponse(status_code=409, content=error.body)
        return JSONResponse(content=verdict)

    return app


def aggregate_capture(context: ConversionContext, canonical: str) -> QuestionnaireResponse:
    """One small aggregate report: the form it answers, the period, the place, and two numbers."""
    return QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        extension=[
            Extension(url=context.naming.form_type_url, valueCode="aggregate"),
            Extension(url=context.naming.period_url, extension=REPORTED_PERIOD),
        ],
        subject=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
        item=[
            QuestionnaireResponseItem(linkId=link_id, answer=[QuestionnaireResponseAnswer(valueInteger=value)])
            for link_id, value in REPORTED_NUMBERS.items()
        ],
    )


async def main() -> None:
    """Drive the recipe in-process: one capture DHIS2 grades, and one the translator refuses first."""
    context = conversion_context()
    # The demo validates only; a real facade drops the parameter and DHIS2 keeps what it is sent.
    app = build_facade(context, resolve_profile(), dry_run=True)
    served = aggregate_capture(context, form_canonical(aggregate_form_id()))
    unknown = aggregate_capture(context, "http://example.org/fhir/Questionnaire/NotAServedForm")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://facade") as caller:
        for label, response in (("a form the context carries", served), ("a form it does not", unknown)):
            answer = await caller.post(
                "/QuestionnaireResponse", json=response.model_dump(mode="json", by_alias=True, exclude_none=True)
            )
            print(f"POST /QuestionnaireResponse, {label} -> {answer.status_code}")
            print(json.dumps(answer.json(), indent=2), end="\n\n")


if __name__ == "__main__":
    run_example(main)
