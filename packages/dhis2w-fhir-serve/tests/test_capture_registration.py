"""Capturing a tracker registration response: the envelope it mints, and what a server can honestly check.

A registration is the one contract whose DHIS2 identities are the client's. The tracked entity the
response is subject to and the enrollment its extension names do not exist anywhere yet, so the
phases here check their **shape** and nothing about their existence - which is the whole of what a
facade holding no instance data can say. The tests below hold that line in both directions: a
malformed identifier is refused, and a perfectly-shaped one nobody has ever seen is accepted.

Two things are deliberately not checked, and each has a test saying so. Uniqueness: a `unique`
tracked entity attribute is a business identifier, and only the instance knows whether the value is
taken - DHIS2 refuses the duplicate at import, and this server stores the receipt. And the incident
date: `D2IncidentAt` is 0..1 and the compiled Questionnaire publishes no statement of whether the
program displays one, so a response is accepted with it and without it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from dhis2w_fhir_serve.capture import (
    CaptureIndexCache,
    CaptureIssue,
    CaptureNaming,
    CaptureRejection,
    ValidatedCapture,
    validate_response,
)
from dhis2w_fhir_serve.store import ResourceStore
from fixture_project import (
    CAPTURE_CANONICAL,
    REGISTRATION_CODED_ATTRIBUTE,
    REGISTRATION_DATE_ATTRIBUTE,
    REGISTRATION_PROGRAM_UID,
    REGISTRATION_UNIQUE_ATTRIBUTE,
    SEX_CODE_SYSTEM,
)

REGISTRATION_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{REGISTRATION_PROGRAM_UID}"

FORM_TYPE_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-form-type"
ORGANISATION_UNIT_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-organisation-unit"
TRACKER_ENROLLMENT_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-tracker-enrollment"
ENROLLED_AT_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-enrolled-at"
INCIDENT_AT_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-incident-at"

TRACKED_ENTITY_SYSTEM = "http://dhis2.org/fhir/id/tracked-entity"
TRACKER_ENROLLMENT_SYSTEM = "http://dhis2.org/fhir/id/tracker-enrollment"

#: The identities a compliant client mints for one submission - shaped DHIS2 UIDs nobody has seen.
MINTED_TRACKED_ENTITY = "TeAaBbCcDd1"
MINTED_ENROLLMENT = "EnAaBbCcDd1"

#: A unit the registration form's assignment admits, and one the registry publishes but it does not.
ADMITTED_UNIT = "Location/DiszpKrYNg8"
UNASSIGNED_UNIT = "Location/ImspTQPwCqd"


def _registration(**overrides: Any) -> dict[str, Any]:
    """One compliant registration submission, the caller replacing whichever top-level element it is about."""
    body: dict[str, Any] = {
        "resourceType": "QuestionnaireResponse",
        "extension": [
            {"url": ORGANISATION_UNIT_URL, "valueReference": {"reference": ADMITTED_UNIT}},
            {
                "url": TRACKER_ENROLLMENT_URL,
                "valueIdentifier": {"system": TRACKER_ENROLLMENT_SYSTEM, "value": MINTED_ENROLLMENT},
            },
            {"url": ENROLLED_AT_URL, "valueDateTime": "2026-07-20T09:00:00Z"},
            {"url": FORM_TYPE_URL, "valueCode": "tracker"},
        ],
        "questionnaire": REGISTRATION_QUESTIONNAIRE,
        "status": "completed",
        "subject": {
            "type": "Patient",
            "identifier": {"system": TRACKED_ENTITY_SYSTEM, "value": MINTED_TRACKED_ENTITY},
        },
        "authored": "2026-07-20T09:00:00Z",
        "item": [
            {"linkId": REGISTRATION_UNIQUE_ATTRIBUTE, "answer": [{"valueString": "19850101-11111"}]},
            {"linkId": REGISTRATION_DATE_ATTRIBUTE, "answer": [{"valueDate": "1985-01-01"}]},
            {
                "linkId": REGISTRATION_CODED_ATTRIBUTE,
                "answer": [{"valueCoding": {"system": SEX_CODE_SYSTEM, "code": "OpFemale001", "display": "Female"}}],
            },
        ],
    }
    body.update(overrides)
    return body


def _without(body: dict[str, Any], url: str) -> dict[str, Any]:
    """The same submission with every extension under one url removed."""
    body["extension"] = [extension for extension in body["extension"] if extension["url"] != url]
    return body


def _accept(
    body: dict[str, Any],
    indexes: CaptureIndexCache,
    naming: CaptureNaming,
    store: ResourceStore,
    strict_codes: bool = False,
) -> ValidatedCapture:
    """Validate one submission, failing the test when it is refused."""
    return validate_response(json.dumps(body).encode(), indexes, naming, store, strict_codes)


def _refuse(
    body: dict[str, Any],
    indexes: CaptureIndexCache,
    naming: CaptureNaming,
    store: ResourceStore,
    strict_codes: bool = False,
) -> CaptureRejection:
    """Validate one submission, failing the test when it is accepted."""
    with pytest.raises(CaptureRejection) as raised:
        validate_response(json.dumps(body).encode(), indexes, naming, store, strict_codes)
    return raised.value


def _errors(rejection: CaptureRejection) -> tuple[CaptureIssue, ...]:
    """Only the issues that refused the submission."""
    return tuple(issue for issue in rejection.issues if issue.is_error())


def _diagnostics(issues: tuple[CaptureIssue, ...]) -> str:
    """Every issue's diagnostics, joined, for one readable assertion."""
    return " | ".join(issue.diagnostics or "" for issue in issues)


@pytest.mark.parametrize("strict_codes", [False, True])
def test_a_compliant_registration_is_accepted_however_strict_the_server_is(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
    strict_codes: bool,
) -> None:
    """The documented envelope clears every phase, and its coding is the concept code the contract asks for."""
    accepted = _accept(_registration(), capture_indexes, capture_naming, capture_store, strict_codes)

    assert accepted.form_kind == "tracker"
    assert accepted.canonical == REGISTRATION_QUESTIONNAIRE
    assert accepted.warnings == ()


def test_a_registration_naming_no_subject_identifier_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The tracked entity the response creates is named by identifier, so a subject without one says nothing."""
    rejection = _refuse(_registration(subject={"type": "Patient"}), capture_indexes, capture_naming, capture_store)

    assert "no tracked-entity identifier" in _diagnostics(_errors(rejection))


def test_a_registration_minting_a_malformed_tracked_entity_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A client mints the UID, so its shape is the one thing about it a server without an instance can check."""
    body = _registration(
        subject={"type": "Patient", "identifier": {"system": TRACKED_ENTITY_SYSTEM, "value": "not-a-uid"}}
    )

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "is not a DHIS2 UID" in _diagnostics(_errors(rejection))


def test_a_registration_minting_a_malformed_enrollment_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The enrollment UID travels to DHIS2 as sent, so a shape DHIS2 cannot take is refused at the door."""
    body = _registration()
    for extension in body["extension"]:
        if extension["url"] == TRACKER_ENROLLMENT_URL:
            extension["valueIdentifier"]["value"] = "1-bad-uid"

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "is not a DHIS2 UID" in _diagnostics(_errors(rejection))


def test_a_registration_naming_no_enrollment_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The enrollment extension is what the stage responses of the same sitting answer against."""
    rejection = _refuse(
        _without(_registration(), TRACKER_ENROLLMENT_URL), capture_indexes, capture_naming, capture_store
    )

    assert "carries exactly one" in _diagnostics(_errors(rejection))
    assert TRACKER_ENROLLMENT_URL in _diagnostics(_errors(rejection))


def test_a_registration_stating_no_enrollment_date_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """DHIS2 requires every enrollment to say when it began, so the response the enrollment comes from does."""
    rejection = _refuse(_without(_registration(), ENROLLED_AT_URL), capture_indexes, capture_naming, capture_store)

    assert "states when the enrollment began" in _diagnostics(_errors(rejection))


def test_an_enrollment_date_that_is_not_an_r4_date_time_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A date that does not read as an instant would import as an enrollment beginning nowhere."""
    body = _registration()
    for extension in body["extension"]:
        if extension["url"] == ENROLLED_AT_URL:
            extension["valueDateTime"] = "yesterday"

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "is not an R4 dateTime" in _diagnostics(_errors(rejection))


def test_a_registration_carrying_an_incident_date_is_accepted(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The compiled form does not say whether the program displays one, so both answers are valid."""
    body = _registration()
    body["extension"].insert(3, {"url": INCIDENT_AT_URL, "valueDateTime": "2026-07-01T00:00:00Z"})

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    assert accepted.warnings == ()


def test_a_registration_carrying_no_incident_date_is_accepted(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """`D2IncidentAt` is 0..1, and a server that cannot read the program's rule does not invent one."""
    accepted = _accept(_registration(), capture_indexes, capture_naming, capture_store)

    assert accepted.warnings == ()


def test_a_malformed_incident_date_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """What capture can check about the incident date is the primitive, and that it does check."""
    body = _registration()
    body["extension"].insert(3, {"url": INCIDENT_AT_URL, "valueDateTime": "last winter"})

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "is not an R4 dateTime" in _diagnostics(_errors(rejection))


def test_a_registration_naming_no_organisation_unit_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A registration's subject is the person, so the owning unit rides on an extension of its own."""
    rejection = _refuse(
        _without(_registration(), ORGANISATION_UNIT_URL), capture_indexes, capture_naming, capture_store
    )

    assert "carries exactly one" in _diagnostics(_errors(rejection))
    assert ORGANISATION_UNIT_URL in _diagnostics(_errors(rejection))


def test_a_registration_outside_the_forms_assignment_warns_by_default(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The assignment dial reads the tracker kinds' organisation-unit extension, not their subject."""
    body = _registration()
    body["extension"][0]["valueReference"]["reference"] = UNASSIGNED_UNIT

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    assert [issue.code for issue in accepted.warnings] == ["business-rule"]
    assert "E1029" in _diagnostics(accepted.warnings)


@pytest.mark.parametrize("strict_codes", [True])
def test_a_registration_outside_the_forms_assignment_is_refused_under_strict_codes(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
    strict_codes: bool,
) -> None:
    """The same grading a coded answer gets: a warning by default, a refusal when the project asks for one."""
    body = _registration()
    body["extension"][0]["valueReference"]["reference"] = UNASSIGNED_UNIT

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store, strict_codes)

    assert "E1029" in _diagnostics(_errors(rejection))


def test_an_attribute_answered_on_the_wrong_element_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A tracked entity attribute is typed the way a data element is, so its answers are checked the same way."""
    body = _registration()
    body["item"][1]["answer"] = [{"valueString": "1985-01-01"}]

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "carries `valueDate`, not `valueString`" in _diagnostics(_errors(rejection))


def test_an_unanswered_mandatory_attribute_warns(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """DHIS2 `mandatory` becomes R4 `required`, and a missing required answer annotates rather than refuses."""
    body = _registration()
    body["item"] = [item for item in body["item"] if item["linkId"] != REGISTRATION_UNIQUE_ATTRIBUTE]

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    assert REGISTRATION_UNIQUE_ATTRIBUTE in _diagnostics(accepted.warnings)
    assert "required by the form" in _diagnostics(accepted.warnings)


def test_a_coded_attribute_answered_outside_its_value_set_grades_on_the_dial(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """An option-bound attribute resolves through the very resolvers a coded data element does."""
    body = _registration()
    body["item"][2]["answer"] = [{"valueCoding": {"system": SEX_CODE_SYSTEM, "code": "OpUnknown01"}}]

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)
    rejection = _refuse(body, capture_indexes, capture_naming, capture_store, strict_codes=True)

    assert [issue.code for issue in accepted.warnings] == ["code-invalid"]
    assert "OpUnknown01" in _diagnostics(_errors(rejection))


def test_a_coded_attribute_answered_by_dhis2_code_warns_and_is_stored(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The lenient tiers apply to attributes too: the option is named, in a spelling the contract does not ask for."""
    body = _registration()
    body["item"][2]["answer"] = [{"valueCoding": {"system": SEX_CODE_SYSTEM, "code": "F"}}]

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    assert "the contract expects concept code 'OpFemale001'" in _diagnostics(accepted.warnings)


def test_a_duplicate_unique_attribute_value_is_stored_unchecked(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """Uniqueness is global instance state this facade does not hold, so it is DHIS2's to enforce at import."""
    first = _accept(_registration(), capture_indexes, capture_naming, capture_store)
    second = _accept(
        _registration(
            subject={
                "type": "Patient",
                "identifier": {"system": TRACKED_ENTITY_SYSTEM, "value": "TeAaBbCcDd2"},
            }
        ),
        capture_indexes,
        capture_naming,
        capture_store,
    )

    assert first.warnings == ()
    assert second.warnings == ()


def test_a_registration_answering_a_link_id_the_form_does_not_ask_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The item walk is the same one every kind runs: an unknown link id has nowhere to go."""
    body = _registration()
    body["item"].append({"linkId": "TeaMadeUp01", "answer": [{"valueString": "x"}]})

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "is not a question of" in _diagnostics(_errors(rejection))


def test_a_response_declaring_the_wrong_kind_for_a_registration_form_is_refused(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The declared kind and the served form's own kind have to agree before anything else is read."""
    body = _registration()
    for extension in body["extension"]:
        if extension["url"] == FORM_TYPE_URL:
            extension["valueCode"] = "tracker-event"

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store)

    assert "is a `tracker` form" in _diagnostics(_errors(rejection))
