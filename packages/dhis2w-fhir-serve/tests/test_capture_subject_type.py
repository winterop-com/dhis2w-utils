"""What a served form says its responses are about, and what the facade does with a subject typed otherwise.

A DHIS2 tracked entity type is not always a person, so a generated form states what it is on
`Questionnaire.subjectType`. The server reads it from there and nowhere else: `fhir.toml` is the
generator's input and never reaches a running facade, so the compiled form is the only contract
there is. These tests hold both halves - the index carries what the form declares, and a response
that types its subject as something the form is not answered about grades on the strictness dial.
"""

from __future__ import annotations

import copy
import datetime
import json
from typing import Any

import pytest
from dhis2w_fhir.r4 import Questionnaire
from dhis2w_fhir_serve.capture import (
    CaptureIndexCache,
    CaptureNaming,
    CaptureRejection,
    build_capture_index,
    validate_response,
)
from dhis2w_fhir_serve.store import ResourceStore
from dhis2w_fhir_serve.synthesize import generate_response
from fixture_project import CAPTURE_CANONICAL, REGISTRATION_PROGRAM_UID, golden

REGISTRATION_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/{REGISTRATION_PROGRAM_UID}"
AGGREGATE_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/BfMAe6Itzgt"
TRACKER_EVENT_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/ZzYYXq4fJie"

#: The resource type the fixture project's herd-tracking sibling would declare.
GROUP_SUBJECT_TYPE = "Group"

TODAY = datetime.date(2026, 8, 2)


def _retyped_store(store: ResourceStore, canonical: str, subject_type: str) -> ResourceStore:
    """The golden store with one served form declaring a different subject type, as a mapped project emits it."""
    entries = []
    for entry in store.entries:
        if entry.canonical_url != canonical:
            entries.append(entry)
            continue
        body = copy.deepcopy(entry.body)
        body["subjectType"] = [subject_type]
        entries.append(entry.model_copy(update={"body": body}))
    return ResourceStore(entries=tuple(entries))


def _subject_issues(issues: tuple[Any, ...]) -> tuple[Any, ...]:
    """Only the issues the subject-type phase raised."""
    return tuple(issue for issue in issues if issue.expression == "QuestionnaireResponse.subject.type")


def _typed(response: dict[str, Any], subject_type: str | None) -> dict[str, Any]:
    """One golden submission with its subject typed as `subject_type`, or with no type at all."""
    body = copy.deepcopy(response)
    subject = dict(body["subject"])
    if subject_type is None:
        subject.pop("type", None)
    else:
        subject["type"] = subject_type
    body["subject"] = subject
    return body


def test_the_index_carries_what_the_form_declares(
    capture_indexes: CaptureIndexCache, capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    """A tracker form is answered about a person by default, an organisation-unit form about a Location."""
    registration = capture_indexes.resolve(REGISTRATION_QUESTIONNAIRE, capture_naming, capture_store)
    aggregate = capture_indexes.resolve(AGGREGATE_QUESTIONNAIRE, capture_naming, capture_store)

    assert registration.subject_type == "Patient"
    assert aggregate.subject_type == "Location"


def test_a_form_declaring_a_group_indexes_as_one(capture_naming: CaptureNaming, capture_store: ResourceStore) -> None:
    """A project tracking herds emits `subjectType = #Group`, and the index reads it verbatim."""
    body = copy.deepcopy(capture_store.by_canonical(REGISTRATION_QUESTIONNAIRE).body)  # type: ignore[union-attr]
    body["subjectType"] = [GROUP_SUBJECT_TYPE]

    assert build_capture_index(body, capture_naming, capture_store).subject_type == GROUP_SUBJECT_TYPE


def test_a_form_declaring_no_subject_reads_as_the_default(
    capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    """R4 makes `subjectType` optional, and a form that states nothing is read the way an unmapped type is."""
    body = copy.deepcopy(capture_store.by_canonical(REGISTRATION_QUESTIONNAIRE).body)  # type: ignore[union-attr]
    body.pop("subjectType", None)

    assert build_capture_index(body, capture_naming, capture_store).subject_type == "Patient"


def test_a_generated_response_types_its_subject_as_the_form_does(
    capture_naming: CaptureNaming, capture_store: ResourceStore
) -> None:
    """`$generate` mints what the form asks for, so a herd form's generated response is about a Group."""
    body = copy.deepcopy(capture_store.by_canonical(REGISTRATION_QUESTIONNAIRE).body)  # type: ignore[union-attr]
    body["subjectType"] = [GROUP_SUBJECT_TYPE]
    index = build_capture_index(body, capture_naming, capture_store)
    questionnaire = Questionnaire.model_validate(body)

    generated = generate_response(questionnaire, index, capture_naming, capture_store, seed=7, today=TODAY)

    assert generated.subject is not None
    assert generated.subject.type == GROUP_SUBJECT_TYPE


def test_a_response_typed_as_the_form_asks_for_is_accepted(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The golden submission names the type the golden form declares, and nothing is noted about it."""
    captured = validate_response(json.dumps(tracker_response).encode(), capture_indexes, capture_naming, capture_store)

    assert _subject_issues(captured.warnings) == ()


def test_a_response_carrying_no_type_at_all_is_accepted(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """`Reference.type` is optional in R4: a response naming its subject by identifier alone says enough."""
    captured = validate_response(
        json.dumps(_typed(tracker_response, None)).encode(), capture_indexes, capture_naming, capture_store
    )

    assert _subject_issues(captured.warnings) == ()


def test_a_mismatched_type_is_a_warning_by_default(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The submission is stored and the disagreement rides back on the receipt, like every other soft check."""
    captured = validate_response(
        json.dumps(_typed(tracker_response, GROUP_SUBJECT_TYPE)).encode(),
        capture_indexes,
        capture_naming,
        capture_store,
    )
    issues = _subject_issues(captured.warnings)

    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert "`Group`" in issues[0].diagnostics
    assert "`Patient`" in issues[0].diagnostics


def test_a_mismatched_type_is_refused_under_strict_codes(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The same dial the coded answers and the assignment ride: strict turns the note into a refusal."""
    with pytest.raises(CaptureRejection) as rejection:
        validate_response(
            json.dumps(_typed(tracker_response, GROUP_SUBJECT_TYPE)).encode(),
            capture_indexes,
            capture_naming,
            capture_store,
            strict_codes=True,
        )

    assert rejection.value.http_status == 422
    assert _subject_issues(rejection.value.issues)[0].severity == "error"


def test_a_group_typed_response_is_accepted_by_the_form_that_asks_for_one(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """Turn the form into a herd form and the very submission that warned is the one it asks for."""
    store = _retyped_store(capture_store, TRACKER_EVENT_QUESTIONNAIRE, GROUP_SUBJECT_TYPE)

    captured = validate_response(
        json.dumps(_typed(tracker_response, GROUP_SUBJECT_TYPE)).encode(),
        capture_indexes,
        capture_naming,
        store,
        strict_codes=True,
    )

    assert _subject_issues(captured.warnings) == ()


def test_an_organisation_unit_response_is_never_subject_typed(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The two organisation-unit kinds name their subject by reference, so the type check does not apply."""
    body = copy.deepcopy(aggregate_response)
    body["subject"] = {**body["subject"], "type": GROUP_SUBJECT_TYPE}

    captured = validate_response(json.dumps(body).encode(), capture_indexes, capture_naming, capture_store)

    assert _subject_issues(captured.warnings) == ()


def test_the_golden_tracker_response_answers_the_golden_tracker_form() -> None:
    """Guard: the fixture the mismatch tests perturb really is the pair they assume it is."""
    response = golden("QuestionnaireResponse-ZzYYXq4fJie-example-1.json")

    assert response["questionnaire"] == TRACKER_EVENT_QUESTIONNAIRE
    assert response["subject"]["type"] == "Patient"
