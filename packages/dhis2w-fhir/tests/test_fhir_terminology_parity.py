"""Parity for the FSH-authored terminology: the built documents equal what SUSHI compiles from the same data.

Four CodeSystem/ValueSet pairs are declared inside FSH files rather than written as JSON - the
form-type pair, the period-type pair, the organisation-unit level pair, and the whole-selection
organisation-unit pair. A live run compiles no FSH, so each pair has a JSON builder beside its
template, and both render the same Python vocabulary: `FORM_TYPE_DEFINITIONS`,
`PERIOD_TYPE_DEFINITIONS`, the levels a selection reaches, and the selection itself.

`tests/data/organisation-unit-sources/organisation-units.json` is the selection the two
organisation-unit pairs are built from - four units over four levels, one without a DHIS2 code and
one carrying a NAME translation, so every branch of the concept projection is compiled.

Regenerating the goldens, which are SUSHI's own output and are never edited by hand:

1. Write the FSH the same builders write - `build_foundation_artifacts` plus
   `build_organisation_unit_level_terminology` and `build_organisation_unit_terminology` over the
   committed selection - into the `input/fsh` tree of a project whose `sushi-config.yaml` states
   `canonical: http://localhost:8080/fhir` and `status: draft`.
2. Run SUSHI over it.
3. Copy the eight `fsh-generated/resources/{CodeSystem,ValueSet}-*.json` files this module names
   into `tests/data/r4/`.

When this test fails, the builder or the template is what changed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_fhir import (
    GenerateConfig,
    build_foundation_terminology_documents,
    build_organisation_unit_level_terminology_documents,
    build_organisation_unit_terminology_documents,
)
from dhis2w_fhir.foundation.documents import FoundationTerminologyBuild
from dhis2w_fhir.r4 import FhirBase
from dhis2w_fhir.resources.organisation_units.documents import OrganisationUnitTerminologyBuild
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn

_SOURCE_DIRECTORY = Path(__file__).parent / "data" / "organisation-unit-sources"
_GOLDEN_DIRECTORY = Path(__file__).parent / "data" / "r4"

#: The IG the goldens were compiled for - `[ig] canonical` and `[ig] status` of its `fhir.toml`.
_CANONICAL = "http://localhost:8080/fhir"


def _organisation_units() -> list[OrganisationUnitIn]:
    """The selection the organisation-unit pairs are compiled over."""
    parsed = json.loads((_SOURCE_DIRECTORY / "organisation-units.json").read_text(encoding="utf-8"))
    return [OrganisationUnitIn.model_validate(entry) for entry in parsed]


def _config() -> GenerateConfig:
    """The `[generate]` table the goldens were built under - every option left at its default."""
    return GenerateConfig()


def _emitted(resource: FhirBase) -> Any:
    """One built resource as the JSON document it is served as."""
    return json.loads(resource.model_dump_json(exclude_none=True, by_alias=True))


def _golden(stem: str) -> Any:
    """One resource SUSHI compiled from the FSH the same vocabulary renders."""
    return json.loads((_GOLDEN_DIRECTORY / f"{stem}.json").read_text(encoding="utf-8"))


def _built() -> dict[str, Any]:
    """Every terminology document the four builders publish, keyed by the golden's file stem."""
    config = _config()
    organisation_units = _organisation_units()
    builds: list[FoundationTerminologyBuild | OrganisationUnitTerminologyBuild] = [
        build_foundation_terminology_documents(config, _CANONICAL, ig_status="draft"),
        build_organisation_unit_level_terminology_documents(
            [organisation_unit.level for organisation_unit in organisation_units],
            config,
            _CANONICAL,
            ig_status="draft",
        ),
        build_organisation_unit_terminology_documents(organisation_units, config, _CANONICAL, ig_status="draft"),
    ]
    documents: dict[str, Any] = {}
    for build in builds:
        for code_system in build.code_systems:
            documents[f"CodeSystem-{code_system.id}"] = _emitted(code_system)
        for value_set in build.value_sets:
            documents[f"ValueSet-{value_set.id}"] = _emitted(value_set)
    return documents


@pytest.mark.parametrize(
    "stem",
    [
        "CodeSystem-d2-form-type-cs",
        "ValueSet-d2-form-type-vs",
        "CodeSystem-d2-period-type-cs",
        "ValueSet-d2-period-type-vs",
        "CodeSystem-d2-ou-level-cs",
        "ValueSet-d2-ou-level-vs",
        "CodeSystem-d2-ou-cs",
        "ValueSet-d2-ou-vs",
    ],
)
def test_a_built_terminology_document_equals_the_one_sushi_compiled(stem: str) -> None:
    """Every element SUSHI resolved from the FSH is on the built document, and nothing else is."""
    assert _built()[stem] == _golden(stem)


def test_the_builders_publish_exactly_the_documents_the_compiler_does() -> None:
    """No pair is silently dropped from - or added to - the document build."""
    assert sorted(_built()) == [
        "CodeSystem-d2-form-type-cs",
        "CodeSystem-d2-ou-cs",
        "CodeSystem-d2-ou-level-cs",
        "CodeSystem-d2-period-type-cs",
        "ValueSet-d2-form-type-vs",
        "ValueSet-d2-ou-level-vs",
        "ValueSet-d2-ou-vs",
        "ValueSet-d2-period-type-vs",
    ]


def test_the_whole_selection_pair_carries_the_hierarchy_level_as_an_integer() -> None:
    """The `level` property is the one `valueInteger` the generated terminology writes."""
    concepts = _built()["CodeSystem-d2-ou-cs"]["concept"]
    assert [concept["property"][0] for concept in concepts] == [
        {"code": "level", "valueInteger": 1},
        {"code": "level", "valueInteger": 2},
        {"code": "level", "valueInteger": 3},
        {"code": "level", "valueInteger": 4},
    ]
