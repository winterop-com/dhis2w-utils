"""Level two of the facade ladder: the same one route, in the shape a deployment runs it in.

The minimal recipe (`examples/fhir/client/minimal_facade.py`) opens a DHIS2 client per request,
resolves its profile inside the route, and says nothing about what it did. Each of those is fine for
a demo and wrong for a process that runs for months, so this level buys back four guarantees:

- **One client, opened in a FastAPI lifespan.** `open_client` reads `/api/system/info` to bind the
  version tree, so a client per request is a second round trip per capture.
- **Settings resolved once, at startup.** A profile that will not resolve fails the process at boot
  rather than the first capture at 03:00.
- **`/health`, one cheap read of DHIS2.** What a load balancer asks, and the honest answer involves
  the instance rather than this process alone.
- **One log line per verdict.** A capture refused six weeks ago is answerable.

**The trade:** still nothing is written down. A capture that arrives while DHIS2 is unreachable is a
failed request, and its sender is the only one who knows it happened. `/health` will say the instance
is unreachable, which is more than the level below says, and it is not a queue. Captures start
surviving one level up, at `examples/fhir/client/complex_facade.py`.

The guide is [Build your own facade](../../../docs/fhir/401-build-your-own-facade.md); what a valid
response is, is [the capture contract](../../../docs/fhir/401-capture-contract.md).

Usage:
    uv run python examples/fhir/client/basic_facade.py

Requires a DHIS2 profile (`d2w profile list`). The fixture builds the translation context on first run.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import httpx
from _fixture import aggregate_form_id, conversion_context, form_canonical
from _runner import run_example
from dhis2w_client import Dhis2ApiError, Dhis2Client, Dhis2ClientError, Profile
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import resolve
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
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

#: What the demo reports: a facility Child Health is assigned to, a monthly period, two cells.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"
REPORTED_PERIOD_ISO = "202602"
REPORTED_NUMBERS = {"s46m5MS0hxu.Prlt0C1RF0s": 14, "s46m5MS0hxu.psbwp3CQEhs": 9}

#: Wara Wara Yagala, a chiefdom of Koinadugu: a published Location the translator resolves happily,
#: and a place the seeded instance does not collect Child Health at. DHIS2 itself is what refuses it.
UNREPORTING_ORGANISATION_UNIT_UID = "EZPwuUTeIIG"

#: From here up the instance is failing rather than answering, so the failure is about the run.
SERVER_ERROR_STATUS = 500

#: What the facade answers while it holds no client: startup unfinished, or shutdown begun.
SERVICE_UNAVAILABLE_STATUS = 503

logger = logging.getLogger("facade")


class FacadeSettings(BaseModel):
    """Everything the facade resolves once at startup rather than per capture."""

    model_config = ConfigDict(frozen=True)

    profile_name: str
    profile: Profile
    dry_run: bool = False
    """Post under each endpoint's validate-only mode, so a demo leaves nothing on the instance."""

    @classmethod
    def resolved(cls, *, dry_run: bool = False) -> FacadeSettings:
        """Read the DHIS2 profile this process runs against: `DHIS2_PROFILE`, or the configured default.

        Resolution raises here rather than in a route, which is the point of doing it at startup: a
        process that cannot name its instance never starts serving, so nobody is ever answered 500
        for a configuration mistake made before the first capture arrived.
        """
        resolved = resolve()
        return cls(profile_name=resolved.name, profile=resolved.profile, dry_run=dry_run)


class FacadeRuntime(BaseModel):
    """What the process holds for its whole life: the translation context, and one connected client."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    context: ConversionContext
    client: Dhis2Client | None = None
    """None only outside the lifespan - before startup finished, and after shutdown began."""


class HealthReport(BaseModel):
    """Whether this facade can reach DHIS2 right now, and what the instance said about itself."""

    model_config = ConfigDict(frozen=True)

    dhis2_reachable: bool
    instance: str
    profile: str
    version: str | None = None
    detail: str | None = None
    """What stopped the read, when something did - the sentence an operator acts on."""


def build_facade(settings: FacadeSettings, context: ConversionContext) -> FastAPI:
    """A capture route, a health route, and one DHIS2 client held open for the life of the process."""
    runtime = FacadeRuntime(context=context)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Open the one client at startup and close it at shutdown, which is the whole of the lifespan."""
        logger.info("starting against %s (profile %s)", settings.profile.base_url, settings.profile_name)
        async with open_client(settings.profile) as client:
            runtime.client = client
            logger.info("ready, %d form(s) served", len(context.forms))
            yield
            runtime.client = None
        logger.info("stopped")

    def unreachable(detail: str) -> JSONResponse:
        """One 503 saying this facade cannot do its job at the moment, and what is in the way."""
        report = HealthReport(
            dhis2_reachable=False,
            instance=str(settings.profile.base_url),
            profile=settings.profile_name,
            detail=detail,
        )
        return JSONResponse(status_code=SERVICE_UNAVAILABLE_STATUS, content=report.model_dump(exclude_none=True))

    app = FastAPI(title="DHIS2 FHIR capture", lifespan=lifespan)

    @app.get("/health")
    async def health() -> JSONResponse:
        """Whether DHIS2 answers this process right now - one cheap read, no capture involved."""
        client = runtime.client
        if client is None:
            return unreachable("the facade holds no client")
        try:
            # Uncached on purpose: a cached answer says the instance was reachable once, which is
            # not the question a health check asks.
            info = await client.system.info(use_cache=False)
        except (Dhis2ClientError, httpx.HTTPError) as error:
            return unreachable(str(error))
        report = HealthReport(
            dhis2_reachable=True,
            instance=str(settings.profile.base_url),
            profile=settings.profile_name,
            version=info.version,
        )
        return JSONResponse(content=report.model_dump(exclude_none=True))

    @app.post("/QuestionnaireResponse")
    async def capture(response: QuestionnaireResponse) -> JSONResponse:
        """Translate one captured response, post it under the process's client, and say what DHIS2 said."""
        result = translate_response(response, runtime.context)
        if result.is_refused:
            # A refusal is about the response alone, so the instance is never asked about it.
            for refusal in result.refusals:
                logger.info("refused %s [%s] %s", response.questionnaire, refusal.category, refusal.reason)
            refusals = [refusal.model_dump(mode="json", exclude_none=True) for refusal in result.refusals]
            return JSONResponse(status_code=422, content={"refusals": refusals})
        client = runtime.client
        if client is None:
            logger.error("a capture arrived while the facade held no client")
            return unreachable("the facade holds no client")

        # Which endpoint the payload goes to is the payload's own shape: an aggregate envelope is an
        # `/api/dataValueSets` body whole, and each tracker payload rides one key of an `/api/tracker` one.
        payload = result.payload
        assert payload is not None  # a translated result carries a payload; only a refused one does not
        wire = payload.model_dump(by_alias=True, exclude_none=True, mode="json")
        if result.data_value_set is not None:
            path, params = "/api/dataValueSets", {"dryRun": "true"} if settings.dry_run else {}
            body: dict[str, Any] = wire
        else:
            path, params = "/api/tracker", {"importStrategy": "CREATE", "async": "false"}
            if settings.dry_run:
                params["importMode"] = "VALIDATE"
            if result.tracked_entity is not None:
                body = {"trackedEntities": [wire]}
            elif result.enrollment is not None:
                body = {"enrollments": [wire]}
            else:
                body = {"events": [wire]}
        try:
            verdict = await client.post_raw(path, body, params=params)
        except Dhis2ApiError as error:
            # DHIS2's verdict goes back under DHIS2's own status. A 5xx is the instance failing
            # rather than answering, and a body that is no report is about the run: both raise.
            if error.status_code >= SERVER_ERROR_STATUS or not isinstance(error.body, dict):
                raise
            logger.warning("DHIS2 answered %d about %s", error.status_code, response.questionnaire)
            return JSONResponse(status_code=error.status_code, content=error.body)
        logger.info("accepted %s as %s", response.questionnaire, result.target_kind)
        return JSONResponse(content=verdict)

    return app


def aggregate_capture(
    context: ConversionContext, canonical: str, organisation_unit: str = ORGANISATION_UNIT_UID
) -> QuestionnaireResponse:
    """One small aggregate report: the form it answers, the period, the place, and two numbers."""
    period = [Extension(url="iso", valueString=REPORTED_PERIOD_ISO), Extension(url="type", valueCode="Monthly")]
    return QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        extension=[
            Extension(url=context.naming.form_type_url, valueCode="aggregate"),
            Extension(url=context.naming.period_url, extension=period),
        ],
        subject=Reference(reference=f"Location/{organisation_unit}"),
        item=[
            QuestionnaireResponseItem(linkId=link_id, answer=[QuestionnaireResponseAnswer(valueInteger=value)])
            for link_id, value in REPORTED_NUMBERS.items()
        ],
    )


async def main() -> None:
    """Run the facade the way a process runs it: one startup, two captures, one shutdown."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    context = conversion_context()
    # The demo validates only; a deployment drops the flag and DHIS2 keeps what it is sent.
    settings = FacadeSettings.resolved(dry_run=True)
    app = build_facade(settings, context)
    canonical = form_canonical(aggregate_form_id())
    postings = (
        ("a form the context carries", aggregate_capture(context, canonical)),
        (
            "a place the form is not collected at",
            aggregate_capture(context, canonical, organisation_unit=UNREPORTING_ORGANISATION_UNIT_UID),
        ),
    )
    # `httpx.ASGITransport` calls the application and nothing else - it runs no startup and no
    # shutdown, so a client opened in the lifespan would still be None inside every route. Entering
    # the lifespan by hand is what uvicorn does for a served process and what `asgi-lifespan`'s
    # LifespanManager does for a test suite.
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://facade") as caller,
    ):
        health = await caller.get("/health")
        print(f"GET /health -> {health.status_code}: {json.dumps(health.json())}\n")
        for label, response in postings:
            answer = await caller.post(
                "/QuestionnaireResponse", json=response.model_dump(mode="json", by_alias=True, exclude_none=True)
            )
            summary = answer.json().get("response", answer.json())
            print(f"POST /QuestionnaireResponse, {label} -> {answer.status_code}")
            print(f"  {summary.get('status')}: {json.dumps(summary.get('importCount'))}")
            for conflict in summary.get("conflicts", []):
                print(f"  [{conflict.get('errorCode')}] {conflict.get('value')}")
            print()


if __name__ == "__main__":
    run_example(main)
