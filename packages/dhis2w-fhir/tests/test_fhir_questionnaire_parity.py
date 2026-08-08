"""Parity between the two questionnaire emitters: the built documents equal what SUSHI compiles.

`tests/data/questionnaire-sources/` holds the projections one generate run of the local DHIS2
stack fetched, and `tests/data/r4/` holds the resources SUSHI compiled from the FSH that same run
wrote. Rebuilding the documents from the sources and comparing them to the compiled output is
what pins the JSON emitter to the FSH one: an element the two paths disagree about fails here.

Regenerating the source fixtures, against a local stack holding the DHIS2 demo database plus the
seeded FHIR metadata (`make dhis2-up`, profile `local_basic`):

1. Read `sources`, the option-set list, and the attribute code index the way
   `service.generate_questionnaires` does - `_fetch_questionnaire_sources`, an unfiltered
   `optionSets` fetch of `id,name`, and `resolve_attribute_code_index` - under a default
   `GenerateConfig`.
2. Dump each to `sources.json`, `option-sets.json`, and `attribute-codes.json` with
   `model_dump_json(exclude_none=True)`.
3. Run `d2w fhir generate questionnaires` in the IG project the goldens came from, compile it
   with SUSHI, and copy the emitted `fsh-generated/resources/*.json` into `tests/data/r4/`.

The goldens are SUSHI's own output and are never edited by hand: when this test fails, the
builder is what changed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    OptionSetIn,
    QuestionnaireSourceIn,
    build_data_dictionary_documents,
    build_questionnaire_documents,
    option_set_identities,
)
from dhis2w_fhir.r4 import FhirBase

_SOURCE_DIRECTORY = Path(__file__).parent / "data" / "questionnaire-sources"
_GOLDEN_DIRECTORY = Path(__file__).parent / "data" / "r4"

#: The IG the goldens were compiled for - `[ig] canonical` and `[ig] status` of its `fhir.toml`.
_CANONICAL = "http://localhost:8080/fhir"

#: Every Questionnaire the run compiled: two data sets, two event programs, three tracker stages.
_QUESTIONNAIRE_IDS = [
    "A03MvHHogjR",
    "BfMAe6Itzgt",
    "EVTsupVis01",
    "PsAncVisit1",
    "TuL8IOPzpHh",
    "ZzYYXq4fJie",
    "lxAQ7Zs9VYR",
]


def _fixture(name: str) -> Any:
    """Read one committed source fixture."""
    return json.loads((_SOURCE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


def _sources() -> list[QuestionnaireSourceIn]:
    """The forms the run fetched, as the emitter projection."""
    return [QuestionnaireSourceIn.model_validate(entry) for entry in _fixture("sources")]


def _config() -> GenerateConfig:
    """The `[generate]` table the goldens were built under - every option left at its default."""
    return GenerateConfig()


def _built_questionnaires() -> dict[str, Any]:
    """Build the run's Questionnaires and index the emitted JSON by resource id."""
    sources = _sources()
    config = _config()
    option_sets = [OptionSetIn.model_validate(entry) for entry in _fixture("option-sets")]
    build = build_questionnaire_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities(option_sets, config),
        attribute_codes=AttributeCodeIndex.model_validate(_fixture("attribute-codes")),
    )
    assert build.notes == []
    return {str(questionnaire.id): _emitted(questionnaire) for questionnaire in build.questionnaires}


def _emitted(resource: FhirBase) -> Any:
    """One built resource as the JSON document it is served as."""
    return json.loads(resource.model_dump_json(exclude_none=True, by_alias=True))


def _golden(stem: str) -> Any:
    """One resource SUSHI compiled from the FSH the same run wrote."""
    return json.loads((_GOLDEN_DIRECTORY / f"{stem}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("uid", _QUESTIONNAIRE_IDS)
def test_a_built_questionnaire_equals_the_one_sushi_compiled(uid: str) -> None:
    """Every element SUSHI resolved from the FSH is on the built document, and nothing else is."""
    assert _built_questionnaires()[uid] == _golden(f"Questionnaire-{uid}")


def test_the_run_builds_exactly_the_questionnaires_it_compiled() -> None:
    """No form is silently dropped from - or added to - the document build."""
    assert sorted(_built_questionnaires()) == sorted(_QUESTIONNAIRE_IDS)


@pytest.mark.parametrize("code_system_id", ["d2-de-cs", "d2-coc-cs"])
def test_a_built_support_code_system_equals_the_one_sushi_compiled(code_system_id: str) -> None:
    """The data dictionary's concepts, properties, and count match the compiled support terminology."""
    build = build_data_dictionary_documents(_sources(), _config(), _CANONICAL, ig_status="draft")
    built = {str(code_system.id): _emitted(code_system) for code_system in build.code_systems}
    assert built[code_system_id] == _golden(f"CodeSystem-{code_system_id}")


@pytest.mark.parametrize("value_set_id", ["d2-de-vs", "d2-coc-vs"])
def test_a_built_support_value_set_equals_the_one_sushi_compiled(value_set_id: str) -> None:
    """Each support ValueSet includes its whole CodeSystem, exactly as the compiled pair does."""
    build = build_data_dictionary_documents(_sources(), _config(), _CANONICAL, ig_status="draft")
    built = {str(value_set.id): _emitted(value_set) for value_set in build.value_sets}
    assert built[value_set_id] == _golden(f"ValueSet-{value_set_id}")
