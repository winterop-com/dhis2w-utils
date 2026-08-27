"""`GET /facade/terminology/lookup` and `GET /facade/terminology/validate-code`, against the guide's real vocabularies.

Checked against the golden project rather than against a hand-written CodeSystem, because the whole
claim is about what `d2w fhir generate` actually publishes: a data-dictionary system whose concepts
carry properties, and a value set that includes that system whole and enumerates nothing. The second
of those is the shape almost every value set a DHIS2 IG serves has, and answering it is the
difference between a useful check and one that says false about every code a form binds.
"""

from __future__ import annotations

import httpx
from dhis2w_fhir_serve.store import ResourceStore
from dhis2w_fhir_serve.terminology import LookupValueSet, TerminologyState, load_terminology
from fixture_project import CAPTURE_CANONICAL

DATA_ELEMENT_SYSTEM = f"{CAPTURE_CANONICAL}/CodeSystem/d2-de-cs"
DATA_ELEMENT_VALUE_SET = f"{CAPTURE_CANONICAL}/ValueSet/d2-de-vs"
DATA_ELEMENT_CODE = "DeAncDanger"

#: A set composed in a way this server deliberately does not resolve, built for the test that says so.
NARROWED_VALUE_SET = "http://example.org/fhir/ValueSet/narrowed"


async def test_a_lookup_answers_the_display_and_the_properties(capture_client: httpx.AsyncClient) -> None:
    """What the endpoint is for: a code, said in words, with what the guide states about it."""
    answered = await capture_client.get(
        "/facade/terminology/lookup", params={"system": DATA_ELEMENT_SYSTEM, "code": DATA_ELEMENT_CODE}
    )

    assert answered.status_code == 200
    body = answered.json()
    assert body["found"] is True
    assert body["display"] == "ANC danger signs present"
    stated = {held["code"]: held["value"] for held in body["properties"]}
    assert stated["value-type"] == "BOOLEAN"
    assert stated["domain"] == "tracker"


async def test_a_code_the_guide_does_not_publish_is_a_miss_with_a_reason(
    capture_client: httpx.AsyncClient,
) -> None:
    """200 with `found` false, on `$translate`'s posture: the question was well formed, this is its answer."""
    answered = await capture_client.get(
        "/facade/terminology/lookup", params={"system": DATA_ELEMENT_SYSTEM, "code": "NoSuchCode"}
    )

    assert answered.status_code == 200
    assert answered.json()["found"] is False
    assert "states no concept" in answered.json()["message"]


async def test_a_vocabulary_this_server_does_not_serve_says_so_in_those_words(
    capture_client: httpx.AsyncClient,
) -> None:
    """The honesty this surface exists to keep: it serves one project's codes and says so, never guesses."""
    answered = await capture_client.get(
        "/facade/terminology/lookup", params={"system": "http://snomed.info/sct", "code": "260385009"}
    )

    assert answered.json()["found"] is False
    assert "not a general terminology server" in answered.json()["message"]


async def test_a_code_is_validated_against_a_value_set_that_includes_its_system_whole(
    capture_client: httpx.AsyncClient,
) -> None:
    """The generated shape: an include naming a system and enumerating nothing means every code of it."""
    answered = await capture_client.get(
        "/facade/terminology/validate-code",
        params={"valueset": DATA_ELEMENT_VALUE_SET, "system": DATA_ELEMENT_SYSTEM, "code": DATA_ELEMENT_CODE},
    )

    assert answered.status_code == 200
    assert answered.json()["result"] is True
    assert answered.json()["display"] == "ANC danger signs present"


async def test_a_code_outside_the_included_system_is_false(capture_client: httpx.AsyncClient) -> None:
    """False is an answer too, and carries the reason rather than an empty body."""
    answered = await capture_client.get(
        "/facade/terminology/validate-code",
        params={"valueset": DATA_ELEMENT_VALUE_SET, "system": DATA_ELEMENT_SYSTEM, "code": "NoSuchCode"},
    )

    assert answered.json()["result"] is False
    assert answered.json()["message"] is not None


async def test_a_value_set_this_server_publishes_none_of_is_named(capture_client: httpx.AsyncClient) -> None:
    """A canonical the guide never published is stated as unpublished, not as a code that failed."""
    answered = await capture_client.get(
        "/facade/terminology/validate-code",
        params={"valueset": "http://example.org/fhir/ValueSet/nothing", "code": DATA_ELEMENT_CODE},
    )

    assert answered.json()["result"] is False
    assert "publishes no ValueSet" in answered.json()["message"]


async def test_a_system_alone_asks_the_weaker_question_this_server_can_still_answer(
    capture_client: httpx.AsyncClient,
) -> None:
    """Naming no value set asks whether the guide publishes the code at all, which is a real question."""
    answered = await capture_client.get(
        "/facade/terminology/validate-code", params={"system": DATA_ELEMENT_SYSTEM, "code": DATA_ELEMENT_CODE}
    )

    assert answered.json()["result"] is True
    assert answered.json()["valueset"] is None


async def test_naming_neither_a_system_nor_a_value_set_is_refused(capture_client: httpx.AsyncClient) -> None:
    """A check with nothing to check against would answer false about every code there is, so it is refused."""
    answered = await capture_client.get("/facade/terminology/validate-code", params={"code": DATA_ELEMENT_CODE})

    assert answered.status_code == 400
    assert answered.json()["resourceType"] == "OperationOutcome"


def test_a_composition_this_server_does_not_resolve_says_so_rather_than_answering_false(
    capture_store: ResourceStore,
) -> None:
    """The edge of the one rule: an exclusion is beyond it, and the message says the set was not resolved."""
    state = load_terminology(capture_store)
    narrowed = LookupValueSet.model_validate(
        {
            "resourceType": "ValueSet",
            "url": NARROWED_VALUE_SET,
            "status": "active",
            "compose": {
                "include": [{"system": DATA_ELEMENT_SYSTEM}],
                "exclude": [{"system": DATA_ELEMENT_SYSTEM, "concept": [{"code": DATA_ELEMENT_CODE}]}],
            },
        }
    )
    with_exclusion = TerminologyState(
        service=state.service, code_systems=state.code_systems, value_sets=(*state.value_sets, narrowed)
    )

    answered = with_exclusion.validate_code(DATA_ELEMENT_CODE, valueset=NARROWED_VALUE_SET)

    assert answered.result is False
    assert "does not resolve" in (answered.message or "")


def test_the_vocabularies_load_without_a_server(capture_store: ResourceStore) -> None:
    """A caller with a loaded store asks the same question, which is why the state is a value."""
    state = load_terminology(capture_store)

    assert DATA_ELEMENT_SYSTEM in state.code_system_urls()
    assert DATA_ELEMENT_VALUE_SET in state.value_set_urls()
    assert state.unreadable == ()
