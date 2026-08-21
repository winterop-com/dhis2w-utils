"""The routers as values: what `serve_routers` states, and that mounting it by hand builds the same facade.

Two claims are under test. The first is that the route table `create_app` produces is the table
`serve_routers` describes - path for path, method for method, in mount order, which is the order that
decides whether `/metadata` is a read of a resource named `metadata`. The second is that an
application mounting those routers over a runtime it opened itself answers what the factory answers,
which is the contract `docs/fhir/design/library.md` section 3.4 states and the thing an embedder is
entitled to rely on.

Two answers carry the moment they were made - the CapabilityStatement's `date`, and the id a receipt
is minted under - so those two are pinned here. Everything else is compared as the bytes that left
the server.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject, SearchBackend, SearchConfig, ServeAuth, ServeAuthScope
from dhis2w_fhir_serve import capability as capability_module
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.errors import NotFoundError, register_error_handlers
from dhis2w_fhir_serve.routes import accept_head_wherever_get_is_served, serve_routers
from dhis2w_fhir_serve.routes import capture as capture_route_module
from dhis2w_fhir_serve.routes.negotiation import require_json_is_acceptable
from dhis2w_fhir_serve.runtime import attach_serve_runtime, open_serve_runtime
from dhis2w_fhir_serve.settings import ServeSettings
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

BASE_URL = "http://serve.test"

#: The clock and the mint, pinned so two servers answering the same question answer the same bytes.
FIXED_INSTANT = "2026-08-18T09:00:00Z"
FIXED_RESPONSE_ID = "receipt-fixed"


class MountedRoute(BaseModel):
    """One row of a route table: the path a router claimed, and the methods it answers there."""

    model_config = ConfigDict(frozen=True)

    path: str
    methods: tuple[str, ...]


def _route_table(app: FastAPI) -> tuple[MountedRoute, ...]:
    """Every route an application serves, in the order its table was built."""
    return tuple(
        MountedRoute(path=route.path, methods=tuple(sorted(route.methods or ())))
        for route in app.routes
        if isinstance(route, APIRoute)
    )


def _embedded_app(capture: bool = True, authentication: Any = None) -> FastAPI:
    """An application that mounts the facade's routers itself, in the order `ServeRouters` states.

    `authentication` is the seam an embedding application uses: the guarded set is a value, and what
    is mounted over it is the caller's choice. Passing None mounts nothing, which is what a `none`
    posture answers with anyway.
    """
    app = FastAPI()
    register_error_handlers(app)
    routers = serve_routers(capture=capture)
    for router in routers.in_mount_order():
        accept_head_wherever_get_is_served(router)
    for router in routers.fhir:
        app.include_router(router, dependencies=[Depends(require_json_is_acceptable)])
    for router in routers.facade:
        app.include_router(router)
    app.include_router(routers.read, dependencies=[Depends(require_json_is_acceptable)])
    _ = authentication
    return app


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the two values that are the moment an answer was made rather than what the answer says."""
    monkeypatch.setattr(capability_module, "current_instant", lambda: FIXED_INSTANT)
    monkeypatch.setattr(capture_route_module, "current_instant", lambda: FIXED_INSTANT)
    monkeypatch.setattr(capture_route_module, "new_response_id", lambda: FIXED_RESPONSE_ID)


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """An in-process client over one application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
        yield http


@pytest.mark.parametrize("capture", [True, False])
def test_the_factory_mounts_what_serve_routers_states(compiled_project: FhirProject, capture: bool) -> None:
    """The table is the same table, path for path and method for method, in the same order."""
    settings = ServeSettings(project_dir=compiled_project.project_root, capture=capture)

    assert _route_table(create_app(settings)) == _route_table(_embedded_app(capture=capture))


def test_the_read_catch_alls_mount_last(compiled_project: FhirProject) -> None:
    """`/{resource_type}` claims any one-segment path, so every fixed path is claimed before it."""
    table = _route_table(create_app(ServeSettings(project_dir=compiled_project.project_root)))
    catch_alls = tuple(row for row in table if "{resource_type}" in row.path)

    assert catch_alls == table[-len(catch_alls) :]


def test_the_fhir_routers_carry_the_negotiation_and_the_facade_routers_do_not() -> None:
    """The split is stated once, as data: a client that takes no JSON is refused before the FHIR surface runs."""
    routers = serve_routers()
    fhir_paths = {route.path for router in routers.fhir for route in router.routes if isinstance(route, APIRoute)}
    facade_paths = {route.path for router in routers.facade for route in router.routes if isinstance(route, APIRoute)}

    assert "/metadata" in fhir_paths
    assert facade_paths == {
        "/spool",
        "/uiconfig",
        "/tracked-entities/{tracked_entity_uid}/enrollments",
        "/evaluate",
        "/terminology/validate-code",
        "/terminology/lookup",
        "/cds-services",
        "/cds-services/{service_id}",
    }
    assert fhir_paths & facade_paths == set()


async def test_the_guarded_set_is_a_value_an_embedding_application_reads(
    capture_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """An embedder mounts its OWN check over `ServeRouters.guarded`, which is why the set is data.

    The facade's own dependency is never imported here. What is checked is that the set names the
    create route and nothing else, and that a check mounted over it runs on a capture and on no read.
    """
    routers = serve_routers(auth=ServeAuth.DHIS2, auth_scope=ServeAuthScope.WRITE)
    reached: list[str] = []

    async def _its_own_check() -> None:
        reached.append("checked")

    settings = ServeSettings(project_dir=capture_project.project_root)
    app = FastAPI()
    register_error_handlers(app)
    for router in routers.in_mount_order():
        accept_head_wherever_get_is_served(router)
    for router in routers.fhir:
        guard = [Depends(_its_own_check)] if routers.is_guarded(router) else []
        app.include_router(router, dependencies=[*guard, Depends(require_json_is_acceptable)])
    for router in routers.facade:
        app.include_router(router)
    app.include_router(routers.read, dependencies=[Depends(require_json_is_acceptable)])

    assert routers.is_guarded(routers.read) is False
    async with open_serve_runtime(settings) as runtime:
        attach_serve_runtime(app, runtime)
        async with _client(app) as mounted:
            await mounted.get("/Questionnaire")
            assert reached == []
            await mounted.post("/QuestionnaireResponse", content=json.dumps(aggregate_response))

    assert reached == ["checked"]


def test_the_route_table_is_the_same_whatever_the_posture(compiled_project: FhirProject) -> None:
    """A guard is a dependency on a mount, not a route: no posture adds, removes, or renames a path."""
    open_to_everyone = _route_table(create_app(ServeSettings(project_dir=compiled_project.project_root)))
    guarded = _route_table(
        create_app(
            ServeSettings(
                project_dir=compiled_project.project_root,
                auth=ServeAuth.TOKEN,
                auth_scope=ServeAuthScope.ALL,
            )
        )
    )

    assert open_to_everyone == guarded


def test_the_route_table_is_the_same_whatever_answers_a_search(compiled_project: FhirProject) -> None:
    """`[serve.search]` says what a lookup runs through, never where a lookup lives: no path moves with it."""
    default = _route_table(create_app(ServeSettings(project_dir=compiled_project.project_root)))
    through_the_instance = _route_table(
        create_app(
            ServeSettings(
                project_dir=compiled_project.project_root,
                search=SearchConfig(backend=SearchBackend.DHIS2),
            )
        )
    )

    assert default == through_the_instance


def test_the_capture_choice_is_settled_at_mount_time() -> None:
    """One of the create route and the refusal is always mounted, so the address never falls through."""
    receiving = serve_routers(capture=True)
    refusing = serve_routers(capture=False)

    def _capture_paths(routers: tuple[Any, ...]) -> set[str]:
        return {
            route.path
            for router in routers
            for route in router.routes
            if isinstance(route, APIRoute) and "POST" in (route.methods or set())
        }

    assert "/QuestionnaireResponse" in _capture_paths(receiving.fhir)
    assert "/QuestionnaireResponse" in _capture_paths(refusing.fhir)


async def test_a_hand_mounted_facade_answers_the_reads_the_factory_answers(compiled_project: FhirProject) -> None:
    """`/metadata`, a read, and a search leave both servers as the same bytes."""
    settings = ServeSettings(project_dir=compiled_project.project_root)
    factory = create_app(settings)
    embedded = _embedded_app()

    async with open_serve_runtime(settings) as runtime, factory.router.lifespan_context(factory):
        attach_serve_runtime(embedded, runtime)
        async with _client(factory) as served, _client(embedded) as mounted:
            for path in ("/metadata", "/Questionnaire/d2-pr-anc-visit-q", "/Questionnaire"):
                from_factory = await served.get(path)
                from_embedded = await mounted.get(path)

                assert from_factory.status_code == from_embedded.status_code == 200
                assert from_factory.headers["content-type"] == from_embedded.headers["content-type"]
                assert from_factory.content == from_embedded.content


async def test_a_hand_mounted_facade_receives_a_capture_the_way_the_factory_does(
    capture_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """A submission is validated against the served guide and stored, whoever mounted the route."""
    settings = ServeSettings(project_dir=capture_project.project_root)
    factory = create_app(settings)
    embedded = _embedded_app()
    body = json.dumps(aggregate_response)

    async with open_serve_runtime(settings) as runtime, factory.router.lifespan_context(factory):
        attach_serve_runtime(embedded, runtime)
        async with _client(factory) as served, _client(embedded) as mounted:
            from_factory = await served.post("/QuestionnaireResponse", content=body)
            from_embedded = await mounted.post("/QuestionnaireResponse", content=body)

            assert from_factory.status_code == from_embedded.status_code == 201
            assert from_factory.headers["location"] == from_embedded.headers["location"]
            assert from_factory.content == from_embedded.content


async def test_the_error_handlers_are_what_make_a_refusal_an_operation_outcome(
    compiled_project: FhirProject,
) -> None:
    """They are part of the contract: an application that skips them answers 500 where the facade answers 404."""
    settings = ServeSettings(project_dir=compiled_project.project_root)
    handled = _embedded_app()
    unhandled = FastAPI()
    unhandled.include_router(serve_routers().read)

    async with open_serve_runtime(settings) as runtime:
        attach_serve_runtime(handled, runtime)
        attach_serve_runtime(unhandled, runtime)
        async with _client(handled) as mounted:
            refused = await mounted.get("/Questionnaire/missing")

        assert refused.status_code == 404
        assert refused.json()["resourceType"] == "OperationOutcome"
        with pytest.raises(NotFoundError):
            async with _client(unhandled) as bare:
                await bare.get("/Questionnaire/missing")
