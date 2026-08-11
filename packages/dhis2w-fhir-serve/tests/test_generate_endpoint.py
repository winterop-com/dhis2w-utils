"""`Questionnaire/{id}/$generate`: what the operation answers with, and the round trip that justifies it.

The invariant every other test here supports: **a generated response posted back to this server's own
`/QuestionnaireResponse` answers 201**. It is asserted per served form kind - aggregate, event, and
tracker event - over the compiled goldens, and again over a strict-codes server, because a generated
coding has to be the exact concept code the contract asks for rather than one of the lenient
fall-back spellings.

Two things a 201 does not settle, and which are tested here beside it, because DHIS2 grades them and
this server does not: a value has to be spelled the way its DHIS2 value type is parsed, and a stage
event has to name a tracked entity and an enrollment that exist. Both are what the difference between
"this server accepts it" and "`d2w fhir forward` lands it" is made of.
"""

from __future__ import annotations

import random
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
from dhis2w_fhir_serve.spool import ResponseLifecycle, ResponseSpool, StoredResponseEnvelope
from dhis2w_fhir_serve.synthesize import DEFAULT_PERIOD_TYPE, MAXIMUM_SEED, TrackerPair
from fixture_project import ORG_UNITS, REGISTRATION_UNIQUE_ATTRIBUTE, SCOPED_ASSIGNMENT_UNITS

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

#: The tracker program whose registration form the fixture writes, and the two dates its response
#: may carry - the enrolment date the contract requires, and the incident date it slices 0..1.
REGISTRATION_ID = "PrAncCare01"
REGISTRATION_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/{REGISTRATION_ID}"
ENROLLED_AT_URL = f"{CANONICAL}/StructureDefinition/d2-enrolled-at"
INCIDENT_AT_URL = f"{CANONICAL}/StructureDefinition/d2-incident-at"
ORGANISATION_UNIT_URL = f"{CANONICAL}/StructureDefinition/d2-organisation-unit"

#: The stage form of the registration form's own program - the pair a registration mints is what a
#: response to this form is captured against.
STAGE_ID = "PsAncVisit1"
STAGE_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/{STAGE_ID}"

#: How many places a DHIS2 UID carries, which is all a generated tracker identifier claims to be.
UID_LENGTH = 11

#: The units the registration form's published assignment admits, spelled as capture references.
ASSIGNED_UNIT_REFERENCES = {f"Location/{uid}" for uid in SCOPED_ASSIGNMENT_UNITS}

#: Every Location the fixture registry serves, including the curated profile exemplar.
SERVED_UNIT_REFERENCES = {f"Location/{unit.uid}" for unit in ORG_UNITS} | {"Location/d2-location-example"}

#: How many seeds the unit-variance tests range over - enough that a draw over two or more
#: candidates lands on more than one of them, deterministically, since the draw is seed-keyed.
VARIANCE_SEEDS = range(12)

#: How many seedless calls the unseeded-variance test makes, and the stream it makes them over.
#: A seedless call draws its seed off the `random` module's own generator, so pinning that stream
#: is what makes "the drawn seeds, and the units they name, differ" an assertion rather than a coin.
UNSEEDED_CALLS = 12
UNSEEDED_STREAM_SEED = 20260811

#: Every form the golden project serves, including the two extra event forms and the registration one.
EVERY_FORM_ID = (
    AGGREGATE_ID,
    EVENT_ID,
    TRACKER_EVENT_ID,
    "PsAncVisit1",
    "PrTemporal1",
    ATTRIBUTE_COMBO_ID,
    REGISTRATION_ID,
)

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


async def test_a_registration_response_mints_the_identities_it_creates(capture_client: httpx.AsyncClient) -> None:
    """A registration is answered before either identity exists, so `$generate` mints both, shaped as DHIS2 UIDs."""
    response = (await _generate(capture_client, REGISTRATION_ID, seed=5)).json()

    subject = response["subject"]
    enrollment = _extensions(response, TRACKER_ENROLLMENT_URL)[0]["valueIdentifier"]

    assert response["questionnaire"] == REGISTRATION_QUESTIONNAIRE
    assert subject["type"] == "Patient"
    assert subject["identifier"]["system"] == TRACKED_ENTITY_SYSTEM
    assert len(subject["identifier"]["value"]) == UID_LENGTH
    assert len(enrollment["value"]) == UID_LENGTH
    assert subject["identifier"]["value"] != enrollment["value"]


async def test_a_registration_response_dates_the_enrollment_it_creates(capture_client: httpx.AsyncClient) -> None:
    """DHIS2 requires every enrollment to say when it began, so the enrolment date is always generated."""
    response = (await _generate(capture_client, REGISTRATION_ID, seed=5)).json()

    enrolled_at = _extensions(response, ENROLLED_AT_URL)

    assert len(enrolled_at) == 1
    assert enrolled_at[0]["valueDateTime"].endswith("Z")


async def test_a_registration_response_carries_no_incident_date_the_guide_never_shows(
    capture_client: httpx.AsyncClient,
) -> None:
    """The compiled form does not say whether its program displays one, so an unshown date is not invented."""
    response = (await _generate(capture_client, REGISTRATION_ID, seed=5)).json()

    assert _extensions(response, INCIDENT_AT_URL) == []


async def test_a_registration_response_follows_the_incident_date_a_served_example_shows(
    capture_project: FhirProject,
    write_resource: Callable[[Path, dict[str, Any]], None],
) -> None:
    """A compiled IG ships its example instances, and one carrying D2IncidentAt is the guide's own statement."""
    write_resource(
        capture_project.ig_directory / "fsh-generated" / "resources" / "QuestionnaireResponse-incident.json",
        {
            "resourceType": "QuestionnaireResponse",
            "id": f"{REGISTRATION_ID}-example-9",
            "questionnaire": REGISTRATION_QUESTIONNAIRE,
            "status": "completed",
            "extension": [{"url": INCIDENT_AT_URL, "valueDateTime": "2026-01-02T00:00:00Z"}],
        },
    )
    app = create_app(ServeSettings(project_dir=capture_project.project_root))

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://serve.test") as client:
            generated = await _generate(client, REGISTRATION_ID, seed=5)
            posted = await _post_back(client, generated)

    incident_at = _extensions(generated.json(), INCIDENT_AT_URL)

    assert len(incident_at) == 1
    assert incident_at[0]["valueDateTime"].endswith("Z")
    assert posted.status_code == 201


async def test_a_registration_response_names_the_unit_that_owns_the_enrollment(
    capture_client: httpx.AsyncClient,
) -> None:
    """A registration's subject is the person, so the organisation unit rides on its own extension."""
    response = (await _generate(capture_client, REGISTRATION_ID, seed=5)).json()

    organisation_units = _extensions(response, ORGANISATION_UNIT_URL)

    assert len(organisation_units) == 1
    assert organisation_units[0]["valueReference"]["reference"].startswith("Location/")


def _unique_attribute_value(response: dict[str, Any]) -> str:
    """The generated answer to the registration form's unique tracked entity attribute."""
    item = next(entry for entry in response["item"] if entry["linkId"] == REGISTRATION_UNIQUE_ATTRIBUTE)
    value: str = item["answer"][0]["valueString"]
    return value


async def test_two_generated_registrations_never_repeat_a_unique_attribute_value(
    capture_client: httpx.AsyncClient,
) -> None:
    """DHIS2 refuses the second registration repeating a unique value with E1064, so no two seeds share one."""
    first = (await _generate(capture_client, REGISTRATION_ID, seed=1)).json()
    second = (await _generate(capture_client, REGISTRATION_ID, seed=2)).json()

    assert _unique_attribute_value(first) != _unique_attribute_value(second)


async def test_a_unique_attribute_answer_carries_the_minted_tracked_entity_uid(
    capture_client: httpx.AsyncClient,
) -> None:
    """The distinct value is the response's own minted UID - the one value no other generated response holds."""
    response = (await _generate(capture_client, REGISTRATION_ID, seed=5)).json()

    assert response["subject"]["identifier"]["value"] in _unique_attribute_value(response)


async def test_the_organisation_unit_is_part_of_the_seeded_draw_inside_the_assignment(
    capture_client: httpx.AsyncClient,
) -> None:
    """Different seeds range over the whole admitted set, and every draw stays inside the published assignment."""
    drawn: set[str] = set()
    for seed in VARIANCE_SEEDS:
        response = (await _generate(capture_client, REGISTRATION_ID, seed=seed)).json()
        reference = _extensions(response, ORGANISATION_UNIT_URL)[0]["valueReference"]["reference"]
        assert reference in ASSIGNED_UNIT_REFERENCES
        drawn.add(reference)

    assert drawn == ASSIGNED_UNIT_REFERENCES


async def test_an_unrestricted_form_draws_its_unit_across_the_served_registry(
    capture_client: httpx.AsyncClient,
) -> None:
    """A form publishing no assignment reports for any served Location, varying with the seed."""
    drawn: set[str] = set()
    for seed in VARIANCE_SEEDS:
        response = (await _generate(capture_client, EVENT_ID, seed=seed)).json()
        reference = response["subject"]["reference"]
        assert reference in SERVED_UNIT_REFERENCES
        drawn.add(reference)

    assert len(drawn) > 1


async def test_a_seedless_call_draws_its_unit_across_the_admitted_set_too(
    capture_client: httpx.AsyncClient,
) -> None:
    """A seedless call is answered from a drawn seed, so its unit varies exactly as a named seed's does."""
    stream = random.getstate()
    random.seed(UNSEEDED_STREAM_SEED)
    try:
        responses = [(await _generate(capture_client, REGISTRATION_ID)).json() for _ in range(UNSEEDED_CALLS)]
    finally:
        random.setstate(stream)

    drawn = {_extensions(response, ORGANISATION_UNIT_URL)[0]["valueReference"]["reference"] for response in responses}

    assert drawn <= ASSIGNED_UNIT_REFERENCES
    assert len(drawn) > 1


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


#: A form asking one question per DHIS2 value type R4 has no item type of its own for: five that ride
#: a `string` item and DHIS2 parses anyway, one that is genuinely free text, and three DHIS2 stores a
#: document or a UID reference for. The compiled goldens ask none of them, so the form is written into
#: the project by the tests that need it rather than into the fixture every other test shares.
WIDE_FORM_ID = "PrWideType1"
WIDE_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/{WIDE_FORM_ID}"
WIDE_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-wide-cs"

#: Which question of that form asks which DHIS2 value type.
WIDE_VALUE_TYPES = {
    "DeCoord0001": "COORDINATE",
    "DePhone0001": "PHONE_NUMBER",
    "DeEmail0001": "EMAIL",
    "DeLetter001": "LETTER",
    "DeUsernam01": "USERNAME",
    "DeFreeText1": "TEXT",
    "DeGeoJson01": "GEOJSON",
    "DeReferenc1": "REFERENCE",
    "DeAssociat1": "TRACKER_ASSOCIATE",
}

#: The questions DHIS2 stores a document or a reference to one of its own objects behind, which a
#: generated response leaves unanswered rather than inventing a target for.
WIDE_UNANSWERED_QUESTIONS = ("DeGeoJson01", "DeReferenc1", "DeAssociat1")

#: The wide questions asked as a `text` item; every other one is asked as a `string`.
WIDE_TEXT_QUESTIONS = ("DeGeoJson01",)

#: How few characters DHIS2 holds a username to, which is what makes a seeded one an account name.
MINIMUM_USERNAME_LENGTH = 4


def _wide_questionnaire() -> dict[str, Any]:
    """The wide-value-type form, in the shape `d2w fhir generate` writes an event program's form."""
    return {
        "resourceType": "Questionnaire",
        "id": WIDE_FORM_ID,
        "url": WIDE_QUESTIONNAIRE,
        "title": "Wide value types",
        "extension": [{"url": FORM_TYPE_URL, "valueCode": "event"}],
        "identifier": [{"system": "http://dhis2.org/fhir/id/program", "value": WIDE_FORM_ID}],
        "name": f"D2PR_{WIDE_FORM_ID}",
        "status": "draft",
        "experimental": True,
        "subjectType": ["Location"],
        "item": [
            {
                "linkId": link_id,
                "code": [{"system": WIDE_CODE_SYSTEM, "code": link_id, "display": value_type.title()}],
                "text": value_type.title(),
                "type": "text" if link_id in WIDE_TEXT_QUESTIONS else "string",
            }
            for link_id, value_type in WIDE_VALUE_TYPES.items()
        ],
    }


def _wide_code_system() -> dict[str, Any]:
    """The support CodeSystem stating the DHIS2 value type behind each of those questions."""
    return {
        "resourceType": "CodeSystem",
        "id": WIDE_CODE_SYSTEM.rsplit("/", 1)[-1],
        "url": WIDE_CODE_SYSTEM,
        "status": "draft",
        "content": "complete",
        "caseSensitive": True,
        "property": [{"code": "value-type", "uri": "http://dhis2.org/fhir/property/value-type", "type": "code"}],
        "concept": [
            {
                "code": link_id,
                "display": value_type.title(),
                "property": [{"code": "value-type", "valueCode": value_type}],
            }
            for link_id, value_type in WIDE_VALUE_TYPES.items()
        ],
        "count": len(WIDE_VALUE_TYPES),
    }


def _answered_strings(response: dict[str, Any]) -> dict[str, str]:
    """Every string answer of one generated response, by the question that carries it."""
    return {
        item["linkId"]: item["answer"][0]["valueString"]
        for item in response.get("item", [])
        if item.get("answer") and "valueString" in item["answer"][0]
    }


async def _generated_wide_response(
    capture_project: FhirProject,
    write_resource: Callable[[Path, dict[str, Any]], None],
    seed: int,
) -> tuple[dict[str, Any], int]:
    """Serve the wide-value-type form beside the goldens, generate against it, and post the answer back."""
    compiled = capture_project.ig_directory / "fsh-generated" / "resources"
    write_resource(compiled / f"Questionnaire-{WIDE_FORM_ID}.json", _wide_questionnaire())
    write_resource(compiled / f"CodeSystem-{WIDE_CODE_SYSTEM.rsplit('/', 1)[-1]}.json", _wide_code_system())
    app = create_app(ServeSettings(project_dir=capture_project.project_root))

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://serve.test") as client:
            generated = await _generate(client, WIDE_FORM_ID, seed=seed)
            posted = await _post_back(client, generated)

    return generated.json(), posted.status_code


async def test_a_format_constrained_answer_is_spelled_the_way_its_dhis2_value_type_is_parsed(
    capture_project: FhirProject,
    write_resource: Callable[[Path, dict[str, Any]], None],
) -> None:
    """R4 asks all five as `string`; DHIS2 parses each of them, and refuses a value it cannot with `E1302`."""
    response, posted = await _generated_wide_response(capture_project, write_resource, seed=5)
    answered = _answered_strings(response)
    longitude, latitude = (float(part) for part in answered["DeCoord0001"].strip("[]").split(","))
    username = answered["DeUsernam01"]

    assert -180 <= longitude <= 180
    assert -90 <= latitude <= 90
    assert answered["DePhone0001"].startswith("+")
    assert answered["DePhone0001"][1:].isdigit()
    assert answered["DeEmail0001"].count("@") == 1
    assert answered["DeEmail0001"].endswith("@example.invalid")
    assert answered["DeLetter001"].isalpha()
    assert len(answered["DeLetter001"]) == 1
    assert username.isalnum()
    assert len(username) >= MINIMUM_USERNAME_LENGTH
    assert posted == 201


async def test_a_free_text_answer_still_names_the_question_it_answers(
    capture_project: FhirProject,
    write_resource: Callable[[Path, dict[str, Any]], None],
) -> None:
    """Free text is what DHIS2 stores for a TEXT question, so naming the question is an honest answer to it."""
    response, _ = await _generated_wide_response(capture_project, write_resource, seed=5)

    assert _answered_strings(response)["DeFreeText1"] == "Example DeFreeText1"


async def test_a_value_type_holding_a_document_or_a_dhis2_reference_is_left_unanswered(
    capture_project: FhirProject,
    write_resource: Callable[[Path, dict[str, Any]], None],
) -> None:
    """An invented GeoJSON blob or object UID names a target nothing resolves, which DHIS2 refuses as `E1302`."""
    response, posted = await _generated_wide_response(capture_project, write_resource, seed=5)

    answered = {item["linkId"] for item in response.get("item", []) if item.get("answer")}

    assert not answered & set(WIDE_UNANSWERED_QUESTIONS)
    assert posted == 201


async def test_a_format_constrained_answer_is_the_same_for_the_same_seed(
    capture_project: FhirProject,
    write_resource: Callable[[Path, dict[str, Any]], None],
) -> None:
    """The constrained values are drawn off the same seeded stream as every other answer, so they repeat."""
    first, _ = await _generated_wide_response(capture_project, write_resource, seed=13)
    second, _ = await _generated_wide_response(capture_project, write_resource, seed=13)

    assert _answered_strings(first) == _answered_strings(second)


def _tracker_pair(response: dict[str, Any]) -> TrackerPair:
    """The tracked entity and the enrollment one generated tracker response is captured against."""
    return TrackerPair(
        tracked_entity_uid=response["subject"]["identifier"]["value"],
        enrollment_uid=_extensions(response, TRACKER_ENROLLMENT_URL)[0]["valueIdentifier"]["value"],
    )


def _spool_registration(
    project: FhirProject,
    response: dict[str, Any],
    *,
    response_id: str,
    received_at: str,
    lifecycle: ResponseLifecycle,
) -> None:
    """Store one registration receipt in the state named, as the facade writes it and the forwarder moves it."""
    spool = ResponseSpool.at(project.project_root)
    directory = spool.directory_for(lifecycle)
    directory.mkdir(parents=True, exist_ok=True)
    envelope = StoredResponseEnvelope(
        response_id=response_id,
        received_at=received_at,
        form_kind="tracker",
        questionnaire=REGISTRATION_QUESTIONNAIRE,
        response=response,
    )
    (directory / f"{response_id}.json").write_text(envelope.model_dump_json(indent=2) + "\n", encoding="utf-8")


async def test_a_stage_response_answers_against_the_pair_a_captured_registration_minted(
    capture_client: httpx.AsyncClient,
) -> None:
    """A stage event naming a pair that never existed is refused `E1079`, so a spooled registration's is adopted."""
    registration = await _generate(capture_client, REGISTRATION_ID, seed=5)
    assert (await _post_back(capture_client, registration)).status_code == 201

    generated = await _generate(capture_client, STAGE_ID, seed=5)
    posted = await _post_back(capture_client, generated)

    assert generated.json()["questionnaire"] == STAGE_QUESTIONNAIRE
    assert _tracker_pair(generated.json()) == _tracker_pair(registration.json())
    assert posted.status_code == 201


async def test_a_stage_response_prefers_a_forwarded_registration_over_a_received_one(
    capture_client: httpx.AsyncClient,
    capture_project: FhirProject,
) -> None:
    """A forwarded pair names objects DHIS2 already holds; a received one will only after the next drain."""
    forwarded = (await _generate(capture_client, REGISTRATION_ID, seed=1)).json()
    received = (await _generate(capture_client, REGISTRATION_ID, seed=2)).json()
    _spool_registration(
        capture_project,
        forwarded,
        response_id="registration-forwarded",
        received_at="2026-08-01T09:00:00Z",
        lifecycle=ResponseLifecycle.FORWARDED,
    )
    _spool_registration(
        capture_project,
        received,
        response_id="registration-received",
        received_at="2026-08-09T09:00:00Z",
        lifecycle=ResponseLifecycle.RECEIVED,
    )

    generated = (await _generate(capture_client, STAGE_ID, seed=5)).json()

    assert _tracker_pair(generated) == _tracker_pair(forwarded)


async def test_a_rejected_registration_is_never_answered_against(
    capture_client: httpx.AsyncClient,
    capture_project: FhirProject,
) -> None:
    """DHIS2 refused the registration, so its pair names nothing and no forwarder run will change that."""
    before = await _generate(capture_client, STAGE_ID, seed=5)
    rejected = (await _generate(capture_client, REGISTRATION_ID, seed=1)).json()
    _spool_registration(
        capture_project,
        rejected,
        response_id="registration-rejected",
        received_at="2026-08-09T09:00:00Z",
        lifecycle=ResponseLifecycle.REJECTED,
    )

    after = await _generate(capture_client, STAGE_ID, seed=5)

    assert after.content == before.content
    assert _tracker_pair(after.json()) != _tracker_pair(rejected)


async def test_a_stage_response_mints_a_pair_when_no_registration_of_its_program_is_spooled(
    capture_client: httpx.AsyncClient,
) -> None:
    """The join is the program the two forms share, so another program's registration is not one to answer against.

    The stage form is drawn on a seed of its own, because the pair is the first thing any tracker
    form takes off the seeded stream: two forms generated on one seed mint the same pair, and a
    stage response that had adopted this registration would be indistinguishable from one that had not.
    """
    before = await _generate(capture_client, TRACKER_EVENT_ID, seed=6)
    registration = await _generate(capture_client, REGISTRATION_ID, seed=5)
    assert (await _post_back(capture_client, registration)).status_code == 201

    after = await _generate(capture_client, TRACKER_EVENT_ID, seed=6)
    minted = _tracker_pair(after.json())

    assert after.content == before.content
    assert minted != _tracker_pair(registration.json())
    assert len(minted.tracked_entity_uid) == UID_LENGTH
    assert len(minted.enrollment_uid) == UID_LENGTH


async def test_an_answered_pair_wins_over_the_pair_the_seed_would_mint(
    capture_client: httpx.AsyncClient,
    capture_project: FhirProject,
) -> None:
    """Which person a stage event is about is a fact about this project's data, not a value the seed draws.

    And adoption moves those two identifiers and nothing else: the drawn pair comes off the seeded
    stream whether or not it is then answered over, so every other value of the document stands.
    """
    minted = await _generate(capture_client, STAGE_ID, seed=5)
    registration = (await _generate(capture_client, REGISTRATION_ID, seed=8)).json()
    _spool_registration(
        capture_project,
        registration,
        response_id="registration-adopted",
        received_at="2026-08-09T09:00:00Z",
        lifecycle=ResponseLifecycle.RECEIVED,
    )

    adopted = await _generate(capture_client, STAGE_ID, seed=5)

    minted_pair = _tracker_pair(minted.json())
    adopted_pair = _tracker_pair(adopted.json())
    restored = adopted.text.replace(adopted_pair.tracked_entity_uid, minted_pair.tracked_entity_uid).replace(
        adopted_pair.enrollment_uid, minted_pair.enrollment_uid
    )

    assert adopted_pair == _tracker_pair(registration)
    assert adopted_pair != minted_pair
    assert restored == minted.text


async def test_a_stage_response_is_the_same_bytes_for_one_seed_and_one_spool_state(
    capture_client: httpx.AsyncClient,
    capture_project: FhirProject,
) -> None:
    """Determinism holds with the spool in it: the same seed against the same receipts is the same document."""
    _spool_registration(
        capture_project,
        (await _generate(capture_client, REGISTRATION_ID, seed=8)).json(),
        response_id="registration-stable",
        received_at="2026-08-09T09:00:00Z",
        lifecycle=ResponseLifecycle.RECEIVED,
    )

    first = await _generate(capture_client, STAGE_ID, seed=1234)
    second = await _generate(capture_client, STAGE_ID, seed=1234)

    assert first.content == second.content
