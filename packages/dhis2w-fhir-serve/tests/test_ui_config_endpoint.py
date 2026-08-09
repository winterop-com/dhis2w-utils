"""`GET /uiconfig` - the run-time settings the capture UI acts on, and what it refuses to carry.

The endpoint exists because one thing the UI renders is not a property of the served guide: which
raster tiles the organisation-unit map draws under the boundaries. That is decided when the process
starts, and a bundle compiled weeks earlier cannot know it.

These tests hold two contracts. The first is the shape - a plain JSON body, mounted ahead of the
read catch-alls that would otherwise answer that `uiconfig` is not a served resource type. The
second is the omission: nothing about the process that a browser has no business knowing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from dhis2w_fhir.config import DEFAULT_BASEMAP_TEMPLATE, FhirProject
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.routes.uiconfig import OPENSTREETMAP_ATTRIBUTION, UI_CONFIG_PATH, basemap_config
from dhis2w_fhir_serve.settings import ServeSettings
from fastapi import FastAPI


@pytest.fixture
def basemap() -> str:
    """The `[serve] basemap` value the app under test was started with; override to change it."""
    return DEFAULT_BASEMAP_TEMPLATE


@pytest.fixture
def ui_config_app(compiled_project: FhirProject, basemap: str) -> FastAPI:
    """The facade over the compiled project, started with one basemap setting."""
    return create_app(ServeSettings(project_dir=compiled_project.project_root, basemap=basemap))


@pytest.fixture
async def ui_config_client(ui_config_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process client over that facade, with the lifespan run around the test."""
    async with ui_config_app.router.lifespan_context(ui_config_app):
        transport = httpx.ASGITransport(app=ui_config_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://serve.test") as client:
            yield client


async def test_the_default_answers_the_openstreetmap_template_with_its_attribution(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """A project stating nothing gets tiles, because a boundary on a blank canvas says where nothing is."""
    response = await ui_config_client.get(UI_CONFIG_PATH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["basemap"]["template"] == DEFAULT_BASEMAP_TEMPLATE
    assert body["basemap"]["attribution"] == OPENSTREETMAP_ATTRIBUTION


@pytest.mark.parametrize("basemap", ["none", "None", " NONE "])
async def test_none_turns_the_tiles_off_however_it_is_spelled(ui_config_client: httpx.AsyncClient) -> None:
    """`none` is a word rather than an empty string, so it is matched the way a person would write it."""
    response = await ui_config_client.get(UI_CONFIG_PATH)

    assert response.json() == {"basemap": None}


@pytest.mark.parametrize("basemap", ["https://tiles.example.org/{z}/{x}/{y}.png"])
async def test_a_custom_source_is_served_without_an_attribution_this_server_cannot_know(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """Crediting somebody else's tiles is the deployment's obligation; inventing a credit is worse than none."""
    body = (await ui_config_client.get(UI_CONFIG_PATH)).json()

    assert body["basemap"]["template"] == "https://tiles.example.org/{z}/{x}/{y}.png"
    assert body["basemap"]["attribution"] is None


async def test_the_settings_carry_nothing_a_browser_has_no_business_knowing(
    ui_config_client: httpx.AsyncClient,
) -> None:
    """The model is the enumeration of what the UI acts on, and the omissions are the point."""
    body = (await ui_config_client.get(UI_CONFIG_PATH)).json()

    assert set(body) == {"basemap"}
    serialised = str(body)
    for leaked in ("profile", "project_dir", "strict_codes", "live", "port"):
        assert leaked not in serialised, serialised


async def test_the_path_is_not_claimed_by_the_read_catch_all(client: httpx.AsyncClient) -> None:
    """Mounted with the fixed paths: reversed, this answers that `uiconfig` is not a served type."""
    response = await client.get(UI_CONFIG_PATH)

    assert response.status_code == 200
    # The read catch-all would have answered an OperationOutcome naming an unserved resource type.
    assert "resourceType" not in response.json()
    assert "basemap" in response.json()


def test_a_tile_host_this_server_knows_is_credited_however_the_template_is_written() -> None:
    """The OSM attribution follows the host, so a deployment mirroring their tiles still credits them."""
    resolved = basemap_config("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")

    assert resolved is not None
    assert resolved.attribution == OPENSTREETMAP_ATTRIBUTION


def test_an_empty_template_is_read_as_no_basemap_rather_than_as_a_broken_one() -> None:
    """`basemap = ""` is somebody clearing the value, and the honest reading of that is no tiles."""
    assert basemap_config("") is None
    assert basemap_config("   ") is None
