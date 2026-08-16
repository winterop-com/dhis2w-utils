"""`GET /Patient` with no identifier: the paged register, and what `[serve.tracked_entities]` does to it.

Mocked (respx); no live stack, on the same terms as `test_register.py` - the compiled capture
fixture is the guide, and a DHIS2 client against a mocked host is put on `app.state.live_client`,
which is what makes these routes answer rather than refuse. `[serve.tracked_entities]` is handed to the app
through `ServeSettings.tracked_entities`, which is exactly what `d2w fhir serve` reads off `fhir.toml`.

What is held here is the paging contract a client actually depends on: that `next` reaches the
second page and `previous` returns to the first, that `self` names the page it answers with, that
`_count` is honoured up to the project's limit and clamped rather than refused above it, that the
cursor crosses from one tracked entity type to the next without a client knowing there is a
boundary, and that a total is stated only when DHIS2 stated one for the whole searchset.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import FhirProject, TrackedEntitiesConfig
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.register.index import TrackedEntityIndex
from dhis2w_fhir_serve.register.listing import ListingCursor
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_project import (
    CAPTURE_IDENTIFIER_BASE,
    REGISTRATION_DATE_ATTRIBUTE,
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    REGISTRATION_UNIQUE_ATTRIBUTE,
)

_HOST = "https://dhis2.example"

_BASE_URL = "http://serve.test"

_SYSTEM_INFO = {"version": "2.42.0"}

_TRACKER_URL = f"{_HOST}/api/tracker/trackedEntities"

#: A second tracked entity type, named only by `[serve.tracked_entities]` - the guide publishes one type.
_HOUSEHOLD_TYPE_UID = "TetHouseh01"

_NATIONAL_ID_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/tracked-entity-attribute/{REGISTRATION_UNIQUE_ATTRIBUTE}"
_BIRTH_DATE_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/tracked-entity-attribute/{REGISTRATION_DATE_ATTRIBUTE}"

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""


def _person(tracked_entity_uid: str, tracked_entity_type_uid: str = REGISTRATION_TRACKED_ENTITY_TYPE_UID) -> Any:
    """One tracked entity as the tracker endpoint sends it, carrying nothing a listing does not read."""
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": tracked_entity_type_uid,
        "orgUnit": "DiszpKrYNg8",
        "attributes": [],
        "enrollments": [],
    }


def _tracker_page(*people: Any, page: int = 1, page_size: int = 20, total: int | None = None) -> dict[str, Any]:
    """One page as `totalPages=true` answers it: the array, and the pager stating where it sits."""
    pager: dict[str, Any] = {"page": page, "pageSize": page_size}
    if total is not None:
        pager["total"] = total
        pager["pageCount"] = -(-total // page_size)
    return {"pager": pager, "trackedEntities": list(people)}


@pytest.fixture
def tracked_entities() -> TrackedEntitiesConfig:
    """The `[serve.tracked_entities]` table the app under test was started with; override to change it."""
    return TrackedEntitiesConfig()


@pytest.fixture
def listing_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
async def listing_client(
    capture_project: FhirProject,
    listing_profile: Profile,
    tracked_entities: TrackedEntitiesConfig,
) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over the capture guide, holding a DHIS2 client against the mocked host.

    The compiled store plus a client on `app.state.live_client` is the same stand-in for a live run
    that `test_register.py` builds and argues for: the routes read the guide only through the
    surface and the instance only through `register.wire`, so a live store would cost an IG fetch
    and change nothing under test. `/metadata` is the one thing that stand-in cannot answer for -
    the statement reads `settings.live` - so the declarations are asserted off the builder instead.
    """
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(
            ServeSettings(project_dir=capture_project.project_root, tracked_entities=tracked_entities)
        )
        async with (
            app.router.lifespan_context(app),
            open_client(listing_profile) as dhis2,
        ):
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


def _capability(project: FhirProject, tracked_entities: TrackedEntitiesConfig) -> Any:
    """The statement a live run over this guide publishes under one `[serve.tracked_entities]` table."""
    store = load_compiled_store(project)
    settings = ServeSettings(project_dir=project.project_root, live=True, tracked_entities=tracked_entities)
    return build_server_capability(
        project=project,
        store_summary=store.summary(),
        settings=settings,
        register_surface=RegisterSurface.resolve(TrackedEntityIndex.from_store(project, store), tracked_entities),
        server_version="9.9.9",
    )


def _link(bundle: dict[str, Any], relation: str) -> str | None:
    """One relation's URL out of a Bundle's links, or None when the Bundle offers no such link."""
    return next((link["url"] for link in bundle.get("link", []) if link["relation"] == relation), None)


def _parameters(url: str) -> dict[str, str]:
    """The query one link carries, as a client reading it would."""
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


def _cursor(url: str) -> ListingCursor:
    """The page one link leads to, decoded the way this server encoded it."""
    return ListingCursor.from_token(_parameters(url)["page"])


async def test_the_first_page_is_the_first_people_of_the_first_type(listing_client: httpx.AsyncClient) -> None:
    """A request naming no identifier is the register, one page of it, in DHIS2's own order."""
    route = respx.get(_TRACKER_URL).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), _person("PerBbb00002"), total=2))
    )

    body = (await listing_client.get("/Patient")).json()

    assert body["type"] == "searchset"
    assert [entry["resource"]["id"] for entry in body["entry"]] == ["PerAaa00001", "PerBbb00002"]
    assert [entry["search"]["mode"] for entry in body["entry"]] == ["match", "match"]
    parameters = route.calls[0].request.url.params
    assert parameters["trackedEntityType"] == REGISTRATION_TRACKED_ENTITY_TYPE_UID
    assert parameters["ouMode"] == "ACCESSIBLE"
    assert parameters["page"] == "1"
    assert parameters["pageSize"] == "20"
    assert parameters["totalPages"] == "true"
    assert "filter" not in parameters


async def test_the_second_page_is_reached_by_following_the_next_link(listing_client: httpx.AsyncClient) -> None:
    """The two-page walk: `next` leads to page two, whose `previous` leads back to page one."""
    respx.get(_TRACKER_URL, params__contains={"page": "1"}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=1, total=2))
    )
    respx.get(_TRACKER_URL, params__contains={"page": "2"}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerBbb00002"), page=2, page_size=1, total=2))
    )

    first = (await listing_client.get("/Patient?_count=1")).json()
    second = (await listing_client.get(_link(first, "next") or "")).json()
    back = (await listing_client.get(_link(second, "previous") or "")).json()

    assert [entry["resource"]["id"] for entry in first["entry"]] == ["PerAaa00001"]
    assert [entry["resource"]["id"] for entry in second["entry"]] == ["PerBbb00002"]
    assert [entry["resource"]["id"] for entry in back["entry"]] == ["PerAaa00001"]
    assert _link(first, "previous") is None
    assert _link(second, "next") is None
    assert _cursor(_link(first, "self") or "") == ListingCursor(type_index=0, upstream_page=1)
    assert _cursor(_link(second, "self") or "") == ListingCursor(type_index=0, upstream_page=2)


async def test_every_link_names_the_page_and_the_count_it_leads_to(listing_client: httpx.AsyncClient) -> None:
    """A link a client follows carries the whole query, so following it twice answers the same page."""
    respx.get(_TRACKER_URL).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=1, total=3))
    )

    body = (await listing_client.get("/Patient?_count=1")).json()

    assert _parameters(_link(body, "self") or "") == {"_count": "1", "page": ListingCursor().token()}
    assert _parameters(_link(body, "next") or "") == {
        "_count": "1",
        "page": ListingCursor(upstream_page=2).token(),
    }
    assert (_link(body, "self") or "").startswith(f"{_BASE_URL}/Patient?")


async def test_a_count_above_the_projects_limit_is_served_the_limit(listing_client: httpx.AsyncClient) -> None:
    """R4 lets a server answer with fewer than were asked for, so an over-large `_count` is clamped."""
    route = respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(total=0)))

    body = (await listing_client.get("/Patient?_count=5000")).json()

    assert route.calls[0].request.url.params["pageSize"] == "100"
    assert _parameters(_link(body, "self") or "")["_count"] == "100"


async def test_a_count_that_is_not_a_number_of_people_is_refused(listing_client: httpx.AsyncClient) -> None:
    """An ambitious `_count` is served what it can have; a malformed one is a malformed query."""
    respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(total=0)))

    words = await listing_client.get("/Patient?_count=lots")
    negative = await listing_client.get("/Patient?_count=-1")

    assert words.status_code == 400
    assert words.json()["issue"][0]["code"] == "invalid"
    assert negative.status_code == 400
    assert negative.json()["issue"][0]["code"] == "invalid"


async def test_a_count_of_zero_answers_how_large_the_register_is(listing_client: httpx.AsyncClient) -> None:
    """`_count=0` asks how many people the instance holds, and is answered with that and nobody."""
    counted = respx.get(_TRACKER_URL).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=1, total=137))
    )

    response = await listing_client.get("/Patient?_count=0")
    body = response.json()

    assert response.status_code == 200
    assert body["type"] == "searchset"
    assert body["total"] == 137
    assert "entry" not in body
    assert _parameters(_link(body, "self") or "") == {"_count": "0"}
    assert _link(body, "next") is None
    assert counted.calls[0].request.url.params["pageSize"] == "1"


async def test_a_listing_parameter_this_server_cannot_answer_is_refused(listing_client: httpx.AsyncClient) -> None:
    """The listing takes `_count` and `page` and nothing else - a filter it cannot apply is refused."""
    tracker = respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(total=0)))

    response = await listing_client.get("/Patient?family=Smith&_count=5")

    assert response.status_code == 400
    assert response.json()["issue"][0]["diagnostics"] == (
        "`family` is not a search parameter this server answers `Patient` on: `identifier` is the one it supports"
    )
    assert not tracker.called


async def test_a_bare_listing_is_untouched_by_the_refusal(listing_client: httpx.AsyncClient) -> None:
    """A request naming no parameter at all is the listing, exactly as it was."""
    respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), total=1)))

    response = await listing_client.get("/Patient")

    assert response.status_code == 200
    assert [entry["resource"]["id"] for entry in response.json()["entry"]] == ["PerAaa00001"]


async def test_a_page_token_this_server_did_not_mint_is_refused(listing_client: httpx.AsyncClient) -> None:
    """`page` is a link to follow, not a number to compose, and a hand-written one says so."""
    respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(total=0)))

    response = await listing_client.get("/Patient?page=2")

    assert response.status_code == 400
    assert "next" in response.json()["issue"][0]["diagnostics"]


async def test_the_total_is_the_one_the_instance_stated(listing_client: httpx.AsyncClient) -> None:
    """One type in scope, so the type's total is the searchset's, and the Bundle carries it."""
    respx.get(_TRACKER_URL).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=1, total=643))
    )

    assert (await listing_client.get("/Patient?_count=1")).json()["total"] == 643


@pytest.mark.parametrize(
    "tracked_entities",
    [TrackedEntitiesConfig(tracked_entity_types=[REGISTRATION_TRACKED_ENTITY_TYPE_UID, _HOUSEHOLD_TYPE_UID])],
)
async def test_the_cursor_crosses_from_one_tracked_entity_type_to_the_next(
    listing_client: httpx.AsyncClient,
) -> None:
    """Two types are two pagings walked in the declared order, and a client sees one listing."""
    person = respx.get(_TRACKER_URL, params__contains={"trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=1, total=1))
    )
    household = respx.get(_TRACKER_URL, params__contains={"trackedEntityType": _HOUSEHOLD_TYPE_UID}).mock(
        return_value=httpx.Response(
            200, json=_tracker_page(_person("HouAaa00001", _HOUSEHOLD_TYPE_UID), page=1, page_size=1, total=1)
        )
    )

    first = (await listing_client.get("/Patient?_count=1")).json()
    second = (await listing_client.get(_link(first, "next") or "")).json()
    back = (await listing_client.get(_link(second, "previous") or "")).json()

    assert [entry["resource"]["id"] for entry in first["entry"]] == ["PerAaa00001"]
    assert [entry["resource"]["id"] for entry in second["entry"]] == ["HouAaa00001"]
    assert _cursor(_link(first, "next") or "") == ListingCursor(type_index=1, upstream_page=1, searchset_total=2)
    assert _cursor(_link(second, "previous") or "") == ListingCursor(type_index=0, upstream_page=1, searchset_total=2)
    assert [entry["resource"]["id"] for entry in back["entry"]] == ["PerAaa00001"]
    assert _link(second, "next") is None
    assert person.called
    assert household.called


@pytest.mark.parametrize(
    "tracked_entities",
    [TrackedEntitiesConfig(tracked_entity_types=[REGISTRATION_TRACKED_ENTITY_TYPE_UID, _HOUSEHOLD_TYPE_UID])],
)
async def test_a_searchset_over_several_types_sums_the_total_of_each(listing_client: httpx.AsyncClient) -> None:
    """DHIS2 counts one type at a time, so the searchset's total is asked for once per type and summed."""
    person = respx.get(_TRACKER_URL, params__contains={"trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=1, total=643))
    )
    household = respx.get(_TRACKER_URL, params__contains={"trackedEntityType": _HOUSEHOLD_TYPE_UID}).mock(
        return_value=httpx.Response(
            200, json=_tracker_page(_person("HouAaa00001", _HOUSEHOLD_TYPE_UID), page=1, page_size=1, total=57)
        )
    )

    first = (await listing_client.get("/Patient?_count=1")).json()

    assert first["total"] == 700
    assert person.called
    assert household.called


@pytest.mark.parametrize(
    "tracked_entities",
    [TrackedEntitiesConfig(tracked_entity_types=[REGISTRATION_TRACKED_ENTITY_TYPE_UID, _HOUSEHOLD_TYPE_UID])],
)
async def test_a_deeper_page_reuses_the_total_the_first_page_counted(listing_client: httpx.AsyncClient) -> None:
    """The count is spent once per walk: the page token carries the figure the links hand forward."""
    respx.get(_TRACKER_URL, params__contains={"trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=1, total=1))
    )
    respx.get(_TRACKER_URL, params__contains={"trackedEntityType": _HOUSEHOLD_TYPE_UID}).mock(
        return_value=httpx.Response(
            200, json=_tracker_page(_person("HouAaa00001", _HOUSEHOLD_TYPE_UID), page=1, page_size=1, total=1)
        )
    )

    first = (await listing_client.get("/Patient?_count=1")).json()
    # The system-info handshake, the page itself, then one count-only request per type in scope.
    assert len(respx.calls) == 4
    counted_calls = len(respx.calls)
    second = (await listing_client.get(_link(first, "next") or "")).json()

    assert first["total"] == 2
    assert second["total"] == 2
    # The second page reads its total off the token, so it spends the page and the one request a
    # `previous` link across a type boundary costs - and no count of its own.
    assert len(respx.calls) - counted_calls == 2


@pytest.mark.parametrize(
    "tracked_entities",
    [TrackedEntitiesConfig(tracked_entity_types=[REGISTRATION_TRACKED_ENTITY_TYPE_UID, _HOUSEHOLD_TYPE_UID])],
)
async def test_a_type_the_instance_states_no_total_for_leaves_the_searchset_stating_none(
    listing_client: httpx.AsyncClient,
) -> None:
    """A sum missing one of its terms is not a total, and a partial number would be worse than none."""
    respx.get(_TRACKER_URL, params__contains={"trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=1, total=643))
    )
    respx.get(_TRACKER_URL, params__contains={"trackedEntityType": _HOUSEHOLD_TYPE_UID}).mock(
        return_value=httpx.Response(
            200, json=_tracker_page(_person("HouAaa00001", _HOUSEHOLD_TYPE_UID), page=1, page_size=1, total=None)
        )
    )

    assert "total" not in (await listing_client.get("/Patient?_count=1")).json()


@pytest.mark.parametrize(
    "tracked_entities",
    [TrackedEntitiesConfig(tracked_entity_types=[_HOUSEHOLD_TYPE_UID, REGISTRATION_TRACKED_ENTITY_TYPE_UID])],
)
async def test_a_configured_type_holding_nobody_is_skipped_rather_than_served_empty(
    listing_client: httpx.AsyncClient,
) -> None:
    """A `next` link never lands on an empty page while people remain further down the type list."""
    respx.get(_TRACKER_URL, params__contains={"trackedEntityType": _HOUSEHOLD_TYPE_UID}).mock(
        return_value=httpx.Response(200, json=_tracker_page(page=1, page_size=20, total=0))
    )
    respx.get(_TRACKER_URL, params__contains={"trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), page=1, page_size=20, total=1))
    )

    body = (await listing_client.get("/Patient")).json()

    assert [entry["resource"]["id"] for entry in body["entry"]] == ["PerAaa00001"]
    assert _cursor(_link(body, "self") or "") == ListingCursor(type_index=1, upstream_page=1)
    assert _link(body, "previous") is None


async def test_a_register_holding_nobody_is_an_empty_searchset(listing_client: httpx.AsyncClient) -> None:
    """Nobody in the instance is an empty Bundle, not a 404 - the endpoint exists either way."""
    respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(total=0)))

    response = await listing_client.get("/Patient")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert "entry" not in response.json()


@pytest.mark.parametrize(
    "tracked_entities",
    [TrackedEntitiesConfig(tracked_entity_types=[REGISTRATION_TRACKED_ENTITY_TYPE_UID, _HOUSEHOLD_TYPE_UID])],
)
async def test_an_explicit_type_list_scopes_the_identifier_search_too(listing_client: httpx.AsyncClient) -> None:
    """The table restricts what this server answers about, and a search answers about no more than it."""
    respx.get(f"{_TRACKER_URL}/NOBODY00001").mock(return_value=httpx.Response(404, json={"status": "ERROR"}))
    search = respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json={"trackedEntities": []}))

    await listing_client.get("/Patient?identifier=NOBODY00001")

    # Four search keys by default - the unique national identifier, laboratory reference and generated
    # programme identifier, plus the searchable date of birth - each asked of each type in scope, since
    # DHIS2 takes one type per query.
    assert [call.request.url.params["trackedEntityType"] for call in search.calls] == [
        REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        _HOUSEHOLD_TYPE_UID,
    ] * 4


@pytest.mark.parametrize("tracked_entities", [TrackedEntitiesConfig(search_attributes=[REGISTRATION_DATE_ATTRIBUTE])])
async def test_named_search_attributes_are_the_identifier_keys_unique_or_not(
    listing_client: httpx.AsyncClient,
) -> None:
    """The operator naming an attribute has said it names a person here, whatever DHIS2 enforces."""
    respx.get(f"{_TRACKER_URL}/1994-03-02").mock(return_value=httpx.Response(404, json={"status": "ERROR"}))
    search = respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json={"trackedEntities": []}))

    named = await listing_client.get(f"/Patient?identifier={_BIRTH_DATE_SYSTEM}|1994-03-02")
    no_longer_a_key = await listing_client.get(f"/Patient?identifier={_NATIONAL_ID_SYSTEM}|SCEN-A-0001")

    assert named.status_code == 200
    assert [call.request.url.params["filter"] for call in search.calls] == [
        f"{REGISTRATION_DATE_ATTRIBUTE}:eq:1994-03-02"
    ]
    # The unique attribute is not in the stated key set, so its system names no key on this surface.
    assert no_longer_a_key.json()["total"] == 0


@pytest.mark.parametrize("tracked_entities", [TrackedEntitiesConfig(listing=False)])
async def test_listing_off_refuses_the_bare_search_and_leaves_identifier_search_alone(
    listing_client: httpx.AsyncClient,
) -> None:
    """The one request `listing = false` refuses is the one that means everybody."""
    respx.get(f"{_TRACKER_URL}/NOBODY00001").mock(return_value=httpx.Response(404, json={"status": "ERROR"}))
    respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json={"trackedEntities": []}))

    listing = await listing_client.get("/Patient")
    search = await listing_client.get("/Patient?identifier=NOBODY00001")

    assert listing.status_code == 404
    assert listing.json()["issue"][0]["code"] == "not-supported"
    assert listing.json()["issue"][0]["diagnostics"] == (
        "this facade serves no `Patient` listing; name an `identifier` to search for one, or set "
        "`[serve.tracked_entities] listing = true` in fhir.toml and serve again"
    )
    assert search.status_code == 200


@pytest.mark.parametrize("tracked_entities", [TrackedEntitiesConfig(enabled=False)])
async def test_the_surface_switched_off_refuses_every_route_it_covers(
    listing_client: httpx.AsyncClient,
) -> None:
    """`enabled = false` is the whole register, the enrollment listing beside the FHIR routes."""
    tracker = respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json={"trackedEntities": []}))

    responses = [
        await listing_client.get("/Patient"),
        await listing_client.get("/Patient?identifier=PerAaa00001"),
        await listing_client.get("/Patient/PerAaa00001"),
        await listing_client.get("/tracked-entities/PerAaa00001/enrollments"),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404]
    for response, named in zip(responses, ["Patient", "Patient", "Patient", "enrollments"], strict=True):
        assert response.json()["issue"][0]["code"] == "not-supported"
        assert response.json()["issue"][0]["diagnostics"] == (
            f"`{named}` is not served here: this project sets `[serve.tracked_entities] enabled` to false; "
            "set it true in fhir.toml and serve again to search or list the register"
        )
    assert not tracker.called


def test_a_statement_over_a_switched_off_surface_declares_no_patient(capture_project: FhirProject) -> None:
    """`/metadata` states the refusal ahead of the request, as it does for a compiled run."""
    capability = _capability(capture_project, TrackedEntitiesConfig(enabled=False))

    assert "Patient" not in [resource.type for resource in capability.rest[0].resource or []]


def test_a_live_statement_says_the_listing_is_there_to_be_paged(capture_project: FhirProject) -> None:
    """A client reading the statement learns the listing exists and that `page` is the server's to compose."""
    capability = _capability(capture_project, TrackedEntitiesConfig())

    patient = next(resource for resource in capability.rest[0].resource or [] if resource.type == "Patient")
    assert "one page of the register" in (patient.documentation or "")
    assert "`page` parameter" in (patient.documentation or "")


def test_a_live_statement_states_how_several_identifiers_combine(capture_project: FhirProject) -> None:
    """The union semantics are the one thing a client cannot guess, so the entry writes them down."""
    capability = _capability(capture_project, TrackedEntitiesConfig())

    patient = next(resource for resource in capability.rest[0].resource or [] if resource.type == "Patient")
    assert "Several identifiers are alternatives rather than conditions" in (patient.documentation or "")
    assert "deduplicated by tracked entity" in (patient.documentation or "")


def test_a_statement_over_a_search_only_surface_says_so(capture_project: FhirProject) -> None:
    """The declaration follows the config: a project serving no listing does not advertise one."""
    capability = _capability(capture_project, TrackedEntitiesConfig(listing=False))

    patient = next(resource for resource in capability.rest[0].resource or [] if resource.type == "Patient")
    assert "the register by identifier only" in (patient.documentation or "")


def _unknown_type_refusal() -> httpx.Response:
    """The 400 DHIS2 answers a tracked-entity query naming a type the instance does not hold."""
    return httpx.Response(
        400,
        json={
            "httpStatus": "Bad Request",
            "httpStatusCode": 400,
            "status": "ERROR",
            "errorCode": "E1003",
            "message": "Tracked entity type is specified but does not exist: Zz9QqWwEe11",
        },
    )


@pytest.mark.parametrize("tracked_entities", [TrackedEntitiesConfig(tracked_entity_types=["Zz9QqWwEe11"])])
async def test_a_configured_type_the_instance_does_not_hold_lists_nobody(listing_client: httpx.AsyncClient) -> None:
    """A mistyped tracked_entity_types uid is a surface that finds nobody, never a dead one."""
    respx.get(_TRACKER_URL).mock(return_value=_unknown_type_refusal())

    listing = (await listing_client.get("/Patient")).json()
    assert listing["type"] == "searchset"
    assert listing.get("entry", []) == []

    search = await listing_client.get(f"/Patient?identifier={_NATIONAL_ID_SYSTEM}|SCEN-A-0001")
    assert search.status_code == 200
    assert search.json().get("entry", []) == []


@pytest.mark.parametrize(
    "tracked_entities",
    [TrackedEntitiesConfig(tracked_entity_types=[REGISTRATION_TRACKED_ENTITY_TYPE_UID, "Zz9QqWwEe11"])],
)
async def test_a_bad_type_late_in_the_list_does_not_kill_the_walk(listing_client: httpx.AsyncClient) -> None:
    """The listing serves the types the instance holds and skips past the one it does not."""
    respx.get(_TRACKER_URL, params__contains={"trackedEntityType": "Zz9QqWwEe11"}).mock(
        return_value=_unknown_type_refusal()
    )
    respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(_person("PerAaa00001"), total=1)))

    listing = (await listing_client.get("/Patient")).json()
    assert listing["type"] == "searchset"
    assert [entry["resource"]["id"] for entry in listing["entry"]] == ["PerAaa00001"]
