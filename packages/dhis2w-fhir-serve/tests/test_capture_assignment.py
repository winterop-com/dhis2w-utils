"""Capture against a form's published organisation-unit assignment, on both positions of the dial.

The assignment artifact is optional by design, so the cases that matter are the three the design
turns on: no artifact means the whole registry and nothing is checked, an in-assignment unit is
silent, and an out-of-assignment unit warns by default and refuses under `--strict-codes` - the
same grading a coded answer takes, because both describe drift between a client and the instance
rather than a malformed submission.
"""

from __future__ import annotations

import copy
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
from dhis2w_fhir_serve.store import ResourceStore, StoreEntry

#: The canonical the dhis2w-fhir goldens were compiled under, as `capture_project` serves them.
CANONICAL = "http://localhost:8080/fhir"
AGGREGATE_QUESTIONNAIRE = f"{CANONICAL}/Questionnaire/BfMAe6Itzgt"


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


_ASSIGNMENT_EXTENSION_URL = f"{CANONICAL}/StructureDefinition/d2-organisation-unit-assignment"
_ASSIGNMENT_LIST_ID = "d2-ds-BfMAe6Itzgt-org-units"

#: The one unit the fixture's assignment admits - the golden aggregate response reports for it.
_ADMITTED_LOCATION = "Location/ImspTQPwCqd"


def _assignment_list(*references: str) -> dict[str, Any]:
    """The published assignment artifact, in the shape the generate target writes it."""
    return {
        "resourceType": "List",
        "id": _ASSIGNMENT_LIST_ID,
        "status": "current",
        "mode": "snapshot",
        "title": "Child Health - assigned organisation units",
        "entry": [{"item": {"reference": reference}} for reference in references],
    }


def _scoped_store(store: ResourceStore, *references: str) -> ResourceStore:
    """The golden store with the aggregate form scoped by an assignment List naming `references`."""
    entries: list[StoreEntry] = []
    for entry in store.entries:
        if entry.canonical_url != AGGREGATE_QUESTIONNAIRE:
            entries.append(entry)
            continue
        body = copy.deepcopy(entry.body)
        extensions = list(body.get("extension") or [])
        extensions.append(
            {
                "url": _ASSIGNMENT_EXTENSION_URL,
                "valueReference": {"reference": f"List/{_ASSIGNMENT_LIST_ID}"},
            }
        )
        body["extension"] = extensions
        entries.append(entry.model_copy(update={"body": body}))
    entries.append(
        StoreEntry(
            resource_type="List",
            resource_id=_ASSIGNMENT_LIST_ID,
            source="test",
            body=_assignment_list(*references),
        )
    )
    return ResourceStore(entries=tuple(entries))


def _assignment_issues(issues: tuple[CaptureIssue, ...]) -> tuple[CaptureIssue, ...]:
    """Only the issues the assignment phase raised."""
    return tuple(issue for issue in issues if issue.code == "business-rule")


def test_a_form_publishing_no_assignment_is_scoped_to_the_whole_registry(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """Absence means every published unit may report the form, which is what a client already assumed."""
    aggregate_response["subject"] = {"reference": "Location/NowhereNear"}

    accepted = _accept(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert _assignment_issues(accepted.warnings) == ()


def test_a_subject_inside_the_assignment_is_silent(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The form's own assignment admits the unit the golden reports for, so nothing is noted."""
    store = _scoped_store(capture_store, _ADMITTED_LOCATION, "Location/O6uvpzGd5pu")

    accepted = _accept(aggregate_response, capture_indexes, capture_naming, store)

    assert accepted.warnings == ()


def test_a_subject_outside_the_assignment_is_a_warning_by_default(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The submission is stored and the receipt says DHIS2 will refuse the write."""
    store = _scoped_store(capture_store, "Location/O6uvpzGd5pu")

    accepted = _accept(aggregate_response, capture_indexes, capture_naming, store)

    noted = _assignment_issues(accepted.warnings)
    assert len(noted) == 1
    assert noted[0].severity == "warning"
    assert noted[0].expression == "QuestionnaireResponse.subject.reference"
    assert noted[0].diagnostics is not None
    assert f"`{_ADMITTED_LOCATION}` is not in the form's organisation-unit assignment" in noted[0].diagnostics
    assert "E1029" in noted[0].diagnostics


def test_a_strict_facade_refuses_the_subject_a_lenient_one_warns_about(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The dial that grades a coded answer grades the organisation unit the same way."""
    store = _scoped_store(capture_store, "Location/O6uvpzGd5pu")

    rejection = _refuse(aggregate_response, capture_indexes, capture_naming, store, strict_codes=True)

    assert rejection.http_status == 422
    refused = _assignment_issues(_errors(rejection))
    assert len(refused) == 1
    assert refused[0].expression == "QuestionnaireResponse.subject.reference"


def test_an_empty_assignment_admits_nothing(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A form assigned to no published unit is a form no published unit may report for."""
    store = _scoped_store(capture_store)

    accepted = _accept(aggregate_response, capture_indexes, capture_naming, store)

    assert len(_assignment_issues(accepted.warnings)) == 1


def test_an_assignment_the_facade_does_not_serve_checks_nothing(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A named List the store does not hold is the project's incomplete build, not the client's mistake."""
    store = _scoped_store(capture_store, "Location/O6uvpzGd5pu")
    without_list = ResourceStore(entries=tuple(entry for entry in store.entries if entry.resource_type != "List"))

    accepted = _accept(aggregate_response, capture_indexes, capture_naming, without_list)

    assert _assignment_issues(accepted.warnings) == ()


@pytest.mark.parametrize("strict_codes", [False, True])
def test_a_tracker_events_organisation_unit_extension_is_graded_the_same_way(
    tracker_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
    strict_codes: bool,
) -> None:
    """A tracker event carries its unit on an extension, and the assignment reads it from there."""
    canonical = tracker_response["questionnaire"]
    entries: list[StoreEntry] = []
    for entry in capture_store.entries:
        if entry.canonical_url != canonical:
            entries.append(entry)
            continue
        body = copy.deepcopy(entry.body)
        body["extension"] = [
            *(body.get("extension") or []),
            {"url": _ASSIGNMENT_EXTENSION_URL, "valueReference": {"reference": f"List/{_ASSIGNMENT_LIST_ID}"}},
        ]
        entries.append(entry.model_copy(update={"body": body}))
    entries.append(
        StoreEntry(
            resource_type="List",
            resource_id=_ASSIGNMENT_LIST_ID,
            source="test",
            body=_assignment_list("Location/SomewhereElse"),
        )
    )
    store = ResourceStore(entries=tuple(entries))

    if strict_codes:
        rejection = _refuse(tracker_response, capture_indexes, capture_naming, store, strict_codes=True)
        issues = _assignment_issues(_errors(rejection))
    else:
        issues = _assignment_issues(_accept(tracker_response, capture_indexes, capture_naming, store).warnings)

    assert len(issues) == 1
    assert issues[0].expression == "QuestionnaireResponse.extension"


def test_the_rejection_is_raised_with_every_other_phase_already_cleared(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The assignment phase runs after the form resolves, so it never masks an unreadable submission."""
    store = _scoped_store(capture_store, "Location/O6uvpzGd5pu")
    aggregate_response["questionnaire"] = f"{CANONICAL}/Questionnaire/NotServed01"

    with pytest.raises(CaptureRejection) as raised:
        validate_response(json.dumps(aggregate_response).encode(), capture_indexes, capture_naming, store, False)

    assert _assignment_issues(raised.value.issues) == ()


def _temporal_response(unit_reference: str) -> dict[str, Any]:
    """One submission against the temporal event form, answering its ORGANISATION_UNIT question."""
    return {
        "resourceType": "QuestionnaireResponse",
        "extension": [{"url": f"{CANONICAL}/StructureDefinition/d2-form-type", "valueCode": "event"}],
        "questionnaire": f"{CANONICAL}/Questionnaire/PrTemporal1",
        "status": "completed",
        "subject": {"reference": _ADMITTED_LOCATION},
        "authored": "2026-07-25T16:00:00Z",
        "item": [{"linkId": "DeVisitUnit1", "answer": [{"valueReference": {"reference": unit_reference}}]}],
    }


def _temporal_store(store: ResourceStore, *references: str) -> ResourceStore:
    """The golden store with the temporal event form scoped by an assignment List naming `references`."""
    canonical = f"{CANONICAL}/Questionnaire/PrTemporal1"
    entries: list[StoreEntry] = []
    for entry in store.entries:
        if entry.canonical_url != canonical:
            entries.append(entry)
            continue
        body = copy.deepcopy(entry.body)
        body["extension"] = [
            *(body.get("extension") or []),
            {"url": _ASSIGNMENT_EXTENSION_URL, "valueReference": {"reference": f"List/{_ASSIGNMENT_LIST_ID}"}},
        ]
        entries.append(entry.model_copy(update={"body": body}))
    entries.append(
        StoreEntry(
            resource_type="List",
            resource_id=_ASSIGNMENT_LIST_ID,
            source="test",
            body=_assignment_list(*references),
        )
    )
    return ResourceStore(entries=tuple(entries))


def test_an_organisation_unit_answer_inside_the_assignment_is_silent(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """An ORGANISATION_UNIT answer is checked against the same List the subject is."""
    store = _temporal_store(capture_store, _ADMITTED_LOCATION)

    accepted = _accept(_temporal_response(_ADMITTED_LOCATION), capture_indexes, capture_naming, store)

    assert _assignment_issues(accepted.warnings) == ()


@pytest.mark.parametrize("strict_codes", [False, True])
def test_an_organisation_unit_answer_outside_the_assignment_grades_on_the_dial(
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
    strict_codes: bool,
) -> None:
    """The answer takes the same warning-or-refusal grading the subject takes."""
    store = _temporal_store(capture_store, _ADMITTED_LOCATION)
    body = _temporal_response("Location/O6uvpzGd5pu")

    if strict_codes:
        issues = _assignment_issues(_errors(_refuse(body, capture_indexes, capture_naming, store, strict_codes=True)))
    else:
        issues = _assignment_issues(_accept(body, capture_indexes, capture_naming, store).warnings)

    assert len(issues) == 1
    assert issues[0].expression == "QuestionnaireResponse.item.where(linkId='DeVisitUnit1')"
