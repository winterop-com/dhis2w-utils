"""Resolving a received code back to the DHIS2 option it names, in either spelling the IG publishes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from dhis2w_fhir_serve.capture import (
    AmbiguousCodingError,
    CodingResolver,
    CodingResolverSet,
    UnresolvableCodingError,
)
from dhis2w_fhir_serve.store import ResourceStore

#: The canonical the dhis2w-fhir goldens were compiled under, as `capture_project` serves them.
CANONICAL = "http://localhost:8080/fhir"

INFANT_FEEDING_CODE_SYSTEM = f"{CANONICAL}/CodeSystem/d2-os-x31y45jvIQL-cs"

#: The first concept of the `CodeSystem-richest` golden, which publishes option UIDs as concept codes.
HYGIENE_OPTION_UID = "s6eRzXxw4Rq"
HYGIENE_OPTION_CODE = "1.0.0.0"

Golden = Callable[[str], dict[str, Any]]


def _code_mode_code_system() -> dict[str, Any]:
    """A CodeSystem generated with `concept_code_source = "code"`: option codes as concepts, UIDs carried."""
    return {
        "resourceType": "CodeSystem",
        "id": "d2-os-b4P0xzW5wcD-cs",
        "url": f"{CANONICAL}/CodeSystem/d2-os-b4P0xzW5wcD-cs",
        "status": "draft",
        "content": "complete",
        "property": [{"code": "dhis2-id", "description": "DHIS2 option UID.", "type": "code"}],
        "concept": [
            {
                "code": HYGIENE_OPTION_CODE,
                "display": "I. Hygiene and health Promotion",
                "property": [{"code": "dhis2-id", "valueCode": HYGIENE_OPTION_UID}],
            }
        ],
    }


def _substituted_code_system() -> dict[str, Any]:
    """A code-mode CodeSystem from a substitute-posture run: the code hyphenated, the DHIS2 one beside it."""
    return {
        "resourceType": "CodeSystem",
        "id": "d2-os-OsSpc000001-cs",
        "url": f"{CANONICAL}/CodeSystem/d2-os-OsSpc000001-cs",
        "status": "draft",
        "content": "complete",
        "property": [
            {"code": "dhis2-id", "description": "DHIS2 option UID.", "type": "code"},
            {"code": "dhis2-code", "description": "DHIS2 option code.", "type": "string"},
        ],
        "concept": [
            {
                "code": "Pre-eclampsia",
                "display": "Pre eclampsia",
                "property": [
                    {"code": "dhis2-id", "valueCode": "OpSpc000001"},
                    {"code": "dhis2-code", "valueString": "Pre eclampsia"},
                ],
            }
        ],
    }


def _ambiguous_code_system() -> dict[str, Any]:
    """A CodeSystem where two options were given the same DHIS2 code - a defect the server cannot resolve."""
    return {
        "resourceType": "CodeSystem",
        "id": "d2-os-clash-cs",
        "url": f"{CANONICAL}/CodeSystem/d2-os-clash-cs",
        "status": "draft",
        "content": "complete",
        "concept": [
            {"code": "aaaaaaaaaa1", "display": "One", "property": [{"code": "dhis2-code", "valueString": "SAME"}]},
            {"code": "aaaaaaaaaa2", "display": "Two", "property": [{"code": "dhis2-code", "valueString": "SAME"}]},
        ],
    }


def _resolver(body: dict[str, Any]) -> CodingResolver:
    """A resolver over one code system body, failing the test when the body cannot be read."""
    resolver = CodingResolver.from_code_system_json(body)
    assert resolver is not None
    return resolver


def test_an_id_mode_concept_carries_the_option_uid_and_its_dhis2_code(load_golden: Golden) -> None:
    resolver = _resolver(load_golden("CodeSystem-richest.json"))

    resolved = resolver.resolve(HYGIENE_OPTION_UID, strict=False)

    assert resolved.option_uid == HYGIENE_OPTION_UID
    assert resolved.dhis2_code == HYGIENE_OPTION_CODE
    assert resolved.concept_code == HYGIENE_OPTION_UID
    assert resolved.matched_by == "concept-code"


def test_a_dhis2_code_resolves_on_the_last_tier(load_golden: Golden) -> None:
    resolver = _resolver(load_golden("CodeSystem-richest.json"))

    resolved = resolver.resolve(HYGIENE_OPTION_CODE, strict=False)

    assert resolved.option_uid == HYGIENE_OPTION_UID
    assert resolved.matched_by == "dhis2-code"


def test_a_strict_server_takes_the_concept_code_and_nothing_else(load_golden: Golden) -> None:
    resolver = _resolver(load_golden("CodeSystem-richest.json"))

    assert resolver.resolve(HYGIENE_OPTION_UID, strict=True).matched_by == "concept-code"
    with pytest.raises(UnresolvableCodingError, match=HYGIENE_OPTION_CODE):
        resolver.resolve(HYGIENE_OPTION_CODE, strict=True)


def test_a_code_outside_the_terminology_is_unresolvable(load_golden: Golden) -> None:
    resolver = _resolver(load_golden("CodeSystem-richest.json"))

    with pytest.raises(UnresolvableCodingError, match="not in the served terminology") as raised:
        resolver.resolve("never-published", strict=False)

    assert raised.value.system == resolver.system


def test_a_code_mode_concept_carries_the_option_code_and_its_uid() -> None:
    resolver = _resolver(_code_mode_code_system())

    resolved = resolver.resolve(HYGIENE_OPTION_CODE, strict=False)

    assert resolved.option_uid == HYGIENE_OPTION_UID
    assert resolved.dhis2_code == HYGIENE_OPTION_CODE
    assert resolved.concept_code == HYGIENE_OPTION_CODE
    assert resolved.matched_by == "concept-code"


def test_a_substituted_concept_resolves_to_the_dhis2_code_the_instance_holds() -> None:
    """A substitute-posture guide publishes `Pre-eclampsia` and states `Pre eclampsia` beside it.

    Whichever spelling the client sends, the option lowers to the DHIS2 code - the rewrite is the
    guide's, and DHIS2 never sees it.
    """
    resolver = _resolver(_substituted_code_system())

    published = resolver.resolve("Pre-eclampsia", strict=True)
    sent_as_dhis2 = resolver.resolve("Pre eclampsia", strict=False)

    assert published.concept_code == "Pre-eclampsia"
    assert published.dhis2_code == "Pre eclampsia"
    assert published.option_uid == "OpSpc000001"
    assert sent_as_dhis2.matched_by == "dhis2-code"
    assert sent_as_dhis2.dhis2_code == "Pre eclampsia"


def test_a_uid_sent_against_a_code_mode_system_resolves_on_the_uid_tier() -> None:
    resolver = _resolver(_code_mode_code_system())

    resolved = resolver.resolve(HYGIENE_OPTION_UID, strict=False)

    assert resolved.option_uid == HYGIENE_OPTION_UID
    assert resolved.concept_code == HYGIENE_OPTION_CODE
    assert resolved.matched_by == "option-uid"


def test_a_code_naming_two_options_is_ambiguous_whatever_the_strictness() -> None:
    resolver = _resolver(_ambiguous_code_system())

    with pytest.raises(AmbiguousCodingError, match="more than one option") as raised:
        resolver.resolve("SAME", strict=False)

    assert {candidate.option_uid for candidate in raised.value.candidates} == {"aaaaaaaaaa1", "aaaaaaaaaa2"}


def test_a_body_that_is_not_a_readable_code_system_builds_no_resolver() -> None:
    assert CodingResolver.from_code_system_json({"resourceType": "CodeSystem", "concept": "not a list"}) is None
    assert CodingResolver.from_code_system_json({"resourceType": "CodeSystem", "id": "no-url"}) is None


def test_the_resolver_set_reads_a_served_code_system_once(capture_store: ResourceStore) -> None:
    resolvers = CodingResolverSet(store=capture_store)

    first = resolvers.for_system(INFANT_FEEDING_CODE_SYSTEM)
    second = resolvers.for_system(INFANT_FEEDING_CODE_SYSTEM)

    assert first is not None
    assert first is second
    assert first.resolve("odMfnhhpjUj", strict=True).option_uid == "odMfnhhpjUj"


def test_the_resolver_set_has_nothing_for_a_system_the_facade_does_not_serve(capture_store: ResourceStore) -> None:
    resolvers = CodingResolverSet(store=capture_store)

    assert resolvers.for_system(f"{CANONICAL}/CodeSystem/never-published") is None
    assert resolvers.for_system(f"{CANONICAL}/Questionnaire/BfMAe6Itzgt") is None
