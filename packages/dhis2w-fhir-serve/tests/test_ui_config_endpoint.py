"""`GET /uiconfig` - the run-time settings the capture UI acts on, and what it refuses to carry.

The endpoint exists because three things the UI renders are not properties of the served guide:
which raster layers the organisation-unit map may draw under the boundaries, which DHIS2 instance
the guide was generated from, and whether this process answers for people at all. All three are
decided when the process starts, and a bundle compiled weeks earlier cannot know any of them.

These tests hold two contracts. The first is the shape - a plain JSON body, mounted ahead of the
read catch-alls that would otherwise answer that `uiconfig` is not a served resource type. The
second is the omission: nothing about the process that a browser has no business knowing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from dhis2w_fhir.config import DEFAULT_BASEMAP_TEMPLATE, BasemapSource, FhirProject, TrackedEntitiesConfig
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.routes.uiconfig import (
    OPENSTREETMAP_ATTRIBUTION,
    UI_CONFIG_PATH,
    RegisteredTypeUiConfig,
    RegisterUiConfig,
    TrackedEntitiesUiConfig,
    basemap_layers,
    public_instance_url,
    tracked_entities_config,
)
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_project import (
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    SPECIMEN_RESOURCE_TYPE,
    SPECIMEN_TRACKED_ENTITY_TYPE_NAME,
    SPECIMEN_TRACKED_ENTITY_TYPE_UID,
)

#: The layers the app under test is started with unless a test overrides the `basemaps` fixture.
OPENSTREETMAP_LAYERS = [BasemapSource(name="OpenStreetMap", url=DEFAULT_BASEMAP_TEMPLATE)]


@pytest.fixture
def basemaps() -> list[BasemapSource]:
    """The `[serve.basemaps]` layers the app under test was started with; override to change them."""
    return OPENSTREETMAP_LAYERS


@pytest.fixture
def dhis2_base_url() -> str | None:
    """The instance address the run resolved a profile for; override to serve one, or none."""
    return None


@pytest.fixture
def ui_config_app(compiled_project: FhirProject, basemaps: list[BasemapSource], dhis2_base_url: str | None) -> FastAPI:
    """The facade over the compiled project, started with one set of run-time settings."""
    return create_app(
        ServeSettings(
            project_dir=compiled_project.project_root,
            basemaps=basemaps,
            dhis2_base_url=dhis2_base_url,
        )
    )


@pytest.fixture
async def ui_config_client(ui_config_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over that facade, with the lifespan run around the test."""
    async with ui_config_app.router.lifespan_context(ui_config_app):
        transport = httpx.ASGITransport(app=ui_config_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://serve.test") as client:
            yield client


async def test_the_default_answers_the_openstreetmap_layer_with_its_attribution(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """A project stating nothing gets tiles, because a boundary on a blank canvas says where nothing is."""
    response = await ui_config_client.get(UI_CONFIG_PATH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["basemaps"] == [
        {
            "name": "OpenStreetMap",
            "url": DEFAULT_BASEMAP_TEMPLATE,
            "attribution": OPENSTREETMAP_ATTRIBUTION,
        }
    ]


@pytest.mark.parametrize("basemaps", [[]])
async def test_no_configured_layer_is_served_as_an_empty_list_rather_than_as_an_absence(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """`basemaps = []` is the air-gapped posture: the map's layer control then offers None alone."""
    assert (await ui_config_client.get(UI_CONFIG_PATH)).json()["basemaps"] == []


@pytest.mark.parametrize(
    "basemaps",
    [
        [
            BasemapSource(name="OpenStreetMap", url=DEFAULT_BASEMAP_TEMPLATE),
            BasemapSource(name="Satellite", url="https://tiles.example.org/{z}/{x}/{y}.jpg"),
        ]
    ],
)
async def test_the_layers_are_served_in_the_order_they_were_configured(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """The order is the deployment's own statement of which layer the map opens with - the first."""
    served = (await ui_config_client.get(UI_CONFIG_PATH)).json()["basemaps"]

    assert [layer["name"] for layer in served] == ["OpenStreetMap", "Satellite"]
    # Crediting somebody else's tiles is the deployment's obligation; inventing a credit is worse.
    assert served[1]["attribution"] is None


@pytest.mark.parametrize("dhis2_base_url", ["https://play.example.org/dhis"])
async def test_a_resolved_profile_puts_its_instance_address_where_the_screens_can_link_to_it(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """The address is the whole of what makes a link; the profile's name and credentials stay here."""
    body = (await ui_config_client.get(UI_CONFIG_PATH)).json()

    assert body["dhis2_base_url"] == "https://play.example.org/dhis"


async def test_no_resolved_profile_is_served_as_null_rather_than_as_a_guess(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """A compiled guide on a machine that names no profile has nowhere honest to point, and says so."""
    assert (await ui_config_client.get(UI_CONFIG_PATH)).json()["dhis2_base_url"] is None


async def test_the_settings_carry_nothing_a_browser_has_no_business_knowing(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """The model is the enumeration of what the UI acts on, and the omissions are the point."""
    body = (await ui_config_client.get(UI_CONFIG_PATH)).json()

    assert set(body) == {"capture", "basemaps", "dhis2_base_url", "tracked_entities"}
    serialised = str(body)
    for leaked in ("profile", "project_dir", "strict_codes", "live", "port"):
        assert leaked not in serialised, serialised


async def test_a_compiled_run_reports_no_register_surface_to_navigate_to(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """The state is the effective one, not the table read back: a compiled run answers for nothing."""
    assert (await ui_config_client.get(UI_CONFIG_PATH)).json()["tracked_entities"] == {
        "enabled": False,
        "listing": False,
        "registers": [],
    }


def test_the_register_is_reported_as_a_live_run_resolves_it(capture_project: FhirProject) -> None:
    """Live, over a guide publishing registration forms: the register is served, and so is the listing.

    `registers` is the shape the screens act on: one entry per FHIR resource the published map names,
    each carrying the tracked entity types riding it under the names the instance holds - which is
    what lets a page title a section "Specimen batch" rather than calling a sample a person.
    """
    index = TrackedEntityIndex.from_store(capture_project, load_compiled_store(capture_project))
    registers = [
        RegisterUiConfig(
            resource="Patient",
            types=[RegisteredTypeUiConfig(uid=REGISTRATION_TRACKED_ENTITY_TYPE_UID, name="Person")],
        ),
        RegisterUiConfig(
            resource=SPECIMEN_RESOURCE_TYPE,
            types=[
                RegisteredTypeUiConfig(uid=SPECIMEN_TRACKED_ENTITY_TYPE_UID, name=SPECIMEN_TRACKED_ENTITY_TYPE_NAME)
            ],
        ),
    ]

    served = tracked_entities_config(live=True, surface=RegisterSurface.resolve(index, TrackedEntitiesConfig()))
    listing_off = tracked_entities_config(
        live=True, surface=RegisterSurface.resolve(index, TrackedEntitiesConfig(listing=False))
    )
    disabled = tracked_entities_config(
        live=True, surface=RegisterSurface.resolve(index, TrackedEntitiesConfig(enabled=False))
    )

    assert served == TrackedEntitiesUiConfig(enabled=True, listing=True, registers=registers)
    assert listing_off == TrackedEntitiesUiConfig(enabled=True, listing=False, registers=registers)
    assert disabled == TrackedEntitiesUiConfig(enabled=False, listing=False, registers=[])


async def test_the_path_is_not_claimed_by_the_read_catch_all(client: httpx.AsyncClient) -> None:
    """Mounted with the fixed paths: reversed, this answers that `uiconfig` is not a served type."""
    response = await client.get(UI_CONFIG_PATH)

    assert response.status_code == 200
    # The read catch-all would have answered an OperationOutcome naming an unserved resource type.
    assert "resourceType" not in response.json()
    assert "basemaps" in response.json()


def test_a_tile_host_this_server_knows_is_credited_however_the_template_is_written() -> None:
    """The OSM attribution follows the host, so a deployment mirroring their tiles still credits them."""
    layers = basemap_layers([BasemapSource(name="Mirror", url="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")])

    assert [layer.attribution for layer in layers] == [OPENSTREETMAP_ATTRIBUTION]


def test_a_layer_with_an_empty_template_is_dropped_rather_than_offered_as_one_that_draws_nothing() -> None:
    """A control entry that draws nothing when picked lies about what picking it does; None is already there."""
    assert basemap_layers([BasemapSource(name="Cleared", url="   ")]) == []


def test_a_layer_naming_itself_nothing_is_named_by_its_own_template() -> None:
    """A blank name would render a blank row in the layer control, which names no layer at all."""
    layers = basemap_layers([BasemapSource(name=" ", url="https://tiles.example.org/{z}/{x}/{y}.png")])

    assert [layer.name for layer in layers] == ["https://tiles.example.org/{z}/{x}/{y}.png"]


def test_a_password_written_into_a_base_url_does_not_cross_to_the_browser() -> None:
    """The address is the fact the links are made of; whatever userinfo rides on it is a credential."""
    assert public_instance_url("https://admin:district@play.example.org:8080/dhis") == (
        "https://play.example.org:8080/dhis"
    )
    assert public_instance_url("https://play.example.org/dhis") == "https://play.example.org/dhis"
    assert public_instance_url(None) is None
    assert public_instance_url("   ") is None
