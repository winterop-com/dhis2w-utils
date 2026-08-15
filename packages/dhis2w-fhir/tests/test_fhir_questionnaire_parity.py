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

`categories.json` is the fourth source fixture, read the way `service.generate_questionnaires`
reads it - `_fetch_categories` under the same default `GenerateConfig` - because both combo
vocabularies decompose their concepts into the categories the same run publishes. The combos
state what they are composed of on `sources.json` itself: `category_uids` on each category combo
and `category_option_uids` on each of its option combos, which is what the questionnaire fetch
now asks for.

The goldens are SUSHI's own output and are never edited by hand: when this test fails, the
builder is what changed. The compile is a plain `npx fsh-sushi .` over a project whose
`input/fsh` holds the foundation, the organisation-unit profiles and level terminology, the
attribute-option-combo pair, and the questionnaires, and whose `input/resources` holds the
option-set and category JSON those forms bind by canonical - SUSHI resolves nothing it cannot
see, so a project missing any of them reports errors that are about the project rather than
about the emitter.

`sources.json` holds the run's own selection - two data sets, two event programs, three tracker
stages - and a re-harvest is filtered back to those seven UIDs. The tracker registration and
person-only forms are pinned by `test_fhir_registration.py` and `test_fhir_tracked_entity_forms.py`
against goldens of their own, which is why adding them here would overwrite a support pair that
belongs to another corpus.
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
    build_attribute_combo_artifacts,
    build_category_decomposition,
    build_data_dictionary_documents,
    build_questionnaire_documents,
    option_set_identities,
)
from dhis2w_fhir.r4 import FhirBase
from dhis2w_fhir.resources.categories.decomposition import CategoryDecomposition
from dhis2w_fhir.resources.categories.schemas import CategoryIn

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


def _categories() -> list[CategoryIn]:
    """The categories the same run publishes, which the combo vocabularies decompose their concepts into."""
    return [CategoryIn.model_validate(entry) for entry in _fixture("categories")]


def _decomposition() -> CategoryDecomposition:
    """What every category option combo of the run is composed of, resolved against those categories."""
    return build_category_decomposition(_sources(), _categories(), _config(), _CANONICAL)


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
        attribute_combos=build_attribute_combo_artifacts(sources, config, _CANONICAL, ig_status="draft").plan,
    )
    assert [note.message for note in build.notes] == []
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
    build = build_data_dictionary_documents(
        _sources(), _config(), _CANONICAL, ig_status="draft", decomposition=_decomposition()
    )
    built = {str(code_system.id): _emitted(code_system) for code_system in build.code_systems}
    assert built[code_system_id] == _golden(f"CodeSystem-{code_system_id}")


@pytest.mark.parametrize("value_set_id", ["d2-de-vs", "d2-coc-vs"])
def test_a_built_support_value_set_equals_the_one_sushi_compiled(value_set_id: str) -> None:
    """Each support ValueSet includes its whole CodeSystem, exactly as the compiled pair does."""
    build = build_data_dictionary_documents(
        _sources(), _config(), _CANONICAL, ig_status="draft", decomposition=_decomposition()
    )
    built = {str(value_set.id): _emitted(value_set) for value_set in build.value_sets}
    assert built[value_set_id] == _golden(f"ValueSet-{value_set_id}")


@pytest.mark.parametrize("stem", ["CodeSystem-d2-aoc-idcDPkDtepR-cs", "ValueSet-d2-aoc-idcDPkDtepR-vs"])
def test_the_attribute_option_combo_pair_equals_the_one_sushi_compiled(stem: str) -> None:
    """The one data set on a non-default combo publishes the pair its Questionnaire binds by canonical."""
    build = build_attribute_combo_artifacts(
        _sources(), _config(), _CANONICAL, ig_status="draft", decomposition=_decomposition()
    )
    built = {artifact.relative_path.rsplit("/", 1)[-1]: json.loads(artifact.content) for artifact in build.artifacts}
    assert built[f"{stem}.json"] == _golden(stem)
