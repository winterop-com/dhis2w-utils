"""Capture against the attribute option combo a form declares, on both positions of the dial.

The third key of a data value set is stated per form: a data set on the default category combo
declares no vocabulary and its responses name nothing, and a data set on a non-default one declares
a ValueSet its responses have to draw one concept from. So the cases that matter are the four the
design turns on - absent on both sides is silent, a declared vocabulary left unnamed grades, a
combo named against a form that declares none grades, and a concept the store really holds passes -
plus the terminology grading a coded answer already takes.

The submissions are the dhis2w-fhir goldens, so a test that accepts them is a test that the facade
accepts the documented contract.
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
    build_capture_index,
    validate_response,
)
from dhis2w_fhir_serve.store import ResourceStore, StoreEntry
from fixture_project import ATTRIBUTE_COMBO_CODE_SYSTEM, ATTRIBUTE_COMBO_VALUE_SET, CAPTURE_CANONICAL

#: The form on the non-default category combo, and the one on the default combo beside it.
COMBO_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/TuL8IOPzpHh"
DEFAULT_QUESTIONNAIRE = f"{CAPTURE_CANONICAL}/Questionnaire/BfMAe6Itzgt"

COMBO_EXTENSION_URL = f"{CAPTURE_CANONICAL}/StructureDefinition/d2-attribute-option-combo"

#: One concept the published CodeSystem really holds - the golden response is filed under it.
PUBLISHED_CONCEPT = "BqblOcSwGey"

#: The DHIS2 category option combo code of another concept, which is the spelling the contract
#: does not ask for under `concept_code_source = "id"`.
PUBLISHED_DHIS2_CODE = "COC_1452092"


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
    strict_codes: bool = True,
) -> CaptureRejection:
    """Validate one submission, failing the test when it is accepted."""
    with pytest.raises(CaptureRejection) as raised:
        validate_response(json.dumps(body).encode(), indexes, naming, store, strict_codes)
    return raised.value


def _combo_issues(issues: tuple[CaptureIssue, ...]) -> tuple[CaptureIssue, ...]:
    """Only the issues that name the attribute option combo, whichever code they carry."""
    return tuple(
        issue
        for issue in issues
        if issue.diagnostics is not None and "attribute option combo" in issue.diagnostics.lower()
    )


def _without_combo(response: dict[str, Any]) -> dict[str, Any]:
    """The same submission with its D2AttributeOptionCombo extension dropped."""
    body = copy.deepcopy(response)
    body["extension"] = [entry for entry in body.get("extension") or [] if entry.get("url") != COMBO_EXTENSION_URL]
    return body


def _with_combo(response: dict[str, Any], coding: dict[str, Any]) -> dict[str, Any]:
    """The same submission filed under one hand-written coding instead of the one it carries."""
    body = _without_combo(response)
    body["extension"] = [*(body.get("extension") or []), {"url": COMBO_EXTENSION_URL, "valueCoding": coding}]
    return body


def test_the_golden_response_names_a_concept_the_published_vocabulary_holds(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The IG's own example of the non-default-combo data set is accepted with nothing noted."""
    accepted = _accept(attribute_combo_response, capture_indexes, capture_naming, capture_store)

    assert _combo_issues(accepted.warnings) == ()


def test_a_default_combo_form_declaring_nothing_checks_nothing(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """Absence on both sides means the default attribute option combo, which is what a consumer assumed."""
    accepted = _accept(aggregate_response, capture_indexes, capture_naming, capture_store)

    assert _combo_issues(accepted.warnings) == ()


def test_the_index_reads_the_declared_vocabulary_and_the_code_system_behind_it(
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The declaration is read off `D2AttributeOptionCombos`, and its CodeSystem off the served ValueSet."""
    combo_entry = capture_store.by_canonical(COMBO_QUESTIONNAIRE)
    default_entry = capture_store.by_canonical(DEFAULT_QUESTIONNAIRE)
    assert combo_entry is not None
    assert default_entry is not None

    declared = build_capture_index(combo_entry.body, capture_naming, capture_store).attribute_option_combos
    silent = build_capture_index(default_entry.body, capture_naming, capture_store).attribute_option_combos

    assert declared is not None
    assert declared.value_set == ATTRIBUTE_COMBO_VALUE_SET
    assert declared.system == ATTRIBUTE_COMBO_CODE_SYSTEM
    assert silent is None


def test_a_declared_combo_the_response_does_not_name_is_a_warning_by_default(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The submission is stored and the receipt says DHIS2 will refuse the write."""
    accepted = _accept(_without_combo(attribute_combo_response), capture_indexes, capture_naming, capture_store)

    noted = _combo_issues(accepted.warnings)
    assert len(noted) == 1
    assert noted[0].severity == "warning"
    assert noted[0].expression == "QuestionnaireResponse.extension"
    assert noted[0].diagnostics is not None
    assert ATTRIBUTE_COMBO_VALUE_SET in noted[0].diagnostics
    assert "E8023" in noted[0].diagnostics


def test_a_strict_facade_refuses_the_missing_combo_a_lenient_one_warns_about(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The dial that grades a coded answer and an organisation unit grades the third key the same way."""
    rejection = _refuse(_without_combo(attribute_combo_response), capture_indexes, capture_naming, capture_store)

    assert rejection.http_status == 422
    refused = _combo_issues(tuple(issue for issue in rejection.issues if issue.is_error()))
    assert len(refused) == 1
    assert refused[0].expression == "QuestionnaireResponse.extension"
    assert refused[0].diagnostics is not None
    assert "E8023" in refused[0].diagnostics


@pytest.mark.parametrize("strict_codes", [False, True])
def test_a_combo_named_against_a_form_that_declares_none_grades_on_the_same_dial(
    aggregate_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
    strict_codes: bool,
) -> None:
    """The mirror case: a combo the payload has no field for would be stored and silently not written."""
    body = _with_combo(aggregate_response, {"system": ATTRIBUTE_COMBO_CODE_SYSTEM, "code": PUBLISHED_CONCEPT})

    if strict_codes:
        rejection = _refuse(body, capture_indexes, capture_naming, capture_store)
        issues = _combo_issues(tuple(issue for issue in rejection.issues if issue.is_error()))
    else:
        issues = _combo_issues(_accept(body, capture_indexes, capture_naming, capture_store).warnings)

    assert len(issues) == 1
    assert issues[0].expression == "QuestionnaireResponse.extension"
    assert issues[0].diagnostics is not None
    assert "default attribute option combo" in issues[0].diagnostics


@pytest.mark.parametrize("strict_codes", [False, True])
def test_a_combo_the_published_vocabulary_does_not_hold_grades_on_the_dial(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
    strict_codes: bool,
) -> None:
    """A concept the store does not hold is drift with the instance, which is what the dial is for."""
    body = _with_combo(attribute_combo_response, {"system": ATTRIBUTE_COMBO_CODE_SYSTEM, "code": "Nowhere0001"})

    if strict_codes:
        rejection = _refuse(body, capture_indexes, capture_naming, capture_store)
        issues = _combo_issues(tuple(issue for issue in rejection.issues if issue.is_error()))
    else:
        issues = _combo_issues(_accept(body, capture_indexes, capture_naming, capture_store).warnings)

    assert len(issues) == 1
    assert issues[0].code == "code-invalid"
    assert issues[0].diagnostics is not None
    assert "E8023" in issues[0].diagnostics


def test_a_combo_sent_in_the_dhis2_spelling_resolves_and_is_noted(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The published CodeSystem carries both spellings, so the other one still names exactly one combo."""
    body = _with_combo(attribute_combo_response, {"system": ATTRIBUTE_COMBO_CODE_SYSTEM, "code": PUBLISHED_DHIS2_CODE})

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    noted = _combo_issues(accepted.warnings)
    assert len(noted) == 1
    assert noted[0].severity == "warning"
    assert noted[0].diagnostics is not None
    assert "the contract expects concept code" in noted[0].diagnostics


def test_a_combo_coded_from_another_system_is_refused_whatever_the_dial(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """Naming a different vocabulary is a malformed document rather than drift, exactly as a coded answer is."""
    body = _with_combo(
        attribute_combo_response,
        {"system": f"{CAPTURE_CANONICAL}/CodeSystem/d2-coc-cs", "code": PUBLISHED_CONCEPT},
    )

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store, strict_codes=False)

    refused = _combo_issues(tuple(issue for issue in rejection.issues if issue.is_error()))
    assert len(refused) == 1
    assert refused[0].code == "code-invalid"


def test_a_combo_coding_carrying_no_code_is_refused(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A coding naming a system and nothing else says which vocabulary, not which combo."""
    body = _with_combo(attribute_combo_response, {"system": ATTRIBUTE_COMBO_CODE_SYSTEM})

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store, strict_codes=False)

    assert _combo_issues(tuple(issue for issue in rejection.issues if issue.is_error()))


def test_two_combos_on_one_response_grade_as_naming_none(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """The aggregate profile slices the extension `0..1`, and two of them name no single third key."""
    body = _with_combo(attribute_combo_response, {"system": ATTRIBUTE_COMBO_CODE_SYSTEM, "code": PUBLISHED_CONCEPT})
    body["extension"] = [
        *(body.get("extension") or []),
        {"url": COMBO_EXTENSION_URL, "valueCoding": {"system": ATTRIBUTE_COMBO_CODE_SYSTEM, "code": "pO5CEqK6c1s"}},
    ]

    accepted = _accept(body, capture_indexes, capture_naming, capture_store)

    noted = _combo_issues(accepted.warnings)
    assert len(noted) == 1
    assert noted[0].diagnostics is not None
    assert "not 2" in noted[0].diagnostics


def test_a_vocabulary_the_facade_does_not_serve_stores_the_combo_unchecked(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """An unpublished ValueSet is the project's incomplete build, not the client's mistake."""
    without_pair = ResourceStore(
        entries=tuple(
            entry
            for entry in capture_store.entries
            if entry.canonical_url not in {ATTRIBUTE_COMBO_VALUE_SET, ATTRIBUTE_COMBO_CODE_SYSTEM}
        )
    )

    accepted = _accept(attribute_combo_response, capture_indexes, capture_naming, without_pair)

    noted = _combo_issues(accepted.warnings)
    assert len(noted) == 1
    assert noted[0].severity == "warning"
    assert noted[0].code == "not-found"


def test_the_phase_runs_after_the_form_resolves(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A submission naming a questionnaire this facade does not serve never reaches the third-key phase."""
    body = _without_combo(attribute_combo_response)
    body["questionnaire"] = f"{CAPTURE_CANONICAL}/Questionnaire/NotServed01"

    rejection = _refuse(body, capture_indexes, capture_naming, capture_store, strict_codes=False)

    assert _combo_issues(rejection.issues) == ()


def test_an_unreadable_value_set_leaves_the_declaration_standing_and_unchecked(
    attribute_combo_response: dict[str, Any],
    capture_indexes: CaptureIndexCache,
    capture_naming: CaptureNaming,
    capture_store: ResourceStore,
) -> None:
    """A ValueSet the R4 models cannot read is a served document the facade cannot expand, not a missing rule."""
    entries: list[StoreEntry] = []
    for entry in capture_store.entries:
        if entry.canonical_url != ATTRIBUTE_COMBO_VALUE_SET:
            entries.append(entry)
            continue
        entries.append(entry.model_copy(update={"body": {"resourceType": "ValueSet", "id": entry.resource_id}}))

    accepted = _accept(
        _without_combo(attribute_combo_response), capture_indexes, capture_naming, ResourceStore(entries=tuple(entries))
    )

    noted = _combo_issues(accepted.warnings)
    assert len(noted) == 1
    assert "E8023" in (noted[0].diagnostics or "")
