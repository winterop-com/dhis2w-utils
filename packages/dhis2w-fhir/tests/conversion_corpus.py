"""The conversion test corpus: one whole generate run's example responses, translated back into DHIS2.

`tests/data/questionnaire-sources/` holds the projections one generate run of the local DHIS2 stack
fetched. This module rebuilds that run's synthetic example responses exactly as
`d2w fhir generate examples` does, assembles the translation context out of the artifacts the same
run publishes, and translates every response back.

Two suites read it. `test_fhir_conversion_roundtrip.py` asserts the payloads come back to the DHIS2
values the examples were built from, cell for cell. `test_fhir_conversion_contract.py` holds the
aggregate half of the same payloads against the published `D2DataValueSet` logical model.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from dhis2w_client.generated.v42.oas import DataValueSet
from dhis2w_fhir import (
    AttributeCodeIndex,
    AttributeComboPlan,
    GenerateConfig,
    OptionSetIn,
    QuestionnaireSourceIn,
    build_attribute_combo_artifacts,
    build_attribute_combo_concept_maps,
    build_example_documents,
    build_questionnaire_documents,
    build_synthetic_responses,
    option_set_identities,
)
from dhis2w_fhir.conversion import (
    ConversionContext,
    ConversionNaming,
    ConversionReport,
    build_conversion_context,
    translate_responses,
)
from dhis2w_fhir.r4 import CodeSystem, Identifier, Location, ValueSet
from dhis2w_fhir.resources.examples.schemas import ExampleResponseIn
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts, build_option_set_concept_maps
from dhis2w_fhir.resources.questionnaires import source_items

SOURCE_DIRECTORY = Path(__file__).parent / "data" / "questionnaire-sources"

#: The IG the fixtures were fetched for - `[ig] canonical` of its `fhir.toml`.
CANONICAL = "http://localhost:8080/fhir"

#: The instance's root organisation unit - the one every synthetic example is subject to.
ROOT_ORG_UNIT = "ImspTQPwCqd"

#: The day the synthetic values are anchored on, which decides the reporting period each data set gets.
REFERENCE_DATE = datetime.date(2026, 8, 8)

#: Every example the run builds, and which DHIS2 payload each one reports as.
AGGREGATE_IDS = ["BfMAe6Itzgt-example-1", "TuL8IOPzpHh-example-1"]
EVENT_IDS = ["EVTsupVis01-example-1", "lxAQ7Zs9VYR-example-1"]
TRACKER_EVENT_IDS = ["A03MvHHogjR-example-1", "PsAncVisit1-example-1", "ZzYYXq4fJie-example-1"]
EXAMPLE_IDS = sorted([*AGGREGATE_IDS, *EVENT_IDS, *TRACKER_EVENT_IDS])


def fixture(name: str) -> Any:
    """Read one committed source fixture."""
    return json.loads((SOURCE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


def sources() -> list[QuestionnaireSourceIn]:
    """The forms the run fetched, as the emitter projection."""
    return [QuestionnaireSourceIn.model_validate(entry) for entry in fixture("sources")]


def option_sets() -> list[OptionSetIn]:
    """The option sets the run's answers are coded from, options included."""
    return [OptionSetIn.model_validate(entry) for entry in fixture("example-option-sets")]


def plan_sets() -> list[OptionSetIn]:
    """The option-set selection the terminology target plans its identities over."""
    return [OptionSetIn.model_validate(entry) for entry in fixture("option-sets")]


def captured() -> list[ExampleResponseIn]:
    """The DHIS2-side captures the run invents - the values the round trip has to come back to."""
    return build_synthetic_responses(sources(), option_sets(), 1, ROOT_ORG_UNIT, REFERENCE_DATE).responses


def attribute_combos(config: GenerateConfig) -> AttributeComboPlan:
    """The attribute-option-combo plan the questionnaire target publishes for the run's data sets."""
    return build_attribute_combo_artifacts(sources(), config, CANONICAL, ig_status="draft").plan


def context(config: GenerateConfig) -> ConversionContext:
    """The translation context, assembled from the artifacts the same run publishes."""
    run_sources = sources()
    plan = option_set_identities(plan_sets(), config)
    questionnaires = build_questionnaire_documents(
        run_sources,
        config,
        CANONICAL,
        ig_status="draft",
        option_set_plan=plan,
        attribute_codes=AttributeCodeIndex(),
        attribute_combos=attribute_combos(config),
    ).questionnaires
    terminology = build_option_set_artifacts(
        option_sets(), config, CANONICAL, ig_status="draft", attribute_codes=AttributeCodeIndex()
    )
    combos = build_attribute_combo_artifacts(run_sources, config, CANONICAL, ig_status="draft")
    code_systems: list[CodeSystem] = []
    value_sets: list[ValueSet] = []
    for artifact in [*terminology.artifacts, *combos.artifacts]:
        name = artifact.relative_path.rsplit("/", 1)[-1]
        if name.startswith("CodeSystem-"):
            code_systems.append(CodeSystem.model_validate_json(artifact.content))
        elif name.startswith("ValueSet-"):
            value_sets.append(ValueSet.model_validate_json(artifact.content))
    naming = ConversionNaming.from_config(config, CANONICAL)
    return build_conversion_context(
        naming,
        questionnaires,
        code_systems=code_systems,
        value_sets=value_sets,
        concept_maps=[
            *build_option_set_concept_maps(option_sets(), config, CANONICAL, ig_status="draft"),
            *build_attribute_combo_concept_maps(run_sources, config, CANONICAL, ig_status="draft"),
        ],
        locations=[
            Location(
                id=ROOT_ORG_UNIT, identifier=[Identifier(system=naming.organisation_unit_system, value=ROOT_ORG_UNIT)]
            )
        ],
        value_types_by_data_element={
            item.uid: item.value_type for source in run_sources for item in source_items(source)
        },
        timezone=config.timezone,
    )


def report(config: GenerateConfig | None = None) -> ConversionReport:
    """Publish the run's example responses and translate every one of them back."""
    resolved = config if config is not None else GenerateConfig()
    documents = build_example_documents(
        sources(),
        captured(),
        option_sets(),
        resolved,
        CANONICAL,
        option_set_plan=option_set_identities(plan_sets(), resolved),
        attribute_combos=attribute_combos(resolved),
    )
    return translate_responses(documents.responses, context(resolved))


def aggregate_payloads(config: GenerateConfig | None = None) -> dict[str, DataValueSet]:
    """Every data value set the run's aggregate examples translate into, keyed by the response id."""
    return {
        str(result.response_id): result.data_value_set
        for result in report(config).results
        if result.data_value_set is not None
    }
