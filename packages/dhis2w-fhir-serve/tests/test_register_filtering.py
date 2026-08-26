"""`d2-attribute={attributeUid}|{value}`: filtering the register by what a record holds.

Mocked (respx), on the same terms as `test_register_listing.py` - the compiled capture fixture is the
guide, and a client against a mocked host on `app.state.live_client` is what makes the routes answer.
The projection half runs against a real SQLite file in a `tmp_path`, filled by hand the way
`test_projection_serving.py` fills one.

Five claims carry the file, and they are the five a filter has to hold to before anybody trusts it.

- **BOTH BACKENDS ANSWER IT AND ANSWER IT THE SAME.** The live one puts `filter=<uid>:eq:<value>` on
  the tracker query; the projection one reads the value index the sync already wrote. A caller
  switching `[serve.search] backend` sees the same people.
- **It composes.** Two filters narrow to who holds both, `_tag` narrows to one type, `identifier`
  narrows to one person, `_count=0` counts the filtered register, and the paging links carry the
  filter forward so a walk stays inside it.
- **EQUALITY IS ALL IT ANSWERS, AND CASE IS ALL IT FORGIVES.** A prefix matches nobody. `female`
  finds the people stored as `Female`, because DHIS2's own `eq` does (BUGS.md 109) and two backends
  called equality must not mean two things.
- **An attribute this register does not filter on is refused, by name.** Empty would read as "nobody
  holds that", which is a different and false statement.
- **The filterable set is declared ahead of the request**, at `/metadata` in prose and at `/uiconfig`
  as values, per register, carrying the attribute's name, its DHIS2 value type, the ValueSet a coded
  one is drawn from, and the tracked entity types that declare it. That last is what a screen
  narrowed to one type of a register reads: the register filters on the union of its types, and a
  type must not be offered an attribute its own forms never ask. Each attribute is declared once,
  keyed by UID, however many forms ask it - two attributes sharing a display name are two filters,
  and the types they are declared by are what tell them apart.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import Profile
from dhis2w_fhir.config import (
    FhirProject,
    ProjectionBackend,
    ProjectionConfig,
    SearchBackend,
    SearchConfig,
    TrackedEntitiesConfig,
)
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capability import build_server_capability
from dhis2w_fhir_serve.projection.base import (
    IndexedName,
    ProjectedResource,
    ProjectionBatch,
    ProjectionCursor,
    ProjectionEndpoint,
)
from dhis2w_fhir_serve.projection.sqlite_store import SqliteProjectionStore
from dhis2w_fhir_serve.register.index import PublishedTrackedEntityType, TrackedEntityIndex
from dhis2w_fhir_serve.register.surface import RegisterSurface
from dhis2w_fhir_serve.routes.uiconfig import tracked_entities_config
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_project import (
    CAPTURE_IDENTIFIER_BASE,
    REGISTRATION_CODED_ATTRIBUTE,
    REGISTRATION_DATE_ATTRIBUTE,
    REGISTRATION_TRACKED_ENTITY_TYPE_UID,
    REGISTRATION_UNIQUE_ATTRIBUTE,
    SEX_VALUE_SET,
    SPECIMEN_RESOURCE_TYPE,
    SPECIMEN_TRACKED_ENTITY_TYPE_UID,
    SPECIMEN_UNIQUE_ATTRIBUTE,
)

_HOST = "https://dhis2.example"
_BASE_URL = "http://serve.test"
_SYSTEM_INFO = {"version": "2.42.0"}
_TRACKER_URL = f"{_HOST}/api/tracker/trackedEntities"

_TRACKED_ENTITY_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity"
_NATIONAL_ID_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/tracked-entity-attribute/{REGISTRATION_UNIQUE_ATTRIBUTE}"
_TYPE_SYSTEM = f"{CAPTURE_IDENTIFIER_BASE}/id/tracked-entity-type"

#: A register of two types, written by hand rather than compiled: the arrangement a live instance
#: has where the fixture guide does not. Both types are published as `Patient`, one attribute is
#: collected by both of them, and each type collects one the other never asks - which is the shape
#: a per-type filter list has to be read off.
_PERSON_TYPE_UID = "TetPerson01"
_FOCUS_AREA_TYPE_UID = "TetFocusA01"
_FIRST_NAME_ATTRIBUTE = "TeaFirstNm1"
_VILLAGE_ATTRIBUTE = "TeaVillage1"
_AREA_CODE_ATTRIBUTE = "TeaAreaCod1"

#: Two people the fixture's instance holds: one woman born in 1990, one man born on the same day.
_WOMAN_UID = "PerAaa00001"
_MAN_UID = "PerBbb00002"
_BIRTH_DATE = "1990-04-02"

_AS_OF = datetime(2026, 8, 21, 9, 0, 0)

_PROFILES_TOML = """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "basic"
username = "admin"
password = "district"
"""


def _attribute(attribute_uid: str, value: str) -> dict[str, Any]:
    """One attribute value as the tracker endpoint sends it."""
    return {"attribute": attribute_uid, "value": value, "valueType": "TEXT"}


def _person(tracked_entity_uid: str, *, sex: str, national_id: str) -> dict[str, Any]:
    """One tracked entity as the instance answers a read of it - a sex, a birth date, and a key."""
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        "orgUnit": "DiszpKrYNg8",
        "attributes": [
            _attribute(REGISTRATION_CODED_ATTRIBUTE, sex),
            _attribute(REGISTRATION_DATE_ATTRIBUTE, _BIRTH_DATE),
            _attribute(REGISTRATION_UNIQUE_ATTRIBUTE, national_id),
        ],
        "enrollments": [],
    }


_WOMAN = _person(_WOMAN_UID, sex="Female", national_id="SCEN-A-0001")
_MAN = _person(_MAN_UID, sex="Male", national_id="SCEN-B-0002")


def _tracker_page(*people: Any, page: int = 1, page_size: int = 20, total: int | None = None) -> dict[str, Any]:
    """One page as `totalPages=true` answers it: the array, and the pager stating where it sits."""
    pager: dict[str, Any] = {"page": page, "pageSize": page_size}
    if total is not None:
        pager["total"] = total
        pager["pageCount"] = -(-total // page_size) if page_size else 0
    return {"pager": pager, "trackedEntities": list(people)}


def _projected(person: dict[str, Any]) -> ProjectedResource:
    """One row as a sync wrote it: the registered resource, carrying the identifiers it always does."""
    tracked_entity_uid = str(person["trackedEntity"])
    national_id = next(
        value["value"] for value in person["attributes"] if value["attribute"] == REGISTRATION_UNIQUE_ATTRIBUTE
    )
    return ProjectedResource(
        resource_type="Patient",
        resource_id=tracked_entity_uid,
        cursor=ProjectionCursor(updated_at=_AS_OF),
        tracked_entity_type_uid=REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        body={
            "resourceType": "Patient",
            "id": tracked_entity_uid,
            "identifier": [
                {"system": _TRACKED_ENTITY_SYSTEM, "value": tracked_entity_uid},
                {"system": _NATIONAL_ID_SYSTEM, "value": national_id},
            ],
        },
    )


def _indexed(person: dict[str, Any]) -> tuple[IndexedName, ...]:
    """Every attribute value of one person as the sync indexes them - the whole of what it holds."""
    return tuple(
        IndexedName(
            tracked_entity_uid=str(person["trackedEntity"]),
            attribute_uid=str(value["attribute"]),
            value=str(value["value"]),
            tracked_entity_type_uid=REGISTRATION_TRACKED_ENTITY_TYPE_UID,
        )
        for value in person["attributes"]
    )


def _read_route(person: dict[str, Any]) -> respx.Route:
    """Mock the one-entity read a projection-served answer resolves each match through."""
    return respx.get(f"{_TRACKER_URL}/{person['trackedEntity']}").mock(return_value=httpx.Response(200, json=person))


def _filters(request: httpx.Request) -> list[str]:
    """Every `filter=` expression one tracker request carried, in the order it carried them."""
    return parse_qs(urlsplit(str(request.url)).query).get("filter", [])


def _link(bundle: dict[str, Any], relation: str) -> str | None:
    """One relation's URL out of a Bundle's links, or None when the Bundle offers no such link."""
    return next((link["url"] for link in bundle.get("link", []) if link["relation"] == relation), None)


def _ids(bundle: dict[str, Any]) -> list[str]:
    """The resources one searchset matched, dropping the `outcome` entry a projection states."""
    return [
        entry["resource"]["id"] for entry in bundle.get("entry", []) if entry.get("search", {}).get("mode") == "match"
    ]


@pytest.fixture
def probe_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Profile:
    """A Basic profile against the mocked host, resolvable from a config home of this test's own."""
    config_directory = tmp_path / ".config" / "dhis2"
    config_directory.mkdir(parents=True)
    (config_directory / "profiles.toml").write_text(_PROFILES_TOML, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_directory.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    return Profile(base_url=_HOST, auth="basic", username="admin", password="district")


@pytest.fixture
async def live_facade(capture_project: FhirProject, probe_profile: Profile) -> AsyncIterator[httpx.AsyncClient]:
    """The facade over the capture guide with the default `[serve.search] backend = "dhis2"`."""
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(ServeSettings(project_dir=capture_project.project_root))
        async with app.router.lifespan_context(app), open_client(probe_profile) as dhis2:
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http


@pytest.fixture
async def synced_facade(capture_project: FhirProject, probe_profile: Profile) -> AsyncIterator[httpx.AsyncClient]:
    """The same facade under `backend = "projection"`, over a projection holding both people."""
    projection = ProjectionConfig(store=ProjectionBackend.SQLITE, path=".serve/projection.sqlite")
    store = SqliteProjectionStore(capture_project.project_root / projection.path)
    await store.write(
        ProjectionBatch(
            resources=(_projected(_WOMAN), _projected(_MAN)),
            names=(*_indexed(_WOMAN), *_indexed(_MAN)),
        )
    )
    for endpoint in (ProjectionEndpoint.TRACKED_ENTITIES, ProjectionEndpoint.ENROLLMENTS):
        await store.write(ProjectionBatch(endpoint=endpoint, cursor=ProjectionCursor(updated_at=_AS_OF)))
    with respx.mock:
        respx.get(f"{_HOST}/api/system/info").mock(return_value=httpx.Response(200, json=_SYSTEM_INFO))
        app: FastAPI = create_app(
            ServeSettings(
                project_dir=capture_project.project_root,
                search=SearchConfig(backend=SearchBackend.PROJECTION),
                projection=projection,
            )
        )
        async with app.router.lifespan_context(app), open_client(probe_profile) as dhis2:
            app.state.live_client = dhis2
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=_BASE_URL) as http:
                yield http
    await store.close()


async def test_the_live_register_narrows_to_who_holds_the_value(live_facade: httpx.AsyncClient) -> None:
    """One filter, one tracker query: the whole register asked for the people holding one value."""
    filtered = respx.get(_TRACKER_URL, params__contains={"filter": f"{REGISTRATION_CODED_ATTRIBUTE}:eq:Female"}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_WOMAN, total=1))
    )
    unfiltered = respx.get(_TRACKER_URL).mock(
        return_value=httpx.Response(200, json=_tracker_page(_WOMAN, _MAN, total=2))
    )

    everybody = (await live_facade.get("/Patient")).json()
    women = (await live_facade.get(f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female")).json()

    assert _ids(everybody) == [_WOMAN_UID, _MAN_UID]
    assert everybody["total"] == 2
    assert _ids(women) == [_WOMAN_UID]
    assert women["total"] == 1, "the total is the filtered register, because DHIS2 counted the filtered query"
    assert unfiltered.called and filtered.called


async def test_the_projection_narrows_to_who_holds_the_value(synced_facade: httpx.AsyncClient) -> None:
    """The same question of the store: the value index the sync wrote answers it, one query."""
    _read_route(_WOMAN)
    _read_route(_MAN)
    collection = respx.get(_TRACKER_URL)

    everybody = (await synced_facade.get("/Patient")).json()
    women = (await synced_facade.get(f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female")).json()

    assert _ids(everybody) == [_WOMAN_UID, _MAN_UID]
    assert _ids(women) == [_WOMAN_UID]
    assert not collection.calls, "the membership came from the projection, so no tracker search went out"


async def test_two_filters_are_the_people_holding_both(live_facade: httpx.AsyncClient) -> None:
    """Occurrences narrow: both expressions ride one tracker query, which is where they are ANDed."""
    route = respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(_WOMAN, total=1)))

    answered = await live_facade.get(
        f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female"
        f"&d2-attribute={REGISTRATION_DATE_ATTRIBUTE}|{_BIRTH_DATE}"
    )

    assert _ids(answered.json()) == [_WOMAN_UID]
    assert _filters(route.calls[0].request) == [
        f"{REGISTRATION_CODED_ATTRIBUTE}:eq:Female",
        f"{REGISTRATION_DATE_ATTRIBUTE}:eq:{_BIRTH_DATE}",
    ]


async def test_two_filters_narrow_the_projection_to_who_holds_both(synced_facade: httpx.AsyncClient) -> None:
    """The same narrowing in the store: a person holding one value and not the other is not a match."""
    _read_route(_WOMAN)
    _read_route(_MAN)

    both = await synced_facade.get(
        f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female"
        f"&d2-attribute={REGISTRATION_DATE_ATTRIBUTE}|{_BIRTH_DATE}"
    )
    contradictory = await synced_facade.get(
        f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female&d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Male"
    )

    assert _ids(both.json()) == [_WOMAN_UID]
    assert _ids(contradictory.json()) == [], "nobody is both, because two occurrences narrow rather than widen"


async def test_the_filter_composes_with_a_type_and_an_identifier(synced_facade: httpx.AsyncClient) -> None:
    """`_tag` chooses the type, `identifier` chooses the person, and the filter still has to hold."""
    _read_route(_WOMAN)
    _read_route(_MAN)
    national_id = f"{_NATIONAL_ID_SYSTEM}|SCEN-A-0001"

    tagged = await synced_facade.get(
        f"/Patient?_tag={_TYPE_SYSTEM}|{REGISTRATION_TRACKED_ENTITY_TYPE_UID}"
        f"&d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female"
    )
    named = await synced_facade.get(
        f"/Patient?identifier={national_id}&d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female"
    )
    contradicted = await synced_facade.get(
        f"/Patient?identifier={national_id}&d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Male"
    )

    assert _ids(tagged.json()) == [_WOMAN_UID]
    assert _ids(named.json()) == [_WOMAN_UID]
    assert _ids(contradicted.json()) == [], "the woman is named by the identifier and excluded by the filter"


async def test_a_live_identifier_search_still_answers_the_filter(live_facade: httpx.AsyncClient) -> None:
    """Live, the filter is read off the record the search already carried back rather than asked again."""
    respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(_WOMAN)))
    _read_route(_WOMAN)
    national_id = f"{_NATIONAL_ID_SYSTEM}|SCEN-A-0001"

    held = await live_facade.get(
        f"/Patient?identifier={national_id}&d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female"
    )
    missed = await live_facade.get(
        f"/Patient?identifier={national_id}&d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Male"
    )

    assert _ids(held.json()) == [_WOMAN_UID]
    assert _ids(missed.json()) == []


async def test_the_filter_rides_the_paging_links_and_the_count(live_facade: httpx.AsyncClient) -> None:
    """A walk stays inside the filter it started in, and `_count=0` counts the filtered register."""
    counted = respx.get(_TRACKER_URL, params__contains={"fields": "trackedEntity"}).mock(
        return_value=httpx.Response(200, json=_tracker_page(page=1, page_size=1, total=2))
    )
    respx.get(_TRACKER_URL, params__contains={"page": "2"}).mock(
        return_value=httpx.Response(200, json=_tracker_page(_MAN, page=2, page_size=1, total=2))
    )
    respx.get(_TRACKER_URL).mock(
        return_value=httpx.Response(200, json=_tracker_page(_WOMAN, page=1, page_size=1, total=2))
    )
    filtered = f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female&_count=1"

    first = (await live_facade.get(filtered)).json()
    following = _link(first, "next") or ""
    size = (await live_facade.get(f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female&_count=0")).json()

    assert f"d2-attribute={REGISTRATION_CODED_ATTRIBUTE}%7CFemale" in (_link(first, "self") or "")
    assert f"d2-attribute={REGISTRATION_CODED_ATTRIBUTE}%7CFemale" in following
    assert size["total"] == 2
    assert _filters(counted.calls[-1].request) == [f"{REGISTRATION_CODED_ATTRIBUTE}:eq:Female"]


async def test_the_filter_matches_a_whole_value_and_forgives_only_its_case(
    synced_facade: httpx.AsyncClient,
) -> None:
    """Equality is all it answers - a prefix finds nobody - and case is all it forgives (BUGS.md 109)."""
    _read_route(_WOMAN)
    _read_route(_MAN)

    prefix = await synced_facade.get(f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Fem")
    lowercase = await synced_facade.get(f"/Patient?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|female")

    assert _ids(prefix.json()) == [], "a filter that answered a prefix would be a search wearing equality's name"
    assert _ids(lowercase.json()) == [_WOMAN_UID]


async def test_an_attribute_this_register_does_not_filter_on_is_refused_by_name(
    live_facade: httpx.AsyncClient,
) -> None:
    """The refusal names the declared set, because an empty searchset would read as "nobody holds it"."""
    tracker = respx.get(_TRACKER_URL)

    response = await live_facade.get(f"/Patient?d2-attribute={SPECIMEN_UNIQUE_ATTRIBUTE}|LAB-1")
    diagnostics = response.json()["issue"][0]["diagnostics"]

    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "invalid"
    assert SPECIMEN_UNIQUE_ATTRIBUTE in diagnostics
    assert REGISTRATION_CODED_ATTRIBUTE in diagnostics
    assert not tracker.called, "an unanswerable question is refused before the instance is asked anything"


async def test_a_filter_naming_no_attribute_is_refused(live_facade: httpx.AsyncClient) -> None:
    """A bare value names no attribute, and looking for it everywhere would match the wrong thing."""
    response = await live_facade.get("/Patient?d2-attribute=Female")

    assert response.status_code == 400
    assert "matches that value exactly" in response.json()["issue"][0]["diagnostics"]


async def test_each_register_filters_on_its_own_types_attributes(live_facade: httpx.AsyncClient) -> None:
    """A sample is filtered by what a sample's form asks, and a person's attribute is refused there."""
    respx.get(_TRACKER_URL).mock(return_value=httpx.Response(200, json=_tracker_page(total=0)))

    sample = await live_facade.get(f"/Specimen?d2-attribute={SPECIMEN_UNIQUE_ATTRIBUTE}|LAB-1")
    person = await live_facade.get(f"/Specimen?d2-attribute={REGISTRATION_CODED_ATTRIBUTE}|Female")

    assert sample.status_code == 200
    assert person.status_code == 400
    assert REGISTRATION_CODED_ATTRIBUTE in person.json()["issue"][0]["diagnostics"]


def test_the_uiconfig_declares_what_each_register_filters_on(capture_project: FhirProject) -> None:
    """A screen drawing the control reads the attributes as values - the uid, the name, the type, the vocabulary.

    Read through `tracked_entities_config`, which is the whole of what `GET /uiconfig` answers with
    for the register; `test_ui_config_endpoint.py` holds the endpoint and the rest of the document.
    """
    index = TrackedEntityIndex.from_store(capture_project, load_compiled_store(capture_project))
    surface = RegisterSurface.resolve(index, TrackedEntitiesConfig())

    served = tracked_entities_config(live=True, surface=surface).model_dump(mode="json")
    registers = served["registers"]
    people = next(register for register in registers if register["resource"] == "Patient")
    samples = next(register for register in registers if register["resource"] == SPECIMEN_RESOURCE_TYPE)
    sex = next(
        attribute for attribute in people["filter_attributes"] if attribute["uid"] == REGISTRATION_CODED_ATTRIBUTE
    )

    assert sex == {
        "uid": REGISTRATION_CODED_ATTRIBUTE,
        "name": "Sex",
        "value_type": "TEXT",
        "value_set": SEX_VALUE_SET,
        "types": [REGISTRATION_TRACKED_ENTITY_TYPE_UID],
    }
    assert [attribute["uid"] for attribute in samples["filter_attributes"]] == [SPECIMEN_UNIQUE_ATTRIBUTE]
    assert [attribute["types"] for attribute in samples["filter_attributes"]] == [[SPECIMEN_TRACKED_ENTITY_TYPE_UID]], (
        "an attribute one type declares names that type and no other"
    )
    assert REGISTRATION_CODED_ATTRIBUTE not in [attribute["uid"] for attribute in samples["filter_attributes"]], (
        "a register of samples declares no filter over a person's attributes"
    )


def test_the_uiconfig_states_which_types_declare_each_filterable_attribute() -> None:
    """A register over two types names, per attribute, the types whose forms ask it - and no others.

    The arrangement is the ordinary one a live instance has and the compiled fixture does not: two
    tracked entity types published as one resource, each collecting attributes the other does not. A
    reader narrowed to the focus area must be offered the focus area's own attributes, so an
    attribute one type declares names that type alone and a shared one names both, in the order the
    types ride the register.
    """
    index = TrackedEntityIndex(
        tracked_entity_system=_TRACKED_ENTITY_SYSTEM,
        tracked_entity_type_system=_TYPE_SYSTEM,
        attribute_value_extension_url=f"{CAPTURE_IDENTIFIER_BASE}/StructureDefinition/d2-tea-value",
        identifier_system_base=CAPTURE_IDENTIFIER_BASE,
        tracked_entity_types=(
            PublishedTrackedEntityType(uid=_PERSON_TYPE_UID, name="Person"),
            PublishedTrackedEntityType(uid=_FOCUS_AREA_TYPE_UID, name="Focus area"),
        ),
        tracked_entity_type_attribute_uids={
            _PERSON_TYPE_UID: (_FIRST_NAME_ATTRIBUTE, _VILLAGE_ATTRIBUTE),
            _FOCUS_AREA_TYPE_UID: (_VILLAGE_ATTRIBUTE, _AREA_CODE_ATTRIBUTE),
        },
    )

    served = tracked_entities_config(live=True, surface=RegisterSurface.resolve(index, TrackedEntitiesConfig()))
    register = next(entry for entry in served.registers if entry.resource == "Patient")

    assert {attribute.uid: attribute.types for attribute in register.filter_attributes} == {
        _FIRST_NAME_ATTRIBUTE: [_PERSON_TYPE_UID],
        _VILLAGE_ATTRIBUTE: [_PERSON_TYPE_UID, _FOCUS_AREA_TYPE_UID],
        _AREA_CODE_ATTRIBUTE: [_FOCUS_AREA_TYPE_UID],
    }
    assert [attribute.uid for attribute in register.filter_attributes] == [
        _FIRST_NAME_ATTRIBUTE,
        _VILLAGE_ATTRIBUTE,
        _AREA_CODE_ATTRIBUTE,
    ], "the attribute both types collect is one filter, in the place the first type asked it"


def test_an_attribute_two_registration_forms_ask_is_declared_once(capture_project: FhirProject) -> None:
    """A type registered by a program's form and by its own is one register: each attribute is one filter.

    The fixture's person type is registered twice - the antenatal programme's registration form and
    the type's own - and three attributes are asked by both. A register concatenating the two
    declarations would offer a reader `National identifier` twice, so the assembly keys the union by
    the DHIS2 attribute UID and keeps the place the first declaration put it.

    A name is not a key here: two distinct attributes may be published under one display, and
    collapsing them would drop a filter the instance genuinely holds. UID is what is deduplicated,
    and the types each attribute is declared by are what tell the look-alikes apart.
    """
    index = TrackedEntityIndex.from_store(capture_project, load_compiled_store(capture_project))
    surface = RegisterSurface.resolve(index, TrackedEntitiesConfig())

    served = tracked_entities_config(live=True, surface=surface)
    register = next(entry for entry in served.registers if entry.resource == "Patient")
    declared = [attribute.uid for attribute in register.filter_attributes]

    assert declared == list(dict.fromkeys(declared)), "an attribute two forms ask is declared once"
    assert declared.count(REGISTRATION_UNIQUE_ATTRIBUTE) == 1
    assert [attribute.types for attribute in register.filter_attributes] == [
        [REGISTRATION_TRACKED_ENTITY_TYPE_UID] for _ in declared
    ], "one type registers this resource, so every attribute of it names that type once"


def _capability(project: FhirProject) -> Any:
    """The statement a live run over this guide publishes, which is where the filter is declared."""
    store = load_compiled_store(project)
    tracked_entities = TrackedEntitiesConfig()
    return build_server_capability(
        project=project,
        store_summary=store.summary(),
        settings=ServeSettings(project_dir=project.project_root, live=True, tracked_entities=tracked_entities),
        register_surface=RegisterSurface.resolve(TrackedEntityIndex.from_store(project, store), tracked_entities),
        server_version="9.9.9",
    )


def test_the_metadata_declares_the_filter_and_says_it_answers_equality_alone(
    capture_project: FhirProject,
) -> None:
    """The searchParam names the attributes in prose and leads with what the filter will not do."""
    capability = _capability(capture_project)

    patient = next(resource for resource in capability.rest[0].resource or [] if resource.type == "Patient")
    declared = next(parameter for parameter in patient.searchParam or [] if parameter.name == "d2-attribute")
    documentation = declared.documentation or ""

    assert declared.type == "token"
    assert "It matches that value exactly - equality and nothing else" in documentation
    assert "case is ignored" in documentation
    # The grammar is stated and the catalog is pointed at, not enumerated: fifty attributes spelled
    # into one sentence buried the rules, and each registration Questionnaire already declares them
    # item by item. The count is the one catalog fact the sentence keeps.
    assert "registration forms declare" in documentation
    assert "linkId" in documentation
    assert REGISTRATION_CODED_ATTRIBUTE not in documentation, "the catalog lives in the Questionnaires, not here"
    assert SPECIMEN_UNIQUE_ATTRIBUTE not in documentation
