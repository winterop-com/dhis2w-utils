"""`Questionnaire/{id}/$generate`: what the operation answers with, and the round trip that justifies it.

The invariant every other test here supports: **a generated response posted back to this server's own
`/QuestionnaireResponse` answers 201**. It is asserted per served form kind - aggregate, event, and
tracker event - over the compiled goldens, and again over a strict-codes server, because a generated
coding has to be the exact concept code the contract asks for rather than one of the lenient
fall-back spellings.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.period import parse_period
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.capture.naming import GENERATE_SEED_IDENTIFIER_SEGMENT
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.synthesize import DEFAULT_PERIOD_TYPE, MAXIMUM_SEED

#: The canonical the dhis2w-fhir goldens were compiled under, as `capture_project` serves them.
CANONICAL = "http://localhost:8080/fhir"

FORM_TYPE_URL = f"{CANONICAL}/StructureDefinition/d2-form-type"
PERIOD_URL = f"{CANONICAL}/StructureDefinition/d2-period"
TRACKER_ENROLLMENT_URL = f"{CANONICAL}/StructureDefinition/d2-tracker-enrollment"
TRACKED_ENTITY_SYSTEM = "http://dhis2.org/fhir/id/tracked-entity"
SYMPTOM_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-os-OsSymptom01-cs"

#: The served forms, by the DHIS2 form kind each one declares.
AGGREGATE_ID = "BfMAe6Itzgt"
EVENT_ID = "EVTsupVis01"
TRACKER_EVENT_ID = "ZzYYXq4fJie"

AGGREGATE_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/{AGGREGATE_ID}"
EVENT_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/{EVENT_ID}"
TRACKER_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/{TRACKER_EVENT_ID}"

#: The aggregate form whose data set rides a non-default category combo, and the vocabulary it
#: declares - a generated response for it has to name one attribute option combo of that pair.
ATTRIBUTE_COMBO_ID = "TuL8IOPzpHh"
ATTRIBUTE_COMBO_URL = f"{CANONICAL}/StructureDefinition/d2-attribute-option-combo"
ATTRIBUTE_COMBO_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-aoc-idcDPkDtepR-cs"

#: Every form the golden project serves, including the two extra event forms.
EVERY_FORM_ID = (AGGREGATE_ID, EVENT_ID, TRACKER_EVENT_ID, "PsAncVisit1", "PrTemporal1", ATTRIBUTE_COMBO_ID)

FHIR_JSON = {"Content-Type": "application/fhir+json"}


def _generate_path(resource_id: str) -> str:
    """The operation's path for one served form."""
    return f"/Questionnaire/{resource_id}/$generate"


async def _generate(client: httpx.AsyncClient, resource_id: str, **params: str | int) -> httpx.Response:
    """Invoke `$generate` on one served form."""
    return await client.get(_generate_path(resource_id), params=params)


async def _post_back(client: httpx.AsyncClient, generated: httpx.Response) -> httpx.Response:
    """Post a generated response back at the server that generated it, byte for byte."""
    return await client.post("/QuestionnaireResponse", content=generated.content, headers=FHIR_JSON)


def _extensions(response: dict[str, Any], url: str) -> list[dict[str, Any]]:
    """Every extension one generated response carries under a url."""
    return [extension for extension in response.get("extension", []) if extension["url"] == url]


def _answers(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Every answer of one generated response, however deep in the item tree it sits."""
    found: list[dict[str, Any]] = []

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            found.extend(item.get("answer", []))
            walk(item.get("item", []))

    walk(response.get("item", []))
    return found


@pytest.mark.parametrize("resource_id", EVERY_FORM_ID)
async def test_a_generated_response_posts_back_201(capture_client: httpx.AsyncClient, resource_id: str) -> None:
    """The invariant: whatever kind of form it fills, `$generate` output is accepted by this same server."""
    generated = await _generate(capture_client, resource_id, seed=7)
    assert generated.status_code == 200
    assert generated.headers["content-type"].startswith("application/fhir+json")

    posted = await _post_back(capture_client, generated)

    assert posted.status_code == 201
    assert "Location" in posted.headers


@pytest.mark.parametrize("resource_id", EVERY_FORM_ID)
async def test_a_seedless_generated_response_posts_back_201(
    capture_client: httpx.AsyncClient, resource_id: str
) -> None:
    """Naming no seed is not a lesser mode: the server draws one and the response is just as valid."""
    generated = await _generate(capture_client, resource_id)
    assert generated.status_code == 200

    posted = await _post_back(capture_client, generated)

    assert posted.status_code == 201


@pytest.mark.parametrize("strict_codes", [True])
@pytest.mark.parametrize("resource_id", EVERY_FORM_ID)
async def test_a_generated_response_posts_back_201_under_strict_codes(
    capture_client: httpx.AsyncClient, resource_id: str
) -> None:
    """A generated coding is the exact concept code the contract asks for, so strict mode accepts it too."""
    generated = await _generate(capture_client, resource_id, seed=11)

    posted = await _post_back(capture_client, generated)

    assert posted.status_code == 201
    assert not [issue for issue in posted.json()["issue"] if issue["severity"] == "warning"]


async def test_the_same_seed_generates_the_same_response(capture_client: httpx.AsyncClient) -> None:
    """Determinism is the point of the seed: same form, same seed, same bytes."""
    first = await _generate(capture_client, TRACKER_EVENT_ID, seed=1234)
    second = await _generate(capture_client, TRACKER_EVENT_ID, seed=1234)

    assert first.content == second.content


async def test_a_different_seed_generates_a_different_response(capture_client: httpx.AsyncClient) -> None:
    """A seed is a handle on the values, not a formality - changing it changes what comes back."""
    first = await _generate(capture_client, AGGREGATE_ID, seed=1)
    second = await _generate(capture_client, AGGREGATE_ID, seed=2)

    assert _answers(first.json()) != _answers(second.json())


async def test_the_seed_is_stated_on_the_generated_response(capture_client: httpx.AsyncClient) -> None:
    """The seed rides back as the response's business identifier, so it survives the post into the receipt."""
    generated = await _generate(capture_client, EVENT_ID, seed=99)

    identifier = generated.json()["identifier"]

    assert identifier == {"system": f"{CANONICAL}/{GENERATE_SEED_IDENTIFIER_SEGMENT}", "value": "99"}


async def test_a_drawn_seed_is_stated_too_and_reproduces_the_response(capture_client: httpx.AsyncClient) -> None:
    """A seedless call is still reproducible: the drawn seed is stated, and naming it back replays the answer."""
    drawn = await _generate(capture_client, EVENT_ID)
    seed = int(drawn.json()["identifier"]["value"])

    replayed = await _generate(capture_client, EVENT_ID, seed=seed)

    assert 0 <= seed <= MAXIMUM_SEED
    assert replayed.content == drawn.content


async def test_an_aggregate_response_carries_the_period_its_examples_declare(
    capture_client: httpx.AsyncClient,
) -> None:
    """The compiled store holds no example for these goldens, so the documented default is what is used."""
    generated = await _generate(capture_client, AGGREGATE_ID, seed=3)

    period = _extensions(generated.json(), PERIOD_URL)[0]
    declared = {nested["url"]: nested for nested in period["extension"]}

    assert declared["type"]["valueCode"] == DEFAULT_PERIOD_TYPE
    assert parse_period(declared["iso"]["valueString"]).period_type == DEFAULT_PERIOD_TYPE


async def test_an_aggregate_response_follows_the_period_type_a_served_example_declares(
    capture_project: FhirProject,
    write_resource: Callable[[Path, dict[str, Any]], None],
) -> None:
    """A compiled IG ships its example instances, and their D2Period is where the data set's type is read."""
    write_resource(
        capture_project.ig_directory / "fsh-generated" / "resources" / "QuestionnaireResponse-weekly.json",
        {
            "resourceType": "QuestionnaireResponse",
            "id": "BfMAe6Itzgt-example-9",
            "questionnaire": AGGREGATE_QUESTIONNAIRE,
            "status": "completed",
            "extension": [
                {
                    "url": PERIOD_URL,
                    "extension": [
                        {"url": "iso", "valueString": "2026W02"},
                        {"url": "type", "valueCode": "Weekly"},
                    ],
                }
            ],
        },
    )
    app = create_app(ServeSettings(project_dir=capture_project.project_root))

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://serve.test") as client:
            generated = await _generate(client, AGGREGATE_ID, seed=3)
            posted = await _post_back(client, generated)

    period = _extensions(generated.json(), PERIOD_URL)[0]
    declared = {nested["url"]: nested for nested in period["extension"]}

    assert declared["type"]["valueCode"] == "Weekly"
    assert parse_period(declared["iso"]["valueString"]).period_type == "Weekly"
    assert posted.status_code == 201


async def test_an_aggregate_response_reports_for_a_served_location(capture_client: httpx.AsyncClient) -> None:
    """An aggregate response names the organisation unit it reports for as a Location reference."""
    generated = await _generate(capture_client, AGGREGATE_ID, seed=3)
    response = generated.json()

    assert response["questionnaire"] == AGGREGATE_QUESTIONNAIRE
    assert response["status"] == "completed"
    assert response["subject"]["reference"].startswith("Location/")
    assert _extensions(response, FORM_TYPE_URL)[0]["valueCode"] == "aggregate"


async def test_a_generated_response_names_an_attribute_option_combo_its_form_declares(
    capture_client: httpx.AsyncClient,
) -> None:
    """A form declaring a vocabulary generates a response drawing one real concept of it, never an invented one."""
    response = (await _generate(capture_client, ATTRIBUTE_COMBO_ID, seed=3)).json()

    carried = _extensions(response, ATTRIBUTE_COMBO_URL)

    assert len(carried) == 1
    assert carried[0]["valueCoding"]["system"] == ATTRIBUTE_COMBO_CODE_SYSTEM
    assert carried[0]["valueCoding"]["code"] in {"pO5CEqK6c1s", "sSeEjeQ0Rgt", "oawMLLH7OjA", "BqblOcSwGey"}


async def test_a_default_combo_form_generates_no_attribute_option_combo(capture_client: httpx.AsyncClient) -> None:
    """Absence means the default combo, so a form declaring nothing generates nothing to declare."""
    response = (await _generate(capture_client, AGGREGATE_ID, seed=3)).json()

    assert _extensions(response, ATTRIBUTE_COMBO_URL) == []


async def test_an_event_response_records_when_it_was_captured(capture_client: httpx.AsyncClient) -> None:
    """The event contract requires an authored instant, so a generated event response carries one."""
    response = (await _generate(capture_client, EVENT_ID, seed=5)).json()

    assert response["questionnaire"] == EVENT_QUESTIONNAIRE
    assert response["authored"].endswith("Z")
    assert _extensions(response, FORM_TYPE_URL)[0]["valueCode"] == "event"


async def test_a_tracker_event_response_carries_its_synthetic_context(capture_client: httpx.AsyncClient) -> None:
    """A tracker event names a tracked entity and an enrollment: shaped UIDs, which is what the contract checks."""
    response = (await _generate(capture_client, TRACKER_EVENT_ID, seed=5)).json()

    subject = response["subject"]
    enrollment = _extensions(response, TRACKER_ENROLLMENT_URL)[0]["valueIdentifier"]

    assert response["questionnaire"] == TRACKER_QUESTIONNAIRE
    assert subject["identifier"]["system"] == TRACKED_ENTITY_SYSTEM
    assert len(subject["identifier"]["value"]) == 11
    assert len(enrollment["value"]) == 11


async def test_a_generated_response_declares_its_form_kind_profile(capture_client: httpx.AsyncClient) -> None:
    """Every generated response is profile-declared, which is what a validating consumer reads it against."""
    aggregate = (await _generate(capture_client, AGGREGATE_ID, seed=2)).json()
    tracker = (await _generate(capture_client, TRACKER_EVENT_ID, seed=2)).json()

    assert aggregate["meta"]["profile"] == [f"{CANONICAL}/StructureDefinition/d2-aggregate-response"]
    assert tracker["meta"]["profile"] == [f"{CANONICAL}/StructureDefinition/d2-tracker-event-response"]


async def test_a_coded_answer_names_a_concept_the_store_publishes(capture_client: httpx.AsyncClient) -> None:
    """Every generated coding is drawn from a served CodeSystem, never invented."""
    response = (await _generate(capture_client, "PrTemporal1", seed=4)).json()

    codings = [answer["valueCoding"] for answer in _answers(response) if "valueCoding" in answer]
    system = f"{CANONICAL}/CodeSystem/d2-os-OsSymptom01-cs"

    assert codings
    assert {coding["system"] for coding in codings} == {system}
    assert {coding["code"] for coding in codings} <= {"OpFever0001", "OpCough0001"}
    assert len({coding["code"] for coding in codings}) == len(codings)


async def test_a_question_bound_to_unpublished_terminology_is_left_unanswered(
    capture_client: httpx.AsyncClient,
) -> None:
    """Answering a binding this project never published would only make the server warn about its own output."""
    response = (await _generate(capture_client, "PrTemporal1", seed=4)).json()

    answered = {item["linkId"] for item in response["item"] if item.get("answer")}

    assert "DeOpenBind01" not in answered


async def test_a_numeric_answer_stays_inside_the_bounds_the_form_pins(capture_client: httpx.AsyncClient) -> None:
    """A bounded question is generated inside its bounds, which is exactly what capture would refuse outside."""
    response = (await _generate(capture_client, "PrTemporal1", seed=6)).json()

    coverage = next(item for item in response["item"] if item["linkId"] == "DeCoverage01")

    assert 0 <= coverage["answer"][0]["valueDecimal"] <= 100


async def test_the_post_spelling_takes_its_seed_from_a_parameters_body(capture_client: httpx.AsyncClient) -> None:
    """R4 lets an operation be invoked with a Parameters body, and the seed is read off it."""
    body = {"resourceType": "Parameters", "parameter": [{"name": "seed", "valueInteger": 4242}]}

    posted = await capture_client.post(_generate_path(EVENT_ID), json=body)
    queried = await _generate(capture_client, EVENT_ID, seed=4242)

    assert posted.status_code == 200
    assert posted.content == queried.content


async def test_the_post_spelling_takes_an_empty_body(capture_client: httpx.AsyncClient) -> None:
    """A bare POST is how a client says `any seed`, and it is answered rather than refused."""
    posted = await capture_client.post(_generate_path(EVENT_ID))

    assert posted.status_code == 200
    assert posted.json()["resourceType"] == "QuestionnaireResponse"


async def test_an_unreadable_seed_is_refused(capture_client: httpx.AsyncClient) -> None:
    """A seed the operation's `integer` input cannot carry is a bad request, not a silently drawn one."""
    unparseable = await _generate(capture_client, EVENT_ID, seed="banana")
    out_of_range = await _generate(capture_client, EVENT_ID, seed=MAXIMUM_SEED + 1)

    assert unparseable.status_code == 400
    assert unparseable.json()["issue"][0]["code"] == "invalid"
    assert out_of_range.status_code == 400


async def test_a_body_that_is_not_parameters_is_refused(capture_client: httpx.AsyncClient) -> None:
    """A client that meant to name a seed and sent the wrong resource is told so, not quietly ignored."""
    refused = await capture_client.post(_generate_path(EVENT_ID), json={"resourceType": "Bundle"})

    assert refused.status_code == 400
    assert refused.json()["resourceType"] == "OperationOutcome"


async def test_an_unknown_questionnaire_is_a_404_outcome(capture_client: httpx.AsyncClient) -> None:
    """A form this server does not hold is a 404 OperationOutcome, the same answer a read of it gives."""
    missing = await _generate(capture_client, "NoSuchForm", seed=1)

    body = missing.json()

    assert missing.status_code == 404
    assert body["resourceType"] == "OperationOutcome"
    assert body["issue"][0]["code"] == "not-found"


async def test_a_questionnaire_declaring_no_form_kind_cannot_be_generated_against(
    client: httpx.AsyncClient,
) -> None:
    """The minimal project's Questionnaire carries no D2FormType, so there is no contract to fill it against."""
    refused = await client.get(_generate_path("d2-pr-anc-visit-q"))

    assert refused.status_code == 422
    assert refused.json()["issue"][0]["code"] == "not-supported"


async def test_metadata_declares_the_operation_on_the_questionnaire_entry(
    capture_client: httpx.AsyncClient,
) -> None:
    """`/metadata` names `$generate` where R4 puts an instance-level operation: on the resource entry."""
    metadata = (await capture_client.get("/metadata")).json()

    questionnaire = next(entry for entry in metadata["rest"][0]["resource"] if entry["type"] == "Questionnaire")
    others = [entry for entry in metadata["rest"][0]["resource"] if entry["type"] != "Questionnaire"]

    assert questionnaire["operation"] == [
        {
            "name": "generate",
            "definition": f"{CANONICAL}/OperationDefinition/d2-generate",
            "documentation": questionnaire["operation"][0]["documentation"],
        }
    ]
    assert all("operation" not in entry for entry in others)
