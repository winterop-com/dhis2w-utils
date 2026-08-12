"""Parity for the translated questionnaire surface: the built documents equal what SUSHI compiles.

The twin of `test_fhir_questionnaire_parity.py` over a corpus that carries translations. The
committed forms there are untranslated, which pins the shape of a guide in one language and says
nothing about the shapes translations take; `tests/data/translated-sources/` is the same fetch
against a stack whose forms are translated into Lao and French, and `tests/data/r4-translated/`
holds the resources SUSHI compiled from the FSH that run wrote.

Only the resources translations actually reached are committed as goldens. A form nobody
translated compiles to the document the untranslated corpus already pins, and a second copy of it
here would pin nothing new.

The two shapes under test are the two FHIR offers, and each is written twice - once as FSH for
SUSHI, once as JSON for the served facade - so the compile is what proves the FSH spelling is
real: `^designation` on the dictionary CodeSystem concepts, and the standard translation
extension on `Questionnaire.title` and `Questionnaire.item.text`, which SUSHI resolves onto the
`_title` and `_text` primitive siblings.

Regenerating the fixtures, against a local stack holding the DHIS2 demo database plus the seeded
FHIR metadata (`make dhis2-up`, profile `local_basic`, which runs `seed_form_translations`):

1. Read `sources`, the option-set list, the categories, and the attribute code index the way
   `service.generate_questionnaires` does, under a default `GenerateConfig`.
2. Dump each into `tests/data/translated-sources/`.
   The assignment plan is the fifth: it names the organisation-unit assignment List each form
   references, which `build_assignment_artifacts` resolves from a fetch the document build does
   not make.
3. Run `d2w fhir generate` in an IG project whose `sushi-config.yaml` states
   `canonical: http://localhost:8080/fhir` and `status: draft`, compile it with SUSHI, and copy
   the emitted resources this module names into `tests/data/r4-translated/`.

The goldens are SUSHI's own output and are never edited by hand: when this test fails, the
builder or the template is what changed.
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
from dhis2w_fhir.resources.categories.schemas import CategoryIn
from dhis2w_fhir.resources.questionnaires.assignments import AssignmentPlan

_SOURCE_DIRECTORY = Path(__file__).parent / "data" / "translated-sources"
_GOLDEN_DIRECTORY = Path(__file__).parent / "data" / "r4-translated"

#: The IG the goldens were compiled for - `[ig] canonical` and `[ig] status` of its `fhir.toml`.
_CANONICAL = "http://localhost:8080/fhir"

#: The forms a translation reached: two registration forms, three stages, an event program, a data set.
_TRANSLATED_QUESTIONNAIRE_IDS = [
    "A03MvHHogjR",
    "BfMAe6Itzgt",
    "EVTsupVis01",
    "IpHINAT79UW",
    "PrAncCare01",
    "PsAncVisit1",
    "ScStageAaa1",
    "ScStageBbb1",
    "nEenWmSyUEp",
]

#: One French designation of a data element, which `locales = ["lo"]` has to drop.
_FRENCH_BCG = "Doses de BCG administrees"

#: The Lao designation beside it, which the same narrowing has to keep.
_LAO_BCG = "ຈຳນວນເຂັມ BCG ທີ່ໃຫ້"


def _fixture(name: str) -> Any:
    """Read one committed source fixture."""
    return json.loads((_SOURCE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


def _sources() -> list[QuestionnaireSourceIn]:
    """The translated forms the run fetched, as the emitter projection."""
    return [QuestionnaireSourceIn.model_validate(entry) for entry in _fixture("sources")]


def _config(locales: list[str] | None = None) -> GenerateConfig:
    """The `[generate]` table the goldens were built under - every option, `locales` included, at its default."""
    return GenerateConfig() if locales is None else GenerateConfig(locales=locales)


def _emitted(resource: FhirBase) -> Any:
    """One built resource as the JSON document it is served as."""
    return json.loads(resource.model_dump_json(exclude_none=True, by_alias=True))


def _golden(stem: str) -> Any:
    """One resource SUSHI compiled from the FSH the same run wrote."""
    return json.loads((_GOLDEN_DIRECTORY / f"{stem}.json").read_text(encoding="utf-8"))


def _built_questionnaires(locales: list[str] | None = None) -> dict[str, Any]:
    """Build the run's Questionnaires and index the emitted JSON by resource id."""
    sources = _sources()
    config = _config(locales)
    option_sets = [OptionSetIn.model_validate(entry) for entry in _fixture("option-sets")]
    build = build_questionnaire_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities(option_sets, config),
        attribute_codes=AttributeCodeIndex.model_validate(_fixture("attribute-codes")),
        assignments=AssignmentPlan.model_validate(_fixture("assignment-plan")),
        attribute_combos=build_attribute_combo_artifacts(sources, config, _CANONICAL, ig_status="draft").plan,
    )
    return {str(questionnaire.id): _emitted(questionnaire) for questionnaire in build.questionnaires}


def _built_code_systems(locales: list[str] | None = None) -> dict[str, Any]:
    """Build the run's data dictionary and index the emitted CodeSystem JSON by resource id."""
    sources = _sources()
    config = _config(locales)
    categories = [CategoryIn.model_validate(entry) for entry in _fixture("categories")]
    build = build_data_dictionary_documents(
        sources,
        config,
        _CANONICAL,
        ig_status="draft",
        decomposition=build_category_decomposition(sources, categories, config, _CANONICAL),
    )
    return {str(code_system.id): _emitted(code_system) for code_system in build.code_systems}


@pytest.mark.parametrize("uid", _TRANSLATED_QUESTIONNAIRE_IDS)
def test_a_translated_questionnaire_equals_the_one_sushi_compiled(uid: str) -> None:
    """The `_title` and `_text` siblings the builder writes are the ones SUSHI resolved from the FSH."""
    assert _built_questionnaires()[uid] == _golden(f"Questionnaire-{uid}")


@pytest.mark.parametrize("code_system_id", ["d2-de-cs", "d2-tea-cs"])
def test_a_translated_dictionary_code_system_equals_the_one_sushi_compiled(code_system_id: str) -> None:
    """Every concept designation the builder writes is the one SUSHI resolved from `^designation`."""
    assert _built_code_systems()[code_system_id] == _golden(f"CodeSystem-{code_system_id}")


def test_every_form_a_translation_reached_is_covered_by_a_golden() -> None:
    """The golden list is the whole translated surface - a form gaining a translation joins it."""
    reached = {
        uid
        for uid, document in _built_questionnaires().items()
        if "translation" in json.dumps(document, ensure_ascii=False)
    }
    assert sorted(reached) == sorted(_TRANSLATED_QUESTIONNAIRE_IDS)


def test_configured_locales_narrow_the_whole_questionnaire_surface() -> None:
    """`locales = ["lo"]` drops every French designation and translation extension, keeping the Lao ones."""
    narrowed = json.dumps([_built_questionnaires(["lo"]), _built_code_systems(["lo"])], ensure_ascii=False)
    assert _LAO_BCG in narrowed
    assert _FRENCH_BCG not in narrowed
    assert '"fr"' not in narrowed


def test_a_form_named_question_is_labelled_from_its_form_name_translation() -> None:
    """A question DHIS2 gives a form name to takes its `_text` from FORM_NAME and its concept from NAME."""
    item = next(entry for entry in _built_questionnaires()["A03MvHHogjR"]["item"] if entry["linkId"] == "a3kGcGDCuk6")
    contents = [
        part["valueString"]
        for extension in item["_text"]["extension"]
        for part in extension["extension"]
        if part["url"] == "content"
    ]
    assert item["text"] == "Apgar Score"
    assert contents == ["Score d'Apgar", "ຄະແນນ Apgar"]

    concept = next(entry for entry in _built_code_systems()["d2-de-cs"]["concept"] if entry["code"] == "a3kGcGDCuk6")
    assert concept["display"] == "MCH Apgar Score"
    assert [designation["value"] for designation in concept["designation"]] == [
        "Score d'Apgar SMI",
        "ຄະແນນ Apgar ຂອງແມ່ ແລະ ເດັກ",
    ]


def test_a_stage_title_is_translated_only_where_both_halves_are() -> None:
    """A stage form is titled `<program> - <stage>`, and each translation joins two translated halves."""
    contents = [
        part["valueString"]
        for extension in _built_questionnaires()["PsAncVisit1"]["_title"]["extension"]
        for part in extension["extension"]
        if part["url"] == "content"
    ]
    assert contents == ["Suivi des CPN - Visite de CPN", "ຕິດຕາມການຝາກທ້ອງ - ການມາກວດຝາກທ້ອງ"]
