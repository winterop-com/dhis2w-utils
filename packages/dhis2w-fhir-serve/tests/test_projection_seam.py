"""The two projection Protocols, and the `dhis2` backend that crosses one of them.

Mocked (respx); no live stack, and no application - the index is a value, so it is tested as one.

What is asserted here is the seam rather than a feature, because step 1 of
`docs/fhir/design/projection.md` improves nothing on purpose. Three claims carry it. The backend
satisfies the Protocol at runtime, so the register can hold any implementation of it. `find` puts
exactly the query section 2 of that paper measured on the wire - `filter=<attribute>:eq:<value>`,
`ouMode=ACCESSIBLE`, one query per key per tracked entity type - so this backend is exactly as weak
as an exact match is, and its weakness is characterized rather than assumed. And a match carries a
tracked entity UID and a score and nothing else, which is what makes R9's authorization-by-
construction a property of the shape rather than a promise: there is no field on `NameMatch` for a
name, an attribute value, or an organisation unit to travel in.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from dhis2w_fhir.config import SearchBackend
from dhis2w_fhir_serve.projection.base import (
    IndexedName,
    NameMatch,
    NameQuery,
    NameSearchIndex,
    ProjectedResource,
    ProjectionBatch,
    ProjectionCursor,
    ProjectionPage,
    ProjectionQuery,
    ProjectionStore,
)
from dhis2w_fhir_serve.projection.dhis2_names import Dhis2NameSearchIndex
from dhis2w_fhir_serve.projection.factory import build_name_search_index
from pydantic import BaseModel, ConfigDict

_HOST = "https://dhis2.example"
_TRACKER_PATH = f"{_HOST}/api/tracker/trackedEntities"

_PERSON_UID = "PLoWmEuLJl2"
_OTHER_PERSON_UID = "QaTbMxTeS01"
_TYPE_UID = "TetPerson01"
_OTHER_TYPE_UID = "TetSample01"
_NATIONAL_ID_ATTRIBUTE = "TeaNationId"
_BIRTH_DATE_ATTRIBUTE = "TeaBirthDte"
_VALUE = "SCEN-A-0001"


class _Reader(BaseModel):
    """A `RegisterReader` over one respx-mocked host, which is what the register hands a backend."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    connection: httpx.AsyncClient

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read one DHIS2 path, answering the parsed JSON body."""
        answer = await self.connection.get(path, params=params)
        body = answer.json()
        return body if isinstance(body, dict) else {"data": body}


class _Store(BaseModel):
    """The smallest thing that satisfies `ProjectionStore`, holding one cursor and nothing else."""

    model_config = ConfigDict(frozen=True)

    async def read(self, resource_type: str, resource_id: str) -> ProjectedResource | None:
        """Hold no resource, which is what an unfilled projection answers with."""
        return None

    async def search(self, query: ProjectionQuery) -> ProjectionPage:
        """Answer an empty page stating the cursor it was read at."""
        return ProjectionPage(total=0)

    async def write(self, batch: ProjectionBatch) -> ProjectionCursor:
        """Answer the cursor the batch carried, which is the watermark advancing with its rows."""
        return batch.cursor

    async def cursor(self) -> ProjectionCursor:
        """How far this projection has been filled - nowhere, since nothing writes it."""
        return ProjectionCursor()

    async def rebuild(self) -> None:
        """Empty a projection that was never filled."""
        return None


def _entity(tracked_entity_uid: str = _PERSON_UID) -> dict[str, Any]:
    """One tracked entity as the tracker endpoint sends it, carrying more than the index keeps."""
    return {
        "trackedEntity": tracked_entity_uid,
        "trackedEntityType": _TYPE_UID,
        "orgUnit": "DiszpKrYNg8",
        "attributes": [{"attribute": _NATIONAL_ID_ATTRIBUTE, "displayName": "National identifier", "value": _VALUE}],
    }


def _search_route(*entities: dict[str, Any]) -> respx.Route:
    """Mock the tracker search, answering every query with the same page."""
    return respx.get(_TRACKER_PATH).mock(return_value=httpx.Response(200, json={"trackedEntities": list(entities)}))


@pytest.fixture
async def index() -> Dhis2NameSearchIndex:
    """The `dhis2` backend over a reader pointed at the mocked host."""
    return Dhis2NameSearchIndex(reader=_Reader(connection=httpx.AsyncClient(base_url=_HOST)))


def test_the_dhis2_backend_satisfies_the_index_protocol(index: Dhis2NameSearchIndex) -> None:
    """A register search holds a `NameSearchIndex`, so what it holds has to be one at runtime."""
    assert isinstance(index, NameSearchIndex)


def test_a_projection_store_is_a_shape_something_can_satisfy() -> None:
    """The store Protocol ships before its first backend, so what it asks for is checked here."""
    assert isinstance(_Store(), ProjectionStore)


def test_a_match_carries_an_identifier_and_a_score_and_nothing_else() -> None:
    """R9 is a property of this shape: there is no field for a name or a value to travel in."""
    assert set(NameMatch.model_fields) == {"tracked_entity_uid", "display_name", "score"}


async def test_finding_puts_the_exact_match_filter_on_the_wire(index: Dhis2NameSearchIndex) -> None:
    """One query per key per tracked entity type, `:eq:` filtered and scoped as wide as the caller may see."""
    with respx.mock:
        search = _search_route()

        await index.find(
            NameQuery(
                value=_VALUE,
                attribute_uids=(_BIRTH_DATE_ATTRIBUTE, _NATIONAL_ID_ATTRIBUTE),
                tracked_entity_type_uids=(_TYPE_UID, _OTHER_TYPE_UID),
            )
        )

    sent = [call.request.url.params for call in search.calls]
    assert [params["filter"] for params in sent] == [
        f"{_BIRTH_DATE_ATTRIBUTE}:eq:{_VALUE}",
        f"{_BIRTH_DATE_ATTRIBUTE}:eq:{_VALUE}",
        f"{_NATIONAL_ID_ATTRIBUTE}:eq:{_VALUE}",
        f"{_NATIONAL_ID_ATTRIBUTE}:eq:{_VALUE}",
    ]
    assert [params["trackedEntityType"] for params in sent] == [
        _TYPE_UID,
        _OTHER_TYPE_UID,
        _TYPE_UID,
        _OTHER_TYPE_UID,
    ]
    assert all(params["ouMode"] == "ACCESSIBLE" for params in sent)


async def test_finding_answers_identifiers_and_keeps_none_of_what_it_read(index: Dhis2NameSearchIndex) -> None:
    """The instance answers with whole entities and the index keeps their UIDs - the record is not its to hand over."""
    with respx.mock:
        _search_route(_entity(), _entity(_OTHER_PERSON_UID))

        found = await index.find(
            NameQuery(value=_VALUE, attribute_uids=(_NATIONAL_ID_ATTRIBUTE,), tracked_entity_type_uids=(_TYPE_UID,))
        )

    assert [match.tracked_entity_uid for match in found.matches] == [_PERSON_UID, _OTHER_PERSON_UID]
    assert all(match.display_name is None for match in found.matches)
    assert found.cursor is None


async def test_a_person_two_keys_both_match_is_one_candidate(index: Dhis2NameSearchIndex) -> None:
    """A value held under two keys is one person, so the fold is by tracked entity UID, first match first."""
    with respx.mock:
        _search_route(_entity())

        found = await index.find(
            NameQuery(
                value=_VALUE,
                attribute_uids=(_BIRTH_DATE_ATTRIBUTE, _NATIONAL_ID_ATTRIBUTE),
                tracked_entity_type_uids=(_TYPE_UID,),
            )
        )

    assert [match.tracked_entity_uid for match in found.matches] == [_PERSON_UID]


async def test_a_limit_is_honoured_and_no_limit_carries_everybody(index: Dhis2NameSearchIndex) -> None:
    """The register asks for no limit, because a searchset states what was found rather than a page of it."""
    with respx.mock:
        _search_route(_entity(), _entity(_OTHER_PERSON_UID))
        query = NameQuery(value=_VALUE, attribute_uids=(_NATIONAL_ID_ATTRIBUTE,), tracked_entity_type_uids=(_TYPE_UID,))

        everybody = await index.find(query)
        capped = await index.find(query.model_copy(update={"limit": 1}))

    assert len(everybody.matches) == 2
    assert [match.tracked_entity_uid for match in capped.matches] == [_PERSON_UID]


async def test_a_value_nobody_holds_matches_nobody(index: Dhis2NameSearchIndex) -> None:
    """An unmatched lookup is an empty answer, which is what the register turns into an empty searchset."""
    with respx.mock:
        _search_route()

        found = await index.find(
            NameQuery(value=_VALUE, attribute_uids=(_NATIONAL_ID_ATTRIBUTE,), tracked_entity_type_uids=(_TYPE_UID,))
        )

    assert found.matches == ()


async def test_naming_no_key_or_no_type_asks_the_instance_nothing(index: Dhis2NameSearchIndex) -> None:
    """This backend holds no keys of its own, so a query naming none has nothing to filter on."""
    with respx.mock:
        search = _search_route(_entity())

        by_no_key = await index.find(NameQuery(value=_VALUE, tracked_entity_type_uids=(_TYPE_UID,)))
        by_no_type = await index.find(NameQuery(value=_VALUE, attribute_uids=(_NATIONAL_ID_ATTRIBUTE,)))

    assert by_no_key.matches == ()
    assert by_no_type.matches == ()
    assert not search.called


async def test_holding_names_and_forgetting_them_are_the_instance_s_business(index: Dhis2NameSearchIndex) -> None:
    """This backend is the instance, so a sync has nothing to write into it and a tombstone nothing to remove."""
    with respx.mock:
        search = _search_route()

        await index.index(
            [IndexedName(tracked_entity_uid=_PERSON_UID, attribute_uid=_NATIONAL_ID_ATTRIBUTE, value="A")]
        )
        await index.forget([_PERSON_UID])

    assert not search.called


def test_the_dial_names_the_backend_a_search_is_built_over(index: Dhis2NameSearchIndex) -> None:
    """`[serve.search] backend` is read once per lookup, and `dhis2` is the instance itself."""
    built = build_name_search_index(SearchBackend.DHIS2, reader=index.reader)

    assert isinstance(built, Dhis2NameSearchIndex)
