"""The runtime as a value: what a facade loads, opened without an application to serve it from.

The claim under test is that there is one loading path and the lifespan is a caller of it. So every
assertion here compares a runtime opened on its own against the state `create_app`'s lifespan leaves
on the application for the same settings - the store, the spool, the register surface, and the
CapabilityStatement, all four.

The statement is the one thing that cannot be compared byte for byte: it carries the instant it was
built, so two builds differ in exactly that element and in nothing else.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_client import BasicAuth, Dhis2Client
from dhis2w_fhir.config import FhirProject, ServeAuth
from dhis2w_fhir_serve import runtime as runtime_module
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.errors import register_error_handlers
from dhis2w_fhir_serve.passthrough import FACADE_PROVENANCE_HEADER
from dhis2w_fhir_serve.routes import register_routes
from dhis2w_fhir_serve.runtime import ServeContext, ServeRuntime, attach_serve_runtime, open_serve_runtime
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseSpool, StoredResponseEnvelope
from dhis2w_fhir_serve.store import ResourceStore, StoreEntry
from fastapi import FastAPI

BASE_URL = "http://serve.test"

#: The one element two builds of the same statement disagree about, because each is stamped when built.
STAMPED_ELEMENT = "date"

#: The instance a live run reads, and the one a `dhis2` posture opens its pass-through pool against.
INSTANCE_URL = "https://play.example.org/dhis"


@pytest.fixture
def settings(compiled_project: FhirProject, stored_responses: tuple[StoredResponseEnvelope, ...]) -> ServeSettings:
    """The compiled project, with the receipts a running facade would already hold seeded on disk."""
    spool = ResponseSpool.at(compiled_project.project_root)
    for envelope in stored_responses:
        spool.save(envelope)
    return ServeSettings(project_dir=compiled_project.project_root)


@asynccontextmanager
async def _lifespan_context(app: FastAPI) -> AsyncGenerator[ServeContext]:
    """Run one application's lifespan and hand back the context it attached."""
    async with app.router.lifespan_context(app):
        context: ServeContext = app.state.context
        yield context


def _statement_without_the_stamp(capability_body: dict[str, Any]) -> dict[str, Any]:
    """One CapabilityStatement minus the instant it was built at, which is what two builds differ in."""
    return {key: value for key, value in capability_body.items() if key != STAMPED_ELEMENT}


async def test_a_runtime_opened_without_an_app_loads_what_the_lifespan_loads(settings: ServeSettings) -> None:
    """The store, the spool, the register, and the statement are the same four whichever door was used."""
    async with open_serve_runtime(settings) as runtime, _lifespan_context(create_app(settings)) as served:
        loaded = runtime.context

        assert loaded.store.summary() == served.store.summary()
        assert loaded.spool.count() == served.spool.count()
        assert loaded.register_surface == served.register_surface
        assert _statement_without_the_stamp(loaded.capability_body) == _statement_without_the_stamp(
            served.capability_body
        )
        assert loaded.capability_body[STAMPED_ELEMENT]
        assert loaded.project.project_root == served.project.project_root
        assert loaded.settings == served.settings


async def test_the_default_mode_holds_no_client(settings: ServeSettings) -> None:
    """A facade serving a compiled guide opens no connection anywhere, which is what makes the register live-only."""
    async with open_serve_runtime(settings) as runtime:
        assert runtime.live_client is None


async def test_the_live_client_is_open_inside_the_context_and_closed_after(
    compiled_project: FhirProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The client's lifetime is the context manager's: entering opens it, leaving closes it."""
    client = Dhis2Client(base_url="https://play.example.org/dhis", auth=BasicAuth(username="a", password="b"))
    opened: list[bool] = []

    @asynccontextmanager
    async def _open(project: FhirProject, settings: ServeSettings) -> AsyncGenerator[Dhis2Client]:
        opened.append(True)
        try:
            yield client
        finally:
            opened.append(False)

    async def _live_store(project: FhirProject, settings: ServeSettings, live: Dhis2Client) -> ResourceStore:
        return ResourceStore(
            entries=(StoreEntry(resource_type="Questionnaire", resource_id="live", source="live", body={}),)
        )

    monkeypatch.setattr(runtime_module, "open_live_client", _open)
    monkeypatch.setattr(runtime_module, "build_live_store", _live_store)
    settings = ServeSettings(project_dir=compiled_project.project_root, live=True)

    async with open_serve_runtime(settings) as runtime:
        assert runtime.live_client is client
        assert opened == [True]

    assert opened == [True, False]


async def test_a_client_the_caller_holds_is_read_through_and_left_open(
    compiled_project: FhirProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process that authenticated once serves over the connection it already has, and keeps owning it."""
    client = Dhis2Client(base_url="https://play.example.org/dhis", auth=BasicAuth(username="a", password="b"))
    read_through: list[Dhis2Client] = []

    async def _live_store(project: FhirProject, settings: ServeSettings, live: Dhis2Client) -> ResourceStore:
        read_through.append(live)
        return ResourceStore(entries=())

    def _refuse_to_open(project: FhirProject, settings: ServeSettings) -> None:
        raise AssertionError("a handed-in client is the connection, and no second one is opened")

    monkeypatch.setattr(runtime_module, "open_live_client", _refuse_to_open)
    monkeypatch.setattr(runtime_module, "build_live_store", _live_store)
    settings = ServeSettings(project_dir=compiled_project.project_root, live=True)

    async with open_serve_runtime(settings, client=client) as runtime:
        assert runtime.live_client is client

    assert read_through == [client]


async def test_a_client_handed_to_a_run_that_is_not_live_is_refused(settings: ServeSettings) -> None:
    """A connection beside `live = False` is two statements that disagree, and it says so rather than guessing."""
    client = Dhis2Client(base_url="https://play.example.org/dhis", auth=BasicAuth(username="a", password="b"))

    with pytest.raises(ValueError, match="live=True"):
        async with open_serve_runtime(settings, client=client):
            pass


async def test_a_runtime_is_read_only(settings: ServeSettings) -> None:
    """What one facade holds is settled when it is opened - a request never rewrites it."""
    async with open_serve_runtime(settings) as runtime:
        with pytest.raises(ValueError, match="frozen"):
            runtime.live_client = None


async def test_attaching_a_runtime_is_what_the_routers_need(settings: ServeSettings) -> None:
    """An application that attaches a runtime and mounts the routers answers `/metadata` as the factory does."""
    embedded = FastAPI()
    register_error_handlers(embedded)
    register_routes(embedded)

    async with open_serve_runtime(settings) as runtime, _lifespan_context(create_app(settings)) as served:
        attach_serve_runtime(embedded, runtime)
        transport = httpx.ASGITransport(app=embedded)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            answered = await http.get("/metadata")

        assert answered.status_code == 200
        assert _statement_without_the_stamp(answered.json()) == _statement_without_the_stamp(served.capability_body)


async def test_attaching_places_both_names_the_handlers_read(settings: ServeSettings) -> None:
    """The state an embedding application must promise the routers is two names, and this writes both."""
    embedded = FastAPI()

    async with open_serve_runtime(settings) as runtime:
        attach_serve_runtime(embedded, runtime)

        assert embedded.state.context is runtime.context
        assert embedded.state.live_client is None
        assert embedded.state.caller_client is None


def test_a_runtime_names_what_a_facade_holds(tmp_path: Path) -> None:
    """`ServeContext` is what is served, and the two connections are what it is served over."""
    fields = set(ServeRuntime.model_fields)

    assert fields == {"context", "live_client", "caller_client"}


async def test_the_pass_through_connection_is_opened_only_for_the_dhis2_posture(
    compiled_project: FhirProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing else forwards anybody's credential, so nothing else opens the pool that would carry one."""
    client = Dhis2Client(base_url=INSTANCE_URL, auth=BasicAuth(username="a", password="b"))

    async def _live_store(project: FhirProject, settings: ServeSettings, live: Dhis2Client) -> ResourceStore:
        return ResourceStore(entries=())

    monkeypatch.setattr(runtime_module, "build_live_store", _live_store)

    async with open_serve_runtime(_live_settings(compiled_project, ServeAuth.TOKEN), client=client) as runtime:
        assert runtime.caller_client is None


async def test_the_pass_through_connection_is_open_inside_the_context_and_closed_after(
    compiled_project: FhirProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its lifetime is the runtime's, exactly as the client's is - and it carries no credential of its own."""
    client = Dhis2Client(base_url=INSTANCE_URL, auth=BasicAuth(username="a", password="b"))

    async def _live_store(project: FhirProject, settings: ServeSettings, live: Dhis2Client) -> ResourceStore:
        return ResourceStore(entries=())

    monkeypatch.setattr(runtime_module, "build_live_store", _live_store)

    async with open_serve_runtime(_live_settings(compiled_project, ServeAuth.DHIS2), client=client) as runtime:
        pool = runtime.caller_client
        assert pool is not None
        assert str(pool.base_url) == f"{INSTANCE_URL}/"
        assert pool.auth is None
        assert "authorization" not in pool.headers
        assert pool.headers[FACADE_PROVENANCE_HEADER].startswith("dhis2w-fhir-serve/")

    assert pool.is_closed


def _live_settings(project: FhirProject, posture: ServeAuth) -> ServeSettings:
    """A live run under one posture, against the instance the `dhis2` posture would check callers with."""
    return ServeSettings(project_dir=project.project_root, live=True, auth=posture, dhis2_base_url=INSTANCE_URL)
